"""Read and write 25xx SPI EEPROMs and SPI FRAMs (FM25, MB85RS).

Not a sensor, so no catalogue entry: every function takes the board's SPI mode
object and uses only ``write_then_read(data, count)``. The caller must name the
part; a wrong size silently wraps and there is no safe autodetect.
"""

from __future__ import annotations

import re
import time
from typing import Dict, Tuple

from ..exceptions import BusPirateError

READ, WRITE, WREN, RDSR = 0x03, 0x02, 0x06, 0x05
BUSY = 0x01
BLOCK_PROTECT = 0x0C

# part -> (bytes, address bytes, write-page bytes); FRAMs write in one go (page = size).
PARTS: Dict[str, Tuple[int, int, int]] = {
    "25010": (128, 1, 16), "25020": (256, 1, 16), "25040": (512, 1, 16),
    "25080": (1024, 2, 16), "25160": (2048, 2, 16), "25320": (4096, 2, 32),
    "25640": (8192, 2, 32), "25128": (16384, 2, 64), "25256": (32768, 2, 64),
    "25512": (65536, 2, 128), "25M01": (131072, 3, 256), "25M02": (262144, 3, 256),
    "FM25L16B": (2048, 2, 2048), "MB85RS64V": (8192, 2, 8192),
    "FM25V02": (32768, 2, 32768), "MB85RS256": (32768, 2, 32768),
    "FM25V10": (131072, 3, 131072),
}

_MAKER = re.compile(r"(?:25(?:LC|AA|C)?|AT25|CAT25|M95)(\w+)")


class ProtectedError(BusPirateError):
    """The chip's block-protect bits are set, so a write would be ignored."""


class WriteTimeout(BusPirateError):
    """The chip did not finish its internal write in time."""


def normalize(part: str) -> str:
    """The generic key for a part name: 25LC256, AT25256 and M95256 are all 25256."""
    name = str(part).strip().upper()
    if name not in PARTS:
        match = _MAKER.fullmatch(name)
        if match:
            name = "25" + match.group(1)
    if name not in PARTS:
        raise ValueError("unknown part %r; known: %s" % (part, ", ".join(sorted(PARTS))))
    return name


def status(spi) -> int:
    return spi.write_then_read(bytes([RDSR]), 1)[0]


def _command(opcode: int, key: str, offset: int) -> bytes:
    """Opcode and address; the 512-byte part carries A8 in opcode bit 3."""
    _, width, _ = PARTS[key]
    if width == 1 and PARTS[key][0] == 512 and offset >= 256:
        opcode |= 0x08
    return bytes([opcode]) + (offset % (1 << (8 * width)) if width == 1
                              else offset).to_bytes(width, "big")


def read(spi, part: str, offset: int, length: int) -> bytes:
    key = normalize(part)
    size = PARTS[key][0]
    if offset < 0 or length < 0 or offset + length > size:
        raise ValueError("%s has %d bytes; cannot read %d at offset %d" % (key, size, length, offset))
    out = bytearray()
    for start in range(offset, offset + length, 512):
        n = min(512, offset + length - start)
        out += spi.write_then_read(_command(READ, key, start), n)
    return bytes(out)


def write(spi, part: str, offset: int, data: bytes, timeout: float = 0.025) -> None:
    """Write ``data`` page by page, WREN before each and RDSR polled until the chip is idle."""
    key = normalize(part)
    size, _, page = PARTS[key]
    data = bytes(data)
    if offset < 0 or offset + len(data) > size:
        raise ValueError("%s has %d bytes; cannot write %d at offset %d"
                         % (key, size, len(data), offset))
    current = status(spi)
    if current & BLOCK_PROTECT:
        raise ProtectedError("the chip is write-protected (status 0x%02X, block-protect bits "
                             "set): clear them or the write is ignored" % current)
    pos, end = offset, offset + len(data)
    while pos < end:
        n = min(end - pos, page - pos % page, 512 - 4)
        spi.write_then_read(bytes([WREN]), 0)
        spi.write_then_read(_command(WRITE, key, pos) + data[pos - offset:pos - offset + n], 0)
        deadline = time.monotonic() + timeout
        while status(spi) & BUSY:
            if time.monotonic() > deadline:
                raise WriteTimeout("the chip was still busy %.0f ms after a page write"
                                   % (timeout * 1000))
        pos += n


# Reader module, not a catalogue entry (see devices/__init__ _MODULES).
DEVICES: list = []
