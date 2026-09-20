"""1-Wire mode (``1W0x``)."""

from __future__ import annotations

from typing import List

from .mode import Mode

CMD_RESET = 0x02
CMD_READ_BYTE = 0x04
CMD_ROM_SEARCH = 0x08
CMD_ALARM_SEARCH = 0x09

ROM_SEARCH = 0xF0
ROM_READ = 0x33
ROM_MATCH = 0x55
ROM_SKIP = 0xCC


class OneWire(Mode):
    """1-Wire master on the MOSI pin (needs an external pull-up to Vpu)."""

    enter_command = 0x04
    banner_prefix = "1W0"
    title = "1-Wire"

    def reset(self) -> None:
        """Send a reset pulse and wait for the presence pulse."""
        self._check_active()
        self.bp.command_expect_ack(CMD_RESET)

    def read_byte(self) -> int:
        self._check_active()
        self.bp.write(bytes([CMD_READ_BYTE]))
        return self.bp.read(1)[0]

    def read(self, count: int) -> bytes:
        return bytes(self.read_byte() for _ in range(count))

    def write(self, data: bytes) -> None:
        """Write any number of bytes, chunked into bulk writes."""
        self._write_bulk_chunks(data, "1-Wire bulk write")

    def search_rom(self, alarm: bool = False) -> List[bytes]:
        """Run the firmware's ROM search and return the 8-byte addresses.

        The firmware streams a fixed 32 slots of 8 bytes; unused slots come
        back as all-``0xFF`` and are dropped here.
        """
        self._check_active()
        self.bp.write(bytes([CMD_ALARM_SEARCH if alarm else CMD_ROM_SEARCH]))
        raw = self.bp.read(8 * 32)
        addresses = [raw[i : i + 8] for i in range(0, len(raw), 8)]
        return [a for a in addresses if a != b"\xff" * 8 and a != b"\x00" * 8]

    def read_rom(self) -> bytes:
        """Read the single device's 8-byte ROM. Only valid with one device."""
        self.reset()
        self.write(bytes([ROM_READ]))
        return self.read(8)
