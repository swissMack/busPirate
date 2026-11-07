"""The Bit Pirate's Web CLI address, read from what the board says over USB.

The firmware runs its browser terminal *instead of* the USB one (it picks at
power-up), so the only time this app can learn the address is while it is on
USB and the board has joined Wi-Fi. Two replies carry it (v1.8,
Controllers/WifiController.cpp): ``connect`` ends with
``WiFi Web UI: http://<ip> (reset and select WiFi Connect)``, and ``status``
has an ``IP : <ip>`` row, ``0.0.0.0`` until it has joined.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

log = logging.getLogger(__name__)

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


def _memory() -> Path:
    """Where the last real address is kept: the app's window keeps no browser
    storage between launches, so the app keeps it. ``~/BusPirate`` is the
    folder the frozen app already writes its captures under."""
    root = os.environ.get("BUSPIRATE_STATE_DIR") or os.path.expanduser(os.path.join("~", "BusPirate"))
    return Path(root) / "web-cli.json"


def load_last() -> Optional[Dict[str, Any]]:
    """The last real board's address and when it was seen (ms), or None."""
    try:
        data = json.loads(_memory().read_text())
        ip, seen = data["ip"], float(data["seen"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if not isinstance(ip, str) or not re.fullmatch(_IPV4, ip):
        return None
    return {"ip": ip, "seen": seen}


def save_last(ip: str, seen: float) -> None:
    """Remember a real board's address; never fails the reply it came from."""
    path = _memory()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"ip": ip, "seen": seen}))
    except OSError:
        log.debug("could not remember the Web CLI address in %s", path, exc_info=True)


def reply_drops_wifi(lines: Iterable[str]) -> bool:
    """The reply says the board has left (or failed to join) Wi-Fi."""
    return any(line.strip() in _DROPS for line in lines)
