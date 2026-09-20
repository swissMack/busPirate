"""Raw-wire mode (``RAWx``) — bit-level access to arbitrary 2- and 3-wire buses.

Use this for anything that is nearly-but-not-quite SPI or I2C: chips with an
odd number of clock cycles, single-wire protocols, or a bus you are still
reverse-engineering. Nothing here knows about framing, so you drive the clock
and the data lines yourself.
"""

from __future__ import annotations

from typing import List

from .mode import Mode

CMD_START_BIT = 0x02
CMD_STOP_BIT = 0x03
CMD_CS_LOW = 0x04
CMD_CS_HIGH = 0x05
CMD_READ_BYTE = 0x06
CMD_READ_BIT = 0x07
CMD_PEEK_INPUT = 0x08
CMD_CLOCK_TICK = 0x09
CMD_CLOCK_LOW = 0x0A
CMD_CLOCK_HIGH = 0x0B
CMD_DATA_LOW = 0x0C
CMD_DATA_HIGH = 0x0D
SPEED_BASE = 0x60
CONFIG_BASE = 0x80


class RawWire(Mode):
    """Direct control of the clock and data pins."""

    enter_command = 0x05
    banner_prefix = "RAW"
    title = "Raw wire"

    SPEED_5KHZ = 0
    SPEED_50KHZ = 1
    SPEED_100KHZ = 2
    SPEED_400KHZ = 3

    def set_speed(self, speed: int) -> None:
        self._check_active()
        if speed not in (0, 1, 2, 3):
            raise ValueError("speed must be RawWire.SPEED_5KHZ..SPEED_400KHZ")
        self.bp.command_expect_ack(SPEED_BASE | speed)

    def configure(
        self,
        push_pull: bool = True,
        three_wire: bool = False,
        lsb_first: bool = False,
    ) -> None:
        """Set the output driver, wire count and bit order.

        ``push_pull=False`` selects open-drain, which needs external pull-ups.
        """
        self._check_active()
        value = CONFIG_BASE
        if push_pull:
            value |= 0x08
        if three_wire:
            value |= 0x04
        if lsb_first:
            value |= 0x02
        self.bp.command_expect_ack(value)

    # -- framing -----------------------------------------------------------

    def start_bit(self) -> None:
        self._check_active()
        self.bp.command_expect_ack(CMD_START_BIT)

    def stop_bit(self) -> None:
        self._check_active()
        self.bp.command_expect_ack(CMD_STOP_BIT)

    def cs_low(self) -> None:
        self._check_active()
        self.bp.command_expect_ack(CMD_CS_LOW)

    def cs_high(self) -> None:
        self._check_active()
        self.bp.command_expect_ack(CMD_CS_HIGH)

    # -- data --------------------------------------------------------------

    def write(self, data: bytes) -> None:
        """Clock out any number of bytes."""
        self._write_bulk_chunks(data, "raw-wire bulk write")

    def read_byte(self) -> int:
        self._check_active()
        self.bp.write(bytes([CMD_READ_BYTE]))
        return self.bp.read(1)[0]

    def read(self, count: int) -> bytes:
        return bytes(self.read_byte() for _ in range(count))

    def read_bit(self) -> int:
        """Clock in a single bit."""
        self._check_active()
        self.bp.write(bytes([CMD_READ_BIT]))
        return self.bp.read(1)[0] & 1

    def peek_input(self) -> int:
        """Read the data pin without clocking."""
        self._check_active()
        self.bp.write(bytes([CMD_PEEK_INPUT]))
        return self.bp.read(1)[0] & 1

    # -- manual pin wiggling ----------------------------------------------

    def clock_tick(self) -> None:
        self._check_active()
        self.bp.command_expect_ack(CMD_CLOCK_TICK)

    def set_clock(self, high: bool) -> None:
        self._check_active()
        self.bp.command_expect_ack(CMD_CLOCK_HIGH if high else CMD_CLOCK_LOW)

    def set_data(self, high: bool) -> None:
        self._check_active()
        self.bp.command_expect_ack(CMD_DATA_HIGH if high else CMD_DATA_LOW)
