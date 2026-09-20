"""SPI mode (``SPIx``)."""

from __future__ import annotations

from .exceptions import ProtocolError
from .mode import Mode

CMD_CS_LOW = 0x02
CMD_CS_HIGH = 0x03
CMD_WRITE_THEN_READ = 0x04
CMD_WRITE_THEN_READ_NO_CS = 0x05
SPEED_BASE = 0x60
CONFIG_BASE = 0x80

MAX_WRITE_THEN_READ = 4096


class SPI(Mode):
    """SPI master. The Bus Pirate drives CS, CLK and MOSI; MISO is sampled."""

    enter_command = 0x01
    banner_prefix = "SPI"
    title = "SPI"

    SPEED_30KHZ = 0
    SPEED_125KHZ = 1
    SPEED_250KHZ = 2
    SPEED_1MHZ = 3
    SPEED_2MHZ = 4
    SPEED_2_6MHZ = 5
    SPEED_4MHZ = 6
    SPEED_8MHZ = 7

    _SPEEDS = {
        SPEED_30KHZ: 30_000,
        SPEED_125KHZ: 125_000,
        SPEED_250KHZ: 250_000,
        SPEED_1MHZ: 1_000_000,
        SPEED_2MHZ: 2_000_000,
        SPEED_2_6MHZ: 2_600_000,
        SPEED_4MHZ: 4_000_000,
        SPEED_8MHZ: 8_000_000,
    }

    # -- configuration -----------------------------------------------------

    def set_speed(self, speed: int) -> None:
        """Set the clock rate. Use one of the ``SPEED_*`` constants."""
        self._check_active()
        if speed not in self.bp.profile.spi_speeds:
            raise ValueError("speed must be one of SPI.SPEED_30KHZ..SPEED_8MHZ")
        self.bp.command_expect_ack(SPEED_BASE | speed)

    def configure(
        self,
        push_pull: bool = True,
        clock_idle_high: bool = False,
        clock_edge_falling: bool = True,
        sample_end: bool = False,
    ) -> None:
        """Set output driver and clock polarity/phase.

        ``push_pull=False`` selects open-drain outputs, which need external
        pull-ups. The CPOL/CPHA pairs map as: mode 0 = idle low + falling edge,
        mode 1 = idle low + rising, mode 2 = idle high + rising, mode 3 =
        idle high + falling.
        """
        self._check_active()
        value = CONFIG_BASE
        for flag, bit in (
            (push_pull, 0x08),
            (clock_idle_high, 0x04),
            (clock_edge_falling, 0x02),
            (sample_end, 0x01),
        ):
            if flag:
                value |= bit
        self.bp.command_expect_ack(value)

    def set_mode(self, mode: int, push_pull: bool = True) -> None:
        """Configure clock polarity and phase by SPI mode number (0-3)."""
        if mode not in (0, 1, 2, 3):
            raise ValueError("SPI mode must be 0, 1, 2 or 3")
        cpol = bool(mode & 0b10)
        cpha = bool(mode & 0b01)
        # On the Bus Pirate the edge bit means "output on the falling edge",
        # which is the idle-low, CPHA=0 case and its CPOL-inverted twin.
        self.configure(
            push_pull=push_pull,
            clock_idle_high=cpol,
            clock_edge_falling=(cpol == cpha),
        )

    # -- chip select -------------------------------------------------------

    def cs_low(self) -> None:
        """Assert chip select (active low)."""
        self._check_active()
        self.bp.command_expect_ack(CMD_CS_LOW)

    def cs_high(self) -> None:
        """Release chip select."""
        self._check_active()
        self.bp.command_expect_ack(CMD_CS_HIGH)

    def select(self) -> "_ChipSelect":
        """Context manager that holds CS low for the duration of a block."""
        return _ChipSelect(self)

    # -- transfers ---------------------------------------------------------

    def transfer_bulk(self, data: bytes) -> bytes:
        """Clock out 1-16 bytes and return what MISO carried back.

        CS is left exactly as it was; wrap this in :meth:`select` yourself.
        """
        self._check_active()
        data = bytes(data)
        header = self._bulk_header(len(data))
        self.bp.write(bytes([header]) + data)
        self._expect_ack("SPI bulk transfer")
        return self.bp.read(len(data))

    def transfer(self, data: bytes) -> bytes:
        """Full-duplex transfer of any length, chunked into bulk writes."""
        out = bytearray()
        for start in range(0, len(data), 16):
            out += self.transfer_bulk(data[start : start + 16])
        return bytes(out)

    def write_then_read(
        self, data: bytes = b"", read_count: int = 0, assert_cs: bool = True
    ) -> bytes:
        """Write ``data`` then clock in ``read_count`` bytes in one command.

        With ``assert_cs`` the firmware takes CS low for the whole transaction
        and releases it afterwards — the right call for most flash and sensor
        chips. Both lengths are capped at 4096 bytes by the firmware.
        """
        self._check_active()
        data = bytes(data)
        if len(data) > MAX_WRITE_THEN_READ or read_count > MAX_WRITE_THEN_READ:
            raise ValueError(f"write_then_read is limited to {MAX_WRITE_THEN_READ} bytes")
        command = CMD_WRITE_THEN_READ if assert_cs else CMD_WRITE_THEN_READ_NO_CS
        self.bp.write(
            bytes([command])
            + len(data).to_bytes(2, "big")
            + read_count.to_bytes(2, "big")
            + data
        )
        status = self.bp.read(1)[0]
        if status != 0x01:
            raise ProtocolError(
                f"SPI write_then_read rejected (status 0x{status:02X}); "
                "the byte counts most likely exceed the firmware's buffer"
            )
        return self.bp.read(read_count) if read_count else b""


class _ChipSelect:
    def __init__(self, spi: SPI) -> None:
        self.spi = spi

    def __enter__(self) -> SPI:
        self.spi.cs_low()
        return self.spi

    def __exit__(self, *exc_info) -> None:
        self.spi.cs_high()
