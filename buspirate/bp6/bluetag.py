"""JTAG and SWD pin finding through the Bus Pirate 6's ``bluetag`` command.

``bluetag jtag -c <n>`` / ``bluetag swd -c <n>`` run the scan without any
prompt and return to the prompt by themselves (research doc section 5). The
scan cannot be interrupted, so the console timeout is sized from the number of
pin permutations. The ``-d`` flag (no pin pulsing) is JTAG only.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from .console import TerminalError

RANGES = {"jtag": (4, 8), "swd": (2, 8)}
PROTOCOLS = tuple(RANGES)
NOT_FOUND_HINT = "check VREF and GND, and that each IO wire is on a separate pad"

_JTAG_PINS = ("TDI", "TDO", "TCK", "TMS", "TRST")
_SWD_PINS = ("SWDIO", "SWCLK")
_PIN = re.compile(r"([A-Z]+)=(IO\d+|N/A)")
_DEVICE = re.compile(r"\[ Device (\d+) \]\s+(0x[0-9A-Fa-f]+)"
                     r"(?:\s+\(mfg: '([^']*)', part: (0x[0-9A-Fa-f]+), ver: (0x[0-9A-Fa-f]+)\))?")


def check_channels(protocol: Any, channels: Any) -> None:
    """Refuse a request the firmware would refuse; raises ValueError."""
    if protocol not in RANGES:
        raise ValueError("protocol must be one of %s, not %r" % (", ".join(PROTOCOLS), protocol))
    low, high = RANGES[protocol]
    if isinstance(channels, bool) or not isinstance(channels, int) or not low <= channels <= high:
        raise ValueError("%s needs %d to %d channels (IO0 upward), not %r"
                         % (protocol.upper(), low, high, channels))


def scan_seconds(protocol: str, channels: int) -> float:
    n = channels
    permutations = n * (n - 1) * (n - 2) * (n - 3) if protocol == "jtag" else n * (n - 1)
    return 10 + permutations * 0.06


def scan(con: Any, protocol: str, channels: int, pulsing: bool = True) -> Dict[str, Any]:
    check_channels(protocol, channels)
    line = "bluetag %s -c %d" % (protocol, channels)
    if protocol == "jtag" and not pulsing:
        line += " -d"
    reply = con.command(line, timeout=scan_seconds(protocol, channels))
    if reply.error:
        raise TerminalError(reply.error)
    text = reply.text
    names = _JTAG_PINS if protocol == "jtag" else _SWD_PINS
    pinout = {}  # type: Dict[str, Any]
    marker = text.find("[  Pinout  ]")
    if marker >= 0:
        found = dict(_PIN.findall(text[marker:text.find("\n", marker) if "\n" in text[marker:] else None]))
        pinout = {n: (None if found.get(n, "N/A") == "N/A" else found[n]) for n in names if n in found}
    devices = []  # type: List[Dict[str, Any]]
    for m in _DEVICE.finditer(text):
        devices.append({"idcode": m.group(2), "manufacturer": m.group(3),
                        "part": m.group(4), "version": m.group(5)})
    out = {"found": bool(pinout), "pinout": pinout, "devices": devices, "channels": channels}
    if not pinout:
        if "No " not in text or "devices found" not in text:
            raise TerminalError("bluetag gave no result: %s" % text.strip()[-200:])
        out["hint"] = NOT_FOUND_HINT
    return out
