"""The Bus Pirate 6's scripted terminal console against the simulated board."""

import time

import pytest
import serial

from buspirate.bp6 import BusPirate6
from buspirate.bp6.console import Answer, Console, TerminalError, clean
from buspirate.exceptions import BusPirateError, PortGoneError
from buspirate.simulator_bp6 import FakeBp6


@pytest.fixture
def fake():
    board = FakeBp6()
    yield board
    # The terminal must never be sent Ctrl-C: at a prompt it can silence it for good.
    assert b"\x03" not in bytes(board.terminal.written)


def make(fake):
    return BusPirate6(FakeBp6.BINARY, terminal_port=FakeBp6.TERMINAL,
                      serial_factory=fake.factory(), reply_timeout=0.2, connect_timeout=0.1,
                      bpio2_settle=0.25, first_reply_timeout=0.4, drain_seconds=0.1)


def test_clean_strips_escapes():
    raw = "\x1b[38;2;1;2;3mHiZ\x1b[0m> \x03\x07\r\n\x1b[0K\r\x1b[5C"
    assert clean(raw) == "HiZ> \n"


def test_command_returns_text_and_mode(fake):
    with make(fake).open().console() as con:
        reply = con.command("m dio")
    assert reply.mode == "DIO" and con.mode == "DIO"
    assert "Mode: DIO" in reply.text
    assert reply.error is None


def test_error_line_is_reported(fake):
    with make(fake).open().console() as con:
        reply = con.command("W 3.3 100")
    assert reply.error == "Command has no effect in HiZ mode, press 'm' to choose a mode"


def test_invalid_command_is_an_error(fake):
    with make(fake).open().console() as con:
        assert con.command("frobnicate").error.startswith("Invalid command: frobnicate")


def test_power_on_is_seen_over_bpio2(fake):
    bp = make(fake).open()
    with bp.console() as con:
        con.command("m dio")
        reply = con.command("W 3.3 100")
    assert reply.error is None and "Power supply:  Enabled" in reply.text
    assert bp.status().psu_enabled and bp.status().psu_mv == 3300


def test_tripped_supply_reports_the_error(fake):
    fake.trip_next_w = True
    with make(fake).open().console() as con:
        con.command("m dio")
        assert con.command("W 3.3 100").error == "Error: Current over limit, power supply disabled"


def test_unexpected_subprompt_aborts(fake):
    fake.saved_modes = {"i2c"}
    with make(fake).open().console() as con:
        started = time.monotonic()
        with pytest.raises(TerminalError, match=r"Use previous settings\?"):
            con.command("m i2c")
        assert time.monotonic() - started < 1
        assert b"x\r" in fake.lines_received()
        assert con.command("i").error is None
        assert con.mode == "HiZ"


def test_answers_are_used_once(fake):
    answers = (Answer("Period or frequency", "1khz"), Answer("Duty cycle", "50%"))
    with make(fake).open().console() as con:
        con.command("m dio")
        reply = con.command("G 0", answers=answers)
        assert "Enabled on IO0" in reply.text and reply.error is None
        assert fake.pwm[0] == (1000.0, 50.0)
        con.command("g 0")
        # The simulator re-asks the frequency for an invalid value: no answer is left.
        with pytest.raises(TerminalError, match="Period or frequency"):
            con.command("G 0", answers=(Answer("Period or frequency", "1hz"),
                                        Answer("Duty cycle", "50%")))
        assert con.command("i").mode == "DIO"


def test_a_bare_space_reply_is_sent_without_enter(fake):
    # An answer whose reply is " " is one key press, not a line.
    sent = []

    class Port:
        out = bytearray(b"")

        def write(self, data):
            sent.append(data)
            if data == b"go\r":
                self.out += b"go\r\nPUSH BUTTON (SPACE TO SKIP):"
            elif data == b" ":
                self.out += b"\r\nDIO> \x03"

        def read(self, n):
            data, self.out = bytes(self.out[:n]), self.out[n:]
            return data

    con = Console(Port(), lambda *a: None)
    con.command("go", answers=(Answer("PUSH BUTTON", " "),))
    assert sent == [b"go\r", b" "]


def test_console_resyncs_bpio2(fake):
    bp = make(fake).open()
    with bp.console() as con:
        assert fake.terminal.is_open
        con.command("m dio")
    assert not fake.terminal.is_open
    assert bp.status().mode == "DIO"


def test_console_does_not_nest(fake):
    bp = make(fake).open()
    with bp.console():
        with pytest.raises(TerminalError):
            with bp.console():
                pass


def test_unplug_mid_command(fake):
    bp = make(fake).open()
    started = time.monotonic()
    with pytest.raises(PortGoneError):
        with bp.console() as con:
            def gone(_count):
                raise serial.SerialException("device disconnected")
            fake.terminal.read = gone
            con.command("m dio")
    assert time.monotonic() - started < 1


