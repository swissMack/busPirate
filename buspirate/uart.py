"""UART mode (``ARTx``)."""

from __future__ import annotations

from .mode import Mode

CMD_ECHO_START = 0x02
CMD_ECHO_STOP = 0x03
CMD_MANUAL_BAUD = 0x07
CMD_BRIDGE = 0x0F
SPEED_BASE = 0x60
CONFIG_BASE = 0x80


class UART(Mode):
    """UART bridge. The Bus Pirate transmits on MOSI and receives on MISO."""

    enter_command = 0x03
    banner_prefix = "ART"
    title = "UART"

    BAUD_300 = 0
    BAUD_1200 = 1
    BAUD_2400 = 2
    BAUD_4800 = 3
    BAUD_9600 = 4
    BAUD_19200 = 5
    BAUD_31250 = 6  # MIDI
    BAUD_38400 = 7
    BAUD_57600 = 8
    BAUD_115200 = 10

    _BAUDS = {
        BAUD_300: 300,
        BAUD_1200: 1200,
        BAUD_2400: 2400,
        BAUD_4800: 4800,
        BAUD_9600: 9600,
        BAUD_19200: 19200,
        BAUD_31250: 31250,
        BAUD_38400: 38400,
        BAUD_57600: 57600,
        BAUD_115200: 115200,
    }

    def set_baudrate(self, baud: int) -> None:
        """Set the line rate. Use one of the ``BAUD_*`` constants."""
        self._check_active()
        if baud not in self._BAUDS:
            raise ValueError("baud must be one of UART.BAUD_300..BAUD_115200")
        self.bp.command_expect_ack(SPEED_BASE | baud)

    def configure(
        self,
        push_pull: bool = True,
        databits_parity: int = 0,
        stop_bits: int = 1,
        rx_idle_low: bool = False,
    ) -> None:
        """Set framing.

        ``databits_parity``: 0 = 8/none, 1 = 8/even, 2 = 8/odd, 3 = 9/none.
        ``stop_bits``: 1 or 2. ``rx_idle_low`` inverts receive polarity.
        """
        self._check_active()
        if databits_parity not in (0, 1, 2, 3):
            raise ValueError("databits_parity must be 0-3")
        if stop_bits not in (1, 2):
            raise ValueError("stop_bits must be 1 or 2")
        value = CONFIG_BASE
        if push_pull:
            value |= 0x10
        value |= databits_parity << 2
        if stop_bits == 2:
            value |= 0x02
        if rx_idle_low:
            value |= 0x01
        self.bp.command_expect_ack(value)

    def set_manual_baudrate(self, brg: int) -> None:
        """Set a non-standard rate via the raw BRG divisor (two bytes)."""
        self._check_active()
        if not 0 <= brg <= 0xFFFF:
            raise ValueError("BRG divisor must fit in 16 bits")
        self.bp.write(bytes([CMD_MANUAL_BAUD]) + brg.to_bytes(2, "big"))
        self._expect_ack("UART manual baud rate")

    def write(self, data: bytes) -> None:
        """Transmit any number of bytes, chunked into bulk writes."""
        self._write_bulk_chunks(data, "UART bulk write")

    def start_receive(self) -> None:
        """Begin echoing received bytes back over the USB link.

        Once started, read the bytes off ``bp.serial`` yourself — the firmware
        streams them unsolicited, so there is no framed response to wait for.
        """
        self._check_active()
        self.bp.command_expect_ack(CMD_ECHO_START)

    def stop_receive(self) -> None:
        self._check_active()
        self.bp.command_expect_ack(CMD_ECHO_STOP)

    def start_bridge(self) -> None:
        """Start the transparent UART bridge.

        **There is no way out in software.** The firmware documents this as
        "reset to exit" — you have to unplug the Bus Pirate. Everything this
        library does afterwards will fail until you do.
        """
        self._check_active()
        self.bp.write(bytes([CMD_BRIDGE]))
        self.bp.streaming = True

    def read_available(self, max_bytes: int = 256) -> bytes:
        """Drain whatever the echo has delivered so far. May return ``b""``."""
        self._check_active()
        return self.bp.serial.read(max_bytes)
