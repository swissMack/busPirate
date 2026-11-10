"""Read 24xx I2C EEPROMs and the MB85RC256V FRAM.

Not a sensor, so no catalogue entry: ``read`` takes the board's I2C mode object
and uses only ``write(address, data)`` and ``read(address, count)``, which every
board has. The caller must name the part — a wrong size silently wraps, and
there is no safe autodetect.

Addressing: parts up to 24C16 take a 1-byte pointer; the 24C04/08/16 (and the
2-byte 24M01/24M02) carry the bits above the pointer in the device address
(``0x50 | block``), so a read must not run across a block boundary in one go.
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

# part -> (bytes, address bytes)
SIZES: Dict[str, Tuple[int, int]] = {
    "24C01": (128, 1),
    "24C02": (256, 1),
    "24C04": (512, 1),
    "24C08": (1024, 1),
    "24C16": (2048, 1),
    "24C32": (4096, 2),
    "24C64": (8192, 2),
    "24C128": (16384, 2),
    "24C256": (32768, 2),
    "24C512": (65536, 2),
    "24M02": (262144, 2),
    "MB85RC256V": (32768, 2),
}


def read(i2c, address: int, part: str, offset: int = 0,
         length: Optional[int] = None, chunk: int = 256) -> bytes:
    """Read ``length`` bytes (default: to the end) from ``offset``.

    ``address`` is the 7-bit base address (0x50 + A0-A2). ``chunk`` is the most
    bytes asked of the board per read; pass the board's ``max_read``.
    """
    key = part.upper()
    if key not in SIZES:
        raise ValueError("unknown part %r; known: %s" % (part, ", ".join(sorted(SIZES))))
    size, addr_bytes = SIZES[key]
    if length is None:
        length = size - offset
    if offset < 0 or length < 0 or offset + length > size:
        raise ValueError("%s has %d bytes; cannot read %d from offset %d" % (key, size, length, offset))
    if chunk < 1:
        raise ValueError("chunk must be at least 1")

    block_size = 1 << (8 * addr_bytes)  # bytes one device address reaches
    out = bytearray()
    pos = offset
    end = offset + length
    while pos < end:
        block, within = divmod(pos, block_size)
        n = min(chunk, end - pos, block_size - within)
        pointer = within.to_bytes(addr_bytes, "big")
        i2c.write(address | block, pointer)
        out += i2c.read(address | block, n)
        pos += n
    return bytes(out)
