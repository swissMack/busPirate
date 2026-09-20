"""A byte-level fake of the Bus Pirate's binary protocol, for tests and demos.

It models enough of the firmware's state machine — the terminal, bitbang, and
the I2C, SPI, UART, 1-Wire and raw-wire modes — to exercise the driver and the
dashboard without hardware. Unknown commands raise, so a driver bug fails
loudly instead of silently reading zeros.

Construct it with ``variant="v4"`` to get a device that answers the v4-only
commands and refuses the v3-only ones.
"""

from __future__ import annotations

BANNERS = {
    "v3": (
        "Bus Pirate v3.5\r\n"
        "Firmware v6.1 r1676  Bootloader v4.4\r\n"
        "DEVID:0x0447 REVID:0x3046 (24FJ64GA002 B8)\r\n"
        "http://dangerousprototypes.com\r\n"
        "HiZ>"
    ),
    "v4": (
        "Bus Pirate v4\r\n"
        "Firmware v6.3-beta1 r2151  Bootloader v4.5\r\n"
        "DEVID:0x1019 REVID:0x0003 (24FJ256GB106 A3)\r\n"
        "http://dangerousprototypes.com\r\n"
        "HiZ>"
    ),
    "unknown": "?\r\nHiZ>",
}


class FakeSerial:
    def __init__(
        self,
        i2c_devices=(0x50, 0x68),
        spi_fill=0xA5,
        variant="v3",
        banner=None,
        voltage_counts=512,
        frequency=1000,
    ):
        self.i2c_devices = set(i2c_devices)
        self.spi_fill = spi_fill
        self.variant = variant
        self.banner = BANNERS.get(variant, BANNERS["unknown"]) if banner is None else banner
        self.voltage_counts = voltage_counts
        self.frequency = frequency

        self.state = "term"
        self.written = bytearray()  # everything the driver sent, for asserts
        self.pins = 0x00  # last pin state written
        self.uart_rx = bytearray()  # queue bytes here to simulate a talker
        #: Set True to simulate a target already driving the VPU pin, which
        #: makes a v4 refuse to connect its own pull-up rail.
        self.vextern_powered = False
        self._in = bytearray()  # bytes awaiting parsing
        self._out = bytearray()  # bytes awaiting the driver's read()
        self._term_line = bytearray()
        self._i2c_expect_address = False
        self._i2c_read_value = 0x00
        self._echoing = False
        self.closed = False

    # -- serial.Serial surface --------------------------------------------

    def write(self, data: bytes) -> int:
        self.written += data
        self._in += data
        self._process()
        return len(data)

    def read(self, count: int) -> bytes:
        if self._echoing and self.uart_rx:
            self._out += self.uart_rx
            self.uart_rx.clear()
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
        return getattr(self, f"_state_{self.state}")(self._in[0])

    def _supports(self, capability: str) -> bool:
        if capability in ("pullup_voltage", "extended_aux"):
            return self.variant == "v4"
        if capability == "self_test":
            return self.variant == "v3"
        return True

    # -- terminal ----------------------------------------------------------

    def _state_term(self, cmd: int) -> int:
        if cmd == 0x00:
            self.state = "bbio"
            self._term_line.clear()
            self._out += b"BBIO1"
            return 1
        if cmd in (0x0A, 0x0D):
            line = self._term_line.decode("ascii", "replace").strip().lower()
            self._term_line.clear()
            self._out += (self.banner if line == "i" else "HiZ>").encode()
            return 1
        self._term_line.append(cmd)
        return 1

    # -- bitbang -----------------------------------------------------------

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
        elif cmd == 0x05:
            self.state = "rawwire"
            self._out += b"RAW1"
        elif cmd == 0x0F:
            self.state = "term"
        elif cmd in (0x10, 0x11):  # self-test
            if not self._supports("self_test"):
                raise AssertionError("v4 hardware has no binary self-test")
            self.state = "selftest"
            self._out += b"\x00"  # zero errors
        elif cmd == 0x12:  # PWM setup: the command plus 5 config bytes
            if len(self._in) < 6:
                return 0
            self._out += b"\x01"
            return 6
        elif cmd == 0x13:
            self._out += b"\x01"
        elif cmd == 0x14:  # voltage probe
            self._out += int(self.voltage_counts).to_bytes(2, "big")
        elif cmd == 0x16:  # frequency
            self._out += int(self.frequency).to_bytes(4, "big")
        elif 0x40 <= cmd <= 0x5F:  # pin directions
            self._out += bytes([self.pins])
        elif 0x80 <= cmd <= 0xFF:  # pin states
            self.pins = cmd & 0x7F
            self._out += bytes([self.pins])
        else:
            raise AssertionError(f"unexpected bitbang command 0x{cmd:02X}")
        return 1

    def _state_selftest(self, cmd: int) -> int:
        self.state = "bbio"
        self._out += b"\x01"
        return 1

    # -- I2C ---------------------------------------------------------------

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
        if cmd in (0x03, 0x06, 0x07) or 0x60 <= cmd <= 0x63:
            if cmd == 0x03:
                self._i2c_expect_address = False
            self._out += b"\x01"
            return 1
        if 0x50 <= cmd <= 0x53:  # pull-up voltage select, v4 only
            if not self._supports("pullup_voltage"):
                raise AssertionError("v3 hardware has no pull-up voltage select")
            # 0x00 means "voltage already present on VEXTERN", no connection made.
            connecting = (cmd & 0x03) != 0
            self._out += b"\x00" if (connecting and self.vextern_powered) else b"\x01"
            return 1
        if 0x40 <= cmd <= 0x4F:  # configure peripherals
            self._out += b"\x01"
            return 1
        if cmd == 0x0F:  # start bus sniffer; any byte exits
            self.state = "i2c_sniffer"
            return 1
        if cmd == 0x04:  # read byte
            self._out += bytes([self._i2c_read_value])
            self._i2c_read_value = (self._i2c_read_value + 1) & 0xFF
            return 1
        if cmd == 0x09:  # extended AUX, v4 only
            if len(self._in) < 2:
                return 0
            if not self._supports("extended_aux"):
                raise AssertionError("v3 hardware has no extended AUX command")
            self._out += b"\x01"
            return 2
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
            # The firmware sends its own start, so the first written byte is
            # the address. With nothing written it cannot address anyone.
            acked = write_count > 0 and (self._in[5] >> 1) in self.i2c_devices
            if acked:
                self._out += b"\x01" + bytes(i & 0xFF for i in range(read_count))
            else:
                self._out += b"\x00"
            return 5 + write_count
        raise AssertionError(f"unexpected I2C command 0x{cmd:02X}")

    def _state_i2c_sniffer(self, cmd: int) -> int:
        self.state = "i2c"
        self._out += b"\x01"
        return 1

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

    # -- SPI ---------------------------------------------------------------

    def _state_spi(self, cmd: int) -> int:
        if cmd == 0x00:
            self.state = "bbio"
            self._out += b"BBIO1"
            return 1
        if cmd == 0x01:
            self._out += b"SPI1"
            return 1
        if (
            cmd in (0x02, 0x03)
            or 0x40 <= cmd <= 0x4F
            or 0x60 <= cmd <= 0x67
            or 0x80 <= cmd <= 0x8F
        ):
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

    # -- UART --------------------------------------------------------------

    def _state_uart(self, cmd: int) -> int:
        if cmd == 0x00:
            self.state = "bbio"
            self._echoing = False
            self._out += b"BBIO1"
            return 1
        if cmd == 0x01:
            self._out += b"ART1"
            return 1
        if cmd in (0x02, 0x03):
            self._echoing = cmd == 0x02
            self._out += b"\x01"
            return 1
        if 0x40 <= cmd <= 0x4F or 0x60 <= cmd <= 0x6F or 0x80 <= cmd <= 0x9F:
            self._out += b"\x01"
            return 1
        if cmd == 0x07:  # manual baud rate, 2 more bytes
            if len(self._in) < 3:
                return 0
            self._out += b"\x01"
            return 3
        if 0x10 <= cmd <= 0x1F:
            count = (cmd & 0x0F) + 1
            if len(self._in) < 1 + count:
                return 0
            self._out += b"\x01" + b"\x01" * count
            return 1 + count
        raise AssertionError(f"unexpected UART command 0x{cmd:02X}")

    # -- 1-Wire ------------------------------------------------------------

    def _state_onewire(self, cmd: int) -> int:
        if cmd == 0x00:
            self.state = "bbio"
            self._out += b"BBIO1"
            return 1
        if cmd == 0x01:
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

    # -- raw wire ----------------------------------------------------------

    def _state_rawwire(self, cmd: int) -> int:
        if cmd == 0x00:
            self.state = "bbio"
            self._out += b"BBIO1"
            return 1
        if cmd == 0x01:
            self._out += b"RAW1"
            return 1
        if cmd in (0x02, 0x03, 0x04, 0x05, 0x09, 0x0A, 0x0B, 0x0C, 0x0D):
            self._out += b"\x01"
            return 1
        if cmd in (0x06, 0x07, 0x08):
            self._out += b"\x01"
            return 1
        if 0x40 <= cmd <= 0x4F or 0x60 <= cmd <= 0x63 or 0x80 <= cmd <= 0x8F:
            self._out += b"\x01"
            return 1
        if 0x10 <= cmd <= 0x1F:
            count = (cmd & 0x0F) + 1
            if len(self._in) < 1 + count:
                return 0
            self._out += b"\x01" + b"\x01" * count
            return 1 + count
        raise AssertionError(f"unexpected raw-wire command 0x{cmd:02X}")


def fake_factory(fake: FakeSerial):
    """Build a ``serial_factory`` for :class:`BusPirate` returning ``fake``."""

    def factory(port, baudrate, timeout):
        return fake

    return factory
