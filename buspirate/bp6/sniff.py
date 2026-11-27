"""Parsers and listeners for the terminal's I2C and 2WIRE sniffers.

Only the firmware's default output format is used (no ``-q``, ``-r`` or ``-7``):
I2C lines look like ``[ [0xA0]+ [0x00]+ [0x12]-]`` and 2WIRE lines like
``[ 0x30 0x00 0xFF]``. A ``U`` line is a byte the sniffer could not decode.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from .console import Console, TerminalError

MAX_TRANSACTIONS = 200
_I2C_BYTE = re.compile(r"\[0x([0-9A-Fa-f]{2})\]([+-])")
_2W_BYTE = re.compile(r"0x([0-9A-Fa-f]{2})")


def _lines(text: str) -> List[str]:
    return [ln.strip() for ln in text.replace("\r", "\n").split("\n") if ln.strip()]


def parse_i2c(text: str) -> List[Dict[str, Any]]:
    """One dict per transaction line; ``U`` lines and lines without a byte are skipped."""
    out = []  # type: List[Dict[str, Any]]
    for line in _lines(text):
        if line.startswith("U"):
            continue
        found = _I2C_BYTE.findall(line)
        if not found:
            continue
        first = int(found[0][0], 16)
        # "[" not followed by "0x": a start condition; the first one opens the line.
        starts = len(re.findall(r"\[(?!0x)", line))
        out.append({"address": first >> 1, "read": bool(first & 1),
                    "data": " ".join(b.upper() for b, _ in found[1:]),
                    "acks": "".join(a for _, a in found),
                    "complete": line.endswith("]"),
                    "restarts": max(starts - 1, 0)})
    return out


def parse_2wire(text: str) -> List[Dict[str, Any]]:
    out = []  # type: List[Dict[str, Any]]
    for line in _lines(text):
        if line.startswith("U"):
            continue
        found = _2W_BYTE.findall(line)
        if not found:
            continue
        out.append({"data": " ".join(b.upper() for b in found), "complete": line.endswith("]")})
    return out


def _listen(con: Console, seconds: float, parse: Any) -> Dict[str, Any]:
    reply = con.listen("sniff", seconds, "x")
    if reply.error:
        raise TerminalError("sniff failed: %s" % reply.error)
    items = parse(reply.text)
    unknown = sum(1 for ln in _lines(reply.text) if ln.startswith("U"))
    return {"transactions": items[:MAX_TRANSACTIONS], "count": len(items),
            "truncated": len(items) > MAX_TRANSACTIONS, "unknown": unknown,
            "seconds": seconds}


def listen_i2c(con: Console, seconds: float) -> Dict[str, Any]:
    return _listen(con, seconds, parse_i2c)


def listen_2wire(con: Console, seconds: float) -> Dict[str, Any]:
    return _listen(con, seconds, parse_2wire)
