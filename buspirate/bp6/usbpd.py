"""USB-PD plank (AP33772S at I2C 0x52) through the terminal's ``usbpd`` command.

The board must already be in ``m i2c``. ``usbpd status`` prints the source,
the measurements and the source's offers (PDOs); ``usbpd request -p <n>
[-v <mV>] [-i <mA>]`` asks for one (``-v`` only for PPS/AVS: a fixed PDO is
always requested at its own voltage); ``usbpd reset`` sends a PD hard reset.
The firmware flags none of its failures as errors (no BEL), so the text is
parsed: a ``Failed ...`` line, an invalid index or an out-of-range value
raises ``TerminalError``.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from .console import TerminalError

_FIELDS = (
    ("vbus_mv", re.compile(r"VBUS voltage\s*:\s*(-?\d+)\s*mV")),
    ("vbus_ma", re.compile(r"VBUS current\s*:\s*(-?\d+)\s*mA")),
    ("requested_mv", re.compile(r"Requested V\s*:\s*(-?\d+)\s*mV")),
    ("requested_ma", re.compile(r"Requested I\s*:\s*(-?\d+)\s*mA")),
    ("temperature_c", re.compile(r"Temperature\s*:\s*(-?\d+)\s*C")),
)
_TEXTS = (
    ("source", re.compile(r"^\s*Source\s*:\s*(.+?)\s*$", re.M)),
    ("cc_line", re.compile(r"^\s*CC line\s*:\s*(.+?)\s*$", re.M)),
    ("data_role", re.compile(r"^\s*Data role\s*:\s*(.+?)\s*$", re.M)),
    ("derating", re.compile(r"^\s*De-rating\s*:\s*(.+?)\s*$", re.M)),
)
_PDO = re.compile(r"^\s*(PDO\s+(\d+)\s+\((SPR|EPR)\s+(Fixed|PPS|AVS)\):\s*(.*?))\s*$", re.M)
_FIXED = re.compile(r"^(\d+)\s*mV,\s*(\d+)-(\d+)\s*mA")
_RANGE = re.compile(r"^(.*?)\s+to\s+(\d+)\s*mV,\s*(\d+)-(\d+)\s*mA")
_RESULT = re.compile(r"PD request (\w+)")
_NEGOTIATED = re.compile(r"Negotiated voltage\s*:\s*(\d+)\s*mV")
_REFUSED = re.compile(r"^\s*(Failed\b.*|Invalid PDO index.*|Requested (?:voltage|current)\b"
                      r".*out of range.*)$", re.M)


def _pdo(match: Any) -> Optional[Dict[str, Any]]:
    index, domain, kind, rest = int(match.group(2)), match.group(3), match.group(4), match.group(5)
    if kind == "Fixed":
        m = _FIXED.match(rest)
        if not m:
            return None
        low = high = int(m.group(1))
        min_ma, max_ma = int(m.group(2)), int(m.group(3))
    else:
        m = _RANGE.match(rest)
        if not m:
            return None
        high = int(m.group(2))
        numbers = re.findall(r"\d+", m.group(1))
        # ">=3300" -> 3300; ">3300 and <=5000" -> 5000 (the lowest it may be asked for);
        # "reserved" -> the top.
        low = int(numbers[-1]) if numbers else high
        min_ma, max_ma = int(m.group(3)), int(m.group(4))
    return {"index": index, "domain": domain, "type": kind, "min_mv": low, "max_mv": high,
            "min_ma": min_ma, "max_ma": max_ma}


def parse_status(text: str) -> Dict[str, Any]:
    """The source, the measurements (None when absent) and the offered PDOs."""
    out = {}  # type: Dict[str, Any]
    for key, pattern in _TEXTS:
        m = pattern.search(text)
        out[key] = m.group(1) if m else None
    for key, pattern in _FIELDS:
        m = pattern.search(text)
        out[key] = int(m.group(1)) if m else None
    pdos = []  # type: List[Dict[str, Any]]
    lines = []  # type: List[str]
    for m in _PDO.finditer(text):
        pdo = _pdo(m)
        if pdo is not None:
            pdos.append(pdo)
            lines.append(m.group(1))
    out["pdos"] = pdos
    out["pdo_lines"] = lines
    return out


def _run(con: Any, line: str, timeout: float = 3.0) -> str:
    reply = con.command(line, timeout=timeout)
    if reply.error:
        raise TerminalError("'%s' failed: %s" % (line, reply.error))
    refused = _REFUSED.search(reply.text)
    if refused:
        raise TerminalError("'%s': %s" % (line, refused.group(1).strip()))
    return reply.text


def status(con: Any) -> Dict[str, Any]:
    return parse_status(_run(con, "usbpd status"))


def request(con: Any, pdo: int, mv: Optional[int], ma: Optional[int]) -> Dict[str, Any]:
    """Ask the source for PDO ``pdo``; ``mv`` only for a PPS/AVS PDO."""
    line = "usbpd request -p %d" % pdo
    if mv is not None:
        line += " -v %d" % mv
    if ma is not None:
        line += " -i %d" % ma
    text = _run(con, line, timeout=8.0)
    m = _RESULT.search(text)
    if not m:
        raise TerminalError("'%s' gave no result: %s" % (line, text.strip()[-200:] or "no reply"))
    st = parse_status(text)
    negotiated = _NEGOTIATED.search(text)
    return {"pdo": pdo, "result": m.group(1), "accepted": m.group(1) == "accepted",
            "negotiated_mv": int(negotiated.group(1)) if negotiated else None,
            "vbus_mv": st["vbus_mv"], "vbus_ma": st["vbus_ma"],
            "requested_mv": st["requested_mv"], "requested_ma": st["requested_ma"]}


def reset(con: Any) -> Dict[str, Any]:
    """Send a PD hard reset: the source drops back to 5 V."""
    text = _run(con, "usbpd reset")
    if "hard reset sent" not in text:
        raise TerminalError("'usbpd reset' gave no result: %s" % (text.strip()[-200:] or "no reply"))
    return {"sent": True}
