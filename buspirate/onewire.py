"""1-Wire mode (``1W0x``)."""

from __future__ import annotations

from typing import List

from .exceptions import ProtocolError
from .mode import Mode

CMD_RESET = 0x02
CMD_READ_BYTE = 0x04
CMD_ROM_SEARCH = 0x08
CMD_ALARM_SEARCH = 0x09

ROM_SEARCH = 0xF0
ROM_READ = 0x33
ROM_MATCH = 0x55
ROM_SKIP = 0xCC

#: The search reply ends with eight 0xFF bytes. Stop well before a runaway
#: stream could fill memory if that marker never comes.
END_OF_SEARCH = b"\xff" * 8
MAX_SEARCH_DEVICES = 256


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

        The firmware answers ``0x01``, then one 8-byte address per device,
        then eight ``0xFF`` bytes to end the list — so an empty bus is
        ``01 ff ff ff ff ff ff ff ff``. An all-zero address (a data line held
        low) is dropped rather than reported as a device.
        """
        self._check_active()
        self.bp.write(bytes([CMD_ALARM_SEARCH if alarm else CMD_ROM_SEARCH]))
        ack = self.bp.read(1)
        if ack != b"\x01":
            raise ProtocolError(f"ROM search was refused: got {ack.hex()} instead of 01")
        found = []
        for _ in range(MAX_SEARCH_DEVICES):
            address = self.bp.read(8)
            if address == END_OF_SEARCH:
                return [a for a in found if a != b"\x00" * 8]
            found.append(address)
        raise ProtocolError(
            f"ROM search sent {MAX_SEARCH_DEVICES} addresses without an end marker"
        )

    def read_rom(self) -> bytes:
        """Read the single device's 8-byte ROM. Only valid with one device."""
        self.reset()
        self.write(bytes([ROM_READ]))
        return self.read(8)
