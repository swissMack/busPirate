"""Serial NOR flash on top of :class:`~buspirate.spi.SPI`.

The command set below is the one almost every 25-series SPI flash shares:
Winbond W25Q, Macronix MX25, Micron/ST M25P, SST/Microchip SST25, GigaDevice
GD25. Check the datasheet before trusting it on anything unusual.

Two facts govern everything here:

* **Programming can only clear bits.** A write turns 1s into 0s, never the
  other way, so a region must be erased (back to all ``0xFF``) first.
* **Erase works in blocks**, not bytes — 4 KB sectors typically, and the whole
  chip at once. Erasing is what wears the part out.
"""

from __future__ import annotations

import time
from typing import Callable, Iterator, Optional

from .exceptions import BusPirateError

CMD_WRITE_ENABLE = 0x06
CMD_WRITE_DISABLE = 0x04
CMD_READ_STATUS = 0x05
CMD_READ_DATA = 0x03
CMD_PAGE_PROGRAM = 0x02
CMD_SECTOR_ERASE_4K = 0x20
CMD_BLOCK_ERASE_64K = 0xD8
CMD_CHIP_ERASE = 0xC7
CMD_JEDEC_ID = 0x9F

STATUS_BUSY = 0x01  # WIP: a write or erase is still running
STATUS_WRITE_ENABLED = 0x02  # WEL

PAGE_SIZE = 256
SECTOR_SIZE = 4096
BLOCK_SIZE = 65536

# The firmware buffers at most 4096 bytes in each direction per command.
MAX_TRANSFER = 4096


class FlashError(BusPirateError):
    """The flash chip did not do what it was asked."""


def _address(offset: int) -> bytes:
    if not 0 <= offset <= 0xFFFFFF:
        raise ValueError(f"address 0x{offset:X} is outside the 24-bit range")
    return bytes([(offset >> 16) & 0xFF, (offset >> 8) & 0xFF, offset & 0xFF])


