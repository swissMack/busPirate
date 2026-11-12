"""A simulated Bus Pirate 6: its BPIO2 port and its terminal port.

Built from what the real board did on 2026-10-14 (see the design spec), so
the dashboard and the tests can run with no hardware. It answers only what
the driver asks; it is not a firmware emulator.
"""

from __future__ import annotations

import re
import struct
import time
from typing import List

import flatbuffers

from .bp6.bpio import ConfigurationRequest as _CR
from .bp6.bpio import ConfigurationResponse as _CRS
from .bp6.bpio import DataRequest as _DR
from .bp6.bpio import DataResponse as _DRS
from .bp6.bpio import RequestPacket as _RP
from .bp6.bpio import ResponsePacket as _RS
from .bp6.bpio import StatusResponse as _ST
from .bp6.bpio.RequestPacketContents import RequestPacketContents
from .bp6.bpio.ResponsePacketContents import ResponsePacketContents
from .bp6.framing import FrameReader, cobs_decode, frame
from .devices.aht20 import crc8
from .devices.eeprom24 import PAGES as _EEPROM_PAGES, SIZES as _EEPROM_SIZES
from .devices.eeprom25 import PARTS as _SPI_PARTS
from .devices.eeprom93 import PARTS as _MW_PARTS
from .devices.onewire_eeprom import FAMILIES as _OW_FAMILIES
from .simulator import FakeFlash

BINMODES = {1: "SUMP logic analyzer", 2: "BPIO2 flatbuffer interface",
            3: "Arduino CH32V003 SWIO", 4: "Follow along logic analyzer",
            5: "Legacy Binary Mode for Flashrom and AVRdude", 6: "IRMAN IR decoder (LIRC, etc)",
            7: "AIR capture (AnalysIR, etc)",
            8: "Bus Pirate v3 unbrick: bootloader v4.6 (ICSP)"}
LEGACY_DONE = ("Done! Just execute flashrom or avrdude using the binary com port\r\n"
               "To exit: press the button, or type 'q' here and confirm with 'y'.\r\n"
               "Either way the Bus Pirate resets on exit.\r\n")
_YN = "\r\ny/n, x to exit (Y) >\x03"

MODES = ("HiZ", "1WIRE", "UART", "HDUART", "I2C", "SPI", "2WIRE", "3WIRE",
         "DIO", "LED", "INFRARED", "JTAG", "PS2", "USB")
BPIO_MODES = ("HiZ", "1WIRE", "I2C", "SPI", "UART", "LED")
PIN_LABELS = {
    "HiZ": ["OFF"] + [""] * 8 + ["GND"],
    "I2C": ["VOUT", "SDA", "SCL", "", "", "", "", "", "", "GND"],
    "SPI": ["VOUT", "", "", "", "", "MISO", "CS", "CLK", "MOSI", "GND"],
    "UART": ["VOUT", "", "", "", "", "TX", "RX", "", "", "GND"],
    "1WIRE": ["VOUT", "OWD", "", "", "", "", "", "", "", "GND"],
    "LED": ["VOUT", "SDO", "", "", "", "", "", "", "", "GND"],
    "DIO": ["VOUT"] + [""] * 8 + ["GND"],
    "JTAG": ["VOUT"] + [""] * 8 + ["GND"],
    "2WIRE": ["VOUT", "SDA", "SCLK", "RST", "", "", "", "", "", "GND"],
    "PS2": ["VOUT", "DAT", "CLK", "", "", "", "", "", "", "GND"],
    "INFRARED": ["VOUT"] + [""] * 8 + ["GND"],
}


def _crc8(data: bytes) -> int:
    """Dallas/Maxim CRC-8, as a 1-Wire ROM carries in its last byte."""
    crc = 0
    for byte in data:
        for _ in range(8):
            mix = (crc ^ byte) & 1
            crc >>= 1
            if mix:
                crc ^= 0x8C
            byte >>= 1
    return crc


_ROM7 = bytes([0x28, 0xFF, 0x4C, 0x1A, 0x61, 0x16, 0x04])
DS18B20_ROM = _ROM7 + bytes([_crc8(_ROM7)])


class _Port:
    def __init__(self, on_write) -> None:
        self._on_write = on_write
        self.out = bytearray()
        self.written = bytearray()
        self.is_open = True

    def write(self, data: bytes) -> int:
        self.written += data
        self._on_write(bytes(data))
        return len(data)

    def read(self, count: int) -> bytes:
        data = bytes(self.out[:count])
        del self.out[:count]
        return data

    def flush(self) -> None:
        pass

    def reset_input_buffer(self) -> None:
        self.out.clear()

    def close(self) -> None:
        self.is_open = False


class _TerminalPort(_Port):
    """The terminal port: a streaming command's chunks come out 20 ms apart."""

    def __init__(self, owner) -> None:
        super().__init__(owner._on_terminal)
        self.owner = owner

    def read(self, count: int) -> bytes:
        self.owner._pump_stream()
        return super().read(count)


class _BinaryPort(_Port):
    """The BPIO2 port, with replies that can arrive late.

    The real firmware's send_packet() waits, with no timeout, for room in the
    USB buffer. A reply still on its way when the host closes the port never
    finds room, and the board's main loop — terminal included — hangs until
    it is replugged (firmware built 2026-10-12, src/binmode/bpio.c).
    """

    def __init__(self, owner) -> None:
        super().__init__(owner._on_binary)
        self.owner = owner
        self.pending = []  # (due, bytes) not yet sent by the board

    def send(self, data: bytes, delay: float = 0.0) -> None:
        if delay > 0 or self.pending:
            due = max([time.monotonic() + delay] + [d for d, _ in self.pending])
            self.pending.append((due, data))
        else:
            self.out += data

    def read(self, count: int) -> bytes:
        now = time.monotonic()
        while self.pending and self.pending[0][0] <= now:
            self.out += self.pending.pop(0)[1]
        return super().read(count)

    def close(self) -> None:
        if self.pending:
            self.owner.terminal_wedged = True  # a reply with nowhere to go
            self.pending.clear()
        super().close()
        self.owner._binary_closed()


class FakeNack(Exception):
    """Raised by an I2C handler to answer as a missing address does."""


class FakeEeprom24:
    """A 24xx EEPROM / FRAM: memory, a pointer, page wrap and a busy time after a write."""

    def __init__(self, part: str, data=None, busy_polls: int = 2) -> None:
        self.part = part.upper()
        self.size, self.addr_bytes = _EEPROM_SIZES[self.part]
        self.page = _EEPROM_PAGES[self.part]
        self.mem = bytearray(data if data is not None else bytes(self.size))
        if len(self.mem) < self.size:
            self.mem += bytes(self.size - len(self.mem))
        self.pointer = 0
        self.busy_polls = busy_polls
        self.busy = 0
        self.writes = []  # (offset, length) of each data write
        self.protected = False

    def handle(self, block: int, written: bytes, count: int) -> bytes:
        if self.busy > 0:
            self.busy -= 1
            raise FakeNack()
        width = self.addr_bytes
        if len(written) >= width:
            self.pointer = ((block << (8 * width)) | int.from_bytes(written[:width], "big")) % self.size
            data = written[width:]
            if data:
                self.writes.append((self.pointer, len(data)))
                pos = self.pointer
                for byte in data:
                    if not self.protected:
                        self.mem[pos] = byte
                    start = pos - pos % self.page
                    pos = start + (pos + 1 - start) % self.page
                self.pointer = pos
                self.busy = self.busy_polls
        out = bytearray()
        for _ in range(count):
            out.append(self.mem[self.pointer])
            self.pointer = (self.pointer + 1) % self.size
        return bytes(out)


