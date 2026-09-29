"""Shared behaviour for the protocol modes reachable from bitbang mode."""

from __future__ import annotations

from typing import Dict, Optional

from .exceptions import ModeError, ProtocolError
from .protocol import BANNER_BITBANG, banner_length, match_banner

ACK = 0x01
CMD_EXIT = 0x00
CMD_MODE_VERSION = 0x01
PERIPHERAL_BASE = 0x40  # 0b0100wxyz
MAX_BULK = 16


class Mode:
    """A protocol mode entered from raw bitbang mode.

    Subclasses set :attr:`enter_command` (the bitbang byte that selects the
    mode) and :attr:`banner_prefix` (the banner it answers with, without the
    trailing protocol version digit).
    """

    enter_command: int = 0
    banner_prefix: str = ""
    #: Human-readable name used in error messages and by the dashboard.
    title: str = ""

    def __init__(self, bp) -> None:
        self.bp = bp
        self._active = False
        #: Protocol version digit from the mode's banner, e.g. 1 for "I2C1".
        self.version: Optional[int] = None
        #: The last peripheral state sent, so callers can tell what the board
        #: ought to be doing. Nothing reads it back off the hardware.
        self.peripherals: Dict[str, bool] = {
            "power": False, "pullups": False, "aux": False, "cs": False,
        }

    # -- lifecycle ---------------------------------------------------------

    def enter(self) -> None:
        self.bp.write(bytes([self.enter_command]))
        banner = self.bp.read(banner_length(self.banner_prefix))
        self.version = match_banner(
            banner, self.banner_prefix, f"entering {type(self).__name__}"
        )
        self._active = True

    def close(self) -> None:
        """Leave this mode and return the Bus Pirate to bitbang mode."""
        if not self._active:
            return
        self._active = False
        try:
            self.bp.write(bytes([CMD_EXIT]))
            banner = self.bp.read(banner_length(BANNER_BITBANG))
            match_banner(banner, BANNER_BITBANG, f"leaving {type(self).__name__}")
        finally:
            # Even when the exit reply is lost, this mode is finished: it has
            # already marked itself inactive, so a second close() would return
            # early. Leaving the device still pointing at it made every later
            # attempt to enter the same mode fail with "already in …".
            self.bp._mode_closed(self)

    def __enter__(self) -> "Mode":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    @property
    def is_active(self) -> bool:
        return self._active

    def _check_active(self) -> None:
        if not self._active:
            raise ModeError(f"{type(self).__name__} has been closed")

    # -- common commands ---------------------------------------------------

    def configure_peripherals(
        self,
        power: bool = False,
        pullups: bool = False,
        aux: bool = False,
        cs: bool = False,
    ) -> None:
        """Switch the on-board power supplies, pull-ups, AUX and CS pins.

        The Bus Pirate's pull-ups are passive — for I2C you usually want
        ``power=True, pullups=True``, and an external supply on Vpullup if the
        target does not run from the Bus Pirate's own 3V3/5V rails.
        """
        self._check_active()
        value = PERIPHERAL_BASE
        for flag, bit in ((power, 0x08), (pullups, 0x04), (aux, 0x02), (cs, 0x01)):
            if flag:
                value |= bit
        self.bp.command_expect_ack(value)
        self.peripherals = {
            "power": power, "pullups": pullups, "aux": aux, "cs": cs,
        }

    def mode_version(self) -> int:
        """Ask the mode to re-announce its version banner."""
        self._check_active()
        self.bp.write(bytes([CMD_MODE_VERSION]))
        banner = self.bp.read(banner_length(self.banner_prefix))
        return match_banner(banner, self.banner_prefix, "reading the mode version")

    def _bulk_header(self, count: int) -> int:
        if not 1 <= count <= MAX_BULK:
            raise ValueError(f"bulk transfers carry 1-{MAX_BULK} bytes, got {count}")
        return 0x10 | (count - 1)

    def _expect_ack(self, what: str) -> None:
        response = self.bp.read(1)
        if response[0] != ACK:
            raise ProtocolError(f"{what}: got 0x{response[0]:02X}, want 0x01")

    def _write_bulk_chunks(self, data: bytes, what: str) -> bytes:
        """Write any length as 16-byte bulk chunks, returning the status bytes."""
        self._check_active()
        status = bytearray()
        data = bytes(data)
        for start in range(0, len(data), MAX_BULK):
            chunk = data[start : start + MAX_BULK]
            self.bp.write(bytes([self._bulk_header(len(chunk))]) + chunk)
            self._expect_ack(what)
            status += self.bp.read(len(chunk))
        return bytes(status)

    def __repr__(self) -> str:
        state = "active" if self._active else "closed"
        return f"<{type(self).__name__} {state}>"
