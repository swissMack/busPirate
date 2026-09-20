"""Shared behaviour for the protocol modes reachable from bitbang mode."""

from __future__ import annotations

from .exceptions import ModeError, ProtocolError

ACK = 0x01
CMD_EXIT = 0x00
PERIPHERAL_BASE = 0x40  # 0b0100wxyz
MAX_BULK = 16


class Mode:
    """A protocol mode entered from raw bitbang mode.

    Subclasses set :attr:`enter_command` (the bitbang byte that selects the
    mode) and :attr:`version_string` (the banner the mode answers with).
    """

    enter_command: int = 0
    version_string: bytes = b""

    def __init__(self, bp) -> None:
        self.bp = bp
        self._active = False

    # -- lifecycle ---------------------------------------------------------

    def enter(self) -> None:
        self.bp.write(bytes([self.enter_command]))
        banner = self.bp.read(len(self.version_string))
        if banner != self.version_string:
            raise ModeError(
                f"entering {type(self).__name__}: got {banner!r}, "
                f"want {self.version_string!r}"
            )
        self._active = True

    def close(self) -> None:
        """Leave this mode and return the Bus Pirate to bitbang mode."""
        if not self._active:
            return
        self._active = False
        self.bp.write(bytes([CMD_EXIT]))
        banner = self.bp.read(5)
        if banner != b"BBIO1":
            raise ModeError(f"leaving {type(self).__name__}: got {banner!r}")
        self.bp._mode_closed(self)

    def __enter__(self) -> "Mode":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

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
        ``power=True, pullups=True``, and an external Vpullup source on Vextern
        if the target is not 3V3/5V from the Bus Pirate itself.
        """
        self._check_active()
        value = PERIPHERAL_BASE
        for flag, bit in ((power, 0x08), (pullups, 0x04), (aux, 0x02), (cs, 0x01)):
            if flag:
                value |= bit
        self.bp.command_expect_ack(value)

    def mode_version(self) -> bytes:
        """Ask the mode to re-announce its version banner."""
        self._check_active()
        return self.bp.command(0x01, len(self.version_string))

    def _bulk_header(self, count: int) -> int:
        if not 1 <= count <= MAX_BULK:
            raise ValueError(f"bulk transfers carry 1-{MAX_BULK} bytes, got {count}")
        return 0x10 | (count - 1)

    def _expect_ack(self, what: str) -> None:
        response = self.bp.read(1)
        if response[0] != ACK:
            raise ProtocolError(f"{what}: got 0x{response[0]:02X}, want 0x01")

    def __repr__(self) -> str:
        state = "active" if self._active else "closed"
        return f"<{type(self).__name__} {state}>"