class Trickle:
    """The terminal port, delivering at most ``size`` bytes per read."""

    def __init__(self, port, size):
        self.port, self.size = port, size

    def read(self, count):
        return self.port.read(min(count, self.size))

    def __getattr__(self, name):
        return getattr(self.port, name)


def test_prompts_split_across_reads_do_not_abort(fake):
    fake.saved_modes = {"i2c"}
    bp = make(fake).open()
    with bp.console() as con:
        con.serial = Trickle(con.serial, 3)
        reply = con.command("m dio")
        assert reply.mode == "DIO" and "Mode: DIO" in reply.text
        con.command("m hiz")
        with pytest.raises(TerminalError, match=r"Use previous settings\?"):
            con.command("m i2c")


def test_an_error_raised_between_commands_is_not_lost(fake):
    with make(fake).open().console() as con:
        con.command("m dio")
        fake.terminal.out += (b"\x07\r\nError: Current over limit, power supply disabled"
                              b"\r\nDIO> \x03")
        reply = con.command("i")
        assert reply.error == "Error: Current over limit, power supply disabled"
        assert con.command("i").error is None


# -- listen: a streaming command, bounded in time, stopped with a raw key ----------

class ScriptPort:
    """A scripted terminal: ``on_write(port, data)`` decides what the board says."""

    def __init__(self, on_write):
        self.out = bytearray()
        self.sent = []
        self.timed = []  # (due, bytes)
        self.on_write = on_write

    def say_at(self, delay, data):
        self.timed.append((time.monotonic() + delay, data))

    def write(self, data):
        self.sent.append(bytes(data))
        self.on_write(self, bytes(data))
        return len(data)

    def read(self, n):
        now = time.monotonic()
        for item in [t for t in self.timed if t[0] <= now]:
            self.timed.remove(item)
            self.out += item[1]
        data, self.out = bytes(self.out[:n]), self.out[n:]
        return data


def test_listen_stops_after_seconds():
    def on_write(port, data):
        if data == b"sniff\r":
            port.out += b"sniff\r\nPress x to exit\r\n[ [0xA0]+]\r\n"
        elif data == b"x":
            port.out += b"\r\nI2C> \x03"

    port = ScriptPort(on_write)
    con = Console(port, lambda *a: None)
    start = time.monotonic()
    reply = con.listen("sniff", 0.2, "x")
    assert time.monotonic() - start >= 0.2
    assert "[0xA0]+" in reply.text
    assert reply.mode == "I2C" and reply.error is None
    assert port.sent == [b"sniff\r", b"x"]
    assert b"\x03" not in b"".join(port.sent)


def test_listen_returns_early_at_prompt():
    def on_write(port, data):
        if data == b"sniff\r":
            port.out += b"sniff\r\nInvalid command: sniff. Type ? for help.\r\nHiZ> \x03"

    port = ScriptPort(on_write)
    con = Console(port, lambda *a: None)
    start = time.monotonic()
    reply = con.listen("sniff", 5, "x")
    assert time.monotonic() - start < 0.5
    assert reply.mode == "HiZ" and reply.error.startswith("Invalid command")
    assert port.sent == [b"sniff\r"]


def test_listen_waits_for_ready():
    stopped = []

    def on_write(port, data):
        if data == b"sniff\r":
            port.say_at(0.3, b"Sniffing...\r\n")
        elif data == b"q":
            stopped.append("Sniffing..." in bytes(port.seen).decode())
            port.out += b"\r\nI2C> \x03"

    port = ScriptPort(on_write)
    port.seen = bytearray()
    real_read = port.read

    def read(n):
        data = real_read(n)
        port.seen += data
        return data

    port.read = read
    con = Console(port, lambda *a: None)
    start = time.monotonic()
    con.listen("sniff", 0.1, "q", ready="Sniffing...")
    assert time.monotonic() - start >= 0.4
    assert stopped == [True]


def test_listen_ready_missing_raises():
    def on_write(port, data):
        if data == b"sniff\r":
            port.out += b"sniff\r\nWarming up\r\n"
        elif data == b"q":
            port.out += b"\r\nI2C> \x03"

    port = ScriptPort(on_write)
    con = Console(port, lambda *a: None)
    with pytest.raises(TerminalError, match="did not start"):
        con.listen("sniff", 0.1, "q", ready="Sniffing...", timeout=0.3)
    assert port.sent[-1] == b"q"


def test_listen_answers_menu_repeatedly():
    asked = []

    def on_write(port, data):
        if data == b"sniff\r":
            port.out += b"sniff\r\nspace for next, 'x' to exit > "
        elif data == b" ":
            asked.append(1)
            if len(asked) == 1:
                port.out += b"\r\nspace for next, 'x' to exit > "
        elif data == b"x":
            port.out += b"\r\nI2C> \x03"

    port = ScriptPort(on_write)
    con = Console(port, lambda *a: None)
    con.listen("sniff", 0.3, "x", keys=[Answer("space for next", " ", 0)])
    assert port.sent[:3] == [b"sniff\r", b" ", b" "] and port.sent[-1] == b"x"
    assert port.sent.count(b" ") == 2
