"""A simulated Bus Pirate 6: its BPIO2 port and its terminal port.

Built from what the real board did on 2026-10-14 (see the design spec), so
the dashboard and the tests can run with no hardware. It answers only what
the driver asks; it is not a firmware emulator.
"""

from __future__ import annotations

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


class FakeBp6:
    TERMINAL = "/dev/cu.usbmodem6buspirate1"
    BINARY = "/dev/cu.usbmodem6buspirate3"

    def __init__(self, bpio_active: bool = True, color_prompt: bool = False, load_ma: int = 12) -> None:
        self.bpio_active = bpio_active
        self.color_prompt = color_prompt
        self.load_ma = load_ma
        self.mode = "HiZ"
        self.psu_enabled = False
        self.psu_tripped = False
        self.psu_mv = 0
        self.psu_ma = 0
        self.pullups = False
        self.requests = []
        device = bytearray(256)
        device[0xD0] = 0x58
        self.i2c_devices = {0x76: device}
        self._pointer = {0x76: 0}
        self.flash = FakeFlash()
        self.onewire_rom = DS18B20_ROM
        self.uart_echo = True
        self._spi_written, self._spi_read = bytearray(), 0
        self._reader = FrameReader()
        self._terminal_state = "prompt"
        self.binary = _Port(self._on_binary)
        self.terminal = _Port(self._on_terminal)

    def factory(self, terminal_port: str = TERMINAL, binary_port: str = BINARY):
        def make(port, baudrate, timeout):
            if port == terminal_port:
                self.terminal.is_open = True
                return self.terminal
            self.binary.is_open = True
            return self.binary
        return make

    # -- the target ----------------------------------------------------------

    def uart_receive(self, data: bytes) -> None:
        self.binary.out += frame(self._data_response(bytes(data), is_async=True))

    # -- BPIO2 ---------------------------------------------------------------

    def _on_binary(self, data: bytes) -> None:
        for raw in self._reader.feed(data):
            if not self.bpio_active:
                continue
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
                reply = self._data(request)
            else:
                raise AssertionError("a RequestPacket with no contents was sent")
            self.binary.out += frame(reply)

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
        adc = [self.psu_mv if (self.pullups and self.psu_enabled) else 0] * 8
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
        _ST.StatusResponseAddPsuMeasuredMv(b, self.psu_mv if self.psu_enabled else 22)
        _ST.StatusResponseAddPsuMeasuredMa(b, self.load_ma if self.psu_enabled else 1)
        _ST.StatusResponseAddPsuCurrentError(b, self.psu_tripped)
        _ST.StatusResponseAddPullupEnabled(b, self.pullups)
        _ST.StatusResponseAddAdcMv(b, adc_vec)
        _ST.StatusResponseAddLedCount(b, 18)
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
                self.psu_mv, self.psu_ma = request.PsuSetMv(), request.PsuSetMa()
                self.psu_tripped = 0 < self.psu_ma < self.load_ma
                self.psu_enabled = not self.psu_tripped
        if request.PsuDisable():
            self.psu_enabled = False
            self.psu_tripped = False
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
            if len(written) > 1:
                self._pointer[address] = written[1]
                for offset, byte in enumerate(written[2:]):
                    device[(written[1] + 1 + offset) & 0xFF] = byte
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
            if count:
                whole = self.flash.exchange(bytes(self._spi_written), self._spi_read + count)
                data = whole[self._spi_read:]
                self._spi_read += count
            elif stopped and not self._spi_read and self._spi_written:
                # A write-only command (write enable, program, erase) acts at CS high.
                self.flash.exchange(bytes(self._spi_written), 0)
            return self._data_response(data)
        if self.mode == "1WIRE":
            if started and not self.onewire_rom:
                return self._data_response(b"", error="Protocol request failed")
            if written[:1] == b"\x33":
                return self._data_response(self.onewire_rom[:count])
            return self._data_response(bytes(count))
        if self.mode == "UART":
            if written and self.uart_echo:
                self.uart_receive(written)
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

    def _say(self, text: str) -> None:
        self.terminal.out += text.encode()

    def _on_terminal(self, keys: bytes) -> None:
        if keys == b"\x03":
            self._say("^C\r\n" + ("VT100 compatible color mode? (Y/n)> " if self.color_prompt else "HiZ> "))
            return
        if self.color_prompt:
            if keys in (b"n\r", b"y\r"):
                self.color_prompt = False
                self._say(keys.decode()[0] + "\n\r\n\r\nHiZ> ")
            else:
                self._say("\n\r\n\r\nVT100 compatible color mode? (Y/n)> ")
            return
        line = keys.decode("ascii", "replace")
        if self._terminal_state == "binmode-menu" and line == "2\r":
            self._terminal_state = "binmode-save"
            self._say("2\n\r\n\r\nBinmode selected: BPIO2 flatbuffer interface\r\nSave setting?\r\ny/n > ")
        elif self._terminal_state == "binmode-save" and line in ("n\r", "y\r"):
            self._terminal_state = "prompt"
            self.bpio_active = True
            self._say(line[0] + "\n\r\n\r\nHiZ> ")
        elif line == "binmode\r":
            self._terminal_state = "binmode-menu"
            self._say("binmode\n\r\n 1. SUMP logic analyzer\r\n 2. BPIO2 flatbuffer interface\r\n"
                      "Select binary mode\r\nx to exit (1) > ")
        elif line == "i\r":
            self._say("i\n\r\nBus Pirate 6\r\nFirmware main branch @ unknown (Oct 12 2026 09:04:39)\r\n"
                      "RP2350B with 512KB RAM, 128Mbit FLASH\r\n\r\nHiZ> ")
        elif line == "\r":
            self._say("\n\r\nHiZ> ")
        else:
            self._say(f"{line.strip()}\n\r\nInvalid command: {line.strip()}. Type ? for help.\r\nHiZ> ")
