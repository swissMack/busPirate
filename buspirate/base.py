"""Transport and raw bitbang (BBIO) layer for the Bus Pirate."""

from __future__ import annotations

import logging
import time
from typing import Callable, List, Optional

from . import device as device_module
from .device import UNKNOWN_PROFILE, DeviceProfile, parse_banner
from .exceptions import ConnectionError, ModeError, ProtocolError
from .protocol import BANNER_BITBANG, banner_length, match_banner

log = logging.getLogger(__name__)

# Raw bitbang (BBIO) commands.
CMD_RESET_BBIO = 0x00
CMD_MODE_SPI = 0x01
CMD_MODE_I2C = 0x02
CMD_MODE_UART = 0x03
CMD_MODE_1WIRE = 0x04
CMD_MODE_RAWWIRE = 0x05
CMD_MODE_JTAG = 0x06
CMD_RESET_HARDWARE = 0x0F
CMD_SELF_TEST_SHORT = 0x10
CMD_SELF_TEST_FULL = 0x11
CMD_PWM_SETUP = 0x12
CMD_PWM_CLEAR = 0x13
CMD_VOLTAGE_ONCE = 0x14
CMD_VOLTAGE_CONTINUOUS = 0x15
CMD_FREQUENCY = 0x16

# Pin control, bitbang mode only.
PIN_DIRECTION_BASE = 0x40  # 0b010xxxxx
PIN_STATE_BASE = 0x80  # 0b1xxxxxxx

ACK = 0x01

# The ADC sits behind a divide-by-two in front of a 3.3V, 10-bit converter.
ADC_FULL_SCALE_VOLTS = 6.6
ADC_COUNTS = 1024.0

# PIC24F timer feeding the PWM output compare on AUX.
PWM_FCY = 16_000_000
PWM_PRESCALERS = {0: 1, 1: 8, 2: 64, 3: 256}

TrafficHook = Callable[[str, bytes], None]


