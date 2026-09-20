"""Transport and raw bitbang (BBIO1) layer for the Bus Pirate."""

from __future__ import annotations

import logging
import time
from .exceptions import ConnectionError, ModeError, ProtocolError

log = logging.getLogger(__name__)

# Raw bitbang (BBIO1) commands.
CMD_RESET_BBIO = 0x00
CMD_MODE_SPI = 0x01
CMD_MODE_I2C = 0x02
CMD_MODE_UART = 0x03
CMD_MODE_1WIRE = 0x04
CMD_MODE_RAWWIRE = 0x05
CMD_MODE_JTAG = 0x06
CMD_RESET_HARDWARE = 0x0F

# Pin control, bitbang mode only.
PIN_DIRECTION_BASE = 0x40  # 0b010xxxxx, bitbang mode only
PIN_STATE_BASE = 0x80  # 0b1xxxxxxx, bitbang mode only

ACK = 0x01


class BusPirate:
    """Owns the serial port and the raw bitbang protocol.

    The Bus Pirate boots into a human-readable terminal. :meth:`open` puts it
    into binary mode, from which each protocol mode is entered with
    :meth:`i2c`, :meth:`spi`, :meth:`uart` or :meth:`onewire`.
    """

    def __init__(
        self,
        port: str,
        baudrate: int = 115200,
        timeout: float = 0.2,
        serial_factory=None,
    ) -> None:
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._serial_factory = serial_factory
        self.serial = None
        self._mode = None

    # -- transport ---------------------------------------------------------

    def open(self) -> "BusPirate":
        """Open the port and enter binary bitbang mode."""
        if self.serial is None:
            self.serial = self._make_serial()
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
            raise ConnectionError(f"cannot open {self.port}: {exc}") from exc

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

    # -- primitives --------------------------------------------------------

    def write(self, data: bytes) -> None:
        if self.serial is None:
            raise ConnectionError("port is not open")
        log.debug("-> %s", data.hex(" "))
        self.serial.write(data)
        flush = getattr(self.serial, "flush", None)
        if flush is not None:
            flush()

    def read(self, count: int) -> bytes:
        """Read exactly ``count`` bytes or raise :class:`ProtocolError`."""
        if self.serial is None:
            raise ConnectionError("port is not open")
        data = self.serial.read(count)
        log.debug("<- %s", data.hex(" "))
        if len(data) != count:
            raise ProtocolError(
                f"expected {count} byte(s), got {len(data)}: {data!r}"
            )
        return data

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

    # -- mode control ------------------------------------------------------

    def enter_binary_mode(self, retries: int = 25) -> None:
        """Knock on the port with 0x00 until the Bus Pirate answers ``BBIO1``.

        The device answers only once it has seen enough nulls to leave the
        terminal, so this is a loop by design rather than a single write.
        """
        self.flush_input()
        for attempt in range(retries):
            self.write(b"\x00")
            response = self.serial.read(5)
            if response == b"BBIO1":
                log.debug("binary mode entered after %d write(s)", attempt + 1)
                self._mode = None
                return
            if response and not response.endswith(b"BBIO1"):
                # Terminal banner or echo still draining; keep knocking.
                self.flush_input()
            time.sleep(0.01)
        raise ModeError(
            f"no BBIO1 response after {retries} attempts on {self.port}; "
            "check the port, the baud rate, and that nothing else holds it open"
        )

    def reset_hardware(self) -> None:
        """Reset the Bus Pirate back to its human-readable terminal."""
        self.write(bytes([CMD_RESET_HARDWARE]))
        self._mode = None
        self.flush_input()

    def _enter_mode(self, mode_cls):
        if self._mode is not None:
            raise ModeError(
                f"already in {type(self._mode).__name__}; close it first"
            )
        mode = mode_cls(self)
        mode.enter()
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
        for flag, bit in ((aux, 0x10), (mosi, 0x08), (clk, 0x04), (miso, 0x02), (cs, 0x01)):
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

    def __repr__(self) -> str:
        state = "open" if self.serial is not None else "closed"
        return f"<BusPirate {self.port} {state} mode={type(self._mode).__name__ if self._mode else None}>"
