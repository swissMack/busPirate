"""Smart card answer to reset: the ATR parser and the terminal helper on the simulator."""

import pytest

from buspirate.bp6 import BusPirate6, smartcard
from buspirate.bp6.console import Reply, TerminalError
from buspirate.devices.smartcard import parse_atr
from buspirate.simulator_bp6 import FakeBp6

SIM_ATR = "3B9F96801FC78031E073FE211B6407689A0082019035"
NO_CARD = "no answer from the card: check that it is inserted and the wiring"


def test_parse_sim_atr():
    atr = parse_atr(bytes.fromhex(SIM_ATR))
    assert atr["convention"] == "direct"
    assert 0 in atr["protocols"]
    assert atr["complete"] is True and atr["tck_ok"] is True
    assert atr["protocols"] == [0]  # T=15 is global bytes, not a protocol
    assert atr["ta1"] == 0x96
    assert atr["historical"] == "8031E073FE211B6407689A00820190"


def test_parse_sim_atr_without_tck_is_incomplete():
    # T=15 in TD2 makes a TCK expected (ISO 7816-3), so 21 bytes are one short.
    atr = parse_atr(bytes.fromhex(SIM_ATR)[:-1])
    assert atr["complete"] is False and atr["tck_ok"] is None


def test_parse_sim_atr_wrong_tck():
    assert parse_atr(bytes.fromhex(SIM_ATR[:-2] + "00"))["tck_ok"] is False


def test_parse_minimal_atr():
    atr = parse_atr(bytes.fromhex("3B00"))
    assert atr["protocols"] == [0]
    assert atr["historical"] == "" and atr["historical_text"] == ""
    assert atr["ta1"] is None and atr["tck_ok"] is None and atr["complete"] is True


def test_parse_inverse_convention():
    assert parse_atr(bytes.fromhex("3F00"))["convention"] == "inverse"


@pytest.mark.parametrize("data", [b"", b"\x12"])
def test_parse_refuses_empty_or_bad_ts(data):
    with pytest.raises(ValueError):
        parse_atr(data)


def test_parse_t1_tck():
    # T0 0x80: TD1 only, no historical bytes; TD1 0x01: T=1, so a TCK follows.
    assert parse_atr(bytes.fromhex("3B800181"))["tck_ok"] is True
    bad = parse_atr(bytes.fromhex("3B800100"))
    assert bad["tck_ok"] is False and bad["protocols"] == [1] and bad["complete"] is True


def test_parse_historical_text():
    atr = parse_atr(b"\x3b\x03ABC")
    assert atr["historical"] == "414243" and atr["historical_text"] == "ABC"


def test_parse_short_atr_is_incomplete():
    atr = parse_atr(bytes.fromhex(SIM_ATR)[:10])
    assert atr["complete"] is False
    assert parse_atr(b"\x3b")["complete"] is False
    t1 = parse_atr(bytes.fromhex("3B8001"))  # T=1 announced, TCK missing
    assert t1["complete"] is False and t1["tck_ok"] is None


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


HDUART = "m hduart -b 9600 -d 8 -p even -s 2 -l listen"


def test_simulator_hduart_mode(fake):
    with make(fake).open().console() as con:
        reply = con.command(HDUART)
    assert "Mode: HDUART" in reply.text and reply.mode == "HDUART"


def test_read_atr_on_the_simulator(fake):
    fake.card_atr = bytes.fromhex("3B00")
    with make(fake).open().console() as con:
        con.command(HDUART)
        mark = len(sent(fake))
        out = smartcard.read_atr(con, 3_571_200, 0.3)
    assert out["bytes"] == "3B 00", out
    assert out["atr"]["convention"] == "direct" and out["clock_hz"] == 3_571_200
    lines = [ln for ln in sent(fake)[mark:] if ln not in (b"3571200hz\r", b"50%\r")]
    assert lines == [b"G 1\r", b"}\r", b"[\r", b"{\r", b"]\r", b"}\r", b"g 1\r"], lines
    assert fake.pwm == {}


