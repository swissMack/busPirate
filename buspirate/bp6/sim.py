"""A read-only T=0 link to a SIM card through the terminal's HDUART mode.

The board must already be in ``m hduart -b 9600 -d 8 -p even -s 2 -l listen``
(IO0 = RXTX, IO2 = RST; listen mode drives the line only while a byte goes
out). :meth:`SimLink.open` starts the card clock on IO1, resets the card,
reads its ATR and leaves the async print (``[``) on; :meth:`SimLink.close`
sends ``]`` and ``g 1``.

Each command header goes out as one terminal line of five bytes
(``0xA0 0xA4 0x00 0x00 0x02``), each data block as one more line after the
card's procedure byte. The card's bytes print as lower-case ``0x%02x`` after
the prompt, never inside the ``TX:`` echo (research
``2026-11-12-bp6-sim-t0.md``).

Read-only by construction: :meth:`SimLink.command` refuses any instruction
outside SELECT, READ BINARY, READ RECORD, GET RESPONSE and STATUS before
anything is sent. VERIFY is reachable only through :meth:`SimLink.pin_status`
(no data: attempts left) and :meth:`SimLink.verify_pin_once`.
"""

from __future__ import annotations

import re
import time
from typing import Any, Dict, Optional, Tuple

from ..devices.smartcard import parse_atr
from . import smartcard
from .console import TerminalError

GSM_CLA = 0xA0
UICC_CLA = 0x00

SELECT = 0xA4
READ_BINARY = 0xB0
READ_RECORD = 0xB2
GET_RESPONSE = 0xC0
STATUS = 0xF2
VERIFY = 0x20
#: The only instructions :meth:`SimLink.command` sends.
ALLOWED = frozenset((SELECT, READ_BINARY, READ_RECORD, GET_RESPONSE, STATUS))

DF_GSM = 0x7F20
NULL = 0x60
#: Data bytes per terminal line (5 characters each keeps a line under 256).
LINE_BYTES = 48
#: Added to the card's work waiting time for the USB and terminal round trip.
LATENCY_S = 0.5
#: How long each read for the card's next bytes lasts.
SLICE_S = 0.02
#: GET RESPONSE rounds followed for one command (61 xx can chain).
MAX_RESPONSES = 8

_TX_ROW = re.compile(r"^\s*TX:")
_ECHO_TOKEN = re.compile(r"(?<!\S)(?:0x[0-9A-Fa-f]{2}|[0-9]{1,3})(?!\S)")
_CONTINUATION = re.compile(r"^\s+((?:0x[0-9A-Fa-f]{2}|[0-9]{1,3})\s*)*$")


def verify_line(cla: int) -> str:
    """The terminal line that sends a VERIFY with a PIN (CHV1, 8 bytes).

    It is the header only: the PIN goes on the next line, after the card's
    procedure byte. Task 4 declares this line as the commit's change line.
    """
    return "0x%02X 0x20 0x00 0x01 0x08" % cla


def _line(data: bytes) -> str:
    return " ".join("0x%02X" % b for b in data)


def _split_echo(text: str) -> Tuple[int, str]:
    """``text`` (a reply) split into the number of values in its ``TX:`` echo
    and the text after it (what the card sent, printed after the prompt)."""
    lines = text.split("\n")
    start = next((i for i, ln in enumerate(lines) if _TX_ROW.match(ln)), None)
    if start is None:
        return 0, text
    count = len(_ECHO_TOKEN.findall(lines[start].split(":", 1)[1]))
    end = start + 1
    while end < len(lines) and lines[end][:1].isspace() and _CONTINUATION.match(lines[end]):
        count += len(_ECHO_TOKEN.findall(lines[end]))
        end += 1
    return count, "\n".join(lines[end:])


def received_bytes(text: str) -> bytes:
    """The bytes the card sent in ``text``: the ``0x%02x`` tokens after the
    ``TX:`` echo (a digit-only echo such as ``0x00`` looks the same)."""
    return bytes(int(h, 16) for h in smartcard._BYTE.findall(_split_echo(text)[1]))


def _sw_text(sw: int) -> str:
    return "%04X" % sw


