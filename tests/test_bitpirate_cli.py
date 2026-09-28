"""The text command line underneath the ESP32 Bit Pirate driver.

The screen parsing and the prompt/question handling are tested against raw
bytes in the firmware's own shapes, including the awkward ones: output split
across reads, the per-key line redraw, and questions that arrive with no
prompt after them.
"""

import pytest

from buspirate.bitpirate.cli import (
    CliTransport,
    CliTimeout,
    parse_hex_after,
    parse_scan,
    screen_lines,
)
from buspirate.exceptions import ModeError


class ScriptedSerial:
    """Replies to each write with the next scripted chunk list."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.pending = []
        self.written = bytearray()

    def write(self, data):
        self.written += data
        if self.replies:
            self.pending.extend(self.replies.pop(0))
        return len(data)

    def read(self, count=1):
        if not self.pending:
            return b""
        chunk = self.pending.pop(0)
        if len(chunk) > count:
            self.pending.insert(0, chunk[count:])
            chunk = chunk[:count]
        return chunk

    def reset_input_buffer(self):
        self.pending.clear()


class Link:
    """The two things CliTransport needs from its device."""

    def __init__(self, serial):
        self.serial = serial
        self.traffic = []

    def write(self, data):
        self.serial.write(data)
        self.traffic.append(("tx", data))

    def _notify(self, direction, data):
        self.traffic.append((direction, data))

    def flush_input(self):
        self.serial.reset_input_buffer()


def transport(replies, **kwargs):
    kwargs.setdefault("timeout", 0.3)
    return CliTransport(Link(ScriptedSerial(replies)), **kwargs)


# -- what the screen shows -----------------------------------------------


def test_the_redraw_on_every_key_collapses_to_the_final_line():
    raw = "\rI2C> s\x1b[K\rI2C> sc\x1b[K\rI2C> scan\x1b[K\r\nI2C> "
    assert screen_lines(raw) == ["I2C> scan", "I2C> "]


def test_crlf_and_a_lone_cr_start_are_both_handled():
    raw = "\r\n\n\rPress any key to start...\r\n"
    assert screen_lines(raw) == ["", "", "Press any key to start...", ""]


def test_scan_lines_are_read_as_addresses():
    lines = [
        "I2C Scan: Scanning I2C bus... Press [ENTER] to stop",
        "",
        "Found device at 0x3C",
        "Found device at 0x68",
        "",
    ]
    assert parse_scan(lines) == [0x3C, 0x68]
    assert parse_scan(["I2C Scan: No I2C devices found."]) == []


def test_read_bytes_stop_at_the_bytecode_dump():
    lines = [
        "I2C Read:",
        "",
        "00 01 02 ",
        "",
        "ByteCode Sequence:",
        "START | data=0 | bits=8 | repeat=1",
        "READ | data=0 | bits=8 | repeat=3",
    ]
    assert parse_hex_after(lines, "I2C Read:") == b"\x00\x01\x02"


def test_no_read_marker_means_nothing_came_back():
    assert parse_hex_after(["", "ByteCode Sequence:"], "I2C Read:") == b""


# -- one command, one reply --------------------------------------------------


def test_a_command_returns_only_its_own_output():
    cli = transport(
        [[b"\rI2C> p", b"ing 0x68\x1b[K\r\n", b"Ping 0x68: I2C Ping: ACK received!", b"\r\nI2C> "]]
    )
    reply = cli.command("ping 0x68")
    assert reply.lines == ["Ping 0x68: I2C Ping: ACK received!"]
    assert reply.mode == "I2C"
    assert cli.link.serial.written == b"ping 0x68\r"


def test_only_a_carriage_return_is_sent():
    # The firmware treats \r and \n each as Enter, so "\r\n" would be two
    # Enters, and the second one would accept the next question's default.
    cli = transport([[b"\r\nHIZ> "]])
    cli.command("")
    assert cli.link.serial.written == b"\r"


def test_questions_are_answered_from_the_table_or_take_their_default():
    cli = transport(
        [
            [b"\rI2C> config\x1b[K\r\nI2C Configuration:\r\nSDA GPIO [2]: "],
            [b"\r\nSCL GPIO [1]: "],
            [b"\r\nFrequency [100000]: "],
            [b"400000\r\nI2C configured.\n\r\nI2C> "],
        ]
    )
    reply = cli.command("config", answers={"Frequency": "400000"})
    assert cli.link.serial.written == b"config\r\r\r400000\r"
    assert "I2C configured." in reply.lines
    assert reply.questions == ["SDA GPIO", "SCL GPIO", "Frequency"]


def test_a_reply_that_never_reaches_a_prompt_times_out_with_what_it_had():
    cli = transport([[b"\rI2C> scan\x1b[K\r\nI2C Scan: Scanning"]], timeout=0.1)
    with pytest.raises(CliTimeout, match="Scanning"):
        cli.command("scan")


def test_too_long_a_line_is_refused_before_it_is_sent():
    cli = transport([])
    with pytest.raises(ValueError, match="512"):
        cli.command("x" * 600)
    assert cli.link.serial.written == b""


def test_an_unknown_mode_is_an_error():
    cli = transport([[b"\rHIZ> m xyz\x1b[K\r\nUnknown mode: xyz\r\nHIZ> "]])
    with pytest.raises(ModeError, match="Unknown mode"):
        cli.enter_mode("xyz")


def test_sync_presses_enter_until_a_prompt_shows_and_keeps_the_banner():
    cli = transport(
        [
            [b"\r\n\n\rPress any key to start...\r\n"],
            [b"     Version 1.7           Ready to board\r\nHIZ> "],
        ]
    )
    text = cli.sync()
    assert "Version 1.7" in text
    assert cli.mode == "HIZ"
