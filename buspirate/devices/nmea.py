"""Decode GGA and RMC sentences from an NMEA GPS (UART, 9600 8N1 by default)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

KMH_PER_KNOT = 1.852


def _checksum_ok(line: str) -> bool:
    body, _, given = line[1:].partition("*")
    if not given:
        return False
    calc = 0
    for ch in body:
        calc ^= ord(ch)
    try:
        return calc == int(given.strip()[:2], 16)
    except ValueError:
        return False


def _coord(value: str, hemi: str) -> Optional[float]:
    """ddmm.mmmm / dddmm.mmmm plus N/S/E/W to signed decimal degrees."""
    if not value or not hemi:
        return None
    try:
        dot = value.index(".")
        deg = int(value[:dot - 2])
        minutes = float(value[dot - 2:])
    except ValueError:
        return None
    result = deg + minutes / 60.0
    return -result if hemi.upper() in ("S", "W") else result


def _time(value: str) -> Optional[str]:
    if len(value) < 6 or not value[:6].isdigit():
        return None
    return "%s:%s:%s" % (value[0:2], value[2:4], value[4:6])


def _int(value: str) -> Optional[int]:
    try:
        return int(value)
    except ValueError:
        return None


def _float(value: str) -> Optional[float]:
    try:
        return float(value)
    except ValueError:
        return None


def _field(f: List[str], i: int) -> str:
    return f[i] if i < len(f) else ""


def parse(text: str) -> List[Dict[str, Any]]:
    """Every GGA/RMC sentence in ``text``; lines with a bad checksum come back
    as ``{"sentence": ..., "error": "checksum"}``. Other lines are ignored."""
    out: List[Dict[str, Any]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line.startswith("$"):
            continue
        kind = line[3:6]
        if kind not in ("GGA", "RMC"):
            continue
        if not _checksum_ok(line):
            out.append({"sentence": line, "error": "checksum"})
            continue
        f = line[1:].split("*")[0].split(",")
        if kind == "GGA":
            out.append({
                "type": "GGA",
                "time": _time(_field(f, 1)),
                "latitude": _coord(_field(f, 2), _field(f, 3)),
                "longitude": _coord(_field(f, 4), _field(f, 5)),
                "fix_quality": _int(_field(f, 6)),
                "satellites": _int(_field(f, 7)),
                "altitude_m": _float(_field(f, 9)),
            })
        else:
            knots = _float(_field(f, 7))
            out.append({
                "type": "RMC",
                "time": _time(_field(f, 1)),
                "valid": _field(f, 2) == "A",
                "latitude": _coord(_field(f, 3), _field(f, 4)),
                "longitude": _coord(_field(f, 5), _field(f, 6)),
                "speed_kmh": None if knots is None else knots * KMH_PER_KNOT,
                "date": _field(f, 9) or None,
            })
    return out

# Reader modules, not catalogue entries (see devices/__init__ _MODULES).
DEVICES: list = []
