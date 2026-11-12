"""Smart card answer to reset through the terminal's HDUART mode.

The board must already be in ``m hduart`` (IO0 = RXTX, IO2 = RST). The card's
clock comes from a PWM on IO1, started here after the mode is set (``m``
switches every PWM off). In HDUART bus syntax ``}`` holds RST low, ``[``
prints received bytes as they arrive, ``{`` releases RST and ``]`` stops the
printing. ``r`` gives up too fast for an ATR and is never used. Received
bytes print as ``0x%02x `` after the prompt (research 3c).
"""

from __future__ import annotations

import re
from typing import Any, Dict

from ..devices.smartcard import parse_atr
from . import signals
from .console import TerminalError

CLOCK_PIN = 1
NO_ANSWER = "no answer from the card: check that it is inserted and the wiring"
#: Exactly the firmware's ``0x%02x `` format: lower-case hex, nothing glued on.
_BYTE = re.compile(r"(?<!\S)0x([0-9a-f]{2})(?!\S)")


def _bus(con: Any, line: str, expect: str) -> str:
    reply = con.command(line)
    if reply.error:
        raise TerminalError("'%s' failed: %s" % (line, reply.error))
    if expect not in reply.text:
        raise TerminalError("'%s' did not answer %r: %s"
                            % (line, expect, reply.text.strip()[-200:] or "no reply"))
    return reply.text


def read_atr(con: Any, clock_hz: int, wait_s: float) -> Dict[str, Any]:
    """Clock the card, pulse RST and return the bytes it answers, decoded.

    Always sends ``]`` and ``g 1`` at the end, even when a step fails.
    """
    done = False
    try:
        clock = signals.pwm_start(con, CLOCK_PIN, clock_hz, 50)
        _bus(con, "}", "RST LOW")
        _bus(con, "[", "UART OPEN")
        text = _bus(con, "{", "RST HIGH")
        text += "\n" + con.collect(wait_s)
        done = True
    finally:
        for line in ("]", "g %d" % CLOCK_PIN):
            try:
                con.command(line)
            except Exception:
                if done:
                    raise
    data = bytes(int(h, 16) for h in _BYTE.findall(text))
    out = {"bytes": " ".join("%02X" % b for b in data), "atr": None,
           "clock_hz": clock["actual_hz"]}  # type: Dict[str, Any]
    if not data:
        out["error"] = NO_ANSWER
        return out
    try:
        out["atr"] = parse_atr(data)
    except ValueError as exc:
        out["error"] = str(exc)
    return out
