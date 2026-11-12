"""A scripted session with the Bus Pirate 6's text terminal.

The console sends one command line, reads until the main prompt, and answers
only the sub-prompts the caller named in advance. Any other sub-prompt is left
with ``x`` (never Ctrl-C: see ``terminal.wake``) and reported as an error, so a
command that unexpectedly asks a question cannot be answered by accident.
"""

from __future__ import annotations

import codecs
import re
import time
from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence, Tuple

from ..exceptions import BusPirateError, PortGoneError

#: Escape sequences (colours, erase-line, cursor moves) the terminal sends.
_ESCAPES = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
#: The start of an escape sequence that the next read may complete.
_ESCAPE_START = re.compile(r"\x1b(?:\[[0-9;?]*)?\Z")
_MODES = r"(HiZ|1WIRE|UART|HDUART|I2C|SPI|2WIRE|3WIRE|DIO|LED|INFRARED|JTAG|PS2|USB)"
#: A prompt that follows unterminated output on the same line (a sniffer that
#: was stopped mid-transaction prints nothing before the prompt).
_INLINE_PROMPT = re.compile(_MODES + r"(?:-\([^)]*\))?> $")
_MAIN_PROMPT = re.compile(r"^([A-Za-z0-9]+)(-\([^)]*\))?> $")
#: A main prompt with its ETX. The ETX is printed only there, so the reply
#: ends at it even when more text follows: in INFRARED mode the board prints
#: each code it receives at the prompt, at any time (research 3b section 6).
_ETX_PROMPT = re.compile(r"\n([A-Za-z0-9]+)(?:-\([^)]*\))?> \x03")
_INLINE_ETX_PROMPT = re.compile(_MODES + r"(?:-\([^)]*\))?> \x03")
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

    In ``Console.command`` a ``reply`` of ``" "`` is sent bare and any other
    with ``\\r``, and each answer is used at most once. In ``Console.listen``
    (a key for a menu) the reply is always sent raw, without ``\\r``, every
    time the pattern shows up.
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
    return _keep_etx(raw).replace("\x03", "")


def _keep_etx(raw: str) -> str:
    """``clean`` that keeps the ETX, which marks the end of a prompt."""
    return _ESCAPES.sub("", raw).replace("\x07", "").replace("\r", "")


def _last_line(text: str) -> str:
    return text.rsplit("\n", 1)[-1]


