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
        self._terminal_lines = []
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
        self.binary = _BinaryPort(self)
        self.terminal = _Port(self._on_terminal)

    def factory(self, terminal_port: str = TERMINAL, binary_port: str = BINARY):
        def make(port, baudrate, timeout):
            if port == terminal_port:
                self.terminal.is_open = True
                # Seen on the real board: the first BPIO2 reply after the
                # terminal port is opened comes seconds late.
                self._delay_next_reply = max(self._delay_next_reply, self.terminal_reply_delay)
                return self.terminal
            self.binary.is_open = True
            self._delay_next_reply = self.first_reply_delay
            return self.binary
        return make

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
    TERMINAL_MODES = ("HiZ", "DIO", "JTAG", "I2C")

    def lines_received(self) -> List[bytes]:
        """Every write the terminal port received, in order."""
        return list(self._terminal_lines)

    def _say(self, text: str) -> None:
        self.terminal.out += text.encode()

    def _prompt(self) -> str:
        return f"\r\n{self.mode}> \x03"

    def _finish(self, echo: str, body: str = "") -> None:
        """Echo (with the redraw noise the real line editor adds), output, prompt."""
        self._say(f"{echo}\x1b[0K\r\n{body}{self._prompt()}")

    def _ask(self, echo: str, body: str, state: str) -> None:
        self._terminal_state = state
        self._say(f"{echo}\x1b[0K\r\n{body}\x03")

    def _set_mode(self, name: str) -> None:
        self.mode = name
        self.psu_enabled = False   # the HiZ setup of every mode switches these off
        self.pullups = False
        self.pwm.clear()

    def _on_terminal(self, keys: bytes) -> None:
        self._terminal_lines.append(bytes(keys))
        if self.terminal_wedged:
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
        if state == "binmode-menu" and line == "2\r":
            self._terminal_state = "binmode-save"
            self._say("2\n\r\n\r\nBinmode selected: BPIO2 flatbuffer interface\r\nSave setting?\r\ny/n > ")
        elif state == "binmode-save" and line in ("n\r", "y\r"):
            self._terminal_state = "prompt"
            self.bpio_active = True
            self._bpio_ready_at = time.monotonic() + self.bpio_settle
            self._say(line[0] + "\n\r\n\r\n" + self._prompt().lstrip("\r\n"))
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
        elif state == "pwm-freq":
            self._pwm_frequency(line)
        elif state == "pwm-duty":
            self._pwm_duty(line)
        elif line == "binmode\r":
            self._terminal_state = "binmode-menu"
            self._say("binmode\n\r\n 1. SUMP logic analyzer\r\n 2. BPIO2 flatbuffer interface\r\n"
                      "Select binary mode\r\nx to exit (1) > ")
        elif line == "i\r":
            binmode = "BPIO2 flatbuffer interface" if self.bpio_active else "SUMP logic analyzer"
            self._say("i\n\r\nBus Pirate 6\r\nFirmware main branch @ unknown (Oct 12 2026 09:04:39)\r\n"
                      "RP2350B with 512KB RAM, 128Mbit FLASH\r\n"
                      f"Active binmode: {binmode}\r\nActive mode: {self.mode}\r\n" + self._prompt())
        elif line == "\r":
            self._say("\n" + self._prompt())
        else:
            self._command(line.strip())

    def _command(self, text: str) -> None:
        words = text.split()
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
        else:
            self._finish(text, f"Invalid command: {text}. Type ? for help.\r\n")

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
