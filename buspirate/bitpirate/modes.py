"""I2C, SPI and UART on the ESP32 Bit Pirate, through its command line.

Each class answers to the same calls as its Bus Pirate namesake in
:mod:`buspirate.i2c`, :mod:`buspirate.spi` and :mod:`buspirate.uart` — the
calls the dashboard's panels make — so a panel never needs to know which
board it is driving. What the Bit Pirate cannot do, it says so, naming where
the feature does live.

Transfers use the firmware's ``[ ... ]`` instructions. Two things about them
differ from a Bus Pirate's and are handled here, not left to the caller
(both from src/Services/I2cService.cpp executeByteCode):

* the first byte after ``[`` is the **7-bit** I2C address, not the 8-bit
  address byte, and ``[addr reg r:N]`` does the repeated start itself;
* nothing reports an ACK or NACK. A read that gets no answer prints no
  bytes, which is caught; a write is checked with ``ping`` beforehand.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Iterable, List, Optional

from ..device import I2C_SPEEDS_MODERN, SPI_SPEEDS
from ..exceptions import (
    BusPirateError,
    ModeError,
    NackError,
    ProtocolError,
    UnsupportedFeatureError,
)
from ..i2c import SCAN_RANGE
from ..uart import UART
from .cli import CliTimeout, Reply, parse_hex_after, parse_scan

if TYPE_CHECKING:  # pragma: no cover
    from ..boards._modes import CliMode

#: Bytes one ``r:N`` can ask for — the firmware keeps N in a uint8_t.
MAX_REPEAT = 255
#: Bytes one I2C read can return: the ESP32 Wire library's buffer.
I2C_MAX_READ = 128
#: Bytes one line can carry as ``0xNN`` tokens and stay under 512 characters.
MAX_WRITE = 96


#: Pins each mode is set to, as answers to its ``config`` questions: the
#: ESP32 Bit Pirate Dock's 10-pin header, which copies the Bus Pirate 6's.
#: Header IO0..IO7 are GPIO15, 16, 17, 18, 10, 11, 12, 13 (the dock's
#: schematic), so I2C sits on IO0/IO1, SPI on IO4..IO7 and UART on IO4/IO5,
#: as on a Bus Pirate 6. The firmware's own s3-devkit defaults put I2C on
#: GPIO6/7, which the dock's header does not carry.
DOCK_PINS: Dict[str, Dict[str, str]] = {
    "I2C": {"SDA GPIO": "15", "SCL GPIO": "16"},
    "SPI": {"MISO GPIO": "10", "CS GPIO": "11", "SCLK GPIO": "12", "MOSI GPIO": "13"},
    "UART": {"TX GPIO number": "10", "RX GPIO number": "11"},
}


def _hex_tokens(data: bytes) -> List[str]:
    return [f"0x{byte:02X}" for byte in data]


def _read_tokens(count: int) -> List[str]:
    tokens = []
    while count > 0:
        step = min(count, MAX_REPEAT)
        tokens.append(f"r:{step}")
        count -= step
    return tokens


class _CliMode:
    """What the three modes share: pull-ups, settings, and being closed."""

    title = ""
    #: The mode's name on the command line and in its prompt.
    name = ""
    #: Its pins, as config answers. See DOCK_PINS.
    pins: Dict[str, str] = {}

    def __init__(self, bp) -> None:
        self.bp = bp
        self.cli = bp.cli
        self._active = True
        # Kept so the dashboard can tell what it last asked for. There are no
        # supplies on this board, so "power" is always False.
        self.peripherals: Dict[str, bool] = {
            "power": False, "pullups": False, "aux": False, "cs": False,
        }

    # -- lifecycle ---------------------------------------------------------

    def close(self) -> None:
        """Nothing to send: the next ``m <mode>`` leaves this one."""
        if not self._active:
            return
        self._active = False
        self.bp._mode_closed(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    @property
    def is_active(self) -> bool:
        return self._active

    def _check_active(self) -> None:
        if not self._active:
            raise ModeError(f"{type(self).__name__} has been closed")

    # -- shared commands ---------------------------------------------------

    def configure_peripherals(
        self,
        power: bool = False,
        pullups: bool = False,
        aux: bool = False,
        cs: bool = False,
    ) -> None:
        """Switch the ESP32's internal pull-ups with ``P`` or ``p``.

        ``power`` is ignored: the Bit Pirate has no supplies to switch, so
        the target needs its own (or a 3V3 pin wired across). AUX and CS are
        Bus Pirate pins with no counterpart here.
        """
        self._check_active()
        if aux or cs:
            raise UnsupportedFeatureError(
                "the Bit Pirate has no AUX or CS peripheral pins to drive. It "
                "is a Bus Pirate v3 and v4 feature."
            )
        self._check(self.cli.command("P" if pullups else "p"))
        self.peripherals = dict(self.peripherals, pullups=pullups)

    def _configure(self, answers: Dict[str, str]) -> None:
        """Run ``config``, answering only what changes; the rest keep theirs.

        The board keeps its settings across mode changes and so does this
        cache, so a dialog runs only when something actually differs.
        """
        self._check_active()
        known = self.bp.settings.setdefault(self.name, {})
        if all(known.get(label) == value for label, value in answers.items()):
            return
        self._check(self.cli.command("config", answers))
        known.update(answers)

    def forget(self, labels: Iterable[str]) -> None:
        """Drop what we last told ``config`` for these questions.

        For a command that changes them on the board itself (``autobaud``
        saves the rate it found), so the next ``_configure`` sets them again.
        """
        known = self.bp.settings.get(self.name, {})
        for label in labels:
            known.pop(label, None)

    # -- any command -------------------------------------------------------

    def run(self, line: str, timeout: float = 5.0) -> List[str]:
        """Run one command line; return what the board said, nothing else.

        The echo and the prompt are left out, and blank lines at either end.
        A refusal (``Unknown command``, ``Cannot execute``, a usage line) is
        raised with the board's own words. A command still running when the
        board has been quiet for ``timeout`` seconds — one waiting for a part
        that never answers — is stopped with Enter, which ends every loop the
        firmware has, and reported.
        """
        self._check_active()
        try:
            reply = self.cli.command(line, timeout=timeout)
        except CliTimeout as exc:
            try:
                self.cli.sync()
            except BusPirateError:
                pass
            raise ModeError(
                f"the Bit Pirate was still busy with {line!r} after {timeout:g} s "
                "without a word, so it was stopped. Is the part connected?"
            ) from exc
        self._check(reply)
        lines = list(reply.lines)
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
        if lines and lines[0].startswith("Usage:"):
            raise ModeError(f"the Bit Pirate said: {lines[0].strip()}")
        return lines

    def start_stream(self, line: str) -> None:
        """Start a command that runs until Enter and hand the port to a stream.

        Everything after the echoed line is the stream's, its first line
        (what the command says it is doing) included. Stopped with
        :meth:`BitPirate.stop_stream`.
        """
        self._check_active()
        self.bp.start_text_stream(line)

    def _check(self, reply: Reply) -> Reply:
        """Refuse a reply given in some other mode, or to a refused command."""
        if reply.mode != self.name:
            raise ModeError(
                f"the Bit Pirate left {self.name} mode (its prompt says "
                f"{reply.mode or 'no mode'}). Was its terminal used meanwhile?"
            )
        for line in reply.lines:
            if line.startswith(("Cannot execute", "Unknown command")):
                raise ModeError(f"the Bit Pirate said: {line.strip()}")
        return reply

    def _instruction(self, tokens: Iterable[str], marker: str) -> bytes:
        reply = self._check(self.cli.command("[" + " ".join(tokens) + "]"))
        return parse_hex_after(reply.lines, marker)


class CliI2C(_CliMode):
    """I2C master through ``scan``, ``ping`` and ``[ ... ]``."""

    title = "I2C"
    name = "I2C"
    pins = DOCK_PINS["I2C"]
    #: A Bus Pirate reports an ACK for every byte written; this board cannot.
    reports_byte_acks = False

    def set_speed(self, speed: int) -> None:
        """The same speed indices as a Bus Pirate: 0 = 5 kHz up to 3 = 400 kHz."""
        if speed not in I2C_SPEEDS_MODERN:
            raise ValueError(f"speed must be one of {sorted(I2C_SPEEDS_MODERN)}")
        self._configure({"Frequency": str(I2C_SPEEDS_MODERN[speed])})

    def scan(self, addresses: Iterable[int] = SCAN_RANGE) -> List[int]:
        self._check_active()
        wanted = set(addresses)
        reply = self._check(self.cli.command("scan", timeout=10.0))
        return [address for address in parse_scan(reply.lines) if address in wanted]

    def ping(self, address: int) -> bool:
        self._check_active()
        reply = self._check(self.cli.command(f"ping 0x{_address(address):02X}"))
        return any("ACK received" in line for line in reply.lines)

    def write(self, address: int, data: bytes = b"") -> None:
        """START, address, ``data``, STOP — after checking the address answers.

        The firmware says nothing about ACKs during a write, so a NACK part
        way through goes unnoticed; only the address is checked, with ping.
        """
        data = bytes(data)
        if len(data) > MAX_WRITE:
            raise ValueError(
                f"the Bit Pirate writes at most {MAX_WRITE} bytes in one I2C "
                "transaction (its command line is 512 characters)"
            )
        if not self.ping(address):
            raise NackError(f"0x{address:02X} did not acknowledge its address")
        self._instruction([f"0x{_address(address):02X}"] + _hex_tokens(data), "I2C Read:")

    def read(self, address: int, count: int) -> bytes:
        """Read ``count`` bytes straight off the device, in 128-byte pieces."""
        if count < 1:
            raise ValueError("count must be >= 1")
        data = bytearray()
        for offset in range(0, count, I2C_MAX_READ):
            size = min(I2C_MAX_READ, count - offset)
            data += self._read_piece(address, b"", size)
        return bytes(data)

    def read_after_write(self, address: int, pointer: bytes, count: int) -> bytes:
        """Write ``pointer``, repeated start, read ``count`` — a register read.

        Longer reads go in 128-byte pieces, each re-pointed at its own
        offset, which is what a register file or EEPROM expects.
        """
        if count < 1:
            raise ValueError("count must be >= 1")
        width = len(pointer)
        base = int.from_bytes(pointer, "big")
        mask = (1 << (8 * width)) - 1
        data = bytearray()
        for offset in range(0, count, I2C_MAX_READ):
            size = min(I2C_MAX_READ, count - offset)
            where = ((base + offset) & mask).to_bytes(width, "big")
            data += self._read_piece(address, where, size)
        return bytes(data)

    def read_register(self, address: int, register: int, count: int = 1) -> bytes:
        return self.read_after_write(address, bytes([register & 0xFF]), count)

    def _read_piece(self, address: int, pointer: bytes, size: int) -> bytes:
        tokens = [f"0x{_address(address):02X}"] + _hex_tokens(pointer) + [f"r:{size}"]
        data = self._instruction(tokens, "I2C Read:")
        if not data:
            raise NackError(
                f"0x{address:02X} did not answer. Check the address, the "
                "wiring and that the bus has pull-ups."
            )
        if len(data) != size:
            raise ProtocolError(f"asked 0x{address:02X} for {size} bytes, got {len(data)}")
        return data


class CliSPI(_CliMode):
    """SPI master through ``[ ... ]``; CS is held for the whole instruction."""

    title = "SPI"
    name = "SPI"
    pins = DOCK_PINS["SPI"]

    def set_speed(self, speed: int) -> None:
        """Speed indices as a Bus Pirate's, where the firmware can do them.

        The Bit Pirate takes whole MHz from 1 to 80, so 1, 2, 4 and 8 MHz
        carry over; the slower settings and 2.6 MHz do not.
        """
        if speed not in SPI_SPEEDS:
            raise ValueError(f"speed must be one of {sorted(SPI_SPEEDS)}")
        hz = SPI_SPEEDS[speed]
        if hz < 1_000_000 or hz % 1_000_000:
            raise UnsupportedFeatureError(
                f"the Bit Pirate sets the SPI clock in whole MHz from 1 to 80, "
                f"so {hz / 1e6:g} MHz is not available. Pick 1, 2, 4 or 8 MHz."
            )
        self._configure({"Frequency (MHz)": str(hz // 1_000_000)})

    def set_mode(self, mode: int, push_pull: bool = True) -> None:
        if mode != 0:
            raise UnsupportedFeatureError(
                "the Bit Pirate's SPI runs in mode 0 only. Other modes are a "
                "Bus Pirate v3 and v4 feature."
            )

    def write_then_read(
        self, data: bytes = b"", read_count: int = 0, assert_cs: bool = True
    ) -> bytes:
        """Write ``data`` then clock in ``read_count`` bytes, CS low throughout."""
        if not assert_cs:
            raise UnsupportedFeatureError(
                "the Bit Pirate always drives CS around a transfer"
            )
        data = bytes(data)
        if len(data) > MAX_WRITE:
            raise ValueError(
                f"the Bit Pirate writes at most {MAX_WRITE} bytes in one SPI "
                "transaction (its command line is 512 characters)"
            )
        if not data and not read_count:
            return b""
        got = self._instruction(_hex_tokens(data) + _read_tokens(read_count), "SPI Read:")
        if len(got) != read_count:
            raise ProtocolError(f"asked for {read_count} SPI bytes, got {len(got)}")
        return got


class CliUART(_CliMode):
    """Send with ``[ ... ]``, watch with ``read``; the config dialog sets the line."""

    title = "UART"
    name = "UART"
    pins = DOCK_PINS["UART"]

    #: The panel's framing choices the firmware can do: data bits and parity.
    FRAMING = {0: ("8", "N"), 1: ("8", "E"), 2: ("8", "O")}

    def set_baudrate(self, baud: int) -> None:
        """The same baud indices as a Bus Pirate's UART."""
        if baud not in UART._BAUDS:
            raise ValueError("baud must be one of UART.BAUD_300..BAUD_115200")
        self._configure({"Baud rate": str(UART._BAUDS[baud])})

    def configure(
        self,
        push_pull: bool = True,
        databits_parity: int = 0,
        stop_bits: int = 1,
        rx_idle_low: bool = False,
    ) -> None:
        if databits_parity not in self.FRAMING:
            raise UnsupportedFeatureError(
                "the Bit Pirate's UART takes 5 to 8 data bits, so 9-bit framing "
                "is a Bus Pirate v3 and v4 feature."
            )
        bits, parity = self.FRAMING[databits_parity]
        self._configure(
            {
                "Data bits (5-8)": bits,
                "Parity (N/E/O)": parity,
                "Stop bits (1 or 2)": str(stop_bits),
                "Inverted?": "y" if rx_idle_low else "n",
            }
        )

    def write(self, data: bytes) -> None:
        """Transmit any number of bytes, in pieces the command line can carry."""
        data = bytes(data)
        for start in range(0, len(data), MAX_WRITE):
            self._instruction(_hex_tokens(data[start : start + MAX_WRITE]), "UART Read:")

    def start_receive(self) -> None:
        """Start ``read``: from here on the port carries the target's bytes.

        The header is read a byte at a time, so nothing the target sends
        straight after it is swallowed. Enter stops it — see
        :meth:`BitPirate.stop_stream`.
        """
        self._check_active()
        self.bp.start_text_stream("read", "UART Read: Streaming")


class CliModeSession(_CliMode):
    """Any Bit Pirate mode described as data (a boards._modes.CliMode)."""

    def __init__(self, bp, spec: "CliMode") -> None:
        super().__init__(bp)
        self.spec = spec
        self.title = spec.title
        self.name = spec.cli_name.upper()
        self.pins = dict(spec.pins)


def _address(address: int) -> int:
    if not 0 <= address <= 0x7F:
        raise ValueError(f"0x{address:X} is not a 7-bit I2C address")
    return address
