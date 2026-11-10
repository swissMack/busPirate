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

import time
from typing import Dict, Optional, Tuple

from ..exceptions import BusPirateError, NackError

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

# Smallest write-page size across makers; a smaller page is always safe.
PAGES: Dict[str, int] = {
    "24C01": 8, "24C02": 8,
    "24C04": 16, "24C08": 16, "24C16": 16,
    "24C32": 32, "24C64": 32,
    "24C128": 64, "24C256": 64,
    "24C512": 128,
    "24M02": 256,
    "MB85RC256V": 32768,
}


class WriteTimeout(BusPirateError):
    """The chip did not finish its internal write in time."""


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

def _ack_poll(i2c, address: int, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while True:
        try:
            i2c.write(address, b"")
            return
        except NackError:
            if time.monotonic() >= deadline:
                raise WriteTimeout("the chip at 0x%02X was still busy %.0f ms after a write"
                                   % (address, timeout * 1000))
            time.sleep(0.0005)


def write(i2c, address: int, part: str, offset: int, data: bytes, chunk: int = 64,
          timeout: float = 0.025) -> None:
    """Write ``data`` at ``offset``, never across a page or a block, ACK-polling after each.

    ``chunk`` is the most data bytes per request (the board's ``max_write`` less the
    address and pointer bytes). Raises ``WriteTimeout`` if the chip stays busy.
    """
    key = part.upper()
    if key not in SIZES:
        raise ValueError("unknown part %r; known: %s" % (part, ", ".join(sorted(SIZES))))
    size, addr_bytes = SIZES[key]
    data = bytes(data)
    if offset < 0 or offset + len(data) > size:
        raise ValueError("%s has %d bytes; cannot write %d at offset %d"
                         % (key, size, len(data), offset))
    if chunk < 1:
        raise ValueError("chunk must be at least 1")
    page = PAGES[key]
    block_size = 1 << (8 * addr_bytes)
    pos, end = offset, offset + len(data)
    while pos < end:
        block, within = divmod(pos, block_size)
        n = min(chunk, end - pos, block_size - within, page - pos % page)
        pointer = within.to_bytes(addr_bytes, "big")
        i2c.write(address | block, pointer + data[pos - offset:pos - offset + n])
        _ack_poll(i2c, address | block, timeout)
        pos += n


# Reader modules, not catalogue entries (see devices/__init__ _MODULES).
DEVICES: list = []
