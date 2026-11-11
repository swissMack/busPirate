"""blueTag JTAG and SWD pin finding on the simulated Bus Pirate 6."""

import pytest

from buspirate.bp6 import BusPirate6, bluetag
from buspirate.simulator_bp6 import FakeBp6


@pytest.fixture
def fake():
    board = FakeBp6()
    yield board
    assert b"\x03" not in bytes(board.terminal.written)


def make(fake):
    return BusPirate6(FakeBp6.BINARY, terminal_port=FakeBp6.TERMINAL,
                      serial_factory=fake.factory(), reply_timeout=0.2, connect_timeout=0.1,
                      bpio2_settle=0.25, first_reply_timeout=0.4, drain_seconds=0.1)


def sent(fake):
    return [ln for ln in fake.lines_received() if ln != b"\r"]


def test_jtag_hit_parses(fake):
    fake.bluetag_hit = {"jtag": FakeBp6.BLUETAG_JTAG_HIT}
    with make(fake).open().console() as con:
        con.command("m jtag")
        out = bluetag.scan(con, "jtag", 6)
    assert out["found"] is True and out["channels"] == 6
    assert out["pinout"] == {"TDI": "IO0", "TDO": "IO3", "TCK": "IO4", "TMS": "IO2", "TRST": None}
    assert out["devices"][0] == {"idcode": "0x59602093", "manufacturer": "Xilinx",
                                 "part": "0x9602", "version": "0x5"}
    assert sent(fake)[-1] == b"bluetag jtag -c 6\r"


def test_swd_hit_parses(fake):
    fake.bluetag_hit = {"swd": FakeBp6.BLUETAG_SWD_HIT}
    with make(fake).open().console() as con:
        con.command("m jtag")
        out = bluetag.scan(con, "swd", 4)
    assert out["pinout"] == {"SWDIO": "IO5", "SWCLK": "IO6"}
    assert out["devices"][0]["idcode"] == "0x0BC12477"
    assert sent(fake)[-1] == b"bluetag swd -c 4\r"


def test_nothing_found(fake):
    with make(fake).open().console() as con:
        con.command("m jtag")
        out = bluetag.scan(con, "jtag", 6)
    assert out["found"] is False and out["pinout"] == {} and out["devices"] == []
    assert out["hint"] == "check VREF and GND, and that each IO wire is on a separate pad"


@pytest.mark.parametrize("proto,n", [("jtag", 3), ("jtag", 9), ("swd", 1)])
def test_channel_range(fake, proto, n):
    with make(fake).open().console() as con:
        con.command("m jtag")
        mark = len(sent(fake))
        with pytest.raises(ValueError):
            bluetag.scan(con, proto, n)
    assert sent(fake)[mark:] == []


def test_pulsing_flag(fake):
    with make(fake).open().console() as con:
        con.command("m jtag")
        bluetag.scan(con, "jtag", 6, pulsing=False)
        bluetag.scan(con, "swd", 4, pulsing=False)
    assert sent(fake)[-2:] == [b"bluetag jtag -c 6 -d\r", b"bluetag swd -c 4\r"]


def test_timeout_scales(fake):
    assert bluetag.scan_seconds("jtag", 8) > bluetag.scan_seconds("jtag", 6) >= 30
    seen = []

    class Spy:
        def command(self, line, timeout=3.0, answers=()):
            seen.append(timeout)
            raise RuntimeError("stop")

    with pytest.raises(RuntimeError):
        bluetag.scan(Spy(), "jtag", 8)
    assert seen == [bluetag.scan_seconds("jtag", 8)]


def test_bluetag_outside_jtag_mode_is_invalid(fake):
    with make(fake).open().console() as con:
        reply = con.command("bluetag jtag -c 6")
    assert "Invalid command" in reply.text