def test_read_atr_full_sim_atr(fake):
    fake.card_atr = bytes.fromhex(SIM_ATR)
    with make(fake).open().console() as con:
        con.command(HDUART)
        out = smartcard.read_atr(con, 3_571_200, 0.3)
    assert out["bytes"].replace(" ", "") == SIM_ATR
    assert out["atr"]["complete"] is True


def test_read_atr_no_card(fake):
    fake.card_atr = b""
    with make(fake).open().console() as con:
        con.command(HDUART)
        out = smartcard.read_atr(con, 3_571_200, 0.2)
    assert out["bytes"] == "" and out["atr"] is None and out["error"] == NO_CARD
    assert b"]\r" in sent(fake) and b"g 1\r" in sent(fake)
    assert fake.pwm == {}


class _Breaks:
    """Answers the PWM prompts, then fails at ``{``."""

    def __init__(self):
        self.lines = []

    def command(self, line, timeout=3.0, answers=(), until=None):
        self.lines.append(line)
        if line == "{":
            raise TerminalError("the board stopped answering")
        texts = {"G 1": "Generate frequency: Enabled on IO1\nActual frequency: 3571200Hz",
                 "}": "RST LOW", "[": "UART OPEN (ASYNC READ)", "]": "UART CLOSE",
                 "g 1": "Generate frequency: Disabled on IO1"}
        return Reply(texts.get(line, ""), "HDUART", None)

    def collect(self, seconds):
        return ""


def test_read_atr_cleans_up_on_error():
    con = _Breaks()
    with pytest.raises(TerminalError):
        smartcard.read_atr(con, 3_571_200, 0.1)
    assert con.lines[-3:] == ["]", "}", "g 1"]


class _CloseBreaks(_Breaks):
    """Fails at ``{`` and again at ``]``: ``g 1`` must still go out."""

    def command(self, line, timeout=3.0, answers=(), until=None):
        if line == "]":
            self.lines.append(line)
            raise TerminalError("close failed")
        return super().command(line, timeout, answers, until)


def test_read_atr_cleanup_tries_both_and_keeps_first_error():
    con = _CloseBreaks()
    with pytest.raises(TerminalError) as exc:
        smartcard.read_atr(con, 3_571_200, 0.1)
    assert "stopped answering" in str(exc.value)
    assert con.lines[-3:] == ["]", "}", "g 1"]


class _CloseOnly(_Breaks):
    """Everything works but ``]`` fails: the error surfaces, ``g 1`` still goes out."""

    def command(self, line, timeout=3.0, answers=(), until=None):
        self.lines.append(line)
        if line == "]":
            raise TerminalError("close failed")
        from buspirate.bp6.console import Reply as R
        texts = {"G 1": "Generate frequency: Enabled on IO1\nActual frequency: 3571200Hz",
                 "}": "RST LOW", "[": "UART OPEN (ASYNC READ)", "{": "RST HIGH 0x3b 0x00",
                 "g 1": "Generate frequency: Disabled on IO1"}
        return R(texts.get(line, ""), "HDUART", None)


def test_read_atr_cleanup_error_raised_after_both():
    con = _CloseOnly()
    with pytest.raises(TerminalError):
        smartcard.read_atr(con, 3_571_200, 0.1)
    assert con.lines[-3:] == ["]", "}", "g 1"]


class _OffClock(_Breaks):
    """The PWM lands far from the asked clock."""

    def command(self, line, timeout=3.0, answers=(), until=None):
        if line == "G 1":
            self.lines.append(line)
            return Reply("Generate frequency: Enabled on IO1\nActual frequency: 3000000Hz",
                         "HDUART", None)
        return super().command(line, timeout, answers, until)


def test_read_atr_refuses_an_off_baud_clock_before_reset():
    con = _OffClock()
    out = smartcard.read_atr(con, 3_571_200, 0.1)
    assert out["atr"] is None and "3000000" in out["error"] and out["bytes"] == ""
    assert out["clock_hz"] == 3000000
    assert "{" not in con.lines and con.lines[-3:] == ["]", "}", "g 1"]


def test_parse_atr_reads_ta2():
    from buspirate.devices.smartcard import parse_atr
    assert parse_atr(bytes.fromhex("3B90961000"))["ta2"] == 0x00
    assert parse_atr(bytes.fromhex("3B1096"))["ta2"] is None