class _Output:
    """Terminal output, decoded and cleaned once as it arrives.

    A flood of output costs linear time: each read is cleaned on its own (an
    escape sequence or a UTF-8 character cut by the read is held back for the
    next one), and the checks look only at the new text plus ``OVERLAP``
    characters before it. The ETX is kept: it marks the end of a prompt.
    """

    #: Characters of earlier text searched again, so a pattern cut by a read is found.
    OVERLAP = 128
    #: The longest unfinished last line kept; a prompt is far shorter.
    LINE_CAP = 512

    def __init__(self) -> None:
        self._decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self._held = ""
        self._parts = []  # type: List[str]
        self.size = 0
        #: The last, unfinished line (its last LINE_CAP characters).
        self.line = ""
        #: Whether the output, trailing blanks aside, ends in an ETX.
        self.ended = False
        self._tail = ""

    def add(self, chunk: bytes) -> Tuple[str, int]:
        """Add ``chunk``; return the text to search and its start in ``text()``."""
        text = self._held + self._decoder.decode(chunk)
        cut = text.rfind("\x1b")
        if cut != -1 and _ESCAPE_START.match(text, cut):
            self._held, text = text[cut:], text[:cut]
        else:
            self._held = ""
        piece = _keep_etx(text)
        window = self._tail + piece
        base = self.size - len(self._tail)
        self._parts.append(piece)
        self.size += len(piece)
        self._tail = window[-self.OVERLAP:]
        newline = piece.rfind("\n")
        line = piece[newline + 1:] if newline != -1 else self.line + piece
        self.line = line[-self.LINE_CAP:]
        if piece.rstrip():
            self.ended = piece.rstrip().endswith("\x03")
        return window, base

    def text(self) -> str:
        """Everything so far (cleaned, ETX kept)."""
        if len(self._parts) > 1:
            self._parts = ["".join(self._parts)]
        return self._parts[0] if self._parts else ""


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
            # Read what is waiting in one go: a sniffer can flood the port.
            waiting = getattr(self.serial, "in_waiting", 0)
            size = min(waiting, 65536) if isinstance(waiting, int) and waiting > 256 else 256
            chunk = self.serial.read(size)
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

    def _ended_reply(self, raw: str) -> Optional[Reply]:
        """The reply, if ``raw`` (cleaned, ETX kept) holds a main prompt with its ETX.

        Text after that prompt (an IR code received at the prompt) is kept at
        the end of the reply.
        """
        found = _ETX_PROMPT.search(raw)
        if found is None:
            return None
        self.mode = found.group(1)
        return self._reply(raw[:found.end()].replace("\x03", ""), raw[found.end():])

    def _read_to_prompt(self, line: str, timeout: float) -> None:
        out = _Output()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            chunk = self._read()
            if not chunk:
                time.sleep(0.005)
                continue
            window, _ = out.add(chunk)
            if _ETX_PROMPT.search(window) or self._at_main_prompt(out.line.replace("\x03", "")):
                return
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
                raw = _keep_etx(seen.decode("utf-8", "replace"))
                text = raw.replace("\x03", "")
                waiting_since = waiting_for = None
                last_data = time.monotonic()
                done = self._ended_reply(raw)
                if done is not None:
                    return done
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

    def listen(self, line: str, seconds: float, stop: str, ready: Optional[str] = None,
               keys: Sequence[Answer] = (), timeout: float = 3.0) -> Reply:
        """Run a streaming command for ``seconds``, then stop it with ``stop``.

        ``stop`` is one raw key (no Enter, never Ctrl-C). With ``ready`` the
        clock starts when that text appears; if it does not within ``timeout``
        the command is stopped and ``TerminalError`` says it did not start.
        Each of ``keys`` is answered every time its pattern shows up in new
        output (a menu that asks again and again). A main prompt that appears
        first ends the call at once, without ``stop``. A line ending in ``>``
        is never taken for a stray question: menus end in ``> `` too.
        """
        self._drain()
        self._write(line.encode() + b"\r")
        out = _Output()
        heard = False       # any byte at all, even one that cleans away
        mark = 0            # start of the output not yet answered
        found = set()       # indexes of the keys seen since mark
        waiting_for = None
        waiting_since = None
        began = time.monotonic()
        started = began if ready is None else None
        last_data = began
        while True:
            now = time.monotonic()
            chunk = self._read()
            if chunk:
                heard = True
                window, base = out.add(chunk)
                waiting_for = waiting_since = None
                last_data = now = time.monotonic()
                prompt = _ETX_PROMPT.search(window)
                if prompt is not None:
                    self.mode = prompt.group(1)
                    return self._split(out, base + prompt.end())
                if started is None and ready is not None and ready in window:
                    started = now
                fresh = window[max(0, mark - base):]
                found.update(i for i, a in enumerate(keys) if a.pattern in fresh)
            settled = out.ended or (heard and now - last_data >= self.QUIET_S)
            if settled and self._at_main_prompt(out.line.replace("\x03", "")):
                return self._reply(out.text().replace("\x03", ""))
            due = next((a for i, a in enumerate(keys) if i in found), None)
            if due is not None:
                if waiting_for is not due:
                    waiting_for, waiting_since = due, now
                if now - waiting_since >= due.wait_s:
                    self._write(due.reply.encode())
                    mark = out.size
                    found.clear()
                    waiting_for = waiting_since = None
                    continue
            if started is None and now - began >= timeout:
                asked = out.text().replace("\x03", "").strip()[-200:]
                self._stop_listening(stop)
                raise TerminalError(f"{line} did not start: {asked}")
            if started is not None and now - started >= seconds:
                break
            if not chunk:
                time.sleep(0.005)
        self._write(stop.encode())
        # A busy bus can leave a long backlog to read after the stop key: wait
        # while it keeps coming, but never longer than a minute in all.
        now = time.monotonic()
        quiet_until, give_up = now + timeout, now + max(timeout, 60.0)
        while now < quiet_until and now < give_up:
            chunk = self._read()
            now = time.monotonic()
            if not chunk:
                time.sleep(0.005)
                continue
            quiet_until = now + timeout
            window, base = out.add(chunk)
            done = self._prompt_after_output(out, window, base)
            if done is not None:
                return done
        raise TerminalError(f"the terminal did not answer {line}")

    def _split(self, out: _Output, end: int, start: Optional[int] = None) -> Reply:
        """The reply up to the prompt ending at ``end``; text after it is kept.

        With ``start`` the prompt (from ``start``) is moved onto its own line,
        keeping whatever came before it on its line (a cut-off transaction).
        """
        full = out.text()
        head = full[:end] if start is None else full[:start] + "\n" + full[start:end]
        return self._reply(head.replace("\x03", ""), full[end:])

    def _prompt_after_output(self, out: _Output, window: str, base: int) -> Optional[Reply]:
        """The reply, once the output shows a prompt after a stop key.

        The prompt may follow output on the same line (a sniffer stopped
        mid-transaction prints nothing before it), and text may follow a
        prompt's ETX (an IR code received at the prompt). None until a prompt
        shows.
        """
        found = _INLINE_ETX_PROMPT.search(window)
        if found is not None:
            self.mode = found.group(1)
            return self._split(out, base + found.end(), base + found.start())
        found = _INLINE_PROMPT.search(out.line.replace("\x03", ""))
        if found is None:
            return None
        self.mode = found.group(1)
        text = out.text().replace("\x03", "")
        return self._reply(text[:len(text) - len(found.group(0))] + "\n" + found.group(0))

    def _stop_listening(self, stop: str) -> None:
        """Send ``stop`` and wait briefly for the prompt, so the board is not left listening."""
        self._write(stop.encode())
        out = _Output()
        deadline = time.monotonic() + self.QUIET_S * 10
        while time.monotonic() < deadline:
            chunk = self._read()
            if not chunk:
                time.sleep(0.005)
                continue
            window, _ = out.add(chunk)
            if _ETX_PROMPT.search(window) or self._at_main_prompt(out.line.replace("\x03", "")):
                return

    def _abort(self, line: str, tail: str) -> None:
        asked = tail.strip()[-200:]
        self._write(b"x\r")
        try:
            self._read_to_prompt(line, self.timeout)
        except TerminalError:
            pass
        raise TerminalError(f"{line} stopped at an unexpected question: {asked}")

    def _reply(self, text: str, after: str = "") -> Reply:
        """``text`` runs from the echo to the prompt; ``after`` is what followed the prompt."""
        lines = text.split("\n")
        body = lines[1:-1]  # drop the echo and the prompt line
        after = clean(after).strip("\n")
        if after.strip():
            body += after.split("\n")
        error = next((ln.strip() for ln in body if _ERROR.match(ln.strip())), None)
        error, self._pending_error = self._pending_error or error, None
        return Reply("\n".join(body).strip("\n"), self.mode, error)
