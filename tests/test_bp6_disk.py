"""The Bus Pirate's own disk: path rules, the parsers and the terminal helpers on the simulator."""

import pytest

from buspirate.bp6 import BusPirate6, disk
from buspirate.bp6.console import Reply, TerminalError
from buspirate.simulator_bp6 import FakeBp6


@pytest.mark.parametrize("path,want", [
    ("BPCONFIG.BP", "/bpconfig.bp"), ("/dumps/flash.bin", "/dumps/flash.bin"),
    ("a~1.txt", "/a~1.txt"),
    ("/abcdefgh/abcdefgh/abcdefgh/a.t", "/abcdefgh/abcdefgh/abcdefgh/a.t"),
    ("README", "/readme"), ("my_dir/x-y.c", "/my_dir/x-y.c")])
def test_check_path_accepts(path, want):
    assert disk.check_path(path) == want


@pytest.mark.parametrize("path,want", [("/", "/"), ("dumps", "/dumps"), ("/Dumps/", "/dumps")])
def test_check_path_directory(path, want):
    assert disk.check_path(path, directory=True) == want


@pytest.mark.parametrize("path", [
    "", "a b.txt", "x;rm y", "longfilename.txt", "a/../b", "/" + "a" * 31, "a" * 31 + "/b",
    "dumps/", "/", "a.b.c", "a.toolong", ".bp", "a//b", "..", "./a", "a\nb", "a.txt\n", None, 5,
    "/abcdefgh/abcdefgh/abcdefgh/a.txt", "abcdefgh/abcdefgh/abcdefgh/a.tx"])
def test_check_path_refuses(path):
    with pytest.raises(ValueError):
        disk.check_path(path)


def test_check_path_directory_refuses_bad_names():
    for bad in ("", "a b", "/x/../y", "/" + "a" * 31):
        with pytest.raises(ValueError):
            disk.check_path(bad, directory=True)


LS = """ls -l /
       -  2020-01-01 00:00  dumps/
       -  2020-01-01 00:00  scripts/
       8  2020-01-01 00:00  bpconfig.bp
  131072  2020-01-01 00:00  flash.bin
2 dirs, 2 files"""


class _Says:
    """A console that answers every line with one fixed text and error."""

    def __init__(self, text, error=None):
        self.text, self.error, self.lines = text, error, []

    def command(self, line, timeout=3.0, answers=(), until=None):
        self.lines.append(line)
        return Reply(self.text, "HiZ", self.error)


def test_parse_listing():
    out = disk.listing(_Says(LS.split("\n", 1)[1]), "/")
    assert out == {"path": "/", "dirs": ["dumps", "scripts"],
                   "files": [{"name": "bpconfig.bp", "size": 8, "date": "2020-01-01 00:00"},
                             {"name": "flash.bin", "size": 131072,
                              "date": "2020-01-01 00:00"}]}


def test_listing_without_summary_is_no_such_directory():
    con = _Says("")
    with pytest.raises(TerminalError) as exc:
        disk.listing(con, "nothere")
    assert "no such directory" in str(exc.value)
    assert con.lines == ["ls -l /nothere"]


def test_error_reply_raises():
    with pytest.raises(TerminalError) as exc:
        disk.show(_Says("Error: no file", "Error: no file"), "x.txt")
    assert "no file" in str(exc.value)


def test_bad_path_is_never_sent():
    con = _Says("")
    for call in (lambda: disk.show(con, "a b"), lambda: disk.hexdump(con, "x;rm y"),
                 lambda: disk.delete(con, "dumps/"), lambda: disk.listing(con, "a/../b")):
        with pytest.raises(ValueError):
            call()
    assert con.lines == []


@pytest.mark.parametrize("start,length", [(-1, 16), (0, 0), (0, 4097), (True, 16), (0, 1.5)])
def test_hexdump_refuses_bad_range(start, length):
    con = _Says("")
    with pytest.raises(ValueError):
        disk.hexdump(con, "a.bin", start, length)
    assert con.lines == []


def test_parse_hex_rows():
    text = ("00000010  10 11 12 13 14 15 16 17 18 19 1a 1b 1c 1d 1e 1f  |................|\n"
            "00000020  41 42                                             |AB|")
    out = disk.hexdump(_Says(text), "a.bin", 16, 18)
    assert out == {"start": 16, "data_hex": bytes(range(16, 32)).hex() + "4142", "length": 18}


def test_show_truncates():
    out = disk.show(_Says("abcdef"), "a.txt", max_chars=4)
    assert out == {"text": "abcd", "truncated": True}


# -- on the simulator ---------------------------------------------------------

DISK = {"bpconfig.bp": b'{"a":1}\n', "dumps/flash.bin": bytes(range(40))}


@pytest.fixture
def fake():
    board = FakeBp6()
    board.disk = dict(DISK)
    yield board


def make(fake):
    return BusPirate6(FakeBp6.BINARY, terminal_port=FakeBp6.TERMINAL,
                      serial_factory=fake.factory(), reply_timeout=0.2, connect_timeout=0.1,
                      bpio2_settle=0.25, first_reply_timeout=0.4, drain_seconds=0.1)


def test_simulator_listing(fake):
    with make(fake).open().console() as con:
        root = disk.listing(con, "/")
        sub = disk.listing(con, "DUMPS")
        with pytest.raises(TerminalError) as exc:
            disk.listing(con, "nothere")
    assert root["dirs"] == ["dumps"]
    assert root["files"] == [{"name": "bpconfig.bp", "size": 8, "date": "2020-01-01 00:00"}]
    assert sub == {"path": "/dumps", "dirs": [],
                   "files": [{"name": "flash.bin", "size": 40, "date": "2020-01-01 00:00"}]}
    assert "no such directory" in str(exc.value)


def test_simulator_show_hex_delete(fake):
    with make(fake).open().console() as con:
        assert disk.show(con, "bpconfig.bp") == {"text": '{"a":1}', "truncated": False}
        out = disk.hexdump(con, "dumps/flash.bin", 16, 16)
        assert out == {"start": 16, "data_hex": bytes(range(16, 32)).hex(), "length": 16}
        tail = disk.hexdump(con, "/dumps/flash.bin", 30, 100)
        assert tail["data_hex"] == bytes(range(30, 40)).hex() and tail["length"] == 10
        assert disk.delete(con, "BPCONFIG.BP") == {"deleted": True}
        with pytest.raises(TerminalError) as exc:
            disk.show(con, "bpconfig.bp")
    assert "no file" in str(exc.value)
    assert "bpconfig.bp" not in fake.disk


def test_simulator_missing_file_errors_in_a_mode(fake):
    with make(fake).open().console() as con:
        con.command("m i2c -s 400")
        for call in (lambda: disk.show(con, "gone.txt"), lambda: disk.hexdump(con, "gone.bin"),
                     lambda: disk.delete(con, "gone.txt")):
            with pytest.raises(TerminalError) as exc:
                call()
            assert "no file" in str(exc.value)
        assert con.command("").mode == "I2C"