class FakeEeprom25:
    """A 25xx SPI EEPROM / FRAM: READ, WRITE, WREN and RDSR, page wrap, one busy poll."""

    def __init__(self, part: str, data=None) -> None:
        self.part = part.upper()
        self.size, self.addr_bytes, self.page = _SPI_PARTS[self.part]
        self.mem = bytearray(data if data is not None else b"\xff" * self.size)
        if len(self.mem) < self.size:
            self.mem += b"\xff" * (self.size - len(self.mem))
        self.write_enabled = False
        self.busy = 0
        self.protect_bits = 0  # status bits 2-3; writes are ignored while set
        self.writes = []  # (offset, length) of each data write

    def _address(self, opcode: int, body: bytes):
        width = self.addr_bytes
        pointer = int.from_bytes(body[:width], "big")
        if width == 1 and self.size == 512 and opcode & 0x08:
            pointer += 256
        return pointer % self.size, body[width:]

    def exchange(self, written: bytes, read_count: int) -> bytes:
        if not written:
            return b"\x00" * read_count
        opcode, body = written[0], written[1:]
        if opcode == 0x05:
            value = (1 if self.busy > 0 else 0) | (2 if self.write_enabled else 0) | self.protect_bits
            if self.busy > 0:
                self.busy -= 1
            return bytes([value]) * read_count
        if opcode == 0x06:
            self.write_enabled = True
            return b""
        if opcode & 0xF7 == 0x03:
            pos, _ = self._address(opcode, body)
            out = bytearray()
            for _ in range(read_count):
                out.append(self.mem[pos])
                pos = (pos + 1) % self.size
            return bytes(out)
        if opcode & 0xF7 == 0x02:
            pos, data = self._address(opcode, body)
            if not self.write_enabled or self.protect_bits:
                self.write_enabled = False
                return b""
            self.writes.append((pos, len(data)))
            for byte in data:
                self.mem[pos] = byte
                start = pos - pos % self.page
                pos = start + (pos + 1 - start) % self.page
            self.write_enabled = False
            self.busy = 1
            return b""
        return b"\x00" * read_count


