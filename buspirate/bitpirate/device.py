"""The ESP32 Bit Pirate as a device the dashboard can drive."""

from __future__ import annotations

import logging
import re
import time
from dataclasses import replace
from typing import Dict, Optional

from ..base import SerialLink, TrafficHook
from ..device import DeviceProfile, parse_bitpirate_banner
from ..exceptions import BusPirateError, ModeError
from .cli import CliTimeout, CliTransport

log = logging.getLogger(__name__)

_RE_SUMMARY_FIRMWARE = re.compile(r"^Firmware\s*:\s*version\s+(\d[\w.\-]*)")


class BitPirate(SerialLink):
    """An ESP32 Bit Pirate (geo-tp firmware) on its USB serial port.

    It offers what :class:`~buspirate.base.BusPirate` offers the dashboard —
    a profile, ``i2c()``, ``spi()`` and ``uart()``, streams and the board's
    own terminal — but underneath it types commands into the firmware's
    command line, since there is no binary mode to use. See
    :mod:`buspirate.bitpirate.cli`.

    Connecting sends nothing but Enter, which is safe in every state the
    board can be in, and never the Bus Pirate's nulls or reset byte.
    """

    device_name = "Bit Pirate"
    protocol_label = "text command line"
    #: There is no binary protocol, so no version of one.
    bitbang_version = None

    def __init__(
        self,
        port: str,
        baudrate: int = 115200,
        timeout: float = 0.05,
        serial_factory=None,
        on_traffic: Optional[TrafficHook] = None,
        reply_timeout: float = 3.0,
        connect_timeout: float = 1.5,
    ) -> None:
        super().__init__(port, baudrate, timeout, serial_factory, on_traffic)
        self.profile: DeviceProfile = parse_bitpirate_banner("")
        self.cli = CliTransport(self, timeout=reply_timeout)
        self.connect_timeout = connect_timeout
        #: What each mode's config dialog was last told, by mode name.
        self.settings: Dict[str, Dict[str, str]] = {}
        self._mode = None
        #: Modes entered this session whose pins HiZ must let go of itself,
        #: by mode id (see boards._modes.CliMode.release).
        self._to_release: Dict[str, object] = {}

    # -- connection --------------------------------------------------------

    def open(self) -> "BitPirate":
        """Open the port and get to the prompt, reading the banner if it comes.

        A board just plugged in spends about three seconds picking its
        terminal before it waits for a key, so the first Enters may go
        unanswered; ``sync`` keeps pressing.
        """
        if self.serial is None:
            self.serial = self._make_serial()
        try:
            banner = self.cli.sync(timeout=self.connect_timeout)
        except CliTimeout as exc:
            raise ModeError(
                f"{self.port} never showed a Bit Pirate prompt. If the board "
                "has just been plugged in, give it a few seconds and connect "
                "again; on a DevKit use the port marked USB or USB OTG, not "
                "UART or USB TTL."
            ) from exc
        self.profile = parse_bitpirate_banner(banner)
        if self.profile.firmware is None:
            firmware = self._firmware_from_system()
            if firmware:
                self.profile = replace(self.profile, firmware=firmware)
        return self

    def _firmware_from_system(self) -> Optional[str]:
        """The version from ``system``'s summary, for a board met past its banner.

        The banner is printed once, on the first key after boot; a board
        something else has already woken only shows it again after a reset.
        The system shell's summary has it too, as ``Firmware : version 1.7``
        (Shells/SysInfoShell.cpp cmdSummary). Its menu is left by its default,
        Exit — its Reboot and Bootloader items are never chosen.
        """
        try:
            reply = self.cli.command("system", picks=["System summary"])
        except BusPirateError:
            log.debug("could not read the firmware version from 'system'", exc_info=True)
            return None
        for line in reply.lines:
            found = _RE_SUMMARY_FIRMWARE.match(line)
            if found:
                return found.group(1)
        return None

    def close(self) -> None:
        """Release every pin (``m hiz``) and close the port."""
        if self.serial is None:
            return
        try:
            if self._mode is not None:
                self._mode.close()
            self.hiz()
        except (BusPirateError, OSError):
            log.debug("could not leave the board in HiZ; closing anyway", exc_info=True)
        finally:
            self.serial.close()
            self.serial = None

    def __enter__(self) -> "BitPirate":
        return self.open()

    def __exit__(self, *exc_info) -> None:
        self.close()

    # -- modes -------------------------------------------------------------

    @property
    def mode(self):
        return self._mode

    def _enter_mode(self, mode_cls, make=None):
        """Enter a mode; ``make(self)`` builds it when it is not ``mode_cls(self)``."""
        if self._mode is not None:
            raise ModeError(f"already in {type(self._mode).__name__}; close it first")
        mode = (make or mode_cls)(self)
        # The Bus Pirate 6 pin layout of the ESP32 Bit Pirate Dock, not the
        # firmware's own defaults (see modes.DOCK_PINS). A first entry asks
        # the config questions itself; later entries need ``config``. A mode
        # with no pins to set (DIO, Wi-Fi) needs neither.
        reply = self.cli.enter_mode(mode.name, mode.pins)
        self._mode = mode
        if set(mode.pins) <= set(reply.questions):
            self.settings.setdefault(mode.name, {}).update(mode.pins)
        else:
            mode._configure(mode.pins)
        return mode

    def _mode_closed(self, mode) -> None:
        if self._mode is mode:
            self._mode = None

    def i2c(self):
        from .modes import CliI2C

        return self._enter_mode(CliI2C)

    def spi(self):
        from .modes import CliSPI

        return self._enter_mode(CliSPI)

    def uart(self):
        from .modes import CliUART

        return self._enter_mode(CliUART)

    def cli_mode(self, spec):
        """Enter one of the board's own modes, described by a boards CliMode."""
        from .modes import CliModeSession

        mode = self._enter_mode(CliModeSession, lambda bp: CliModeSession(bp, spec))
        if spec.release:
            self._to_release[spec.id] = spec
        return mode

    def hiz(self) -> None:
        """Let go of every pin: undo what modes like DIO left driving, then
        ``m hiz``. Call with no mode open."""
        for spec in list(self._to_release.values()):
            mode = self.cli_mode(spec)
            for line in spec.release:
                mode.run(line)
            mode.close()
        self._to_release.clear()
        self.cli.command("m hiz")

    # -- streams and the terminal -----------------------------------------

    def start_text_stream(
        self, command: str, header: Optional[str] = None, timeout: float = 2.0
    ) -> None:
        """Run a command that streams until Enter, and hand over the port.

        Everything up to the end of the line holding ``header`` is consumed,
        one byte at a time so that none of the stream is. With no header,
        only the echo of the command is: the stream starts on the next line.
        """
        self.flush_input()
        self.write((command + "\r").encode("ascii"))
        seen = bytearray()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._port_alive():
                byte = self.serial.read(1)
            if not byte:
                time.sleep(0.002)
                continue
            seen += byte
            text = seen.decode("utf-8", "replace")
            if byte == b"\n" and (header is None or header in text.rsplit("\n", 2)[-2]):
                self._notify("rx", bytes(seen))
                self.streaming = True
                return
        self._notify("rx", bytes(seen))
        raise ModeError(
            f"the Bit Pirate did not start {command!r}; it said: "
            f"{seen.decode('utf-8', 'replace').strip()[-120:] or 'nothing'}"
        )

    def stop_stream(self) -> None:
        """Enter ends every stream the firmware has, then wait for the prompt."""
        self.streaming = False
        if self.serial is None:
            return
        self.cli.sync()
        self._mode = None

    def resync(self) -> None:
        self.cli.sync()
        self._mode = None

    def release_to_terminal(self, settle: float) -> None:
        """Hand the port to the terminal. Nothing resets: just press Enter,
        so the console opens on a fresh prompt."""
        self._mode = None
        self.flush_input()
        self.write(b"\r")

    def __repr__(self) -> str:
        state = "open" if self.serial is not None else "closed"
        mode = type(self._mode).__name__ if self._mode else None
        return f"<BitPirate {self.port} {state} mode={mode}>"
