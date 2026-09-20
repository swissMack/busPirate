"""Banner matching shared by the transport and every mode.

The firmware answers mode changes with a four- or five-character banner whose
final character is a protocol *version* digit: the wiki documents the exit
response as ``BBIOx``, not ``BBIO1``. Comparing against a literal would break
the moment a device answers ``BBIO2``, so all banner checks go through here.
"""

from __future__ import annotations

import re
from typing import Tuple

from .exceptions import ModeError

BANNER_BITBANG = "BBIO"
BANNER_I2C = "I2C"
BANNER_SPI = "SPI"
BANNER_UART = "ART"
BANNER_1WIRE = "1W0"
BANNER_RAWWIRE = "RAW"

# Every banner is its prefix plus one version digit.
BANNER_LENGTHS = {
    BANNER_BITBANG: 5,
    BANNER_I2C: 4,
    BANNER_SPI: 4,
    BANNER_UART: 4,
    BANNER_1WIRE: 4,
    BANNER_RAWWIRE: 4,
}


def banner_length(prefix: str) -> int:
    return BANNER_LENGTHS[prefix]


def match_banner(data: bytes, prefix: str, context: str) -> int:
    """Check ``data`` against ``prefix`` + a digit, returning the digit.

    Raises :class:`ModeError` naming what came back instead, because a wrong
    banner nearly always means the device is mid-stream from a previous
    command rather than that the mode is unsupported.
    """
    expected = re.compile(rf"^{re.escape(prefix)}(\d)$".encode())
    match = expected.match(data)
    if match is None:
        raise ModeError(
            f"{context}: expected a {prefix}<version> banner, got {data!r}. "
            "The device is usually still draining an earlier reply — "
            "reconnect to resynchronise."
        )
    return int(match.group(1))
