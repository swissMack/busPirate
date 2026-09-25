"""A byte-level fake of the Bus Pirate's binary protocol, for tests and demos.

It models enough of the firmware's state machine — the terminal, bitbang, and
the I2C, SPI, UART, 1-Wire and raw-wire modes — to exercise the driver and the
dashboard without hardware. Unknown commands raise, so a driver bug fails
loudly instead of silently reading zeros.

Construct it with ``variant="v4"`` to get a device that answers the v4-only
commands and refuses the v3-only ones.
"""

from __future__ import annotations

import time

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


class FakeFlash:
    """A 25-series SPI NOR flash, enough of one to exercise the write path.

    Programming only clears bits and erasing only works in 4 KB sectors, the
    same as the real thing — so a test that forgets to erase fails here too.
    """

    JEDEC = bytes([0xEF, 0x40, 0x18])  # Winbond, 16 MB
    SECTOR = 4096
    PAGE = 256

    def __init__(self, size=1 << 20):
        self.size = size
        self.memory = bytearray(b"\xff" * size)
        self.write_enabled = False
        self.erases = 0
        self.programs = 0

    def status(self) -> int:
        return 0x02 if self.write_enabled else 0x00  # never busy

    def exchange(self, written: bytes, read_count: int) -> bytes:
        if not written:
            return b"\x00" * read_count
        command, body = written[0], written[1:]
        if command == 0x9F:
            return (self.JEDEC + b"\x00" * read_count)[:read_count]
        if command == 0x05:
            return bytes([self.status()]) * read_count
        if command == 0x06:
            self.write_enabled = True
            return b""
        if command == 0x04:
            self.write_enabled = False
            return b""
        if command == 0x03:
            start = int.from_bytes(body[:3], "big")
            return bytes(self.memory[start : start + read_count]).ljust(read_count, b"\xff")
        if command == 0x02:
            start = int.from_bytes(body[:3], "big")
            payload = body[3:]
            if not self.write_enabled:
                return b""  # silently ignored, exactly as the hardware does
            if (start % self.PAGE) + len(payload) > self.PAGE:
                raise AssertionError("page program crossed a page boundary")
            for index, byte in enumerate(payload):
                # Programming can only turn 1s into 0s.
                self.memory[start + index] &= byte
            self.programs += 1
            self.write_enabled = False
            return b""
        if command == 0x20:
            start = int.from_bytes(body[:3], "big")
            if self.write_enabled:
                base = start - (start % self.SECTOR)
                self.memory[base : base + self.SECTOR] = b"\xff" * self.SECTOR
                self.erases += 1
            self.write_enabled = False
            return b""
        if command == 0xC7:
            if self.write_enabled:
                self.memory[:] = b"\xff" * self.size
                self.erases += 1
            self.write_enabled = False
            return b""
        raise AssertionError(f"fake flash got an unknown command 0x{command:02X}")


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
        #: Set to a FakeFlash to make SPI behave like a real flash chip.
        self.flash = None
        self.variant = variant
        self.banner = BANNERS.get(variant, BANNERS["unknown"]) if banner is None else banner
        self.voltage_counts = voltage_counts
        self.frequency = frequency

        #: Seconds between simulated sniffer bursts.
        self.burst_interval = 0.05
        self._last_burst = 0.0
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
        self._nulls = 0  # consecutive nulls seen at the terminal
        self._i2c_expect_address = False
        self._i2c_read_value = 0x00
        self._aux_pin = "aux"  # last pin selected via extended AUX 0x10/0x20
        self._aux_levels = {"aux": 0, "cs": 0}
        self._echoing = False
        self.closed = False

    # -- serial.Serial surface --------------------------------------------

    def write(self, data: bytes) -> int:
        self.written += data
        self._in += data
        self._process()
        return len(data)

    # A short, realistic burst for each streaming mode, replayed while the
    # stream runs so the dashboard has something to draw.
    SNIFFER_BURSTS = {
        "i2c_sniffer": b"[\\\xa0+\\\x00+\\\x2a+]",
        "spi_sniffer": b"[\\\x9f\xff\\\x00\xef\\\x00\x40\\\x00\x18]",
        "voltage_stream": b"\x02\x00\x01\xf4",
        "uart_bridge": b"bridged\r\n",
    }

    def read(self, count: int) -> bytes:
        if self._echoing and self.uart_rx:
            self._out += self.uart_rx
            self.uart_rx.clear()
        burst = self.SNIFFER_BURSTS.get(self.state)
        if burst and not self._out:
            # Pace it like a real bus rather than a firehose, so the demo is
            # readable and tests do not spin.
            now = time.monotonic()
            if now - self._last_burst >= self.burst_interval:
                self._last_burst = now
                self._out += burst
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

    # -- a menu question in the terminal ----------------------------------

    def leave_at_menu(self, questions: int = 1) -> None:
        """Park the fake half way through a terminal menu, as a board is left
        when someone disconnects while choosing a mode: ``questions`` more
        answers are wanted before it is back at a prompt."""
        self._menu_questions = questions
        self.state = "menu"

    def _state_menu(self, cmd: int) -> int:
        # The firmware takes Enter as "accept the default" and answers
        # anything it cannot use with BEL — a real v4 answered each 0x00 of a
        # binary-mode knock with 0x07.
        if cmd in (0x0A, 0x0D):
            self._menu_questions -= 1
            if self._menu_questions <= 0:
                self.state = "term"
                self._out += b"\r\nReady\r\nSPI>"
            else:
                self._out += b"\r\n(1)>"
        else:
            self._out.append(0x07)
        return 1

    # -- terminal ----------------------------------------------------------

    def _state_term(self, cmd: int) -> int:
        # The firmware leaves its terminal only after 20 nulls in a row; any
        # other byte starts the count again. One null alone does nothing,
        # which is what makes a single null a safe probe of which state the
        # board is in.
        if cmd == 0x00:
            self._nulls += 1
            if self._nulls >= 20:
                self._nulls = 0
                self.state = "bbio"
                self._term_line.clear()
                self._out += b"BBIO1"
            return 1
        self._nulls = 0
        # Echo as the firmware does: every key comes back as typed, a
        # backspace as BS-space-BS, and Enter as CR LF ahead of the reply.
        # The dashboard's terminal sends keys one at a time and relies on
        # this echo to show what was typed.
        if cmd in (0x0A, 0x0D):
            line = self._term_line.decode("ascii", "replace").strip().lower()
            self._term_line.clear()
            self._out += b"\r\n" + self._term_reply(line).encode()
            return 1
        if cmd == 0x08:
            if self._term_line:
                self._term_line.pop()
                self._out += b"\x08 \x08"
            return 1
        self._term_line.append(cmd)
        self._out.append(cmd)
        return 1

    def _term_reply(self, line: str) -> str:
        """A short, plausible reply for one completed terminal line.

        These exist for assertions, not firmware fidelity — a few lines is
        plenty for each command.
        """
        if line == "i":
            return self.banner
        if line == "":
            return "HiZ>"
        if line == "?":
            return "General commands\r\n?  help   i  info   v  pin voltages\r\nHiZ>"
        if line == "v":
            return "ADC: 3.30V  VPU: 0.0V\r\nHiZ>"
        return f"command '{line}' not found\r\nHiZ>"

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
            # Both boards reset on this command. A v3 does it on the board
            # (Firmware/binIO.c:150-158); a real v4 (firmware 6.0-a3) did it
            # too — supplies off, and off USB for about half a second, which
            # BusPirate.reopen_if_reenumerated() follows. Model the reset by
            # clearing the peripheral state it clears: the AUX/CS pin model
            # and the pin byte that carries the power and pull-up flags.
            self._aux_pin = "aux"
            self._aux_levels = {"aux": 0, "cs": 0}
            self.pins = 0x00
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
        elif cmd == 0x15:  # continuous voltage
            self.state = "voltage_stream"
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
            sub = self._in[1]
            if sub == 0x10:  # select AUX
                self._aux_pin = "aux"
                self._out += b"\x01"
            elif sub == 0x20:  # select CS
                self._aux_pin = "cs"
                self._out += b"\x01"
            elif sub == 0x00:  # drive low
                self._aux_levels[self._aux_pin] = 0
                self._out += b"\x01"
            elif sub == 0x01:  # drive high
                self._aux_levels[self._aux_pin] = 1
                self._out += b"\x01"
            elif sub == 0x02:  # release to HiZ; level unchanged, just ack
                self._out += b"\x01"
            elif sub == 0x03:  # read the selected pin's current level
                self._out += bytes([self._aux_levels[self._aux_pin]])
            else:
                raise AssertionError(
                    f"fake extended AUX got an unknown sub-command 0x{sub:02X}"
                )
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
        """Any byte exits the sniffer."""
        self.state = "i2c"
        self._out.clear()
        self._out += b"\x01"
        return 1

    def _state_spi_sniffer(self, cmd: int) -> int:
        self.state = "spi"
        self._out.clear()
        self._out += b"\x01"
        return 1

    def _state_voltage_stream(self, cmd: int) -> int:
        self.state = "bbio"
        self._out.clear()
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
        if cmd in (0x0D, 0x0E):  # sniff all / sniff while CS low
            self.state = "spi_sniffer"
            self._out += b"\x01"
            return 1
        if cmd in (0x04, 0x05):
            if len(self._in) < 5:
                return 0
            write_count = int.from_bytes(self._in[1:3], "big")
            read_count = int.from_bytes(self._in[3:5], "big")
            if len(self._in) < 5 + write_count:
                return 0
            written = bytes(self._in[5 : 5 + write_count])
            if self.flash is not None:
                reply = self.flash.exchange(written, read_count)
            else:
                reply = bytes([self.spi_fill]) * read_count
            self._out += b"\x01" + reply.ljust(read_count, b"\xff")[:read_count]
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
        if cmd == 0x0F:  # transparent bridge: only a power cycle ends it
            self.state = "uart_bridge"
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

    def _state_uart_bridge(self, cmd: int) -> int:
        """Bridge mode forwards bytes and never returns to command mode."""
        return 1

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