class BusPirate:
    """Owns the serial port, the device profile and the raw bitbang protocol.

    The Bus Pirate boots into a human-readable terminal. :meth:`open`
    identifies the hardware from that terminal, then switches to binary mode,
    from which each protocol mode is entered with :meth:`i2c`, :meth:`spi`,
    :meth:`uart`, :meth:`onewire` or :meth:`rawwire`.
    """

    def __init__(
        self,
        port: str,
        baudrate: int = 115200,
        timeout: float = 0.2,
        serial_factory=None,
        on_traffic: Optional[TrafficHook] = None,
        identify_timeout: float = 0.4,
    ) -> None:
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.identify_timeout = identify_timeout
        self._serial_factory = serial_factory
        self.serial = None
        self.profile: DeviceProfile = UNKNOWN_PROFILE
        self.bitbang_version: Optional[int] = None
        self._mode = None
        self._traffic_hooks: List[TrafficHook] = []
        if on_traffic is not None:
            self._traffic_hooks.append(on_traffic)

    # -- transport ---------------------------------------------------------

    def open(self, identify: bool = True) -> "BusPirate":
        """Open the port, identify the device, and enter binary bitbang mode."""
        if self.serial is None:
            self.serial = self._make_serial()
        if identify:
            self.identify()
        self.enter_binary_mode()
        return self

    def _make_serial(self):
        if self._serial_factory is not None:
            return self._serial_factory(self.port, self.baudrate, self.timeout)
        try:
            import serial  # imported lazily so tests need no hardware deps
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise ConnectionError(
                "pyserial is required: pip install pyserial"
            ) from exc
        try:
            return serial.Serial(
                self.port, baudrate=self.baudrate, timeout=self.timeout
            )
        except Exception as exc:  # serial.SerialException and friends
            raise ConnectionError(
                f"cannot open {self.port}: {exc}. If the port exists, something "
                "else is probably holding it — check for a screen session."
            ) from exc

    def close(self) -> None:
        """Return the Bus Pirate to its terminal mode and close the port."""
        if self.serial is None:
            return
        try:
            if self._mode is not None:
                self._mode.close()
            self.reset_hardware()
        except (ProtocolError, ModeError, OSError):
            log.debug("reset on close failed; closing anyway", exc_info=True)
        finally:
            self.serial.close()
            self.serial = None

    def __enter__(self) -> "BusPirate":
        return self.open()

    def __exit__(self, *exc_info) -> None:
        self.close()

    @property
    def is_open(self) -> bool:
        return self.serial is not None

    # -- traffic observers -------------------------------------------------

    def add_traffic_hook(self, hook: TrafficHook) -> None:
        """Observe every byte in both directions.

        The dashboard's live log uses this. ``hook(direction, data)`` is called
        with ``"tx"`` or ``"rx"``; exceptions in a hook are swallowed so a
        broken observer can never break a bus transaction.
        """
        self._traffic_hooks.append(hook)

    def remove_traffic_hook(self, hook: TrafficHook) -> None:
        if hook in self._traffic_hooks:
            self._traffic_hooks.remove(hook)

    def _notify(self, direction: str, data: bytes) -> None:
        for hook in self._traffic_hooks:
            try:
                hook(direction, data)
            except Exception:  # noqa: BLE001 - observers must not break the bus
                log.debug("traffic hook raised", exc_info=True)

    # -- primitives --------------------------------------------------------

    def write(self, data: bytes) -> None:
        if self.serial is None:
            raise ConnectionError("port is not open")
        log.debug("-> %s", data.hex(" "))
        self.serial.write(data)
        flush = getattr(self.serial, "flush", None)
        if flush is not None:
            flush()
        self._notify("tx", data)

    def read(self, count: int) -> bytes:
        """Read exactly ``count`` bytes or raise :class:`ProtocolError`."""
        if self.serial is None:
            raise ConnectionError("port is not open")
        data = self.serial.read(count)
        log.debug("<- %s", data.hex(" "))
        if data:
            self._notify("rx", data)
        if len(data) != count:
            raise ProtocolError(
                f"expected {count} byte(s), got {len(data)}: {data!r}"
            )
        return data

    def read_text(self, settle: float = 0.4, limit: int = 4096) -> str:
        """Drain whatever text the terminal is emitting, until it goes quiet."""
        if self.serial is None:
            raise ConnectionError("port is not open")
        collected = bytearray()
        deadline = time.monotonic() + settle
        while time.monotonic() < deadline and len(collected) < limit:
            chunk = self.serial.read(256)
            if chunk:
                collected += chunk
                deadline = time.monotonic() + settle
            else:
                # A real port blocks for its timeout; a fake returns at once.
                time.sleep(0.005)
        if collected:
            self._notify("rx", bytes(collected))
        return collected.decode("ascii", errors="replace")

    def flush_input(self) -> None:
        if self.serial is None:
            return
        reset = getattr(self.serial, "reset_input_buffer", None)
        if reset is not None:
            reset()
        else:  # minimal fakes and older pyserial
            while self.serial.read(256):
                pass

    def command(self, byte: int, response_len: int = 1) -> bytes:
        """Send one command byte and read a fixed-length response."""
        self.write(bytes([byte]))
        return self.read(response_len) if response_len else b""

    def command_expect_ack(self, byte: int) -> None:
        """Send one command byte and require the single-byte 0x01 success."""
        response = self.command(byte, 1)
        if response[0] != ACK:
            raise ProtocolError(
                f"command 0x{byte:02X} returned 0x{response[0]:02X}, want 0x01"
            )

    # -- identification ----------------------------------------------------

    def identify(self) -> DeviceProfile:
        """Read the firmware's ``i`` banner and work out what this device is.

        Runs in the *terminal*, before binary mode. It is deliberately
        forgiving: a device that will not identify itself still works, it just
        gets the conservative feature set.
        """
        self.flush_input()
        self.write(b"\n")
        self.read_text(settle=self.identify_timeout / 2)
        self.write(b"i\n")
        banner = self.read_text(settle=self.identify_timeout)
        self.profile = parse_banner(banner) if banner.strip() else UNKNOWN_PROFILE
        log.debug("identified %s", self.profile.describe())
        return self.profile

    # -- mode control ------------------------------------------------------

    def enter_binary_mode(self, retries: int = 25) -> None:
        """Knock on the port with 0x00 until the Bus Pirate answers ``BBIOx``.

        The device answers only once it has seen enough nulls to leave the
        terminal, so this is a loop by design rather than a single write.
        """
        self.flush_input()
        expected = banner_length(BANNER_BITBANG)
        for attempt in range(retries):
            self.write(b"\x00")
            response = self.serial.read(expected)
            if response:
                self._notify("rx", response)
            if response.startswith(BANNER_BITBANG.encode()):
                self.bitbang_version = match_banner(
                    response, BANNER_BITBANG, "entering bitbang mode"
                )
                log.debug("binary mode entered after %d write(s)", attempt + 1)
                self._mode = None
                return
            if response:
                # Terminal banner or echo still draining; keep knocking.
                self.flush_input()
            time.sleep(0.01)
        raise ModeError(
            f"no BBIO response after {retries} attempts on {self.port}. "
            "Check that the port is right, that the Bus Pirate is at "
            "115200 8N1, and that nothing else holds the port open."
        )

    def reset_hardware(self) -> None:
        """Reset the Bus Pirate back to its human-readable terminal."""
        self.write(bytes([CMD_RESET_HARDWARE]))
        self._mode = None
        self.flush_input()

    @property
    def mode(self):
        """The protocol mode currently entered, or ``None`` for bitbang."""
        return self._mode

    def _enter_mode(self, mode_cls):
        if self._mode is not None:
            raise ModeError(
                f"already in {type(self._mode).__name__}; close it first"
            )
        mode = mode_cls(self)
        try:
            mode.enter()
        except ModeError:
            # The device may well have changed mode even though we could not
            # read its banner. Knock it back into bitbang so the next call has
            # a known starting point.
            try:
                self.enter_binary_mode()
            except ModeError:
                log.debug("resync after a failed mode entry also failed")
            raise
        self._mode = mode
        return mode

    def _mode_closed(self, mode) -> None:
        if self._mode is mode:
            self._mode = None

    def i2c(self):
        """Enter I2C mode and return an :class:`~buspirate.i2c.I2C`."""
        from .i2c import I2C

        return self._enter_mode(I2C)

    def spi(self):
        """Enter SPI mode and return a :class:`~buspirate.spi.SPI`."""
        from .spi import SPI

        return self._enter_mode(SPI)

    def uart(self):
        """Enter UART mode and return a :class:`~buspirate.uart.UART`."""
        from .uart import UART

        return self._enter_mode(UART)

    def onewire(self):
        """Enter 1-Wire mode and return a :class:`~buspirate.onewire.OneWire`."""
        from .onewire import OneWire

        return self._enter_mode(OneWire)

    def rawwire(self):
        """Enter raw-wire mode and return a :class:`~buspirate.rawwire.RawWire`."""
        from .rawwire import RawWire

        return self._enter_mode(RawWire)

    # -- raw bitbang pin control ------------------------------------------

    def set_pin_directions(
        self,
        aux: bool = True,
        mosi: bool = True,
        clk: bool = True,
        miso: bool = True,
        cs: bool = True,
    ) -> int:
        """Set pins to input (``True``) or output (``False``).

        Bitbang mode only. Returns the byte of read-back pin states.
        """
        value = PIN_DIRECTION_BASE
        for flag, bit in (
            (aux, 0x10),
            (mosi, 0x08),
            (clk, 0x04),
            (miso, 0x02),
            (cs, 0x01),
        ):
            if flag:
                value |= bit
        return self.command(value, 1)[0]

    def set_pins(
        self,
        power: bool = False,
        pullups: bool = False,
        aux: bool = False,
        mosi: bool = False,
        clk: bool = False,
        miso: bool = False,
        cs: bool = False,
    ) -> int:
        """Drive the output pins high (``True``) or low (``False``).

        Bitbang mode only. Returns the byte of read-back pin states.
        """
        value = PIN_STATE_BASE
        for flag, bit in (
            (power, 0x40),
            (pullups, 0x20),
            (aux, 0x10),
            (mosi, 0x08),
            (clk, 0x04),
            (miso, 0x02),
            (cs, 0x01),
        ):
            if flag:
                value |= bit
        return self.command(value, 1)[0]

    @staticmethod
    def decode_pins(state: int) -> dict:
        """Turn a pin read-back byte into named booleans."""
        return {
            "power": bool(state & 0x40),
            "pullups": bool(state & 0x20),
            "aux": bool(state & 0x10),
            "mosi": bool(state & 0x08),
            "clk": bool(state & 0x04),
            "miso": bool(state & 0x02),
            "cs": bool(state & 0x01),
        }

    # -- measurement and PWM (bitbang mode only) ---------------------------

    def read_voltage(self) -> float:
        """One reading from the ADC probe, in volts."""
        self.profile.require(device_module.CAP_ADC)
        self.write(bytes([CMD_VOLTAGE_ONCE]))
        raw = int.from_bytes(self.read(2), "big")
        return raw * ADC_FULL_SCALE_VOLTS / ADC_COUNTS

    def measure_frequency(self) -> int:
        """Frequency on the AUX pin, in Hz."""
        self.profile.require(device_module.CAP_FREQUENCY)
        self.write(bytes([CMD_FREQUENCY]))
        return int.from_bytes(self.read(4), "big")

    def pwm_setup_raw(self, prescaler: int, duty: int, period: int) -> None:
        """Configure PWM on AUX from raw PIC24F register values."""
        self.profile.require(device_module.CAP_PWM)
        if prescaler not in PWM_PRESCALERS:
            raise ValueError("prescaler index must be 0 (1:1), 1 (8), 2 (64) or 3 (256)")
        for name, value in (("duty", duty), ("period", period)):
            if not 0 <= value <= 0xFFFF:
                raise ValueError(f"{name} register must fit in 16 bits")
        self.write(
            bytes([CMD_PWM_SETUP, prescaler])
            + duty.to_bytes(2, "big")
            + period.to_bytes(2, "big")
        )
        response = self.read(1)
        if response[0] != ACK:
            raise ProtocolError(f"PWM setup returned 0x{response[0]:02X}")

    def pwm(self, frequency: float, duty_cycle: float = 0.5) -> None:
        """Enable PWM on AUX at ``frequency`` Hz and ``duty_cycle`` (0.0-1.0).

        Picks the smallest prescaler that can represent the frequency. Note
        the firmware keeps PWM running after you leave bitbang mode.
        """
        if frequency <= 0:
            raise ValueError("frequency must be positive")
        if not 0.0 <= duty_cycle <= 1.0:
            raise ValueError("duty_cycle must be between 0.0 and 1.0")
        for index in sorted(PWM_PRESCALERS):
            period = int(PWM_FCY / (PWM_PRESCALERS[index] * frequency)) - 1
            if 0 < period <= 0xFFFF:
                self.pwm_setup_raw(index, int(period * duty_cycle), period)
                return
        raise ValueError(
            f"{frequency} Hz is outside the PWM range (about 0.24 Hz to 8 MHz)"
        )

    def pwm_clear(self) -> None:
        """Stop PWM on AUX."""
        self.profile.require(device_module.CAP_PWM)
        self.command_expect_ack(CMD_PWM_CLEAR)

    def self_test(self, full: bool = False) -> int:
        """Run the firmware's binary self-test and return the error count.

        v3 hardware only. ``full`` needs the test jumper fitted. Send any byte
        to leave the test — :meth:`enter_binary_mode` does that for you.
        """
        self.profile.require(device_module.CAP_SELF_TEST)
        self.write(bytes([CMD_SELF_TEST_FULL if full else CMD_SELF_TEST_SHORT]))
        errors = self.read(1)[0]
        self.write(b"\xff")  # leave self-test
        self.read(1)
        return errors

    def __repr__(self) -> str:
        state = "open" if self.serial is not None else "closed"
        mode = type(self._mode).__name__ if self._mode else None
        return f"<BusPirate {self.port} {state} {self.profile.variant} mode={mode}>"