class FakeMicrowire:
    """A 93Cxx Microwire EEPROM with a bit-level model; needs an active-high CS.

    Zeros before the start bit (the first 1) are ignored. READ answers a dummy 0 and then
    the data bits; WRITE needs EWEN; after a write it reads 0x00 (busy) for two polls.
    """

    cs_active_high = True

    def __init__(self, part: str, org: int, data=None) -> None:
        self.part, self.org = part.upper(), org
        self.size, x8, x16 = _MW_PARTS[self.part]
        self.abits = x8 if org == 8 else x16
        self.mem = bytearray(data if data is not None else b"\xff" * self.size)
        if len(self.mem) < self.size:
            self.mem += b"\xff" * (self.size - len(self.mem))
        self.write_enabled = False
        self.ewen_works = True  # False: EWEN is ignored, so writes are too
        self.busy_polls = 2
        self.busy = 0
        self.writes = []  # (offset, length) of each write

    def exchange(self, written: bytes, read_count: int) -> bytes:
        if not written:
            if self.busy > 0:
                self.busy -= 1
                return b"\x00" * read_count
            return b"\xff" * read_count
        bits = "".join(format(b, "08b") for b in written)
        start = bits.find("1")
        if start < 0:
            return b"\x00" * read_count
        body = bits[start + 1:]
        opcode, rest = body[:2], body[2:]
        if len(opcode) < 2 or len(rest) < self.abits:
            return b"\x00" * read_count
        address, tail = int(rest[:self.abits], 2), rest[self.abits:]
        unit = 8 if self.org == 8 else 16
        step = unit // 8
        if opcode == "10":  # READ: dummy 0, then data bits, address advancing
            stream, pos = ["0"], (address * step) % self.size
            for _ in range(-(-read_count * 8 // unit) + 1):
                stream.append("".join(format(self.mem[(pos + i) % self.size], "08b")
                                      for i in range(step)))
                pos = (pos + step) % self.size
            out = "".join(stream)
            return int(out[:read_count * 8], 2).to_bytes(read_count, "big") if read_count else b""
        if opcode == "01":  # WRITE
            if len(tail) < unit or not self.write_enabled:
                return b"\x00" * read_count
            pos = (address * step) % self.size
            self.mem[pos:pos + step] = int(tail[:unit], 2).to_bytes(step, "big")
            self.writes.append((pos, step))
            self.busy = self.busy_polls
            return b"\x00" * read_count
        if opcode == "00":  # extended: the top two address bits pick the command
            top = rest[:2]
            if top == "11":
                self.write_enabled = self.ewen_works
            elif top == "00":
                self.write_enabled = False
        return b"\x00" * read_count


class FakeDs2431:
    """A 1-Wire EEPROM (DS2431 / DS2433): READ ROM, skip ROM, read memory, scratchpad, copy.

    Implements ``reset() -> bool``, ``write(data)`` and ``read(count)``. ``reset``
    starts a new command; ``write`` adds to it; ``read`` answers from where the
    last read stopped. ``copy_fails`` makes the chip refuse to copy (no strong pull-up).
    """

    def __init__(self, family=0x2D, data=None, rom=None):
        _, self.size, self.row = _OW_FAMILIES[family]
        self.mem = bytearray(data if data is not None
                             else bytes((i * 3 + 1) & 0xFF for i in range(self.size)))
        if len(self.mem) != self.size:
            raise ValueError("a family 0x%02X chip holds %d bytes" % (family, self.size))
        if rom is None:
            body = bytes([family, 0x11, 0x22, 0x33, 0x44, 0x55, 0x66])
            rom = body + bytes([_crc8(body)])
        self.rom = bytes(rom)
        self.copy_fails = False
        self.family = family
        self.scratch_ta = b"\x00\x00"
        self.scratch = b""
        self.pf = False  # E/S bit 5: the scratchpad is not a copyable one
        self._cmd = bytearray()
        self._sent = 0

    def reset(self):
        self._cmd, self._sent = bytearray(), 0
        return True

    def _es(self):
        end = (self.scratch_ta[0] % self.row + len(self.scratch) - 1) & 0x1F
        return end | (0x20 if self.pf else 0)

    def write(self, data):
        self._cmd += data
        rest = bytes(self._cmd[1:]) if self._cmd[:1] == b"\xcc" else b""
        if rest[:1] == b"\x0f" and len(rest) >= 3:
            ta = rest[1] | rest[2] << 8
            offset = ta % self.row
            self.scratch_ta = rest[1:3]
            self.scratch = rest[3:3 + self.row - offset]  # a row's end truncates the data
            # PF: a write at or past the end of memory; a DS2431 also needs the whole,
            # row-aligned 8 bytes (it copies nothing else), a DS2433 may be partial.
            self.pf = (ta >= self.size or ta + len(self.scratch) > self.size
                       or (self.family == 0x2D and (offset != 0 or len(self.scratch) != self.row)))

    def _stream(self, at):
        cmd = bytes(self._cmd)
        if cmd[:1] == b"\x33":
            return self.rom
        rest = cmd[1:] if cmd[:1] == b"\xcc" else b""
        if rest[:1] == b"\xf0" and len(rest) >= 3:
            start = rest[1] | rest[2] << 8
            return bytes(self.mem[start:]) + b"\xff" * 64
        if rest[:1] == b"\xaa":
            return self.scratch_ta + bytes([self._es()]) + self.scratch
        if rest[:1] == b"\x55" and len(rest) >= 4:
            ok = (rest[1:3] == self.scratch_ta and rest[3] == self._es() and not self.pf
                  and bool(self.scratch) and not self.copy_fails)
            if ok and at == 0:
                start = self.scratch_ta[0] | self.scratch_ta[1] << 8
                self.mem[start:start + len(self.scratch)] = self.scratch
            return b"\xaa" if ok else b"\xff"
        return b""

    def read(self, count):
        out = (self._stream(self._sent) + b"\xff" * count)[self._sent:self._sent + count]
        self._sent += count
        return out


class FakeSht31:
    """An SHT31: ``F3 2D`` reads the status register, ``24 00`` measures 25 °C and 50 %RH."""

    def __init__(self) -> None:
        self._reply = b""

    @staticmethod
    def _word(value: int) -> bytes:
        raw = value.to_bytes(2, "big")
        return raw + bytes([crc8(raw)])

    def __call__(self, written: bytes, count: int) -> bytes:
        if written == b"\xf3\x2d":
            self._reply = self._word(0x8010)
        elif written == b"\x24\x00":
            self._reply = self._word(0x6666) + self._word(0x7FFF)
        return self._reply[:count]


class FakeBp6:
    TERMINAL = "/dev/cu.usbmodem6buspirate1"
    BINARY = "/dev/cu.usbmodem6buspirate3"

    def __init__(self, bpio_active: bool = True, color_prompt: bool = False, load_ma: int = 12,
                 bpio_settle: float = 0.2, first_reply_delay: float = 0.0,
                 terminal_reply_delay: float = 0.0) -> None:
        self.bpio_active = bpio_active
        self.color_prompt = color_prompt
        self.load_ma = load_ma
        self.mode = "HiZ"
        self.psu_enabled = False
        self.psu_tripped = False
        self.psu_mv = 0
        self.psu_ma = 0
        #: A target with its own supply: the mV it puts on IO0..IO7 (8 values),
        #: and on VOUT while our supply is off. None: nothing there.
        self.adc_mv = None
        self.vout_mv = None
        self.pullups = False
        self.requests = []
        #: IO pin state as set over BPIO2 (bit n = IOn, direction 1 = output).
        self.io_direction = 0
        self.io_value = 0
        #: Every request that set pins, LEDs or an LED-mode submode.
        self.pin_log = []
        self.led_log = []   # onboard colour lists; "resume" for a resume
        self.led_submode = 0
        self.led_count = 18
        #: Bytes written to the LED strip, one entry per data request.
        self.pixel_log = []
        device = bytearray(256)
        device[0xD0] = 0x58
        # The Bosch BMP280 datasheet's worked example (§8.1): these calibration
        # words and raw readings compensate to 25.08 °C and 1006.53 hPa.
        device[0x88:0xA0] = struct.pack("<HhhHhhhhhhhh", 27504, 26435, -1000, 36477, -10685,
                                        3024, 2855, 140, -7, 15500, -14600, 6000)
        device[0xF7:0xFD] = bytes((0x65, 0x5A, 0xC0, 0x7E, 0xED, 0x00))
        self.i2c_devices = {0x76: device}
        self._pointer = {0x76: 0}
        #: Devices that are not a plain register file: address -> callable(written, count).
        self.i2c_handlers = {}
        # A PCF8574 LCD backpack, an SHT31 and a 24C02 holding a recognisable pattern.
        self.add_i2c_device(0x27)
        self.add_i2c_device(0x44, handler=FakeSht31())
        self.add_eeprom24(0x50, "24C02", bytes((i * 7 + 3) & 0xFF for i in range(256)))
        self.flash = FakeFlash()
        self.spi_device = self.flash  # whatever answers on CS: swap for another chip
        #: The chip_select_idle of the last SPI mode configuration; False = active-high CS.
        self.spi_cs_idle = True
        self.onewire_rom = DS18B20_ROM
        #: A 1-Wire chip with reset/write/read (FakeDs2431); None keeps onewire_rom's behaviour.
        self.onewire_device = None
        self.uart_echo = True
        self._spi_written, self._spi_read = bytearray(), 0
        #: Failures to inject into the next data requests, in order: an error
        #: string is sent as the reply's error, None means no reply at all.
        self.data_faults = []
        #: Every data request: (start, written, bytes to read, stop).
        self.data_log = []
        self._reader = FrameReader()
        self._terminal_state = "prompt"
        #: Modes whose last settings are saved: ``m <mode>`` then asks to reuse them.
        self.saved_modes = set()
        #: The next ``W`` trips the over-current protection.
        self.trip_next_w = False
        #: Pins generating a frequency (terminal ``G``), pin -> (Hz, duty %).
        self.pwm = {}
        self._pwm_pin = None
        self._pwm_hz = None
        #: Signals the target drives into the pins, for ``f``: pin -> (Hz, duty %).
        self.signals = {}
        #: What ``bluetag`` finds per protocol, e.g. {"jtag": BLUETAG_JTAG_HIT}; empty: nothing.
        self.bluetag_hit = {}
        self._terminal_lines = []
        #: Every key received while a command was streaming (see ``_stream``).
        self.keys_seen = []
        self._streaming = None
        #: What ``sniff`` streams in I2C and 2WIRE modes, one string per chunk.
        self.sniff_lines = []
        #: What PS2 ``sniff`` streams, one string per chunk; and a PSU error code to print instead.
        self.ps2_lines = []
        self.ps2_psu_error = None
        #: The infrared protocol (-p) the INFRARED prompt shows: RAW, NEC or RC5.
        self.ir_protocol = "RAW"
        #: aIR strings (no ``;``) the receiver hears one after another on ``irrx``.
        self.ir_frames = []
        #: What the board was told to send: ("raw", air), ("nec", value) or ("rc5", value).
        self.ir_sent = []
        #: Self-test (``~``): whether a human presses the button, whether the NAND
        #: has a file system, and extra failing lines to print (each is one error).
        self.button_pressed = True
        self.nand_formatted = True
        self.selftest_faults = []
        self._selftest_errors = 0
        #: True once Ctrl-C has hit the colour question: nothing answers.
        self.terminal_wedged = False
        #: How long BPIO2 takes to start answering once selected (real board:
        #: about 2.8 s). Requests before then are lost and wedge the terminal.
        self.bpio_settle = bpio_settle
        self._bpio_ready_at = 0.0
        #: How late the first reply after the binary port is opened arrives.
        self.first_reply_delay = first_reply_delay
        #: How late the first reply after the terminal port is opened arrives.
        self.terminal_reply_delay = terminal_reply_delay
        self._delay_next_reply = 0.0
        #: The binmode menu (research doc section 8), number -> name.
        self.binmode_names = dict(BINMODES)
        #: The binmode chosen with ``y`` at ``Save setting?``: active after a reset.
        self.saved_bpio = bpio_active
        #: Legacy binary mode: None, or the answers to its prompts once asked.
        self.legacy = None
        self._legacy_answers = {}
        #: Bytes written to the binary port while Legacy mode ran.
        self.binary_in_legacy = bytearray()
        #: The supply SUMP switched on when the binary port opened.
        self._sump_powered = False
        #: How long a reset takes the ports away; how many resets so far.
        self.reset_seconds = 0.3
        #: How long the ports stay listed after "Resetting" before they vanish.
        self.reset_lag_s = 0.0
        self.resets = 0
        #: Legacy's exit question never gets its answer: no reset follows ``q``, ``y``.
        self.exit_answer_lost = False
        #: (mV, mA) Legacy sets in place of the answers given; None: the answers.
        self.legacy_psu = None
        self.was_gone = False
        self._gone_from = 0.0
        self._gone_until = 0.0
        self.binary = _BinaryPort(self)
        self.terminal = _TerminalPort(self)

    @property
    def present(self) -> bool:
        """Whether the board's USB ports are there (not unplugged, not resetting)."""
        if self._gone_from <= time.monotonic() < self._gone_until:
            self.was_gone = True
            return False
        return True

    def unplug(self) -> None:
        """Take the board away for good."""
        self._gone_from, self._gone_until = 0.0, float("inf")

    def factory(self, terminal_port: str = TERMINAL, binary_port: str = BINARY):
        def make(port, baudrate, timeout):
            if not self.present:
                raise OSError(2, "No such file or directory: %r" % port)
            if port == terminal_port:
                self.terminal.is_open = True
                # Seen on the real board: the first BPIO2 reply after the
                # terminal port is opened comes seconds late.
                self._delay_next_reply = max(self._delay_next_reply, self.terminal_reply_delay)
                return self.terminal
            self.binary.is_open = True
            self._delay_next_reply = self.first_reply_delay
            if not self.bpio_active and self.legacy is None and self.mode == "HiZ":
                # SUMP: a client opening the port switches the supply on
                # (psu_enable(3.3, 100, ...), research doc section 8).
                self.psu_enabled, self.psu_mv, self.psu_ma = True, 3300, 100
                self._sump_powered = True
            return self.binary
        return make

    def _binary_closed(self) -> None:
        if self._sump_powered:
            self._sump_powered = False
            self.psu_enabled = False

    # -- the target ----------------------------------------------------------

    def over_limit(self) -> bool:
        return 0 < self.psu_ma < self.load_ma

    def add_i2c_device(self, address: int, data: bytes = bytes(256), handler=None) -> None:
        """Answer at ``address`` with a 256-byte register file, or with ``handler``.

        A handler is called as ``handler(written, count)`` with the bytes after the
        address byte and the number to read, and returns the bytes to read.
        """
        self.i2c_devices[address] = bytearray(data)
        self._pointer[address] = 0
        if handler is not None:
            self.i2c_handlers[address] = handler
        else:
            self.i2c_handlers.pop(address, None)

    def add_eeprom24(self, address: int, part: str, data=None) -> "FakeEeprom24":
        """Answer at ``address`` (and the block addresses above it) as a 24xx part."""
        chip = FakeEeprom24(part, data)
        blocks = max(1, chip.size >> (8 * chip.addr_bytes))
        for block in range(blocks):
            self.add_i2c_device(address + block, bytes(256),
                                lambda w, c, b=block: chip.handle(b, w, c))
            self.i2c_devices[address + block] = chip.mem  # the same bytes, for tests to inspect
        return chip

    def set_load(self, milliamps: int) -> None:
        """Change what the target draws, as when a part is plugged in."""
        self.load_ma = milliamps
        if self.psu_enabled and self.over_limit():
            self.psu_enabled, self.psu_tripped = False, True

    def uart_receive(self, data: bytes) -> None:
        self.binary.send(frame(self._data_response(bytes(data), is_async=True)))

    # -- BPIO2 ---------------------------------------------------------------

    def _on_binary(self, data: bytes) -> None:
        if self.legacy is not None:
            self.binary_in_legacy += data  # flashrom's protocol: not simulated
            return
        if not self.bpio_active:
            # Seen on the real board: BPIO2 bytes sent while another binary
            # mode (the logic analyzer, by default) has the port left the
            # terminal silent until a replug. Why is not known; the driver
            # avoids it by asking the terminal first.
            self.terminal_wedged = True
            return
        if time.monotonic() < self._bpio_ready_at:
            # Seen on the real board: BPIO2 takes about 2.8 s to answer after
            # it is selected, and requests sent before then went unanswered
            # and, at least twice, left the terminal silent until a replug.
            self.terminal_wedged = True
            return
        for raw in self._reader.feed(data):
            packet = _RP.RequestPacket.GetRootAs(cobs_decode(raw[:-1]), 0)
            kind, table = packet.ContentsType(), packet.Contents()
            if kind == RequestPacketContents.StatusRequest:
                self.requests.append("status")
                reply = self._status_response()
            elif kind == RequestPacketContents.ConfigurationRequest:
                self.requests.append("configuration")
                request = _CR.ConfigurationRequest()
                request.Init(table.Bytes, table.Pos)
                reply = self._configure(request)
            elif kind == RequestPacketContents.DataRequest:
                self.requests.append("data")
                request = _DR.DataRequest()
                request.Init(table.Bytes, table.Pos)
                self.data_log.append((
                    bool(request.StartMain() or request.StartAlt()),
                    bytes(request.DataWrite(i) for i in range(request.DataWriteLength())),
                    request.BytesRead(),
                    bool(request.StopMain() or request.StopAlt()),
                ))
                if self.data_faults:
                    fault = self.data_faults.pop(0)
                    if fault is None:
                        continue  # the board says nothing
                    self._reply(frame(self._data_response(b"", error=fault)))
                    continue
                reply = self._data(request)
            else:
                raise AssertionError("a RequestPacket with no contents was sent")
            self._reply(frame(reply))

    def _reply(self, data: bytes) -> None:
        delay, self._delay_next_reply = self._delay_next_reply, 0.0
        self.binary.send(data, delay)

    def _status_response(self) -> bytes:
        b = flatbuffers.Builder(512)

        def vector(start, items):
            offsets = [b.CreateString(item) for item in items]
            start(b, len(offsets))
            for offset in reversed(offsets):
                b.PrependUOffsetTRelative(offset)
            return b.EndVector()

        modes = vector(_ST.StatusResponseStartModesAvailableVector, MODES)
        labels = vector(_ST.StatusResponseStartModePinLabelsVector, PIN_LABELS[self.mode])
        if self.adc_mv is not None:
            adc = list(self.adc_mv)
        else:
            adc = [self.psu_mv if (self.pullups and self.psu_enabled) else 0] * 8
        vout_off = 22 if self.vout_mv is None else self.vout_mv
        _ST.StatusResponseStartAdcMvVector(b, 8)
        for value in reversed(adc):
            b.PrependUint32(value)
        adc_vec = b.EndVector()
        date = b.CreateString("Oct 12 2026 09:05:15")
        git = b.CreateString("unknown")
        mode = b.CreateString(self.mode)
        _ST.StatusResponseStart(b)
        _ST.StatusResponseAddVersionFlatbuffersMajor(b, 2)
        _ST.StatusResponseAddVersionHardwareMajor(b, 6)
        _ST.StatusResponseAddVersionHardwareMinor(b, 2)
        _ST.StatusResponseAddVersionFirmwareGitHash(b, git)
        _ST.StatusResponseAddVersionFirmwareDate(b, date)
        _ST.StatusResponseAddModesAvailable(b, modes)
        _ST.StatusResponseAddModeCurrent(b, mode)
        _ST.StatusResponseAddModePinLabels(b, labels)
        _ST.StatusResponseAddModeBitorderMsb(b, True)
        _ST.StatusResponseAddModeMaxPacketSize(b, 640)
        _ST.StatusResponseAddModeMaxWrite(b, 512)
        _ST.StatusResponseAddModeMaxRead(b, 512)
        _ST.StatusResponseAddPsuEnabled(b, self.psu_enabled)
        _ST.StatusResponseAddPsuSetMv(b, self.psu_mv)
        _ST.StatusResponseAddPsuSetMa(b, self.psu_ma)
        _ST.StatusResponseAddPsuMeasuredMv(b, self.psu_mv if self.psu_enabled else vout_off)
        _ST.StatusResponseAddPsuMeasuredMa(b, self.load_ma if self.psu_enabled else 1)
        _ST.StatusResponseAddPsuCurrentError(b, self.psu_tripped)
        _ST.StatusResponseAddPullupEnabled(b, self.pullups)
        _ST.StatusResponseAddAdcMv(b, adc_vec)
        _ST.StatusResponseAddLedCount(b, self.led_count)
        _ST.StatusResponseAddIoDirection(b, self.io_direction)
        _ST.StatusResponseAddIoValue(b, self.io_value)
        return self._packet(b, ResponsePacketContents.StatusResponse, _ST.StatusResponseEnd(b))

    def _configure(self, request) -> bytes:
        error = None
        if request.Mode():
            name = request.Mode().decode()
            match = next((m for m in BPIO_MODES if m.lower() == name.lower()), None)
            if match is None:
                error = "Invalid mode name"
            else:
                self.mode = match
        if error is None and request.PsuEnable():
            if not 800 <= request.PsuSetMv() <= 5000:
                error = "PSU voltage out of range"
            else:
                # As the real board did on 2026-10-16: a load over the limit
                # is refused at switch-on, unless the supply has tripped, in
                # which case it just stays off and tripped. A load the limit
                # covers brings it on and clears the trip.
                self.psu_mv, self.psu_ma = request.PsuSetMv(), request.PsuSetMa()
                if self.over_limit():
                    self.psu_enabled = False
                    if not self.psu_tripped:
                        error = "Power supply initialization failed"
                else:
                    self.psu_enabled, self.psu_tripped = True, False
        if request.IoDirectionMask() or request.IoValueMask():
            dm, d = request.IoDirectionMask(), request.IoDirection()
            vm, v = request.IoValueMask(), request.IoValue()
            self.pin_log.append((dm, d, vm, v))
            self.io_direction = (self.io_direction & ~dm) | (d & dm)
            self.io_value = (self.io_value & ~vm) | (v & vm)
        if not request.LedColorIsNone():
            self.led_log.append([request.LedColor(i) for i in range(request.LedColorLength())])
        if request.LedResume():
            self.led_log.append("resume")
        if request.Mode() and request.ModeConfiguration() is not None:
            self.led_submode = request.ModeConfiguration().Submode()
            self.spi_cs_idle = request.ModeConfiguration().ChipSelectIdle()
        if request.PsuDisable():
            self.psu_enabled = False  # the trip flag stays, as on the real board
        if request.PullupEnable():
            self.pullups = True
        if request.PullupDisable():
            self.pullups = False
        b = flatbuffers.Builder(64)
        err = b.CreateString(error) if error else None
        _CRS.ConfigurationResponseStart(b)
        if err is not None:
            _CRS.ConfigurationResponseAddError(b, err)
        return self._packet(b, ResponsePacketContents.ConfigurationResponse,
                            _CRS.ConfigurationResponseEnd(b))

    def _data(self, request) -> bytes:
        written = bytes(request.DataWrite(i) for i in range(request.DataWriteLength()))
        count = request.BytesRead()
        started = request.StartMain() or request.StartAlt()
        stopped = request.StopMain() or request.StopAlt()
        if self.mode == "I2C":
            if not written:
                return self._data_response(b"")  # a stop-only request
            address = written[0] >> 1
            device = self.i2c_devices.get(address)
            if device is None:
                return self._data_response(b"", error="Protocol request failed")
            handler = self.i2c_handlers.get(address)
            if handler is not None:
                try:
                    reply = handler(written[1:], count)
                except FakeNack:
                    return self._data_response(b"", error="Protocol request failed")
                return self._data_response(reply)
            if len(written) > 1:
                self._pointer[address] = written[1]
                for offset, byte in enumerate(written[2:]):
                    device[(written[1] + offset) & 0xFF] = byte
            start = self._pointer[address]
            return self._data_response(bytes(device[(start + i) & 0xFF] for i in range(count)))
        if self.mode == "SPI":
            # One CS-low transaction can span several requests (long reads are
            # split at 512 bytes), so keep what was written since start and how
            # much has been read, and replay it through FakeFlash.
            if started:
                self._spi_written, self._spi_read = bytearray(), 0
            self._spi_written += written
            data = b""
            if getattr(self.spi_device, "cs_active_high", False) and self.spi_cs_idle:
                # An active-high chip never sees an active-low CS: reads come back 0x00.
                return self._data_response(bytes(count))
            if count:
                whole = self.spi_device.exchange(bytes(self._spi_written), self._spi_read + count)
                data = whole[self._spi_read:]
                self._spi_read += count
            elif stopped and not self._spi_read and self._spi_written:
                # A write-only command (write enable, program, erase) acts at CS high.
                self.spi_device.exchange(bytes(self._spi_written), 0)
            return self._data_response(data)
        if self.mode == "1WIRE":
            device = self.onewire_device
            if device is not None:
                if started and not device.reset():
                    return self._data_response(b"", error="Protocol request failed")
                if written:
                    device.write(written)
                return self._data_response(bytes(device.read(count)) if count else b"")
            if started and not self.onewire_rom:
                return self._data_response(b"", error="Protocol request failed")
            if written[:1] == b"\x33":
                return self._data_response(self.onewire_rom[:count])
            return self._data_response(bytes(count))
        if self.mode == "UART":
            if written and self.uart_echo:
                self.uart_receive(written)
            return self._data_response(b"")
        if self.mode == "LED":
            self.pixel_log.append(written)
            return self._data_response(b"")
        return self._data_response(b"", error="Invalid mode")

    def _data_response(self, data: bytes, error=None, is_async=False) -> bytes:
        b = flatbuffers.Builder(64 + len(data))
        err = b.CreateString(error) if error else None
        vec = b.CreateByteVector(data) if data else None
        _DRS.DataResponseStart(b)
        if err is not None:
            _DRS.DataResponseAddError(b, err)
        if vec is not None:
            _DRS.DataResponseAddDataRead(b, vec)
        if is_async:
            _DRS.DataResponseAddIsAsync(b, True)
        return self._packet(b, ResponsePacketContents.DataResponse, _DRS.DataResponseEnd(b))

    @staticmethod
    def _packet(b, kind, contents) -> bytes:
        _RS.ResponsePacketStart(b)
        _RS.ResponsePacketAddContentsType(b, kind)
        _RS.ResponsePacketAddContents(b, contents)
        b.Finish(_RS.ResponsePacketEnd(b))
        return bytes(b.Output())

    # -- the text terminal ----------------------------------------------------

    HIZ_REFUSAL = "Command has no effect in HiZ mode, press 'm' to choose a mode"
    TERMINAL_MODES = ("HiZ", "DIO", "JTAG", "I2C", "2WIRE", "PS2", "INFRARED")

    def lines_received(self) -> List[bytes]:
        """Every write the terminal port received, in order."""
        return list(self._terminal_lines)

    def _say(self, text: str) -> None:
        self.terminal.out += text.encode()

    def _prompt(self) -> str:
        if self.mode == "INFRARED":
            return f"\r\nINFRARED-({self.ir_protocol})> \x03"
        return f"\r\n{self.mode}> \x03"

    def _stream(self, text: str, banner: str, stop_keys, end_text: str, chunks,
                inline_prompt: bool = False, drain: float = 0.0) -> None:
        """Start a command that streams until a key in ``stop_keys`` is pressed.

        Echoes ``text``, prints ``banner``, then one chunk of ``chunks`` (any
        iterable of strings) every 20 ms. A stop key prints ``end_text`` and the
        prompt; other keys are ignored. Every key is kept in ``keys_seen``.
        With ``inline_prompt`` a last chunk that ends mid-line gets the prompt
        straight after it, as the firmware prints it (a sniffer stopped
        mid-transaction).
        """
        self._terminal_state = "stream"
        self._streaming = {"stop": tuple(stop_keys), "end": end_text,
                           "chunks": iter(chunks), "due": time.monotonic() + 0.02,
                           "inline": inline_prompt, "last": banner,
                           "drain_until": time.monotonic() + drain}
        self._say(f"{text}\x1b[0K\r\n{banner}")

    def _pump_stream(self) -> None:
        s = self._streaming
        if s is None:
            return
        for _ in range(50):  # a slow reader catches up, but never floods
            if time.monotonic() < s["due"]:
                break
            s["due"] += 0.02
            chunk = next(s["chunks"], None)
            if chunk is None:
                break
            s["last"] = chunk
            self._say(chunk)

    def _stream_key(self, keys: bytes) -> None:
        s = self._streaming
        self.keys_seen.append(bytes(keys))
        if time.monotonic() < s.get("drain_until", 0):
            return  # the firmware discards input it drains before its ready line
        if s.get("on_key") is not None:
            s["on_key"](keys.decode("ascii", "replace"))
        if any(k in keys.decode("ascii", "replace") for k in s["stop"]):
            self._streaming = None
            self._terminal_state = "prompt"
            prompt = self._prompt()
            if s["inline"] and not s["end"] and s["last"] and not s["last"].endswith("\n"):
                prompt = prompt.lstrip("\r\n")
            self._say(s["end"] + prompt)

    def _finish(self, echo: str, body: str = "") -> None:
        """Echo (with the redraw noise the real line editor adds), output, prompt."""
        self._say(f"{echo}\x1b[0K\r\n{body}{self._prompt()}")

    def _ask(self, echo: str, body: str, state: str) -> None:
        self._terminal_state = state
        self._say(f"{echo}\x1b[0K\r\n{body}\x03")

    def _set_mode(self, name: str) -> None:
        self.mode = name
        self.ir_protocol = "RAW"
        self.psu_enabled = False   # the HiZ setup of every mode switches these off
        self.pullups = False
        self.pwm.clear()

    def _on_terminal(self, keys: bytes) -> None:
        self._terminal_lines.append(bytes(keys))
        if self.terminal_wedged:
            return
        if self._streaming is not None:
            self._stream_key(keys)
            return
        if keys == b"\x03" and self.color_prompt:
            # Seen on the real board (firmware built 2026-10-12): Ctrl-C stops
            # the colour question's line editor, which the question never
            # restarts. The terminal stays silent until the board is replugged.
            self.terminal_wedged = True
            return
        if keys == b"\x03":
            self._say("^C\r\n" + ("VT100 compatible color mode? (Y/n)> " if self.color_prompt
                                  else f"{self.mode}> \x03"))
            return
        if self.color_prompt:
            if keys in (b"n\r", b"y\r"):
                self.color_prompt = False
                self._say(keys.decode()[0] + "\n\r\n\r\n" + self._prompt().lstrip("\r\n"))
            else:
                self._say("\n\r\n\r\nVT100 compatible color mode? (Y/n)> ")
            return
        line = keys.decode("ascii", "replace")
        state = self._terminal_state
        if state.startswith("legacy"):
            self._legacy_key(state, line)
        elif state == "binmode-menu" and line.strip().lower() == "x":
            self._terminal_state = "prompt"
            self._say("x\n" + self._prompt())
        elif state == "binmode-menu" and line.strip() in ("1", "2", "5"):
            self._select_binmode(line.strip(), int(line))
        elif state.startswith("binmode-save") and line in ("n\r", "y\r"):
            self._terminal_state = "prompt"
            sump = state == "binmode-save-1"
            self.bpio_active = not sump
            if line == "y\r":
                self.saved_bpio = self.bpio_active
            if not sump:
                self._bpio_ready_at = time.monotonic() + self.bpio_settle
            self._say(line[0] + "\n\r\n\r\n" + self._prompt().lstrip("\r\n"))
        elif re.fullmatch(r"binmode [125]\r", line):
            self._select_binmode(line.strip(), int(line.split()[1]))
        elif state == "i2c-previous":
            self._terminal_state = "prompt"
            if line.strip().lower() == "x":
                self._finish("x")
            else:
                self._set_mode("I2C")
                self._finish(line.strip())
        elif state == "w-volts":
            self._terminal_state = "prompt"
            self._finish(line.strip())  # only x is understood: it leaves
        elif state == "selftest-format":
            self._selftest_body(line.strip(), "")
        elif state == "selftest-button":
            if line == " ":
                self._terminal_state = "prompt"
                self._selftest_errors += 1
                self._say("SKIPPED\r\n" + self._selftest_summary())
        elif state == "pwm-freq":
            self._pwm_frequency(line)
        elif state == "pwm-duty":
            self._pwm_duty(line)
        elif line == "binmode\r":
            self._terminal_state = "binmode-menu"
            menu = "".join(" %d. %s\r\n" % kv for kv in sorted(self.binmode_names.items()))
            self._say("binmode\n\r\n" + menu + "Select binary mode\r\nx to exit (1) > ")
        elif line == "i\r":
            binmode = "BPIO2 flatbuffer interface" if self.bpio_active else "SUMP logic analyzer"
            self._say("i\n\r\nBus Pirate 6\r\nFirmware main branch @ unknown (Oct 12 2026 09:04:39)\r\n"
                      "RP2350B with 512KB RAM, 128Mbit FLASH\r\n"
                      f"Active binmode: {binmode}\r\nActive mode: {self.mode}\r\n" + self._prompt())
        elif line == "\r":
            self._say("\n" + self._prompt())
        else:
            self._command(line.strip())

    # Binary modes (research doc section 8).

    def _select_binmode(self, echo: str, number: int) -> None:
        self._say(echo + "\n\r\n\r\nBinmode selected: %s\r\n" % self.binmode_names[number])
        if number in (1, 2):
            self._terminal_state = "binmode-save-%d" % number
            self._say("Save setting?\r\ny/n > ")
            return
        # 5: Legacy locks the terminal and asks its own questions.
        self.bpio_active = False
        self.legacy = {}
        self._say("\r\nBinmode active. Terminal locked\r\n")
        self._legacy_ask("legacy-aux")

    _LEGACY_QUESTIONS = {
        "legacy-aux": "\r\nSet OUTPUT HOLD(IO2) & WP(IO3) pins? (no=INPUT)" + _YN,
        "legacy-hold": "\r\nSet HOLD HIGH? (no=LOW)" + _YN,
        "legacy-wp": "\r\nSet WP HIGH? (no=LOW)" + _YN,
        "legacy-clock": "\r\nClock on IO0 for avrdude -x cpufreq?" + _YN,
        "legacy-volts": "\r\nPower supply\r\nVolts (0.80V-5.00V)\r\nx to exit (3.30) >\x03",
        "legacy-amps": "\r\nMaximum current (0mA-500mA)\r\nx to exit (200.00) >\x03",
    }

    def _legacy_ask(self, state: str) -> None:
        self._terminal_state = state
        self._say(self._LEGACY_QUESTIONS[state])

    def _legacy_key(self, state: str, line: str) -> None:
        answer = line.strip().lower()
        if state == "legacy":
            if "q" in answer:
                self._terminal_state = "legacy-exit"
                self._say("\r\nExit legacy binary mode and reset the Bus Pirate? (y/n) ")
            return
        if state == "legacy-exit":
            if self.exit_answer_lost:
                # The answer never reached the question (it timed out): the
                # board stays in Legacy mode, as after the firmware's 15 s.
                self._terminal_state = "legacy"
                return
            if "y" in answer:
                self._say("y\r\n\r\nExit reason: 'q' then 'y' on the terminal\r\n")
                self._legacy_reset()
            elif "n" in answer:
                self._terminal_state = "legacy"
                self._say("n\r\n")
            return
        self._say(line.strip() + "\r\n")
        if answer == "x":
            self._legacy_reset()
            return
        if state in ("legacy-aux", "legacy-hold", "legacy-wp", "legacy-clock"):
            yes = answer in ("", "y")
            self.legacy[state[7:]] = yes
            if state == "legacy-aux" and not yes:
                self.legacy["hold"] = self.legacy["wp"] = None
            following = {"legacy-aux": "legacy-hold" if yes else "legacy-clock",
                         "legacy-hold": "legacy-wp", "legacy-wp": "legacy-clock",
                         "legacy-clock": "legacy-volts"}[state]
            self._legacy_ask(following)
        elif state == "legacy-volts":
            self.legacy["mv"] = int(round(float(answer or "3.3") * 1000))
            self._legacy_ask("legacy-amps")
        elif state == "legacy-amps":
            self.legacy["ma"] = int(round(float(answer or "200")))
            self.psu_mv, self.psu_ma = self.legacy_psu or (self.legacy["mv"], self.legacy["ma"])
            self.psu_enabled, self.psu_tripped = True, False
            self._terminal_state = "legacy"
            self._say("\r\nPower supply set to %.2fV, %3.0fmA\r\n"
                      % (self.psu_mv / 1000.0, self.psu_ma) + "\r\n" + LEGACY_DONE)

    def _legacy_reset(self) -> None:
        """Leave Legacy: the board resets, its ports vanish and come back."""
        self._say("\r\nExiting Legacy Binary Mode...\r\nResetting Bus Pirate...\r\n"
                  "After reconnect press enter to use Bus Pirate in other modes.\r\n")
        self.resets += 1
        self.legacy = None
        self._terminal_state = "prompt"
        self._set_mode("HiZ")
        self.psu_tripped = False
        self.io_direction = self.io_value = 0
        self.bpio_active = self.saved_bpio
        self._bpio_ready_at = 0.0
        self._reader = FrameReader()
        self.binary.out.clear()
        self.binary.pending.clear()
        self.color_prompt = True  # a fresh boot asks again
        self._gone_from = time.monotonic() + self.reset_lag_s
        self._gone_until = self._gone_from + self.reset_seconds

    #: The line editor keeps 256 characters and drops the rest without a sound.
    MAX_LINE = 256

    def _command(self, text: str) -> None:
        text = text[:self.MAX_LINE]
        words = text.split()
        if not words:  # a stray space at the prompt: the firmware just redraws it
            self._say("\n" + self._prompt())
            return
        name, args = words[0], words[1:]
        if name in ("W", "w", "P", "p", "G", "g") and self.mode == "HiZ":
            self._finish(text, f"\x07{self.HIZ_REFUSAL}\r\n")
        elif name == "m":
            self._cmd_mode(text, args)
        elif name == "W":
            self._cmd_psu_on(text, args)
        elif name == "w":
            self.psu_enabled = False
            self._finish(text, "Power supply: Disabled\r\n")
        elif name == "P":
            self.pullups = True
            self._finish(text, "Pull-up resistors: Enabled (10K ohms @ 3.3V)\r\n")
        elif name == "p":
            self.pullups = False
            self._finish(text, "Pull-up resistors: Disabled\r\n")
        elif name == "G":
            self._cmd_pwm_on(text, args)
        elif name == "g":
            self._cmd_pwm_off(text, args)
        elif name == "f":
            self._cmd_freq(text, args)
        elif name == "~":
            self._cmd_selftest(text)
        elif name == "sniff" and self.mode in ("I2C", "2WIRE"):
            banner = "I2C Sniffer" if self.mode == "I2C" else "2Wire Sniffer"
            self._stream(text, banner + "\r\nPress x to exit\r\n", ("x",), "",
                         ["".join(self.sniff_lines[i:i + 10])
                          for i in range(0, len(self.sniff_lines), 10)], inline_prompt=True)
        elif name == "sniff" and self.mode == "PS2":
            self._cmd_ps2_sniff(text)
        elif name == "irrx" and self.mode == "INFRARED":
            self._cmd_irrx(text, args)
        elif name == "irtx" and self.mode == "INFRARED":
            self._cmd_irtx(text, text[len("irtx"):].strip())
        elif text.lstrip().startswith(">") and self.mode == "INFRARED" and self.ir_protocol != "RAW":
            self._cmd_ir_write(text)
        elif name == "bluetag" and self.mode == "JTAG":
            self._cmd_bluetag(text, args)
        else:
            self._finish(text, f"Invalid command: {text}. Type ? for help.\r\n")

    IR_SENSORS = {"38b": "38kHz barrier", "38d": "36-40kHz demodulator", "56d": "56kHz demodulator"}

    def _cmd_irrx(self, text: str, args) -> None:
        sensor = args[args.index("-s") + 1].lower() if "-s" in args[:-1] else "38d"
        name = self.IR_SENSORS.get(sensor, self.IR_SENSORS["38d"])
        banner = ("No file specified, packets cannot be saved\r\nRX sensor: %s\r\n"
                  "\r\nListening for IR packets (x to exit)...\r\n" % name)
        advance = []   # a space at the menu asks for the next frame

        def frames():
            for i, air in enumerate(list(self.ir_frames)):
                while i and not advance:
                    yield ""
                if advance:
                    advance.pop()
                pairs = (air.count(",") + 1) // 2
                carrier = int(air[1:air.index(":")])
                yield ("\r\n%s;\r\n\r\nModulation frequency %dkHz, %d MARK/SPACE pairs\r\n\r\n"
                       "'r' or 't' to re-transmit, space for next, 'x' to exit > "
                       % (air, carrier, pairs))

        self._stream(text, banner, ("x",), "Exiting...\r\n", frames())
        self._streaming["on_key"] = lambda k: advance.append(1) if k == " " else None

    def _cmd_irtx(self, text: str, air: str) -> None:
        found = re.fullmatch(r"\$(\d+):((?:\d+,)+)", air)
        if not found:
            problem = ("Unable to find start of data ($) in AIR packet" if not air.startswith("$")
                       else "Unable to find modulation frequency (:) in AIR packet" if ":" not in air
                       else "Unable to find end of MARK/SPACE data (,) in AIR packet")
            self._finish(text, "\x07\r\nTransmitting from command line\r\n%s\r\n"
                         "Error parsing AIR packet\r\n" % problem)
            return
        values = found.group(2).split(",")[:-1]
        pairs = (len(values) + 1) // 2
        if pairs > 127:
            self._finish(text, "\x07\r\nTransmitting from command line\r\nToo many MARK/SPACE "
                         "pairs in AIR packet, max 127\r\nError parsing AIR packet\r\n")
            return
        self.ir_sent.append(("raw", air))
        self._finish(text, "\r\nTransmitting from command line\r\n\r\n%s;\r\n\r\n"
                     "Parsed AIR packet: modulation frequency %dkHz, %d MARK/SPACE pairs\r\n"
                     "Transmitting...done\r\n" % (air, int(found.group(1)), pairs))

    def _cmd_ir_write(self, text: str) -> None:
        sent = []
        for word in text.lstrip()[1:].split():
            try:
                value = int(word, 0)
            except ValueError:
                self._finish(text, "\x07\r\nError: invalid number %s\r\n" % word)
                return
            self.ir_sent.append((self.ir_protocol.lower(), value))
            sent.append(value | 0x3000 if self.ir_protocol == "RC5" else value)
        # _finish adds the CRLF after the echo: the firmware prints "\r\n\r\nTX: ...16 \r\n"
        self._finish(text, "\r\nTX: %s\r\n" % "".join("0x%04X.16 " % v for v in sent))

    PS2_BANNER = ("\r\npico-ps2-sniffer started! for Bus Pirate\r\n"
                  "https://github.com/therealdreg/pico-ps2-sniffer\r\n"
                  "MIT License David Reguera Garcia aka Dreg\r\n"
                  "---------------------------------------------------------------\r\n\r\n")

    def _cmd_ps2_sniff(self, text: str) -> None:
        if self.ps2_psu_error is not None:
            self._finish(text, "\r\nPSU ERROR CODE %d\r\n" % self.ps2_psu_error)
            return
        self.psu_enabled, self.psu_mv, self.psu_ma = True, 5000, 400
        self.psu_tripped = False
        self.pullups = True
        ready = "\r\nPress 'q' to exit\r\n\r\nSniffing...\r\n\r\n"
        # Five empty 20 ms chunks are the 0.1 s drain before the ready line.
        self._stream(text, "\r\nPSU 5v Enabled\r\n" + self.PS2_BANNER, ("q", "Q"),
                     "\r\n\r\nexit...\r\n", [""] * 5 + [ready] + list(self.ps2_lines),
                     drain=0.1)

    def _cmd_mode(self, text: str, args) -> None:
        match = next((m for m in self.TERMINAL_MODES if args and m.lower() == args[0].lower()), None)
        if match is None:
            self._finish(text, "\x07\r\nError: Invalid option\r\n")
            return
        if match == "I2C" and "-s" not in args and "i2c" in self.saved_modes:
            self._ask(text, "\r\nMode: I2C\r\n\r\nUse previous settings?\r\n"
                      "Speed: 400kHz\r\n\r\ny/n, x to exit (Y) >", "i2c-previous")
            return
        self._set_mode(match)
        if match == "INFRARED" and "-p" in args[:-1]:
            self.ir_protocol = args[args.index("-p") + 1].upper()
        self._finish(text, f"\r\nMode: {match}")

    def _cmd_psu_on(self, text: str, args) -> None:
        try:
            volts = float(args[0]) if args else None
            ma = float(args[1]) if len(args) > 1 else 300.0
        except ValueError:
            volts, ma = -1.0, 300.0
        if volts is None or not 0.8 <= volts <= 5.0:
            note = ("" if volts is None else
                    f"volts out of range: {volts:.2f}, expected 0.80 to 5.00\r\n")
            self._ask(text, note + "Voltage, 0.8-5.0volts\r\nx to exit (3.30) >", "w-volts")
            return
        if not 0 <= ma <= 500:
            self._finish(text, f"current out of range: {ma:.1f}, expected 0.0 to 500.0\r\n")
            return
        mv = int(round(volts * 1000))
        self.psu_mv, self.psu_ma = mv, int(ma)
        uv = mv * 9 // 10
        body = (f"{volts:.2f}V requested, closest value: {volts:.2f}V\r\n"
                f"{ma:.1f}mA requested, closest value: {ma:.1f}mA\r\n"
                f"Undervoltage limit: {uv // 1000}.{uv % 1000 // 100}V (10%)\r\n")
        if self.trip_next_w or self.over_limit():
            self.trip_next_w = False
            self.psu_enabled, self.psu_tripped = False, True
            self._finish(text, body + "\r\nPower supply:  Enabled\r\n"
                         "\x07\r\nError: Current over limit, power supply disabled\r\n")
            return
        self.psu_enabled, self.psu_tripped = True, False
        self._finish(text, body + "\r\nPower supply:  Enabled\r\n"
                     f"Vreg output: {mv // 1000}.{mv % 1000 // 100}V, "
                     f"Vref/Vout pin: {mv // 1000}.{mv % 1000 // 100}V, "
                     f"Current: {self.load_ma}.0mA\r\n")

    # Self-test: ``~`` (research doc section 4).

    def _cmd_selftest(self, text: str) -> None:
        if self.mode != "HiZ":
            self._finish(text, "Selftest only available in HiZ mode\r\n")
            return
        self._selftest_errors = 0
        if not self.nand_formatted:
            self._ask(text, "No file system!\r\nFormat the Bus Pirate NAND flash?\r\n"
                      "ALL DATA WILL BE DESTROYED.\r\ny/n >", "selftest-format")
            return
        self._selftest_body(text, "")

    def _selftest_body(self, echo: str, _unused: str) -> None:
        self._say(f"{echo}\x1b[0K\r\n")
        out = ("SELF TEST STARTING\r\nDISABLE IRQ: OK\r\n"
               "ADC SUBSYSTEM: VUSB  4.98V OK\r\nFLASH STORAGE: OK\r\nPSU ENABLE: OK\r\n"
               "VREG==VOUT:  3300 = 3300 OK\r\n"
               "BIO FLOAT TEST (SHOULD BE 0/<0.30V)\r\n")
        out += "".join(f"BIO{n} FLOAT: 0/0.00V OK\r\n" for n in range(8))
        for fault in self.selftest_faults:
            out += fault + "\r\n"
            self._selftest_errors += 1
        out += "BIO HIGH TEST (SHOULD BE >3.00V)\r\n"
        out += "".join(f"BIO{n} HIGH: 3.30V OK\r\n" for n in range(8))
        out += "BIO LOW TEST (SHOULD BE <0.30V)\r\n"
        out += "".join(f"BIO{n} LOW: 0.00V OK\r\n" for n in range(8))
        out += ("LA_BPIO TEST (SHOULD BE 1)\r\nTEST RP2350 E9 BUG FIX\r\n"
                "BIO PULL-UP HIGH TEST (SHOULD BE 1/>3.00V)\r\n"
                "BIO PULL-UP LOW TEST (SHOULD BE <0.30V)\r\n"
                "CURRENT OVERRIDE: OK\r\nCURRENT LIMIT TEST: OK\r\n"
                "PUSH BUTTON (SPACE TO SKIP):")
        self.psu_enabled, self.pullups = False, False  # the test ends with both off
        if self.button_pressed:
            self._terminal_state = "prompt"
            self._say(out + " press \r\nPUSH BUTTON (SPACE TO SKIP): release OK\r\n"
                      + self._selftest_summary())
        else:
            self._terminal_state = "selftest-button"
            self._say(out)  # no ETX: the board waits for the button or SPACE

    def _selftest_summary(self) -> str:
        if self._selftest_errors == 0:
            return "\r\nPASS :)\r\n" + self._prompt()
        return f"\r\nERRORS: {self._selftest_errors}\r\nFAIL! :(\r\n" + self._prompt()

    # PWM: G <pin> asks for a frequency, then a duty cycle.

    def _cmd_pwm_on(self, text: str, args) -> None:
        pin = int(args[0]) if args and args[0].isdigit() else 0
        if pin > 7:
            self._finish(text, f"pin out of range: {pin}, expected 0 to 7\r\n")
            return
        if any(p // 2 == pin // 2 for p in self.pwm):
            self._finish(text, f"IO{pin} is not available for PWM generation\r\n")
            return
        self._pwm_pin = pin
        self._ask(text, "\r\nPeriod or frequency (ns, us, ms, Hz, kHz or Mhz) >", "pwm-freq")

    def _pwm_frequency(self, line: str) -> None:
        word = line.strip()
        if word.lower() == "x":
            self._terminal_state = "prompt"
            self._finish("x")
            return
        match = re.fullmatch(r"([0-9.]+)\s*(ns|us|ms|hz|khz|mhz)", word.lower())
        hz = None
        if match:
            value, unit = float(match.group(1)), match.group(2)
            if unit in ("hz", "khz", "mhz"):
                hz = value * {"hz": 1, "khz": 1e3, "mhz": 1e6}[unit]
            elif value:
                hz = 1e9 / (value * {"ns": 1, "us": 1e3, "ms": 1e6}[unit])
        if hz is None or not 7.46 <= hz <= 62.5e6:
            self._ask(word, "\r\nFrequency invalid: 7.46Hz-62.5MHz (134.1ms-16us period)\r\n"
                      "\r\nPeriod or frequency (ns, us, ms, Hz, kHz or Mhz) >", "pwm-freq")
            return
        self._pwm_hz = hz
        self._ask(word, f"\r\nFrequency: {hz:.3f}Hz = {hz:.0f}Hz\r\n"
                  f"\r\nActual frequency: {hz:.0f}Hz\r\n"
                  f"Actual period: {1e9 / hz:.0f}ns\r\n\r\nDuty cycle (%) >", "pwm-duty")

    def _pwm_duty(self, line: str) -> None:
        word = line.strip()
        if word.lower() == "x":
            self._terminal_state = "prompt"
            self._finish("x")
            return
        match = re.fullmatch(r"([0-9.]+)\s*%", word)
        if not match or not 0 <= float(match.group(1)) <= 100:
            self._ask(word, "\r\nDuty cycle (%) >", "pwm-duty")
            return
        duty = float(match.group(1))
        self.pwm[self._pwm_pin] = (self._pwm_hz, duty)
        self._terminal_state = "prompt"
        period_ns = 1e9 / self._pwm_hz
        self._finish(word, f"\r\nDuty cycle: {duty:.2f}% = {period_ns * duty / 100:.0f}ns\r\n"
                     f"Actual duty cycle: {period_ns * duty / 100:.0f}ns\r\n"
                     f"\r\nGenerate frequency: Enabled on IO{self._pwm_pin}\r\n")

    @staticmethod
    def _friendly(value_hz: float) -> str:
        for scale, unit in ((1e6, "MHz"), (1e3, "kHz"), (1.0, "Hz")):
            if value_hz >= scale:
                return f"{value_hz / scale:.2f}{unit}"
        return f"{value_hz:.2f}Hz"

    def _cmd_freq(self, text: str, args) -> None:
        """``f <pin>``: one measurement of ``self.signals[pin]`` (Hz, duty %)."""
        if not args or not args[0].isdigit():
            self._finish(text, "Error: Frequency measurement not active on any IO pins\r\n")
            return
        pin = int(args[0])
        if pin > 7:
            self._finish(text, f"pin out of range: {pin}, expected 0 to 7\r\n")
        elif pin % 2 == 0:
            self._finish(text, f"IO{pin} has no frequency measurement hardware!\r\n"
                         "Freq. measure is currently only possible on odd pins (1,3,5,7).\r\n")
        elif any(p // 2 == pin // 2 for p in self.pwm):
            self._finish(text, f"IO{pin} is unavailable because IO{pin - 1} or IO{pin} is in "
                         "use as a frequency generator (PWM)!\r\n")
        else:
            hz, duty = self.signals.get(pin, (0, 0.0))
            ns = 1e9 / hz if hz else 0.0
            period = (f"{ns / 1e6:.2f}ms" if ns >= 1e6 else
                      f"{ns / 1e3:.2f}us" if ns >= 1e3 else f"{ns:.2f}ns")
            self._finish(text, f"Frequency IO{pin}: {self._friendly(hz)} {period} "
                         f"({hz:.0f}Hz), Duty cycle: {duty:.1f}%\r\n")

    BLUETAG_JTAG_HIT = {
        "pinout": "TDI=IO0 TDO=IO3 TCK=IO4 TMS=IO2 TRST=N/A",
        "device": "0x59602093 (mfg: 'Xilinx', part: 0x9602, ver: 0x5)"}
    BLUETAG_SWD_HIT = {
        "pinout": "SWDIO=IO5 SWCLK=IO6",
        "device": "0x0BC12477 (mfg: 'ARM Ltd', part: 0xbc1, ver: 0x0)"}

    def _cmd_bluetag(self, text: str, args) -> None:
        """``bluetag jtag|swd -c <n> [-d]`` (research doc section 5)."""
        proto = args[0] if args and args[0] in ("jtag", "swd") else None
        if proto is None or "-c" not in args or args.index("-c") + 1 >= len(args):
            self._finish(text, "Specify the number of channels with the -c flag, -h for help\r\n")
            return
        low, high = (4, 8) if proto == "jtag" else (2, 8)
        count = int(args[args.index("-c") + 1]) if args[args.index("-c") + 1].isdigit() else 0
        if not low <= count <= high:
            self._finish(text, f"Invalid number of {proto.upper()} channels (min {low}, max {high})\r\n")
            return
        body = ("Disabled pin pulsing\r\n" if "-d" in args and proto == "jtag" else "")
        body += f"Number of channels set to: {count}\r\n"
        body += "\r     Progress: [" + "#" * 25 + " " * 25 + "] 50.00%"
        body += "\r     Progress: [" + "#" * 50 + "] 100.00%"
        hit = self.bluetag_hit.get(proto)
        if hit is None:
            body += f"\r\n\r\n\tNo {proto.upper()} devices found. Please try again.\r\n"
        else:
            body += (f"\r\n\r\n     [  Pinout  ]  {hit['pinout']} \r\n\r\n"
                     f"     [ Device 0 ]  {hit['device']}\r\n\n")
        self._finish(text, body)

    def _cmd_pwm_off(self, text: str, args) -> None:
        if not self.pwm:
            self._finish(text, "Frequency generation not active on any IO pins!")
            return
        pin = int(args[0]) if args and args[0].isdigit() else next(iter(self.pwm))
        if pin not in self.pwm:
            self._finish(text, f"Error: frequency generator not active on IO{pin}\r\n")
            return
        del self.pwm[pin]
        self._finish(text, f"Generate frequency: Disabled on IO{pin}\r\n")
