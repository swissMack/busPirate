"""IR receive and send through the terminal's ``irrx``, ``irtx`` and bus-syntax writes."""

from __future__ import annotations

import re
from typing import Any, Dict

from ..devices import ir
from .console import Answer, Console, TerminalError

SENSORS = {"38d": "36-40 kHz demodulator on IO5",
           "56d": "56 kHz demodulator on IO7",
           "38b": "38 kHz barrier sensor on IO3"}
MAX_FRAMES = 50
#: The terminal's line limit: longer lines are cut silently (research 3b §9.1).
MAX_LINE = 256
_PARSED = re.compile(r"Parsed AIR packet: modulation frequency (\d+)kHz, (\d+) MARK/SPACE pairs")
_TX = re.compile(r"TX: 0x([0-9A-Fa-f]+)\.16")
_FIRMWARE_ERRORS = ("Unable to find", "Too many MARK/SPACE", "Error parsing AIR", "PIO TX timeout",
                    "Nothing to do")


def receive(con: Console, seconds: float, sensor: str) -> Dict[str, Any]:
    """Listen on ``sensor`` for ``seconds``; each frame comes back as aIR text and decoded."""
    reply = con.listen("irrx -s %s" % sensor, seconds, "x", ready="Listening for IR packets",
                       keys=[Answer("space for next", " ", 0)])
    if reply.error:
        raise TerminalError("irrx failed: %s" % reply.error)
    found = ir.parse_air(reply.text)
    frames = []
    for f in found[:MAX_FRAMES]:
        air = ir.to_air(f["carrier_khz"], f["durations"])
        frames.append({"carrier_khz": f["carrier_khz"], "durations": f["durations"], "air": air,
                       "decoded": ir.decode(f["durations"]),
                       "resendable": len("irtx " + air) <= MAX_LINE})
    return {"frames": frames, "count": len(found), "truncated": len(found) > MAX_FRAMES,
            "sensor": sensor, "seconds": seconds}


def send_air(con: Console, air: str) -> Dict[str, Any]:
    """Send one aIR packet (no ``;``) with ``irtx``."""
    line = "irtx " + air
    if len(line) > MAX_LINE:
        raise ValueError("the line 'irtx ...' would be %d characters and the terminal keeps only "
                         "%d, so the packet would be cut: use ir-send-nec or ir-send-rc5 for a "
                         "NEC or RC5 code" % (len(line), MAX_LINE))
    reply = con.command(line, timeout=5.0)
    text = reply.text
    parsed = _PARSED.search(text)
    if parsed and re.search(r"done\s*$", text, re.M):
        return {"sent": True, "carrier_khz": int(parsed.group(1)), "pairs": int(parsed.group(2))}
    why = next((ln.strip() for ln in text.split("\n")
                if ln.strip().startswith(_FIRMWARE_ERRORS)), None)
    raise TerminalError("irtx failed: %s" % (why or reply.error or text.strip()[-200:] or "no reply"))


def send_code(con: Console, value: int) -> Dict[str, Any]:
    """Send one NEC or RC5 value as bus syntax; ``tx`` is the value the firmware echoed."""
    reply = con.command("> 0x%04X" % value, timeout=5.0)
    echoed = _TX.search(reply.text)
    if not echoed:
        raise TerminalError("the IR send was not confirmed (no 'TX:' line): %s"
                            % (reply.error or reply.text.strip()[-200:] or "no reply"))
    return {"sent": True, "tx": "0x" + echoed.group(1).upper()}
