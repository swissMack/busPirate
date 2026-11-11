"""A scripted session with the Bus Pirate 6's text terminal.

The console sends one command line, reads until the main prompt, and answers
only the sub-prompts the caller named in advance. Any other sub-prompt is left
with ``x`` (never Ctrl-C: see ``terminal.wake``) and reported as an error, so a
command that unexpectedly asks a question cannot be answered by accident.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Callable, Optional, Sequence

from ..exceptions import BusPirateError, PortGoneError

#: Escape sequences (colours, erase-line, cursor moves) the terminal sends.
_ESCAPES = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
_MAIN_PROMPT = re.compile(r"^([A-Za-z0-9]+)(-\([^)]*\))?> $")
_SUB_PROMPT = re.compile(r">\s?$")
_ERROR = re.compile(
    r"^(Error: .*|Invalid command: .*|Command has no effect in HiZ mode.*"
    r"|.* out of range: .*|.*is not available.*|.*is invalid!.*"
    r"|.*has no frequency measurement hardware!.*|.*is unavailable because.*"
    r"|.*is in use by.*)$"
)


class TerminalError(BusPirateError):
    """The terminal did not do what a scripted command expected."""


@dataclass(frozen=True)
class Answer:
    """What to type when ``pattern`` shows up and no main prompt follows.

    A ``reply`` of ``" "`` is sent bare; any other is sent with ``\\r``. Each
    answer is used at most once.
    """

    pattern: str
    reply: str
    wait_s: float = 0.0


@dataclass(frozen=True)
class Reply:
    text: str
    mode: str
    error: Optional[str]


def clean(raw: str) -> str:
    """Drop escapes, ETX, BEL and carriage returns; lines end in ``\\n``."""
    text = _ESCAPES.sub("", raw)
    return text.replace("\x03", "").replace("\x07", "").replace("\r", "")


def _last_line(text: str) -> str:
    return text.rsplit("\n", 1)[-1]


class Console:
    #: How long output with no ETX must stay silent before it is judged.
    QUIET_S = 0.05

    def __init__(self, serial, notify: Callable[[str, bytes], None], timeout: float = 3.0) -> None:
        self.serial = serial
        self.notify = notify
        self.timeout = timeout
        #: The mode named by the last prompt seen ("" before any command).
        self.mode = ""
        self._pending_error: Optional[str] = None

    # -- io ------------------------------------------------------------------

    def _write(self, data: bytes) -> None:
        try:
            self.serial.write(data)
        except OSError as exc:
            raise PortGoneError("the Bus Pirate 6's terminal port stopped working") from exc
        self.notify("tx", data)

    def _read(self) -> bytes:
        try:
            chunk = self.serial.read(256)
        except OSError as exc:
            raise PortGoneError("the Bus Pirate 6's terminal port stopped working") from exc
        if chunk:
            self.notify("rx", bytes(chunk))
        return bytes(chunk)

    def _at_main_prompt(self, text: str) -> bool:
        match = _MAIN_PROMPT.match(_last_line(text))
        if match:
            self.mode = match.group(1)
            return True
        return False

    def _read_to_prompt(self, line: str, timeout: float) -> str:
        seen = bytearray()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            chunk = self._read()
            if not chunk:
                time.sleep(0.005)
                continue
            seen += chunk
            text = clean(seen.decode("utf-8", "replace"))
            if self._at_main_prompt(text):
                return text
        raise TerminalError(f"the terminal did not answer {line}")

    # -- commands ------------------------------------------------------------

    def _drain(self) -> None:
        """Read what is already waiting. An error the board raised on its own
        (a tripped supply) is kept for the next reply instead of being lost."""
        seen = bytearray()
        for _ in range(100):
            chunk = self._read()
            if not chunk:
                break
            seen += chunk
        for ln in clean(seen.decode("utf-8", "replace")).split("\n"):
            if _ERROR.match(ln.strip()):
                self._pending_error = self._pending_error or ln.strip()

    def command(self, line: str, timeout: float = 3.0,
                answers: Sequence[Answer] = (), until: Optional[str] = None) -> Reply:
        """Run ``line`` and return what it printed. Never sends Ctrl-C.

        ``until`` names text that ends the command when no prompt follows it
        (a binary mode that locks the terminal); the reply then keeps the mode
        of the last prompt seen.
        """
        self._drain()
        self._write(line.encode() + b"\r")
        unused = list(answers)
        seen = bytearray()
        mark = 0            # start of the output not yet answered
        waiting_since = None
        waiting_for = None
        last_data = time.monotonic()
        deadline = last_data + timeout
        text = ""
        while time.monotonic() < deadline:
            chunk = self._read()
            if chunk:
                seen += chunk
                text = clean(seen.decode("utf-8", "replace"))
                waiting_since = waiting_for = None
                last_data = time.monotonic()
            # ETX ends every prompt (research doc section 0). Output without one
            # is judged only once the line has gone quiet.
            ended = seen.decode("utf-8", "replace").rstrip().endswith("\x03")
            settled = ended or (bool(seen) and time.monotonic() - last_data >= self.QUIET_S)
            if settled and self._at_main_prompt(text):
                return self._reply(text)
            if settled and until is not None and until in text:
                return self._reply(text + "\n")
            tail = text[mark:]
            due = next((a for a in unused if a.pattern in tail), None)
            if due is not None:
                if waiting_for is not due:
                    waiting_for, waiting_since = due, time.monotonic()
                if time.monotonic() - waiting_since >= due.wait_s:
                    unused.remove(due)
                    self._write(b" " if due.reply == " " else due.reply.encode() + b"\r")
                    mark = len(text)
                    waiting_since = waiting_for = None
                    deadline = max(deadline, time.monotonic() + timeout)
                    continue
            elif settled and tail.strip() and (
                    ended or _SUB_PROMPT.search(_last_line(text).rstrip())):
                self._abort(line, tail)
            if not chunk:
                time.sleep(0.005)
        raise TerminalError(f"the terminal did not answer {line}")

    def _abort(self, line: str, tail: str) -> None:
        asked = tail.strip()[-200:]
        self._write(b"x\r")
        try:
            self._read_to_prompt(line, self.timeout)
        except TerminalError:
            pass
        raise TerminalError(f"{line} stopped at an unexpected question: {asked}")

    def _reply(self, text: str) -> Reply:
        lines = text.split("\n")
        body = lines[1:-1]  # drop the echo and the prompt line
        error = next((ln.strip() for ln in body if _ERROR.match(ln.strip())), None)
        error, self._pending_error = self._pending_error or error, None
        return Reply("\n".join(body).strip("\n"), self.mode, error)
