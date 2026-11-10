"""Read and write 1-Wire EEPROMs: DS2431 / DS28E07 (128 bytes) and DS2433 / DS24B33 (512 bytes).

Not a sensor, so no catalogue entry. Every function takes the board's 1-Wire mode
object and uses only ``reset()``, ``write(data)`` and ``read(count)``. Only the
memory array is addressed: the DS2431's registers at 0x80 and up (one-time
protection) are out of reach by size.

A write goes through the chip's scratchpad, one row at a time: write the scratchpad,
read it back and compare, then copy it to memory.
"""

from __future__ import annotations

import time
from typing import Dict, Tuple

from ..exceptions import BusPirateError

SKIP_ROM, READ_MEMORY, WRITE_SCRATCHPAD = 0xCC, 0xF0, 0x0F
READ_SCRATCHPAD, COPY_SCRATCHPAD = 0xAA, 0x55
COPY_OK = 0xAA
CHUNK = 256

# family code -> (name, bytes, scratchpad row bytes)
FAMILIES: Dict[int, Tuple[str, int, int]] = {
    0x2D: ("DS2431 / DS28E07", 128, 8),
    0x23: ("DS2433 / DS24B33", 512, 32),
}

PULLUP_HINT = "add a 2.2 kΩ pull-up from DQ to VDD"


class ScratchpadError(BusPirateError):
    """The scratchpad did not read back what was written to it, so nothing was copied."""


class CopyError(BusPirateError):
    """The chip did not confirm the copy from its scratchpad to memory."""


def _family(family: int) -> Tuple[str, int, int]:
    if family not in FAMILIES:
        raise ValueError("family 0x%02X is not a 1-Wire EEPROM this driver knows; known: %s"
                         % (family, ", ".join("0x%02X" % f for f in sorted(FAMILIES))))
    return FAMILIES[family]


def read(ow, family: int, offset: int, length: int) -> bytes:
    """Read ``length`` bytes of memory from ``offset``."""
    name, size, _ = _family(family)
    if offset < 0 or length < 0 or offset + length > size:
        raise ValueError("%s has %d bytes; cannot read %d at offset %d"
                         % (name, size, length, offset))
    out = bytearray()
    while len(out) < length:
        at = offset + len(out)
        n = min(length - len(out), CHUNK)
        ow.reset()
        ow.write(bytes([SKIP_ROM, READ_MEMORY, at & 0xFF, at >> 8]))
        out += ow.read(n)
    return bytes(out)


def write(ow, family: int, offset: int, data: bytes, wait: float = 0.015) -> None:
    """Write ``data`` at ``offset``, one scratchpad row at a time (partial rows are merged)."""
    name, size, row = _family(family)
    data = bytes(data)
    if offset < 0 or offset + len(data) > size:
        raise ValueError("%s has %d bytes; cannot write %d at offset %d"
                         % (name, size, len(data), offset))
    first = offset - offset % row
    for start in range(first, offset + len(data), row):
        lo, hi = max(start, offset), min(start + row, offset + len(data))
        if (lo, hi) == (start, start + row):
            image = bytearray(row)
        else:
            image = bytearray(read(ow, family, start, row))  # a partial row: keep the rest
        image[lo - start:hi - start] = data[lo - offset:hi - offset]
        _write_row(ow, start, bytes(image), row, wait)


def _write_row(ow, start: int, image: bytes, row: int, wait: float) -> None:
    ta = bytes([start & 0xFF, start >> 8])
    ow.reset()
    ow.write(bytes([SKIP_ROM, WRITE_SCRATCHPAD]) + ta + image)
    ow.reset()
    ow.write(bytes([SKIP_ROM, READ_SCRATCHPAD]))
    back = bytes(ow.read(3 + row))
    if back[:2] != ta or back[3:] != image:
        raise ScratchpadError("the scratchpad at 0x%04X read back %s, not what was written; "
                              "nothing was copied" % (start, back.hex(" ")))
    ow.reset()
    ow.write(bytes([SKIP_ROM, COPY_SCRATCHPAD]) + ta + back[2:3])
    time.sleep(wait)
    status = bytes(ow.read(1))
    if status != bytes([COPY_OK]):
        # UNVERIFIED on hardware: the copy needs a strong pull-up on DQ, and the Bus Pirate's
        # own pull-up may not be enough, so a failed copy is reported with that hint.
        raise CopyError("the chip did not confirm the copy to memory at 0x%04X (it sent %s): %s"
                        % (start, status.hex(" ") or "nothing", PULLUP_HINT))


# Reader module, not a catalogue entry (see devices/__init__ _MODULES).
DEVICES: list = []
