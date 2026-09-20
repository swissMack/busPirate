"""A byte-level fake of the Bus Pirate's binary protocol, for tests.

It models enough of the firmware's state machine — bitbang, I2C and SPI — to
exercise the driver without hardware. Unknown commands raise, so a test fails
loudly rather than silently reading zeros.
"""

from __future__ import annotations


class FakeSerial:
    def __init__(self, i2c_devices=(0x50, 0x68), spi_fill=0xA5):
        self.i2c_devices = set(i2c_devices)
        self.spi_fill = spi_fill
        self.state = "term"
        self.written = bytearray()  # everything the driver sent, for asserts
        self._in = bytearray()  # bytes awaiting parsing
        self._out = bytearray()  # bytes awaiting the driver's read()
        self._i2c_expect_address = False
        self._i2c_read_value = 0x00
        self.closed = False

    # -- serial.Serial surface --------------------------------------------

    def write(self, data: bytes) -> int:
        self.written += data
        self._in += data
        self._process()
        return len(data)

    def read(self, count: int) -> bytes:
        taken = self._out[:count]
        del self._out[:count]
        return bytes(taken)

    def flush(self) -> None:
        pass

    def reset_input_buffer(self) -> None:
        self._out.clear()

    def close(self) -> None:
        self.closed = True

    # -- emulation ---------------------------------------------------------

    def _process(self) -> None:
        while self._in:
            consumed = self._step()
            if consumed == 0:  # waiting for the rest of a multi-byte command
                return
            del self._in[:consumed]

    def _step(self) -> int:
        cmd = self._in[0]
        handler = getattr(self, f"_state_{self.state}")
        return handler(cmd)

    def _state_term(self, cmd: int) -> int:
        if cmd == 0x00:
            self.state = "bbio"
            self._out += b"BBIO1"
            return 1
        return 1  # terminal mode swallows anything else

    def _state_bbio(self, cmd: int) -> int:
        if cmd == 0x00:
            self._out += b"BBIO1"
        elif cmd == 0x01:
            self.state = "spi"
            self._out += b"SPI1"
        elif cmd == 0x02:
            self.state = "i2c"
            self._out += b"I2C1"
        elif cmd == 0x03:
            self.state = "uart"
            self._out += b"ART1"
        elif cmd == 0x04:
            self.state = "onewire"
            self._out += b"1W01"
        elif cmd == 0x0F:
            self.state = "term"
        elif 0x40 <= cmd <= 0x5F or 0x80 <= cmd <= 0xFF:
            self._out += b"\x00"  # read-back pin states
        else:
            raise AssertionError(f"unexpected bitbang command 0x{cmd:02X}")
        return 1

    def _state_i2c(self, cmd: int) -> int:
        if cmd == 0x00:
            self.state = "bbio"
            self._out += b"BBIO1"
            return 1
        if cmd == 0x01:
            self._out += b"I2C1"
            return 1
        if cmd == 0x02:  # start
            self._i2c_expect_address = True
            self._out += b"\x01"
            return 1
        if cmd in (0x03, 0x06, 0x07) or 0x40 <= cmd <= 0x4F or 0x60 <= cmd <= 0x63:
            if cmd == 0x03:
                self._i2c_expect_address = False
            self._out += b"\x01"
            return 1
        if cmd == 0x04:  # read byte
            self._out += bytes([self._i2c_read_value])
            self._i2c_read_value = (self._i2c_read_value + 1) & 0xFF
            return 1
        if 0x10 <= cmd <= 0x1F:  # bulk write
            count = (cmd & 0x0F) + 1
            if len(self._in) < 1 + count:
                return 0
            payload = bytes(self._in[1 : 1 + count])
            self._out += b"\x01" + self._i2c_write_status(payload)
            return 1 + count
        if cmd == 0x08:  # write then read
            if len(self._in) < 5:
                return 0
            write_count = int.from_bytes(self._in[1:3], "big")
            read_count = int.from_bytes(self._in[3:5], "big")
            if len(self._in) < 5 + write_count:
                return 0
            address = self._in[5] >> 1 if write_count else None
            if address in self.i2c_devices:
                self._out += b"\x01" + bytes(
                    (i & 0xFF) for i in range(read_count)
                )
            else:
                self._out += b"\x00"
            return 5 + write_count
        raise AssertionError(f"unexpected I2C command 0x{cmd:02X}")

    def _i2c_write_status(self, payload: bytes) -> bytes:
        status = bytearray()
        for byte in payload:
            if self._i2c_expect_address:
                self._i2c_expect_address = False
                acked = (byte >> 1) in self.i2c_devices
            else:
                acked = True
            status.append(0x00 if acked else 0x01)
        return bytes(status)

    def _state_spi(self, cmd: int) -> int:
        if cmd == 0x00:
            self.state = "bbio"
            self._out += b"BBIO1"
            return 1
        if cmd == 0x01:
            self._out += b"SPI1"
            return 1
        if cmd in (0x02, 0x03) or 0x40 <= cmd <= 0x4F or 0x60 <= cmd <= 0x67 or 0x80 <= cmd <= 0x8F:
            self._out += b"\x01"
            return 1
        if 0x10 <= cmd <= 0x1F:
            count = (cmd & 0x0F) + 1
            if len(self._in) < 1 + count:
                return 0
            self._out += b"\x01" + bytes([self.spi_fill]) * count
            return 1 + count
        if cmd in (0x04, 0x05):
            if len(self._in) < 5:
                return 0
            write_count = int.from_bytes(self._in[1:3], "big")
            read_count = int.from_bytes(self._in[3:5], "big")
            if len(self._in) < 5 + write_count:
                return 0
            self._out += b"\x01" + bytes([self.spi_fill]) * read_count
            return 5 + write_count
        raise AssertionError(f"unexpected SPI command 0x{cmd:02X}")

    def _state_uart(self, cmd: int) -> int:
        if cmd == 0x00:
            self.state = "bbio"
            self._out += b"BBIO1"
            return 1
        if cmd == 0x01:
            self._out += b"ART1"
            return 1
        if cmd in (0x02, 0x03) or 0x40 <= cmd <= 0x4F or 0x60 <= cmd <= 0x6F or 0x80 <= cmd <= 0x9F:
            self._out += b"\x01"
            return 1
        if 0x10 <= cmd <= 0x1F:
            count = (cmd & 0x0F) + 1
            if len(self._in) < 1 + count:
                return 0
            self._out += b"\x01" + b"\x01" * count
            return 1 + count
        raise AssertionError(f"unexpected UART command 0x{cmd:02X}")

    def _state_onewire(self, cmd: int) -> int:
        if cmd == 0x00:
            self.state = "bbio"
            self._out += b"BBIO1"
            return 1
        if cmd in (0x01,):
            self._out += b"1W01"
            return 1
        if cmd == 0x02 or 0x40 <= cmd <= 0x4F:
            self._out += b"\x01"
            return 1
        if cmd == 0x04:
            self._out += b"\x28"
            return 1
        if cmd in (0x08, 0x09):
            found = b"\x28\x11\x22\x33\x44\x55\x66\x77"
            self._out += found + b"\xff" * (8 * 31)
            return 1
        if 0x10 <= cmd <= 0x1F:
            count = (cmd & 0x0F) + 1
            if len(self._in) < 1 + count:
                return 0
            self._out += b"\x01" + b"\x01" * count
            return 1 + count
        raise AssertionError(f"unexpected 1-Wire command 0x{cmd:02X}")


def fake_factory(fake: FakeSerial):
    """Build a ``serial_factory`` for :class:`BusPirate` returning ``fake``."""

    def factory(port, baudrate, timeout):
        return fake

    return factory
