"""The ESP32 Bit Pirate's command line, as a request/reply transport.

The firmware is a human terminal, not a protocol, so a reply has no length
and no terminator: it ends when the prompt comes back. Three habits of its
line editor (src/Managers/CommandLineManager.cpp) shape everything here:

* it redraws the whole line on every key as ``\\r<MODE>> <line>ESC[K``, so
  what a reply *means* is what a terminal would show — :func:`screen_lines`
  replays the carriage returns and drops the escapes;
* ``\\r`` and ``\\n`` are each Enter, so a line is sent with ``\\r`` alone —
  ``\\r\\n`` would be a second Enter, answering whatever came next;
* a command that needs more asks for it as ``Label [default]: ``, and an
  empty answer takes the default (src/Managers/UserInputManager.cpp).
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..exceptions import BusPirateError, ModeError

#: The firmware ignores keys past this many on one line.
MAX_LINE = 512
#: More questions than any config dialog asks: a command that keeps asking
#: is not one this driver knows how to answer.
MAX_QUESTIONS = 16

_ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_PROMPT = re.compile(r"^([A-Z0-9]*)> $")
_QUESTION = re.compile(r"^(.*?) \[([^\]]*)\]: $")
_SCAN_HIT = re.compile(r"^Found device at 0x([0-9A-Fa-f]+)")
_HEX_BYTE = re.compile(r"^[0-9A-Fa-f]{2}$")


class CliTimeout(BusPirateError):
    """The board stopped talking before its prompt came back."""

    def __init__(self, message: str, partial: str = "") -> None:
        super().__init__(message)
        self.partial = partial


class CliPromptError(BusPirateError):
    """The board kept asking questions this driver has no answers for."""


def screen_lines(raw: str) -> List[str]:
    """The lines a terminal would be showing after ``raw``.

    Escapes are dropped and, within each line, only what follows its last
    carriage return survives — which turns the per-key redraw into the line
    that was finally typed.
    """
    lines = []
    for line in _ANSI.sub("", raw).split("\n"):
        if line.endswith("\r"):
            line = line[:-1]
        lines.append(line.rsplit("\r", 1)[-1])
    return lines


def parse_scan(lines: List[str]) -> List[int]:
    """Addresses from ``scan`` (Controllers/I2cController.cpp handleScan)."""
    found = []
    for line in lines:
        hit = _SCAN_HIT.match(line.strip())
        if hit:
            found.append(int(hit.group(1), 16))
    return found


def parse_hex_after(lines: List[str], marker: str) -> bytes:
    """Bytes printed after ``marker``, up to the "ByteCode Sequence" dump.

    ``[ ... ]`` instructions print what they read as ``XX XX `` after an
    ``I2C Read:`` or ``SPI Read:`` line. A read that got nothing prints no
    marker at all, which comes back here as no bytes.
    """
    data = bytearray()
    reading = False
    for line in lines:
        if line.startswith("ByteCode Sequence"):
            break
        if line.startswith(marker):
            reading = True
            continue
        if reading:
            data += bytes(int(token, 16) for token in line.split() if _HEX_BYTE.match(token))
    return bytes(data)


@dataclass
class Reply:
    """One command's output, without its echo or the prompt that ended it."""

    lines: List[str]
    mode: str
    #: The labels of the questions the command asked, in order.
    questions: List[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


class CliTransport:
    """Sends command lines to a Bit Pirate and collects what comes back.

    ``link`` is the device: something with ``serial``, ``write``, ``_notify``
    and ``flush_input``. ``timeout`` is how long the board may go quiet
    before a reply is given up on — measured from its last byte, not from the
    command, so a long but busy reply is never cut short.
    """

    def __init__(self, link, timeout: float = 3.0) -> None:
        self.link = link
        self.timeout = timeout
        #: The mode the last prompt showed, e.g. "HIZ" or "I2C".
        self.mode: Optional[str] = None

    # -- one command -------------------------------------------------------

    def command(
        self,
        line: str,
        answers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
    ) -> Reply:
        """Run one command line and return its output.

        Questions are answered from ``answers`` by their label; any other
        question gets an empty answer, which takes its default.
        """
        if len(line) >= MAX_LINE:
            raise ValueError(
                f"the Bit Pirate reads at most {MAX_LINE} characters on a "
                f"line and this command is {len(line)}"
            )
        self.link.flush_input()
        self.link.write((line + "\r").encode("ascii"))
        raw, questions = self._read_reply(answers or {}, timeout or self.timeout)
        lines = screen_lines(raw)
        self.mode = _PROMPT.match(lines.pop()).group(1)
        if lines and lines[0].endswith(line):
            lines.pop(0)  # the echo of what was typed
        return Reply(lines=lines, mode=self.mode, questions=questions)

    def enter_mode(self, name: str, answers: Optional[Dict[str, str]] = None) -> Reply:
        """``m <name>``, answering the questions a first entry asks."""
        reply = self.command(f"m {name}", answers)
        for text in reply.lines:
            if text.startswith("Unknown mode"):
                raise ModeError(f"the Bit Pirate said: {text}")
        if reply.mode != name.upper():
            raise ModeError(
                f"asked the Bit Pirate for {name.upper()} mode but its prompt "
                f"says {reply.mode or 'no mode'}"
            )
        return reply

    # -- getting to a prompt -----------------------------------------------

    def sync(self, attempts: int = 6, timeout: Optional[float] = None) -> str:
        """Press Enter until the board shows its prompt. Returns all it said.

        Covers every state a board can be met in: waiting at "Press any key
        to start..." after boot (any key will do, and then the banner comes),
        sitting at its prompt, part way through a question (Enter takes the
        default) or streaming (Enter stops every stream it has).
        """
        collected = self._drain()
        for _ in range(attempts):
            self.link.write(b"\r")
            try:
                raw, _ = self._read_reply({}, timeout or self.timeout)
            except CliTimeout as exc:
                collected += exc.partial
                continue
            collected += raw
            self.mode = _PROMPT.match(screen_lines(raw)[-1]).group(1)
            return collected
        raise CliTimeout(
            f"the board never showed its prompt after {attempts} Enters",
            collected,
        )

    # -- reading -----------------------------------------------------------

    def _read_reply(self, answers: Dict[str, str], timeout: float):
        """Read until the prompt, answering questions on the way."""
        buffer = bytearray()
        questions: List[str] = []
        answered_line = -1
        deadline = time.monotonic() + timeout
        while True:
            chunk = self.link.serial.read(256)
            if chunk:
                buffer += chunk
                self.link._notify("rx", bytes(chunk))
                deadline = time.monotonic() + timeout
                continue
            # Quiet: the board is waiting, either at its prompt or on a
            # question. Both are decided on the screen, never on a fragment.
            lines = screen_lines(buffer.decode("utf-8", "replace"))
            last = lines[-1]
            # The prompt only counts once a line has ended before it: a
            # redraw split just after "I2C> " is not the prompt coming back.
            if len(lines) > 1 and _PROMPT.match(last):
                return buffer.decode("utf-8", "replace"), questions
            question = _QUESTION.match(last)
            if question and len(lines) - 1 > answered_line:
                label = question.group(1)
                questions.append(label)
                if len(questions) > MAX_QUESTIONS:
                    raise CliPromptError(
                        f"the Bit Pirate kept asking questions; the last was {last!r}"
                    )
                self.link.write((answers.get(label, "") + "\r").encode("ascii"))
                answered_line = len(lines) - 1
                deadline = time.monotonic() + timeout
                continue
            if time.monotonic() >= deadline:
                partial = buffer.decode("utf-8", "replace")
                tail = " / ".join(line for line in lines[-3:] if line.strip())
                raise CliTimeout(
                    f"the Bit Pirate went quiet without showing its prompt; it "
                    f"last said: {tail or 'nothing'}",
                    partial,
                )
            time.sleep(0.002)

    def _drain(self, quiet: float = 0.05) -> str:
        """Whatever the board has already said, without sending anything."""
        buffer = bytearray()
        deadline = time.monotonic() + quiet
        while time.monotonic() < deadline:
            chunk = self.link.serial.read(256)
            if chunk:
                buffer += chunk
                self.link._notify("rx", bytes(chunk))
                deadline = time.monotonic() + quiet
            else:
                time.sleep(0.002)
        return buffer.decode("utf-8", "replace")
