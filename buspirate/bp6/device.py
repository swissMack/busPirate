"""The Bus Pirate 6 as a device the dashboard can drive."""

from __future__ import annotations

import logging
from typing import Optional

from ..base import SerialLink, TrafficHook
from ..device import parse_bp6_status
from ..exceptions import BusPirateError, ModeError, ProtocolError
from . import protocol
from .link import BpioLink
from .protocol import Status
from .terminal import select_bpio2

log = logging.getLogger(__name__)

MIN_MV, MAX_MV = 800, 5000
MAX_MA = 500


class BusPirate6(SerialLink):
    """A Bus Pirate 6 on its two USB ports.

    ``port`` is the BPIO2 port (the board's second CDC interface) and
    ``terminal_port`` its text terminal. Everything runs over BPIO2; the
    terminal is opened only to switch BPIO2 on and for the Terminal panel.
    """

    device_name = "Bus Pirate 6"
    protocol_label = "BPIO2"
    bitbang_version = None

    def __init__(
        self,
        port: str,
        terminal_port: Optional[str] = None,
        baudrate: int = 115200,
        timeout: float = 0.05,
        serial_factory=None,
        on_traffic: Optional[TrafficHook] = None,
        reply_timeout: float = 1.0,
        connect_timeout: float = 0.6,
    ) -> None:
        super().__init__(port, baudrate, timeout, serial_factory, on_traffic)
        self.terminal_port = terminal_port
        self.reply_timeout = reply_timeout
        self.connect_timeout = connect_timeout
        self.profile = parse_bp6_status(None)
        self.link: Optional[BpioLink] = None
        self.last_status: Optional[Status] = None
        #: The supply the dashboard asks for whenever it switches power on.
        self.psu_mv = 3300
        self.psu_ma = 300
        self._mode = None
        #: The BPIO2 serial while a stream has lent ``self.serial`` elsewhere.
        self._binary = None
        self._terminal_open = False

    # -- connection --------------------------------------------------------

    def open(self) -> "BusPirate6":
        if self.serial is None:
            self.serial = self._make_serial()
        self.link = BpioLink(self.serial, self._notify, self.reply_timeout)
        try:
            status = self._status(self.connect_timeout)
        except ProtocolError:
            self._switch_bpio2_on()
            try:
                status = self._status(self.connect_timeout * 3)
            except ProtocolError as exc:
                raise ModeError(
                    "the Bus Pirate 6 did not answer on its BPIO2 port, even after "
                    "BPIO2 was selected in its terminal. Unplug it, plug it back "
                    "in, and connect again."
                ) from exc
        if status.flatbuffers_version[0] != protocol.VERSION_MAJOR:
            raise ModeError(
                f"this firmware speaks BPIO {status.flatbuffers_version[0]}."
                f"{status.flatbuffers_version[1]}; the app needs 2.x. Please update "
                "the Bus Pirate's firmware (see the Bus Pirate 6 guide)."
            )
        return self

    def _switch_bpio2_on(self) -> None:
        if not self.terminal_port:
            raise ModeError(
                "the Bus Pirate 6 is not in BPIO2 mode and its terminal port is "
                "unknown. Type binmode, then 2, in its terminal, or connect by "
                "picking the board in the port list."
            )
        terminal = self._make_serial(self.terminal_port)
        try:
            select_bpio2(terminal, self._notify)
        finally:
            terminal.close()

    def _status(self, timeout: Optional[float] = None, quiet: bool = False) -> Status:
        response = self.link.request(protocol.status_request(), timeout, quiet=quiet)
        if response.status is None:
            raise ProtocolError(f"the Bus Pirate 6 did not send its status: {response.error}")
        self.last_status = response.status
        self.profile = parse_bp6_status(response.status)
        return response.status

    def status(self, quiet: bool = False) -> Status:
        """Read the board's status. ``quiet`` keeps it out of the traffic log."""
        return self._status(quiet=quiet)

    def close(self) -> None:
        if self.serial is None:
            return
        try:
            self.stop_stream()
            self.hiz()
        except (BusPirateError, OSError):
            log.debug("could not leave the Bus Pirate 6 in HiZ; closing anyway", exc_info=True)
        finally:
            self.serial.close()
            self.serial = None

    def __enter__(self) -> "BusPirate6":
        return self.open()

    def __exit__(self, *exc_info) -> None:
        self.close()

    # -- configuration -----------------------------------------------------

    def configure(self, **fields) -> None:
        response = self.link.request(protocol.configuration_request(**fields))
        if response.error:
            raise ModeError(f"the Bus Pirate 6 refused that: {response.error}")

    def set_power(self, on: bool, millivolts: Optional[int] = None,
                  milliamps: Optional[int] = None) -> Status:
        if millivolts is not None:
            if not MIN_MV <= millivolts <= MAX_MV:
                raise ValueError(f"the supply goes from {MIN_MV} to {MAX_MV} mV")
            self.psu_mv = int(millivolts)
        if milliamps is not None:
            if not 0 <= milliamps <= MAX_MA:
                raise ValueError(f"the current limit goes from 0 (no limit) to {MAX_MA} mA")
            self.psu_ma = int(milliamps)
        if on:
            self.configure(psu_enable=True, psu_mv=self.psu_mv, psu_ma=self.psu_ma)
        else:
            self.configure(psu_disable=True)
        return self.status()

    def set_pullups(self, on: bool) -> Status:
        self.configure(pullup_enable=on, pullup_disable=not on)
        return self.status()

    def hiz(self) -> None:
        if self._mode is not None:
            self._mode.close()
        self.configure(mode="HiZ", psu_disable=True, pullup_disable=True)
        self.status()

    # -- modes -------------------------------------------------------------

    @property
    def mode(self):
        return self._mode

    def _enter_mode(self, mode_cls):
        if self._mode is not None:
            raise ModeError(f"already in {type(self._mode).__name__}; close it first")
        self._mode = mode_cls(self)
        return self._mode

    def _mode_closed(self, mode) -> None:
        if self._mode is mode:
            self._mode = None

    def i2c(self):
        from .modes import Bp6I2C

        return self._enter_mode(Bp6I2C)

    def spi(self):
        from .modes import Bp6SPI

        return self._enter_mode(Bp6SPI)

    def uart(self):
        from .modes import Bp6UART

        return self._enter_mode(Bp6UART)

    def onewire(self):
        from .modes import Bp6OneWire

        return self._enter_mode(Bp6OneWire)

    # -- streams and the terminal -----------------------------------------

    def lend_serial(self, stand_in) -> None:
        """Let a stream read ``stand_in`` through ``self.serial``."""
        if self._binary is None:
            self._binary = self.serial
        self.serial = stand_in
        self.streaming = True

    def release_to_terminal(self, settle: float) -> None:
        """Open the terminal port in place of BPIO2. Nothing is reset."""
        if not self.terminal_port:
            raise ModeError("this Bus Pirate 6's terminal port is unknown")
        self._mode = None
        terminal = self._make_serial(self.terminal_port)
        self.lend_serial(terminal)
        self._terminal_open = True
        self.write(b"\r")  # a fresh prompt (or the colour question, re-asked)

    def stop_stream(self) -> None:
        if self._binary is None:
            self.streaming = False
            return
        lent, self.serial, self._binary = self.serial, self._binary, None
        self.streaming = False
        if self._terminal_open:
            self._terminal_open = False
            lent.close()
        self._mode = None
        # The terminal may have changed the mode, the supply or the pull-ups.
        self.status()

    def resync(self) -> None:
        self._mode = None
        self.status()

    # -- traffic -----------------------------------------------------------

    def summarize_traffic(self, direction: str, data: bytes) -> str:
        if self._terminal_open:
            return ""
        return protocol.describe_frame(direction, data)

    def __repr__(self) -> str:
        state = "open" if self.serial is not None else "closed"
        mode = type(self._mode).__name__ if self._mode else None
        return f"<BusPirate6 {self.port} {state} mode={mode}>"
