"""What the About page says: this app, and who made the boards it drives.

The connected board's own details (name, firmware, port) come from the
session's status, which the page already has; this is only what never
changes while the app runs.
"""

from __future__ import annotations

import platform
from typing import Any, Dict

from .. import __version__

REPO = "https://github.com/swissMack/busPirate"

CREDITS = [
    {
        "name": "Bus Pirate",
        "by": "Dangerous Prototypes / Where Labs",
        "what": "the Bus Pirate v3, v4 and 6 hardware and firmware",
        "url": "https://buspirate.com/",
    },
    {
        "name": "ESP32 Bit Pirate",
        "by": "geo-tp",
        "what": "the firmware that turns an ESP32-S3 into a Bit Pirate",
        "url": "https://github.com/geo-tp/ESP32-Bit-Pirate",
    },
]


def about() -> Dict[str, Any]:
    return {
        "name": "busPirate",
        "version": __version__,
        "python": platform.python_version(),
        "repo": REPO,
        "credits": CREDITS,
    }
