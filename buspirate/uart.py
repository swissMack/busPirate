"""UART mode (``ARTx``)."""

from __future__ import annotations

import time

from .exceptions import ProtocolError
from .mode import Mode

CMD_ECHO_START = 0x02
CMD_ECHO_STOP = 0x03
CMD_MANUAL_BAUD = 0x07
CMD_BRIDGE = 0x0F
SPEED_BASE = 0x60
CONFIG_BASE = 0x80

#: How many stray received bytes to set aside while waiting for the ack to
#: "stop listening" before giving up on ever seeing it.
MAX_STRAY_BEFORE_ACK = 4096

#: While a bulk write runs the firmware cannot forward what it receives, and
#: the UART's receive buffer holds about four bytes: send at most this many
#: at a time while listening, so a reply (or a loopback) is not lost.
LISTENING_CHUNK = 4
#: Worst-case bits per character (start, 9 data or 8 + parity, 2 stop).
_BITS_PER_CHAR = 12


class UART(Mode):
    """UART bridge. The Bus Pirate transmits on MOSI and receives on MISO."""

    enter_command = 0x03
    banner_prefix = "ART"
    title = "UART"

    def __init__(self, bp) -> None:
        super().__init__(bp)
        #: True once :meth:`configure` has run. Until then the firmware sits at
        #: 300 baud with its transmit pin not driving the line.
        self.configured = False
        self._echoing = False
        #: Received bytes that arrived while a command was being sent, kept
        #: for :meth:`read_available` rather than mistaken for a reply.
        self._received = bytearray()
        #: The line rate, for pacing writes while listening. The firmware
        #: starts at 300 baud.
        self._baud_hz = self._BAUDS[self.BAUD_300]

    @property
    def listening(self) -> bool:
        """True while received bytes are being forwarded (echo on)."""
        return self._echoing

    def _set_aside_received(self) -> None:
        """While echo is on, received bytes arrive unasked, and may be queued
        ahead of the next command's reply. Move them out of the way first.

        Seen on a v4: with the line floating, noise bytes (0x18) sat in front
        of every ack, so each command read one of them as its reply.
        """
        if not self._echoing:
            return
        waiting = getattr(self.bp.serial, "in_waiting", 0)
        if waiting:
            self._received += self.bp.read(waiting)

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
        self._set_aside_received()
        self.bp.command_expect_ack(SPEED_BASE | baud)
        self._baud_hz = self._BAUDS[baud]

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
        self._set_aside_received()
        self.bp.command_expect_ack(value)
        self.configured = True

    def set_manual_baudrate(self, brg: int) -> None:
        """Set a non-standard rate via the raw BRG divisor (two bytes)."""
        self._check_active()
        if not 0 <= brg <= 0xFFFF:
            raise ValueError("BRG divisor must fit in 16 bits")
        self._set_aside_received()
        self.bp.write(bytes([CMD_MANUAL_BAUD]) + brg.to_bytes(2, "big"))
        self._expect_ack("UART manual baud rate")

    def write(self, data: bytes) -> None:
        """Transmit any number of bytes, chunked into bulk writes.

        While listening, received bytes interleave with the acks, and the
        firmware forwards nothing until a write ends; so write a few bytes at
        a time, wait for them to go out, and set aside whatever came back.
        """
        self._set_aside_received()
        if not self._echoing:
            self._write_bulk_chunks(data, "UART bulk write")
            return
        self._check_active()
        data = bytes(data)
        for start in range(0, len(data), LISTENING_CHUNK):
            chunk = data[start : start + LISTENING_CHUNK]
            self.bp.write(bytes([self._bulk_header(len(chunk))]) + chunk)
            self._acks_among_received(1 + len(chunk), "UART bulk write")
            # Give the bytes time to go out and come back before the next
            # write stops the firmware forwarding them.
            time.sleep(len(chunk) * _BITS_PER_CHAR / self._baud_hz + 0.002)
            self._set_aside_received()

    def _acks_among_received(self, count: int, what: str) -> None:
        """Read ``count`` acks (0x01), setting aside received bytes between them."""
        seen = 0
        for _ in range(count + MAX_STRAY_BEFORE_ACK):
            byte = self.bp.read(1)
            if byte == b"\x01":
                seen += 1
                if seen == count:
                    return
            else:
                self._received += byte
        raise ProtocolError(f"{what}: {seen} of {count} acks among the received bytes")

    def start_receive(self) -> None:
        """Begin echoing received bytes back over the USB link.

        Once started, read the bytes off ``bp.serial`` yourself — the firmware
        streams them unsolicited, so there is no framed response to wait for.
        """
        self._check_active()
        self.bp.command_expect_ack(CMD_ECHO_START)
        self._echoing = True

    def stop_receive(self) -> None:
        """Stop the echo. Bytes still in flight are kept, not taken as the ack."""
        self._check_active()
        self._set_aside_received()
        self.bp.write(bytes([CMD_ECHO_STOP]))
        if self._echoing:
            # Bytes received just before the firmware saw the command still
            # come first; the ack is the first 0x01 after them.
            self._acks_among_received(1, "stopping the UART echo")
        else:
            self._expect_ack("stopping the UART echo")
        self._echoing = False

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
        data = bytes(self._received) + self.bp.serial.read(max(0, max_bytes - len(self._received)))
        self._received = bytearray(data[max_bytes:])
        return data[:max_bytes]
