"""I2C, SPI, UART and 1-Wire on the Bus Pirate 6, over BPIO2.

Each class answers to the same calls as its namesake in buspirate.i2c,
buspirate.spi, buspirate.uart and buspirate.onewire — the calls the
dashboard's panels make — so a panel never needs to know which board it is
driving.

Firmware behaviour relied on (src/binmode/bpio_*.c, firmware built 2026-10-12):
* I2C: data_write[0] is the 8-bit address byte; a write followed by a read
  gets a repeated start; an error returns early and skips STOP, so every
  error here is followed by a stop-only request.
* SPI: start/stop drive CS.
* UART: whatever the target sends arrives as unsolicited async frames.
* 1-Wire: byte-level only — start is a reset, which fails with no device.
"""

from __future__ import annotations

from typing import Dict, Iterable, List

from ..device import I2C_SPEEDS_MODERN, SPI_SPEEDS
from ..devices.ds18x20 import crc8
from ..exceptions import BusPirateError, ModeError, NackError, ProtocolError, UnsupportedFeatureError
from ..i2c import SCAN_RANGE
from ..uart import UART
from . import protocol
from .protocol import ModeConfig


class _Bp6Mode:
    title = ""
    #: The mode's name in BPIO2.
    name = ""

    def __init__(self, bp) -> None:
        self.bp = bp
        self._active = True
        self.config = self.default_config()
        self.peripherals: Dict[str, bool] = {
            "power": bool(bp.last_status and bp.last_status.psu_enabled),
            "pullups": bool(bp.last_status and bp.last_status.pullups),
            "aux": False, "cs": False,
        }
        self._apply()

    def default_config(self) -> ModeConfig:
        return ModeConfig()

    def _apply(self) -> None:
        self.bp.configure(mode=self.name, mode_config=self.config)

    # -- lifecycle ---------------------------------------------------------

    def close(self) -> None:
        """Nothing to send: the next mode replaces this one."""
        if not self._active:
            return
        self._active = False
        self.bp._mode_closed(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    @property
    def is_active(self) -> bool:
        return self._active

    def _check_active(self) -> None:
        if not self._active:
            raise ModeError(f"{type(self).__name__} has been closed")

    # -- shared ------------------------------------------------------------

    def configure_peripherals(self, power: bool = False, pullups: bool = False,
                              aux: bool = False, cs: bool = False) -> None:
        """Switch the supply and pull-ups **on** if asked; never off.

        On a Bus Pirate 6 the Power & pull-ups panel owns the supply: its
        voltage and limit are set there, and so is switching it off. A bus
        panel's unticked box leaves the supply as it is, so running a scan
        never cuts the power to a target someone just switched on.
        """
        self._check_active()
        if aux or cs:
            raise UnsupportedFeatureError(
                "the Bus Pirate 6 has no AUX or CS peripheral pins to drive. It is "
                "a Bus Pirate v3 and v4 feature."
            )
        fields = {}
        if pullups:
            fields.update(pullup_enable=True)
        if power:
            fields.update(psu_enable=True, psu_mv=self.bp.psu_mv, psu_ma=self.bp.psu_ma or 300)
        if fields:
            self.bp.configure(**fields)
        status = self.bp.status()
        self.peripherals = dict(self.peripherals, power=status.psu_enabled, pullups=status.pullups)

    def _data(self, **fields) -> protocol.Response:
        self._check_active()
        return self.bp.link.request(protocol.data_request(**fields))

    def _release(self) -> None:
        """A stop-only request: STOP on I2C, CS high on SPI.

        Sent after any failure, so the bus is not left mid-transaction. If it
        fails too, the original error is the one worth reporting.
        """
        try:
            self._data(stop=True)
        except (BusPirateError, OSError):
            pass

    def _limit(self, which: str) -> int:
        status = self.bp.last_status
        value = getattr(status, which, 0) if status is not None else 0
        return value or 512


class Bp6I2C(_Bp6Mode):
    title = "I2C"
    name = "I2C"
    #: BPIO2 reports one ACK/NACK for the whole transaction, not per byte.
    reports_byte_acks = False

    def default_config(self) -> ModeConfig:
        return ModeConfig(speed=100_000, clock_stretch=True)

    def set_speed(self, speed: int) -> None:
        if speed not in I2C_SPEEDS_MODERN:
            raise ValueError(f"speed must be one of {sorted(I2C_SPEEDS_MODERN)}")
        self.config = ModeConfig(speed=I2C_SPEEDS_MODERN[speed], clock_stretch=True)
        self._apply()

    def write_then_read(self, write_data: bytes = b"", read_count: int = 0) -> bytes:
        """START, ``write_data`` (address byte first), [RESTART, read], STOP."""
        write_data = bytes(write_data)
        if not write_data:
            raise ValueError("the first byte written is the address byte")
        try:
            response = self._data(start=True, write=write_data, read=read_count, stop=True)
        except ProtocolError:
            self._release()
            raise
        if response.error:
            self._release()  # the firmware skipped STOP on its way out
            raise NackError(
                f"0x{write_data[0] >> 1:02X} did not answer. Check the address, the "
                "wiring and that the bus has pull-ups."
            )
        if len(response.data) != read_count:
            raise ProtocolError(f"asked for {read_count} bytes, got {len(response.data)}")
        return response.data

    def scan(self, addresses: Iterable[int] = SCAN_RANGE) -> List[int]:
        found = []
        for address in addresses:
            try:
                self.write_then_read(bytes([address << 1]), 0)
            except NackError:
                continue
            found.append(address)
        return found

    def write(self, address: int, data: bytes = b"") -> None:
        self.write_then_read(bytes([_address(address) << 1]) + bytes(data), 0)

    def read(self, address: int, count: int) -> bytes:
        return self._chunked(address, b"", count)

    def read_after_write(self, address: int, pointer: bytes, count: int) -> bytes:
        return self._chunked(address, bytes(pointer), count)

    def read_register(self, address: int, register: int, count: int = 1) -> bytes:
        return self.read_after_write(address, bytes([register & 0xFF]), count)

    def write_register(self, address: int, register: int, data: bytes) -> None:
        self.write(address, bytes([register & 0xFF]) + bytes(data))

    def _chunked(self, address: int, pointer: bytes, count: int) -> bytes:
        if count < 1:
            raise ValueError("count must be >= 1")
        limit = self._limit("max_read")
        width = len(pointer)
        base = int.from_bytes(pointer, "big") if width else 0
        mask = (1 << (8 * width)) - 1
        out = bytearray()
        for offset in range(0, count, limit):
            size = min(limit, count - offset)
            where = ((base + offset) & mask).to_bytes(width, "big") if width else b""
            out += self.write_then_read(bytes([_address(address) << 1]) + where, size)
        return bytes(out)


class Bp6SPI(_Bp6Mode):
    title = "SPI"
    name = "SPI"

    def default_config(self) -> ModeConfig:
        return ModeConfig(speed=1_000_000)

    def set_speed(self, speed: int) -> None:
        if speed not in SPI_SPEEDS:
            raise ValueError(f"speed must be one of {sorted(SPI_SPEEDS)}")
        self.config = ModeConfig(speed=SPI_SPEEDS[speed], clock_polarity=self.config.clock_polarity,
                                 clock_phase=self.config.clock_phase)
        self._apply()

    def set_mode(self, mode: int, push_pull: bool = True) -> None:
        if mode not in (0, 1, 2, 3):
            raise ValueError("SPI mode must be 0, 1, 2 or 3")
        self.config = ModeConfig(speed=self.config.speed, clock_polarity=bool(mode & 0b10),
                                 clock_phase=bool(mode & 0b01))
        self._apply()

    def configure(self, push_pull: bool = True, clock_idle_high: bool = False,
                  clock_edge_active_to_idle: bool = True, sample_at_end: bool = False) -> None:
        mode = (0b10 if clock_idle_high else 0) | (0 if clock_edge_active_to_idle else 0b01)
        self.set_mode(mode, push_pull)

    def cs_low(self) -> None:
        self._data(start=True)

    def cs_high(self) -> None:
        self._data(stop=True)

    def write_then_read(self, data: bytes = b"", read_count: int = 0, assert_cs: bool = True) -> bytes:
        """Write ``data``, then clock in ``read_count``; CS low throughout.

        Anything over the board's 512-byte limits goes in several requests,
        with CS raised only after the last.
        """
        data = bytes(data)
        if not data and not read_count:
            return b""
        limit_w, limit_r = self._limit("max_write"), self._limit("max_read")
        steps = [("w", data[i:i + limit_w]) for i in range(0, len(data), limit_w)]
        steps += [("r", min(limit_r, read_count - i)) for i in range(0, read_count, limit_r)]
        out = bytearray()
        for index, (kind, value) in enumerate(steps):
            first, last = index == 0, index == len(steps) - 1
            fields = dict(start=assert_cs and first, stop=assert_cs and last)
            if kind == "w":
                fields["write"] = value
            else:
                fields["read"] = value
            try:
                response = self._data(**fields)
            except ProtocolError:
                if assert_cs:
                    self._release()  # CS high, or the chip hears the next command as more of this one
                raise
            if response.error:
                if assert_cs:
                    self._release()
                raise ModeError(f"the Bus Pirate 6 said: {response.error}")
            out += response.data
        if len(out) != read_count:
            raise ProtocolError(f"asked for {read_count} SPI bytes, got {len(out)}")
        return bytes(out)


class _AsyncUartStream:
    """``self.serial`` for the UART monitor: reads give the target's bytes."""

    def __init__(self, link) -> None:
        self.link = link

    def read(self, count: int) -> bytes:
        data = self.link.poll_async(0.02)
        if len(data) > count:
            self.link.async_rx[:0] = data[count:]
            data = data[:count]
        return data

    def write(self, data: bytes) -> int:
        raise ModeError("the UART monitor only listens; use Send in the UART panel")

    def flush(self) -> None:
        pass

    def close(self) -> None:
        pass


class Bp6UART(_Bp6Mode):
    title = "UART"
    name = "UART"
    #: The firmware forwards what the target sends at all times in UART mode.
    listening = True
    #: databits_parity index → (data bits, even parity). Odd parity and 9 bits
    #: have no field in BPIO2's ModeConfiguration.
    FRAMING = {0: (8, False), 1: (8, True)}

    def default_config(self) -> ModeConfig:
        return ModeConfig(speed=115200)

    def set_baudrate(self, baud: int) -> None:
        if baud not in UART._BAUDS:
            raise ValueError("baud must be one of UART.BAUD_300..BAUD_115200")
        self.config = ModeConfig(speed=UART._BAUDS[baud], data_bits=self.config.data_bits,
                                 parity=self.config.parity, stop_bits=self.config.stop_bits,
                                 signal_inversion=self.config.signal_inversion)
        self._apply()

    def configure(self, push_pull: bool = True, databits_parity: int = 0, stop_bits: int = 1,
                  rx_idle_low: bool = False) -> None:
        if databits_parity not in self.FRAMING:
            raise UnsupportedFeatureError(
                "the Bus Pirate 6's binary interface offers 8 data bits with no or "
                "even parity. Odd parity and 9-bit framing are in its own terminal "
                "(the Terminal panel), or on a Bus Pirate v3 or v4."
            )
        bits, parity = self.FRAMING[databits_parity]
        self.config = ModeConfig(speed=self.config.speed, data_bits=bits, parity=parity,
                                 stop_bits=stop_bits, signal_inversion=rx_idle_low)
        self._apply()

    def write(self, data: bytes) -> None:
        data = bytes(data)
        limit = self._limit("max_write")
        for start in range(0, len(data), limit):
            response = self._data(write=data[start:start + limit])
            if response.error:
                raise ModeError(f"the Bus Pirate 6 said: {response.error}")

    def read_available(self, max_bytes: int = 256) -> bytes:
        data = self.bp.link.poll_async(0.05)
        if len(data) > max_bytes:
            self.bp.link.async_rx[:0] = data[max_bytes:]
            data = data[:max_bytes]
        return data

    def start_receive(self) -> None:
        """Hand ``bp.serial`` to the monitor stream; stop_stream gives it back."""
        self._check_active()
        self.bp.lend_serial(_AsyncUartStream(self.bp.link))

    def stop_receive(self) -> None:
        self.bp.stop_stream()


class Bp6OneWire(_Bp6Mode):
    title = "1-Wire"
    name = "1WIRE"

    def _transfer(self, **fields) -> bytes:
        response = self._data(**fields)
        if response.error:
            raise NackError(
                "no 1-Wire device answered the reset. Check the data line (IO0), "
                "ground, and a pull-up (switch the pull-ups on)."
            )
        return response.data

    def reset(self) -> None:
        self._transfer(start=True)

    def write(self, data: bytes) -> None:
        self._transfer(write=bytes(data))

    def read(self, count: int) -> bytes:
        return self._transfer(read=count)

    def read_byte(self) -> int:
        return self.read(1)[0]

    def read_rom(self) -> bytes:
        """READ ROM (0x33): only valid with exactly one device on the bus."""
        return self._transfer(start=True, write=b"\x33", read=8)

    def search_rom(self, alarm: bool = False) -> List[bytes]:
        """BPIO2 cannot do the bit-level search, so this is READ ROM.

        With one device that is the same answer. With several, their ROMs
        collide, the CRC fails, and the error says what to do instead.
        """
        if alarm:
            raise UnsupportedFeatureError(
                "the Bus Pirate 6's binary interface cannot run an alarm search; "
                "type 'scan' in the Terminal panel's 1-Wire mode instead."
            )
        rom = self.read_rom()
        if len(rom) != 8 or crc8(rom[:7]) != rom[7]:
            raise ProtocolError(
                "the ROM read back fails its CRC — usually more than one device is "
                "on the bus. The Bus Pirate 6's binary interface can only list one; "
                "type 'scan' in the Terminal panel's 1-Wire mode to list them all."
            )
        return [rom]


def _address(address: int) -> int:
    if not 0 <= address <= 0x7F:
        raise ValueError(f"0x{address:X} is not a 7-bit I2C address")
    return address
