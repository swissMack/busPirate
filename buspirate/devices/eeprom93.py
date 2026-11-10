"""Read and write 93Cxx Microwire EEPROMs (93C46 ... 93C86, also 93LC and 93AA) over SPI.

Microwire is SPI mode 0 with an **active-high** CS and no byte framing: a
command is a start bit (1), two opcode bits, the address, then data. The SPI
engine can only send whole bytes, so a command is right-aligned in whole bytes
and padded with leading zeros, which the chip ignores before the start bit.

Every function takes the board's SPI mode object (``write_then_read`` only).
The caller sets CS active-high first (``set_cs_active_high(True)``).

# UNVERIFIED on hardware: the byte alignment below, and the CS polarity.
"""

from __future__ import annotations

import re
import time
from typing import Dict, Optional, Tuple

from ..exceptions import BusPirateError

# part -> (bytes, address bits sent in x8, address bits sent in x16)
PARTS: Dict[str, Tuple[int, int, int]] = {
    "93C46": (128, 7, 6), "93C56": (256, 9, 8), "93C66": (512, 9, 8),
    "93C76": (1024, 11, 10), "93C86": (2048, 11, 10),
}

_NAME = re.compile(r"93(?:LC|AA|C)(\d\d)([ABC]?)")


class WriteTimeout(BusPirateError):
    """The chip did not finish its internal write in time."""


def normalize(part: str, org: Optional[int] = None) -> str:
    """The generic key for a part name: 93LC46B and 93AA46 are both 93C46.

    An ``A`` suffix is x8 only and ``B`` is x16 only: a clash with ``org`` raises.
    """
    name = str(part).strip().upper()
    match = _NAME.fullmatch(name)
    key = "93C" + match.group(1) if match else name
    if key not in PARTS:
        raise ValueError("unknown part %r; known: %s" % (part, ", ".join(sorted(PARTS))))
    if org is not None and org not in (8, 16):
        raise ValueError("org must be 8 or 16, not %r" % (org,))
    suffix = match.group(2) if match else ""
    if org is not None and ((suffix == "A" and org != 8) or (suffix == "B" and org != 16)):
        raise ValueError("%s is %s only, but org is %d"
                         % (name, "x8" if suffix == "A" else "x16", org))
    return key


def frame(bits: str) -> bytes:
    """Right-align a bit string in whole bytes, padding with leading zeros."""
    count = -(-len(bits) // 8) * 8
    return int(bits, 2).to_bytes(count // 8, "big")


def _bits(value: int, width: int) -> str:
    return format(value, "0%db" % width)


def _geometry(part: str, org: int) -> Tuple[str, int, int, int]:
    key = normalize(part, org)
    size, x8, x16 = PARTS[key]
    return key, size, (x8 if org == 8 else x16), (1 if org == 8 else 2)


def _check_range(key: str, size: int, unit: int, org: int, offset: int, length: int,
                 verb: str) -> None:
    if offset < 0 or length < 0 or offset + length > size:
        raise ValueError("%s has %d bytes; cannot %s %d at offset %d"
                         % (key, size, verb, length, offset))
    if unit == 2 and (offset % 2 or length % 2):
        raise ValueError("in x16 the offset and length must be even (words), not %d and %d"
                         % (offset, length))


def read(spi, part: str, org: int, offset: int, length: int) -> bytes:
    """One READ transaction. Mode 0 samples the dummy 0 first, so read one extra byte and
    shift the whole read left by one bit. # UNVERIFIED on hardware."""
    key, size, abits, unit = _geometry(part, org)
    _check_range(key, size, unit, org, offset, length, "read")
    if not length:
        return b""
    command = frame("110" + _bits(offset // unit, abits))
    raw = spi.write_then_read(command, length + 1)
    if len(raw) != length + 1:
        raise BusPirateError("asked for %d bytes, got %d" % (length + 1, len(raw)))
    return bytes(((raw[i] << 1) | (raw[i + 1] >> 7)) & 0xFF for i in range(length))


def write(spi, part: str, org: int, offset: int, data: bytes, timeout: float = 0.02) -> None:
    """EWEN, then one WRITE per word (x16) or byte (x8), polling until ready, then EWDS."""
    key, size, abits, unit = _geometry(part, org)
    data = bytes(data)
    _check_range(key, size, unit, org, offset, len(data), "write")
    spi.write_then_read(frame("10011" + "0" * (abits - 2)), 0)
    try:
        for pos in range(0, len(data), unit):
            word = int.from_bytes(data[pos:pos + unit], "big")
            spi.write_then_read(
                frame("101" + _bits((offset + pos) // unit, abits) + _bits(word, 8 * unit)), 0)
            deadline = time.monotonic() + timeout
            while spi.write_then_read(b"", 1)[0] == 0x00:  # DO low: still busy
                if time.monotonic() > deadline:
                    raise WriteTimeout("the chip was still busy %.0f ms after a write"
                                       % (timeout * 1000))
    finally:
        try:
            spi.write_then_read(frame("10000" + "0" * (abits - 2)), 0)
        except BusPirateError:
            pass


# Reader module, not a catalogue entry (see devices/__init__ _MODULES).
DEVICES: list = []