class SPIFlash:
    """Read, erase and program a 25-series serial flash."""

    def __init__(self, spi) -> None:
        self.spi = spi

    # -- identity ----------------------------------------------------------

    def jedec_id(self) -> bytes:
        return self.spi.write_then_read(bytes([CMD_JEDEC_ID]), 3)

    def capacity(self) -> Optional[int]:
        """Size in bytes from the JEDEC ID, or ``None`` if it is not encoded."""
        code = self.jedec_id()[2]
        return 1 << code if 0x10 <= code <= 0x2A else None

    # -- status ------------------------------------------------------------

    def status(self) -> int:
        return self.spi.write_then_read(bytes([CMD_READ_STATUS]), 1)[0]

    @property
    def busy(self) -> bool:
        return bool(self.status() & STATUS_BUSY)

    def wait(self, timeout: float = 120.0, poll: float = 0.005) -> None:
        """Block until the chip finishes. A chip erase really can take a minute."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self.busy:
                return
            time.sleep(poll)
        raise FlashError(
            f"the chip was still busy after {timeout:.0f}s. Either the erase is "
            "unusually slow or the status register is not being read correctly."
        )

    def write_enable(self) -> None:
        """Every program and erase needs this immediately beforehand."""
        self.spi.write_then_read(bytes([CMD_WRITE_ENABLE]), 0)
        if not self.status() & STATUS_WRITE_ENABLED:
            raise FlashError(
                "the chip refused to enable writing. Its WP pin is probably "
                "held low, or the status register is write-protected."
            )

    # -- reading -----------------------------------------------------------

    def read(self, offset: int, length: int) -> bytes:
        """Read any length, in chunks the firmware can buffer."""
        out = bytearray()
        for start in range(offset, offset + length, MAX_TRANSFER):
            size = min(MAX_TRANSFER, offset + length - start)
            out += self.spi.write_then_read(bytes([CMD_READ_DATA]) + _address(start), size)
        return bytes(out)

    def iter_read(
        self, offset: int, length: int, chunk: int = 1024
    ) -> Iterator[bytes]:
        """Read in pieces, so a caller can report progress."""
        for start in range(offset, offset + length, chunk):
            size = min(chunk, offset + length - start)
            yield self.spi.write_then_read(bytes([CMD_READ_DATA]) + _address(start), size)

    # -- erasing -----------------------------------------------------------

    def erase_sector(self, offset: int) -> None:
        """Erase the 4 KB sector containing ``offset``."""
        self.write_enable()
        base = offset - (offset % SECTOR_SIZE)
        self.spi.write_then_read(bytes([CMD_SECTOR_ERASE_4K]) + _address(base), 0)
        self.wait()

    def erase_block(self, offset: int) -> None:
        """Erase the 64 KB block containing ``offset``."""
        self.write_enable()
        base = offset - (offset % BLOCK_SIZE)
        self.spi.write_then_read(bytes([CMD_BLOCK_ERASE_64K]) + _address(base), 0)
        self.wait()

    def erase_chip(self) -> None:
        """Erase everything. Slow, and obviously not reversible."""
        self.write_enable()
        self.spi.write_then_read(bytes([CMD_CHIP_ERASE]), 0)
        self.wait()

    def erase_range(
        self, offset: int, length: int, progress: Optional[Callable] = None
    ) -> int:
        """Erase every 4 KB sector touched by the range. Returns the count.

        Erasure is sector-granular, so this clears whole sectors — including
        any part of them outside the range you asked for.
        """
        first = offset - (offset % SECTOR_SIZE)
        last = offset + length - 1
        sectors = list(range(first, last + 1, SECTOR_SIZE))
        for index, base in enumerate(sectors):
            self.erase_sector(base)
            if progress:
                progress(index + 1, len(sectors), f"erased 0x{base:06X}")
        return len(sectors)

    # -- programming -------------------------------------------------------

    def program_page(self, offset: int, data: bytes) -> None:
        """Program up to one page. Must not cross a page boundary."""
        if not data:
            return
        if len(data) > PAGE_SIZE:
            raise ValueError(f"a page program takes at most {PAGE_SIZE} bytes")
        if (offset % PAGE_SIZE) + len(data) > PAGE_SIZE:
            raise ValueError(
                f"a write at 0x{offset:06X} of {len(data)} bytes would cross a "
                "page boundary, and the chip would wrap it back to the start "
                "of the page instead"
            )
        self.write_enable()
        self.spi.write_then_read(
            bytes([CMD_PAGE_PROGRAM]) + _address(offset) + bytes(data), 0
        )
        self.wait()

    def write(
        self, offset: int, data: bytes, progress: Optional[Callable] = None
    ) -> None:
        """Program any length, split on page boundaries.

        The range must already be erased — see :meth:`erase_range`.
        """
        data = bytes(data)
        written = 0
        while written < len(data):
            position = offset + written
            room = PAGE_SIZE - (position % PAGE_SIZE)
            chunk = data[written : written + room]
            self.program_page(position, chunk)
            written += len(chunk)
            if progress:
                progress(written, len(data), f"wrote 0x{position:06X}")

    def verify(
        self, offset: int, data: bytes, progress: Optional[Callable] = None
    ) -> Optional[int]:
        """Read back and compare. Returns the first differing address, or ``None``."""
        data = bytes(data)
        position = 0
        for chunk in self.iter_read(offset, len(data)):
            expected = data[position : position + len(chunk)]
            if chunk != expected:
                for index, (got, want) in enumerate(zip(chunk, expected)):
                    if got != want:
                        return offset + position + index
                return offset + position + len(chunk)
            position += len(chunk)
            if progress:
                progress(position, len(data), f"verified 0x{offset + position:06X}")
        return None

    def erase_write_verify(
        self, offset: int, data: bytes, progress: Optional[Callable] = None
    ) -> None:
        """The whole safe sequence: erase the sectors, program, then check."""
        self.erase_range(offset, len(data), progress)
        self.write(offset, data, progress)
        bad = self.verify(offset, data, progress)
        if bad is not None:
            raise FlashError(
                f"verification failed at 0x{bad:06X}. The erase may not have "
                "completed, or the chip is write-protected."
            )