class SimLink:
    """A T=0 session with a SIM. Open it with :meth:`open`; use it as a
    context manager or call :meth:`close`. Class ``A0`` (GSM) by default;
    set ``cla`` to ``0x00`` for the UICC commands."""

    def __init__(self, con: Any, wwt_s: float = 1.0 + LATENCY_S) -> None:
        self.con = con
        self.wwt_s = wwt_s
        self.cla = GSM_CLA
        self.atr = None  # type: Optional[Dict[str, Any]]
        self.atr_bytes = b""
        self.clock_hz = None  # type: Optional[int]
        self._closed = False
        self._text = ""   # what the card printed since the last line sent
        self._taken = 0   # bytes of it already used

    # -- open and close --------------------------------------------------------

    @classmethod
    def open(cls, con: Any, clock_hz: int, wwt_s: Optional[float] = None,
             atr_wait_s: float = 0.5) -> "SimLink":
        """Clock the card on IO1, reset it and read its ATR; leave the clock and
        the async print running. On any failure ``]`` and ``g 1`` are sent and
        the error is raised.

        ``wwt_s`` defaults to the T=0 work waiting time with WI = 10
        (960 x 10 x 372 / clock: 1 s at 3.5712 MHz) plus :data:`LATENCY_S`.
        """
        link = cls(con)
        try:
            clock, off_baud = smartcard.start_clock(con, clock_hz)
            link.clock_hz = clock["actual_hz"]
            if off_baud:
                raise TerminalError(off_baud)
            data = smartcard.reset_card(con, atr_wait_s)
            if not data:
                raise TerminalError(smartcard.NO_ANSWER)
            try:
                atr = parse_atr(data)
            except ValueError as exc:
                raise TerminalError("the card's answer to reset is not valid: %s" % exc) from None
            if atr["convention"] != "direct":
                raise TerminalError("the card uses the inverse convention, which HDUART cannot read")
            if 0 not in atr["protocols"]:
                raise TerminalError("the card does not offer T=0 (it offers T=%s)"
                                    % ",".join(str(p) for p in atr["protocols"]))
            link.atr, link.atr_bytes = atr, data
        except BaseException as exc:  # noqa: B902  (re-raised after the cleanup)
            link._closed = True
            first = smartcard.stop(con, exc)
            raise first  # type: ignore[misc]
        if wwt_s is None:
            wwt_s = 960 * 10 * 372 / float(link.clock_hz or clock_hz) + LATENCY_S
        link.wwt_s = wwt_s
        return link

    def close(self) -> None:
        """Async print off (``]``) and clock off (``g 1``), each even when the
        other fails; the first error is raised. A second close sends nothing."""
        if self._closed:
            return
        self._closed = True
        first = smartcard.stop(self.con)
        if first is not None:
            raise first

    def _abandon(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    def __enter__(self) -> "SimLink":
        return self

    def __exit__(self, kind, value, trace) -> None:
        if kind is None:
            self.close()
        else:
            self._abandon()

    # -- the line --------------------------------------------------------------

    def _send(self, data: bytes, secret: bool = False) -> None:
        """Write ``data`` as terminal lines; the card's answer is read after."""
        for i in range(0, len(data), LINE_BYTES):
            chunk = data[i:i + LINE_BYTES]
            what = "the PIN block" if secret else _line(chunk)
            try:
                reply = self.con.command(_line(chunk))
            except TerminalError:
                if secret:
                    raise TerminalError("the terminal did not answer %s" % what) from None
                raise
            if reply.error:
                raise TerminalError("'%s' failed: %s" % (what, reply.error))
            count, after = _split_echo(reply.text)
            if count != len(chunk):
                raise TerminalError("the board did not send %s: %s"
                                    % (what, "no TX echo" if secret else
                                       reply.text.strip()[-200:] or "no reply"))
            self._text, self._taken = after, 0

    def _take(self, count: int) -> bytes:
        """The card's next ``count`` bytes, waiting up to ``wwt_s`` for each."""
        last = time.monotonic()
        seen = len(smartcard._BYTE.findall(self._text))
        while True:
            found = smartcard._BYTE.findall(self._text)
            if len(found) > seen:
                seen, last = len(found), time.monotonic()
            if len(found) - self._taken >= count:
                out = bytes(int(h, 16) for h in found[self._taken:self._taken + count])
                self._taken += count
                return out
            if time.monotonic() - last > self.wwt_s:
                raise TerminalError("the card stopped answering (nothing for %.1f s): check that "
                                    "it is still inserted" % self.wwt_s)
            self._text += self.con.collect(SLICE_S)

    def _exchange(self, cla: int, ins: int, p1: int, p2: int, data: bytes,
                  le: Optional[int], secret: bool = False) -> Tuple[bytes, int]:
        """One T=0 command: header, procedure bytes, data, status word."""
        expect = 0 if data else (le or 0)
        p3 = len(data) if data else expect % 256
        self._send(bytes((cla, ins, p1, p2, p3)))
        remaining = bytes(data)
        got = bytearray()
        while True:
            pb = self._take(1)[0]
            if pb == NULL:
                continue
            if pb & 0xF0 in (0x60, 0x90):
                return bytes(got), pb << 8 | self._take(1)[0]
            if pb in (ins, ins ^ 0xFF):
                one = pb != ins
                if remaining:
                    block, remaining = (remaining[:1], remaining[1:]) if one else (remaining, b"")
                    self._send(block, secret)
                    continue
                if len(got) < expect:
                    got += self._take(1 if one else expect - len(got))
                    continue
            raise TerminalError("the card sent an unexpected procedure byte 0x%02X" % pb)

    def _command(self, cla: int, ins: int, p1: int, p2: int, data: bytes = b"",
                 le: Optional[int] = None, secret: bool = False) -> Tuple[bytes, int]:
        if self._closed:
            raise TerminalError("the SIM link is closed")
        for name, value in (("CLA", cla), ("P1", p1), ("P2", p2)):
            if not 0 <= value <= 0xFF:
                raise ValueError("%s must be a byte, not %r" % (name, value))
        if len(data) > 255:
            raise ValueError("at most 255 data bytes")
        if le is not None and not 1 <= le <= 256:
            raise ValueError("Le must be 1 to 256")
        try:
            out, sw = self._exchange(cla, ins, p1, p2, bytes(data), None if data else le, secret)
            if sw >> 8 == 0x6C and not data:
                out, sw = self._exchange(cla, ins, p1, p2, b"", (sw & 0xFF) or 256)
            response = bytearray(out)
            for _ in range(MAX_RESPONSES):
                if sw >> 8 not in (0x61, 0x9F):
                    break
                more, sw = self._exchange(cla, GET_RESPONSE, 0, 0, b"", (sw & 0xFF) or 256)
                response += more
            return bytes(response), sw
        except BaseException:  # noqa: B902  (re-raised: the link is unusable now)
            self._abandon()
            raise

    # -- the read-only commands --------------------------------------------------

    def command(self, cla: int, ins: int, p1: int, p2: int, data: bytes = b"",
                le: Optional[int] = None) -> Tuple[bytes, int]:
        """Send one command; return the response data and the status word.

        Handles the T=0 procedure bytes (INS, INS XOR FF, ``60``), follows
        ``61 xx`` / ``9F xx`` with GET RESPONSE and repeats once with Le = xx
        on ``6C xx``. Raises ``ValueError``, before anything is sent, for an
        instruction outside :data:`ALLOWED`; a card that stops answering
        raises ``TerminalError`` and closes the link.
        """
        if ins not in ALLOWED:
            raise ValueError("instruction 0x%02X is not in the read-only allow-list" % (ins & 0xFF))
        return self._command(cla, ins, p1, p2, data, le)

    def select(self, fid: int) -> Tuple[bytes, int]:
        """SELECT by file ID; the response (GSM response data or UICC FCP) and the SW."""
        p2 = 0x00 if self.cla == GSM_CLA else 0x04
        return self.command(self.cla, SELECT, 0x00, p2, fid.to_bytes(2, "big"))

    def read_binary(self, length: int, offset: int = 0) -> Tuple[bytes, int]:
        """READ BINARY of the selected transparent EF."""
        return self.command(self.cla, READ_BINARY, offset >> 8, offset & 0xFF, le=length)

    def read_record(self, number: int, length: int) -> Tuple[bytes, int]:
        """READ RECORD ``number`` (absolute mode) of the selected linear EF."""
        return self.command(self.cla, READ_RECORD, number, 0x04, le=length)

    # -- the PIN -------------------------------------------------------------------

    def pin_status(self) -> Dict[str, Any]:
        """Whether the PIN (CHV1) is needed and how many attempts are left.

        Class ``00`` (UICC): a VERIFY with no data (``63 Cx``: x attempts
        left; ``90 00``: not needed or already verified; ``69 83``/``69 84``:
        blocked). Class ``A0`` (GSM, which has no such VERIFY): the GET
        RESPONSE of SELECT DF_GSM (byte 14 b8: CHV1 disabled; byte 19 low
        nibble: attempts left). That route leaves DF_GSM selected.
        """
        if self.cla != GSM_CLA:
            _, sw = self._command(self.cla, VERIFY, 0x00, 0x01)
            out = {"needed": None, "attempts_left": None, "blocked": None,
                   "source": "VERIFY", "sw": _sw_text(sw)}  # type: Dict[str, Any]
            if sw & 0xFFF0 == 0x63C0:
                out.update(needed=True, attempts_left=sw & 0x0F, blocked=sw & 0x0F == 0)
            elif sw == 0x9000:
                out.update(needed=False, blocked=False)
            elif sw in (0x6983, 0x6984):
                out.update(needed=True, attempts_left=0, blocked=True)
            return out
        data, sw = self.select(DF_GSM)
        out = {"needed": None, "attempts_left": None, "blocked": None,
               "source": "DF_GSM", "sw": _sw_text(sw)}
        if sw == 0x9000 and len(data) >= 19:
            attempts = data[18] & 0x0F
            out.update(needed=not data[13] & 0x80, attempts_left=attempts, blocked=attempts == 0)
        return out

    def verify_pin_once(self, pin: str) -> Dict[str, Any]:
        """Present ``pin`` (CHV1) exactly once: ASCII digits padded with ``FF``
        to 8 bytes, P2 = 01. Never retried. The PIN is never in the result
        or in an error. The header is :func:`verify_line`."""
        if not isinstance(pin, str) or not re.fullmatch(r"[0-9]{4,8}", pin):
            raise ValueError("a SIM PIN is 4 to 8 digits")
        block = pin.encode("ascii").ljust(8, b"\xff")
        _, sw = self._command(self.cla, VERIFY, 0x00, 0x01, block, secret=True)
        out = {"verified": sw == 0x9000, "attempts_left": None, "blocked": False,
               "sw": _sw_text(sw)}  # type: Dict[str, Any]
        if sw & 0xFFF0 == 0x63C0:
            out.update(attempts_left=sw & 0x0F, blocked=sw & 0x0F == 0)
        elif sw in (0x9840, 0x6983, 0x6984):
            out.update(attempts_left=0, blocked=True)
        return out
