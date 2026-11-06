"""The Bit Pirate's Web CLI address, read from what the board says over USB.

The firmware runs its browser terminal *instead of* the USB one (it picks at
power-up), so the only time this app can learn the address is while it is on
USB and the board has joined Wi-Fi. Two replies carry it (v1.8,
Controllers/WifiController.cpp): ``connect`` ends with
``WiFi Web UI: http://<ip> (reset and select WiFi Connect)``, and ``status``
has an ``IP : <ip>`` row, ``0.0.0.0`` until it has joined.
"""

from __future__ import annotations

import re
from typing import Iterable, Optional

_IPV4 = r"(\d{1,3}(?:\.\d{1,3}){3})"
_PATTERNS = [
    re.compile(r"WiFi Web UI:\s*http://" + _IPV4),
    re.compile(r"^\s*IP\s*:\s*" + _IPV4 + r"\s*$"),
]
_DROPS = ("WiFi: Disconnected.", "WiFi: Connection failed.")


def web_cli_address(lines: Iterable[str]) -> Optional[str]:
    """The station address a reply gives, or None when it gives none."""
    for line in lines:
        for pattern in _PATTERNS:
            match = pattern.search(line)
            if match and match.group(1) != "0.0.0.0":
                return match.group(1)
    return None


def reply_drops_wifi(lines: Iterable[str]) -> bool:
    """The reply says the board has left (or failed to join) Wi-Fi."""
    return any(line.strip() in _DROPS for line in lines)
