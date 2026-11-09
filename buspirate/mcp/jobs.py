"""The work behind each bus tool: I2C, SPI, UART, 1-Wire and the v3/v4 pins.

Each function takes the :class:`~buspirate.mcp.session.BoardSession` and does
its board I/O through ``session.run``, so an unplug becomes ``BoardGone``.
Settings that differ per board (speed indices, the Bit Pirate's SPI clock)
are chosen here; the Bit Pirate's driver re-pins its dock by itself.

A bus tool never powers the target on its own: every mode is opened with
``configure_peripherals(**session.peripherals())``, which asks for power only
once ``power_apply`` has recorded an approved plan. Every result says whether
the target is powered, and when it is not, says so in a ``note``.

Results are in real units, through :mod:`buspirate.devices`; hex appears only
next to a meaning. No ``mcp`` import: this module stays Python 3.8-clean.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

from .. import devices
from ..capabilities import CAP_ADC, CAP_FREQUENCY, CAP_PWM, CAP_SPI_MODES
from ..exceptions import BusPirateError
from ..spiflash import SPIFlash
from ..uart import UART

NO_POWER_NOTE = ("target not powered by the Bus Pirate — it needs its own supply, "
                 "or approve power first")
NOT_BLANK_WARNING = "MISO not connected or WP/HOLD not tied high — the chip is not blank"

I2C_FIRST, I2C_LAST = 0x08, 0x77
_BAUDS = {hz: index for index, hz in UART._BAUDS.items()}


# -- shared -------------------------------------------------------------------

def _with_power(session, out: Dict[str, Any]) -> Dict[str, Any]:
    powered = session.peripherals()["power"]
    out["power"] = powered
    if not powered:
        out["note"] = NO_POWER_NOTE
    return out


def _open(bp, mode: str, session):
    """Enter ``mode`` and reassert exactly the approved power and pull-ups."""
    m = getattr(bp, mode)()
    try:
        m.configure_peripherals(**session.peripherals())
    except BaseException:
        m.close()
        raise
    return m


def _pick(table: Dict[int, int], hz: int) -> int:
    """The index of the fastest speed not above ``hz``; the slowest if all are."""
    fitting = [index for index, rate in table.items() if rate <= hz]
    if fitting:
        return max(fitting, key=lambda index: table[index])
    return min(table, key=lambda index: table[index])


def _spi_speeds(bp) -> Dict[int, int]:
    table = bp.profile.spi_speeds
    if bp.profile.variant == "bitpirate":
        # Whole MHz only (buspirate.bitpirate.modes.CliSPI.set_speed).
        table = {i: hz for i, hz in table.items() if hz >= 1_000_000 and hz % 1_000_000 == 0}
    return table


def _reading(reading) -> Optional[Dict[str, Any]]:
    if reading is None:
        return None
    return {"device": reading.device, "raw_hex": reading.raw.hex(" "),
            "values": dict(reading.meaning)}


def _try_reading(read) -> Optional[Dict[str, Any]]:
    """A scan's reading of one device; a chip that fails to measure does not
    sink the whole scan. An unplug (OSError) still propagates."""
    try:
        return _reading(read())
    except BusPirateError as exc:
        return {"error": str(exc)}


def check_address(address: int) -> int:
    """A 7-bit I2C address in 0x08–0x77, or ValueError saying what to use."""
    if I2C_LAST < address <= 0xFF:
        raise ValueError("that looks like an 8-bit address — use 0x%02X" % (address >> 1))
    if not I2C_FIRST <= address <= I2C_LAST:
        raise ValueError("an I2C address must be 7-bit, 0x08 to 0x77, not 0x%02X" % address)
    return address


def _hex_bytes(text: str) -> bytes:
    cleaned = text.replace("0x", "").replace(",", " ")
    try:
        return bytes.fromhex(cleaned)
    except ValueError:
        raise ValueError("write_hex must be hex bytes such as '9f' or '03 00 00 00', "
                         "not %r" % (text,)) from None


def _baud_index(baud: int) -> int:
    if baud not in _BAUDS:
        raise ValueError("baud must be one of %s" % ", ".join(str(b) for b in sorted(_BAUDS)))
    return _BAUDS[baud]


def _printable(data: bytes) -> str:
    return data.decode("utf-8", "replace")


# -- I2C --------------------------------------------------------------------------

def i2c_scan(session, speed_khz: int = 100) -> Dict[str, Any]:
    def work(bp) -> Dict[str, Any]:
        table = bp.profile.i2c_speeds
        speed = _pick(table, speed_khz * 1000)
        with _open(bp, "i2c", session) as m:
            m.set_speed(speed)
            found = []
            for address in m.scan():
                found.append({
                    "address": "0x%02X" % address,
                    "address_8bit": "0x%02X/0x%02X" % (address << 1, (address << 1) | 1),
                    "label": devices.i2c_label(address),
                    "reading": _try_reading(lambda: devices.read_i2c(m, address)),
                })
        return {"devices": found, "speed_khz": table[speed] // 1000}
    return _with_power(session, session.run(work))


def i2c_read(session, address: int, register: int, count: int = 1) -> Dict[str, Any]:
    check_address(address)
    if not 0 <= register <= 0xFF:
        raise ValueError("register must be 0x00 to 0xFF")
    if count < 1:
        raise ValueError("count must be at least 1")

    def work(bp) -> Dict[str, Any]:
        with _open(bp, "i2c", session) as m:
            data = m.read_register(address, register, count)
            meaning = devices.explain_i2c_register(m, address, register, data)
        return {"hex": data.hex(" "), "meaning": dict(meaning)}
    return _with_power(session, session.run(work))


def i2c_sensor(session, address: int) -> Dict[str, Any]:
    check_address(address)

    def work(bp) -> Dict[str, Any]:
        with _open(bp, "i2c", session) as m:
            reading = devices.read_i2c(m, address)
        if reading is None:
            return {"error": "no decoder for 0x%02X" % address}
        return _reading(reading)
    return _with_power(session, session.run(work))


# -- SPI --------------------------------------------------------------------------

def _spi(bp, session, mode: int, speed_khz: int):
    if mode != 0:
        bp.profile.require(CAP_SPI_MODES)
    m = _open(bp, "spi", session)
    try:
        m.set_speed(_pick(_spi_speeds(bp), speed_khz * 1000))
        m.set_mode(mode)
    except BaseException:
        m.close()
        raise
    return m


def spi_identify(session, mode: int = 0, speed_khz: int = 1000) -> Dict[str, Any]:
    def work(bp) -> Dict[str, Any]:
        with _spi(bp, session, mode, speed_khz) as m:
            flash = SPIFlash(m)
            jedec = flash.jedec_id()
        blank = jedec in (b"\x00\x00\x00", b"\xff\xff\xff")
        maker = devices.JEDEC_MANUFACTURERS.get(jedec[0], "unlisted maker 0x%02X" % jedec[0])
        code = jedec[2]
        return {
            "jedec": jedec.hex(" "),
            "manufacturer_device": None if blank else
            "%s, memory type 0x%02X" % (maker, jedec[1]),
            "capacity_bytes": None if blank or not 0x10 <= code <= 0x2A else 1 << code,
            "warning": NOT_BLANK_WARNING if blank else None,
        }
    return _with_power(session, session.run(work))


def spi_transfer(session, write_hex: str, read_count: int, mode: int = 0,
                 speed_khz: int = 1000) -> Dict[str, Any]:
    data = _hex_bytes(write_hex)
    if read_count < 0:
        raise ValueError("read_count must not be negative")

    def work(bp) -> Dict[str, Any]:
        with _spi(bp, session, mode, speed_khz) as m:
            reply = m.write_then_read(data, read_count)
        return {"read_hex": reply.hex(" ")}
    return _with_power(session, session.run(work))


def spi_sensor_read(session, name: str) -> Dict[str, Any]:
    try:
        device = devices.spi_sensor(name)
    except KeyError:
        return _with_power(session, {
            "error": "no SPI sensor called %r" % (name,),
            "sensors": [d.name for d in devices.spi_sensors()],
        })

    def work(bp) -> Dict[str, Any]:
        with _spi(bp, session, 0, 1000) as m:
            return _reading(device.measure(m))
    return _with_power(session, session.run(work))


# -- UART -------------------------------------------------------------------------

def _uart(bp, session, baud: int):
    m = _open(bp, "uart", session)
    try:
        m.set_baudrate(_baud_index(baud))
        m.configure()  # 8N1, driven; until then a v3/v4 sits at 300 baud, not driving
    except BaseException:
        m.close()
        raise
    return m


def uart_send(session, text: str, baud: int = 115200) -> Dict[str, Any]:
    _baud_index(baud)
    payload = text.encode("utf-8")

    def work(bp) -> Dict[str, Any]:
        with _uart(bp, session, baud) as m:
            m.write(payload)
        return {"sent": text, "bytes": len(payload), "baud": baud}
    return _with_power(session, session.run(work))


def _listen(bp, m, seconds: float) -> bytes:
    deadline = time.monotonic() + seconds
    if hasattr(m, "read_available"):  # v3/v4 echo, BP6 async data
        started = getattr(m, "listening", True) is False
        if started:
            m.start_receive()
        got = bytearray()
        try:
            while time.monotonic() < deadline:
                got += m.read_available(4096)
                time.sleep(0.02)
            got += m.read_available(4096)
        finally:
            if started:
                m.stop_receive()  # so leaving the mode is not mistaken for data
        return bytes(got)
    # The Bit Pirate streams with `read` until Enter.
    m.start_receive()
    got = bytearray()
    try:
        while time.monotonic() < deadline:
            chunk = bp.serial.read(256)
            if chunk:
                got += chunk
            else:
                time.sleep(0.02)
    finally:
        bp.stop_stream()
    return bytes(got)


def uart_listen(session, seconds: float = 2.0, baud: int = 115200) -> Dict[str, Any]:
    _baud_index(baud)
    if not 0 < seconds <= 30:
        raise ValueError("seconds must be more than 0 and at most 30")

    def work(bp) -> Dict[str, Any]:
        with _uart(bp, session, baud) as m:
            data = _listen(bp, m, seconds)
        return {"text": _printable(data), "hex": data.hex(" "), "bytes": len(data),
                "seconds": seconds, "baud": baud}
    return _with_power(session, session.run(work))


# -- 1-Wire -----------------------------------------------------------------------

def onewire_scan(session) -> Dict[str, Any]:
    def work(bp) -> Dict[str, Any]:
        found = []
        with _open(bp, "onewire", session) as m:
            for rom in m.search_rom():
                found.append({
                    "rom": rom.hex(" "),
                    "label": devices.onewire_label(rom[0]),
                    "reading": _try_reading(lambda: devices.read_onewire(m, rom)),
                })
        return {"devices": found}
    return _with_power(session, session.run(work))


# -- v3/v4 pins (bitbang mode) ----------------------------------------------------

def _pins(bp, session, capability: str) -> None:
    """Require ``capability`` and reassert the approved supply and pull-ups.

    Leaving a mode returns a v3/v4 to bitbang with its supplies off, so the
    approved state is driven again here, and nothing more.
    """
    bp.profile.require(capability)
    bp.set_pins(**session.peripherals())


def pins_read_voltage(session) -> Dict[str, Any]:
    def work(bp) -> Dict[str, Any]:
        _pins(bp, session, CAP_ADC)
        return {"ADC_mv": int(round(bp.read_voltage() * 1000))}
    return _with_power(session, session.run(work))


def pwm(session, frequency_hz: float, duty: float) -> Dict[str, Any]:
    if not 0.0 <= duty <= 1.0:
        raise ValueError("duty is a fraction from 0.0 to 1.0, e.g. 0.25 for 25 %")
    if frequency_hz <= 0:
        raise ValueError("frequency_hz must be positive")

    def work(bp) -> Dict[str, Any]:
        _pins(bp, session, CAP_PWM)
        bp.pwm(frequency_hz, duty)
        return {"frequency_hz": frequency_hz, "duty": duty}
    return _with_power(session, session.run(work))


def pwm_off(session) -> Dict[str, Any]:
    def work(bp) -> Dict[str, Any]:
        bp.profile.require(CAP_PWM)
        bp.pwm_clear()
        return {"pwm": False}
    return _with_power(session, session.run(work))


def frequency(session) -> Dict[str, Any]:
    def work(bp) -> Dict[str, Any]:
        _pins(bp, session, CAP_FREQUENCY)
        return {"hz": bp.measure_frequency()}
    return _with_power(session, session.run(work))
