"""I2C mode (``I2C1``)."""

from __future__ import annotations

from typing import Iterable, List, Sequence

from .exceptions import NackError
from .mode import Mode

CMD_START = 0x02
CMD_STOP = 0x03
CMD_READ_BYTE = 0x04
CMD_ACK = 0x06
CMD_NACK = 0x07
CMD_WRITE_THEN_READ = 0x08
CMD_SNIFFER = 0x0F
SPEED_BASE = 0x60

MAX_WRITE_THEN_READ = 4096


class I2C(Mode):
    """Bit-banged I2C master.

    Addresses are 7-bit throughout; the read/write bit is added internally.
    """

    enter_command = 0x02
    version_string = b"I2C1"

    SPEED_5KHZ = 0
    SPEED_50KHZ = 1
    SPEED_100KHZ = 2
    SPEED_400KHZ = 3

    # -- bus primitives ----------------------------------------------------

    def start(self) -> None:
        """Send a start condition (also used for a repeated start)."""
        self._check_active()
        self.bp.command_expect_ack(CMD_START)

    def stop(self) -> None:
        self._check_active()
        self.bp.command_expect_ack(CMD_STOP)

    def read_byte(self, ack: bool = True) -> int:
        """Read one byte, then send ACK (continue) or NACK (last byte)."""
        self._check_active()
        self.bp.write(bytes([CMD_READ_BYTE]))
        value = self.bp.read(1)[0]
        self.bp.command_expect_ack(CMD_ACK if ack else CMD_NACK)
        return value

    def write_bytes(self, data: bytes) -> List[bool]:
        """Write up to 16 bytes, returning the target's ACK flag per byte.

        ``True`` means the target acknowledged. No start or stop is sent.
        """
        self._check_active()
        data = bytes(data)
        header = self._bulk_header(len(data))
        self.bp.write(bytes([header]) + data)
        self._expect_ack("I2C bulk write")
        # One status byte per written byte: 0x00 = ACK, 0x01 = NACK.
        return [b == 0x00 for b in self.bp.read(len(data))]

    def set_speed(self, speed: int) -> None:
        """Set the bus clock. Use one of the ``SPEED_*`` constants."""
        self._check_active()
        if speed not in (0, 1, 2, 3):
            raise ValueError("speed must be one of I2C.SPEED_5KHZ..SPEED_400KHZ")
        self.bp.command_expect_ack(SPEED_BASE | speed)

    # -- transactions ------------------------------------------------------

    def write(self, address: int, data: bytes = b"") -> None:
        """START, address + W, ``data``, STOP. Raises on any NACK."""
        payload = bytes([_addr_byte(address, read=False)]) + bytes(data)
        self.start()
        try:
            for chunk in _chunked(payload, 16):
                acks = self.write_bytes(chunk)
                if not all(acks):
                    raise NackError(
                        f"no ACK from 0x{address:02X} at byte "
                        f"{acks.index(False)} of a {len(chunk)}-byte chunk"
                    )
        finally:
            self.stop()

    def read(self, address: int, count: int) -> bytes:
        """START, address + R, read ``count`` bytes, STOP."""
        if count < 1:
            raise ValueError("count must be >= 1")
        self.start()
        try:
            if not self.write_bytes(bytes([_addr_byte(address, read=True)]))[0]:
                raise NackError(f"no ACK from 0x{address:02X} on read address")
            # NACK the final byte to tell the target to release the bus.
            return bytes(
                self.read_byte(ack=(i < count - 1)) for i in range(count)
            )
        finally:
            self.stop()

    def write_then_read(
        self, address: int, data: bytes = b"", read_count: int = 0
    ) -> bytes:
        """One atomic write-then-repeated-start-read, handled by the firmware.

        Faster than composing :meth:`write` and :meth:`read` and it holds the
        bus across the repeated start. Needs Bus Pirate firmware v5.1+.
        """
        self._check_active()
        data = bytes(data)
        write_payload = bytes([_addr_byte(address, read=False)]) + data
        if read_count:
            # The firmware appends the read address itself only when we ask it
            # to; send it explicitly as part of the write for a repeated start.
            write_payload += bytes([_addr_byte(address, read=True)])
        if len(write_payload) > MAX_WRITE_THEN_READ or read_count > MAX_WRITE_THEN_READ:
            raise ValueError(f"write_then_read is limited to {MAX_WRITE_THEN_READ} bytes")

        self.bp.write(
            bytes([CMD_WRITE_THEN_READ])
            + len(write_payload).to_bytes(2, "big")
            + read_count.to_bytes(2, "big")
            + write_payload
        )
        status = self.bp.read(1)[0]
        if status != 0x01:
            raise NackError(
                f"write_then_read to 0x{address:02X} failed (status "
                f"0x{status:02X}) — usually a NACK from the target"
            )
        return self.bp.read(read_count) if read_count else b""

    # -- convenience -------------------------------------------------------

    def read_register(self, address: int, register: int, count: int = 1) -> bytes:
        """The common `write register pointer, then read` pattern."""
        return self.write_then_read(address, bytes([register]), count)

    def write_register(self, address: int, register: int, data: bytes) -> None:
        self.write(address, bytes([register]) + bytes(data))

    def scan(self, addresses: Iterable[int] = range(0x08, 0x78)) -> List[int]:
        """Probe each 7-bit address and return those that acknowledge.

        The default range skips the reserved addresses at both ends of the map.
        """
        found = []
        for address in addresses:
            self.start()
            try:
                if self.write_bytes(bytes([_addr_byte(address, read=False)]))[0]:
                    found.append(address)
            finally:
                self.stop()
        return found


def _addr_byte(address: int, read: bool) -> int:
    if not 0x00 <= address <= 0x7F:
        raise ValueError(f"7-bit address out of range: 0x{address:02X}")
    return (address << 1) | (1 if read else 0)


def _chunked(data: bytes, size: int):
    for start in range(0, len(data), size):
        yield data[start : start + size]
