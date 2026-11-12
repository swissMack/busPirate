"""The read-only T=0 command layer (bp6/sim.py) against the simulated SIM."""

import pytest

from buspirate.bp6 import BusPirate6, sim
from buspirate.bp6.console import Reply, TerminalError
from buspirate.bp6.sim import SimLink, received_bytes
from buspirate.simulator_bp6 import FakeBp6, FakeSim

HDUART = "m hduart -b 9600 -d 8 -p even -s 2 -l listen"
CLOCK = 3_571_200
ICCID = bytes.fromhex("98141032547698103254")


@pytest.fixture
def fake():
    board = FakeBp6()
    board.sim = FakeSim(iccid=ICCID)
    yield board
    assert b"\x03" not in bytes(board.terminal.written)


def make(fake):
    return BusPirate6(FakeBp6.BINARY, terminal_port=FakeBp6.TERMINAL,
                      serial_factory=fake.factory(), reply_timeout=0.2, connect_timeout=0.1,
                      bpio2_settle=0.25, first_reply_timeout=0.4, drain_seconds=0.1)


def sent(fake):
    return [ln for ln in fake.lines_received() if ln != b"\r"]


def open_link(con, **kw):
    con.command(HDUART)
    kw.setdefault("wwt_s", 0.3)
    kw.setdefault("atr_wait_s", 0.15)
    return SimLink.open(con, CLOCK, **kw)


def instructions(fake):
    return [a[1] for a in fake.sim.apdus]


# -- the parser ----------------------------------------------------------------

def test_received_bytes_skip_the_tx_echo():
    text = "\nTX: 0xA0 0x20 0x00 0x01 0x00 \n0x63 0xc3 "
    assert received_bytes(text) == b"\x63\xc3"


def test_received_bytes_skip_wrapped_tx_rows():
    text = ("TX: 0x31 0x32 0x33 0x34 0xFF 0xFF 0xFF 0xFF \n    0x00 \n0x90 0x00 ")
    assert received_bytes(text) == b"\x90\x00"


def test_received_bytes_without_echo():
    assert received_bytes("0x9f 0x16 ") == b"\x9f\x16"


# -- open and close --------------------------------------------------------------

def test_open_reads_the_atr_and_keeps_printing(fake):
    with make(fake).open().console() as con:
        link = open_link(con)
        try:
            assert link.atr["protocols"] == [0]
            assert link.atr_bytes == fake.sim.atr
            assert fake._hduart_printing and 1 in fake.pwm
        finally:
            link.close()
    assert fake.pwm == {} and not fake._hduart_printing
    tail = sent(fake)[-2:]
    assert tail == [b"]\r", b"g 1\r"], tail


def test_open_with_no_card_cleans_up(fake):
    fake.sim = None
    with make(fake).open().console() as con:
        with pytest.raises(TerminalError) as exc:
            open_link(con)
    assert "no answer from the card" in str(exc.value)
    assert sent(fake)[-2:] == [b"]\r", b"g 1\r"]
    assert fake.pwm == {}


def test_link_is_a_context_manager(fake):
    with make(fake).open().console() as con:
        with open_link(con) as link:
            link.select(0x3F00)
    assert sent(fake)[-2:] == [b"]\r", b"g 1\r"] and fake.pwm == {}


# -- commands ------------------------------------------------------------------

def test_select_and_read_iccid(fake):
    with make(fake).open().console() as con:
        with open_link(con) as link:
            link.select(0x3F00)
            link.select(0x2FE2)
            data, sw = link.read_binary(10)
    assert data == ICCID and sw == 0x9000
    assert b"0xA0 0xA4 0x00 0x00 0x02\r" in sent(fake)
    assert b"0x3F 0x00\r" in sent(fake) and b"0x2F 0xE2\r" in sent(fake)
    assert b"0xA0 0xB0 0x00 0x00 0x0A\r" in sent(fake)


def test_gsm_select_takes_the_9f_get_response(fake):
    with make(fake).open().console() as con:
        with open_link(con) as link:
            data, sw = link.select(0x7F20)
    assert sw == 0x9000 and len(data) == 22 and data[4:6] == b"\x7f\x20"
    assert instructions(fake) == [0xA4, 0xC0]
    assert fake.sim.apdus[1][:5] == bytes([0xA0, 0xC0, 0, 0, 22])


def test_uicc_select_takes_the_61_get_response(fake):
    with make(fake).open().console() as con:
        with open_link(con) as link:
            link.cla = 0x00
            data, sw = link.select(0x3F00)
    assert sw == 0x9000 and data[0] == 0x62
    assert fake.sim.apdus[0][:4] == bytes([0x00, 0xA4, 0x00, 0x04])
    assert fake.sim.apdus[1][:5] == bytes([0x00, 0xC0, 0, 0, len(data)])


def test_6c_repeats_with_the_new_le(fake):
    with make(fake).open().console() as con:
        with open_link(con) as link:
            link.cla = 0x00
            link.select(0x3F00)
            link.select(0x2FE2)
            data, sw = link.read_binary(20)
    assert data == ICCID and sw == 0x9000
    reads = [a[:5] for a in fake.sim.apdus if a[1] == 0xB0]
    assert reads == [bytes([0, 0xB0, 0, 0, 20]), bytes([0, 0xB0, 0, 0, 10])]


def test_one_byte_at_a_time_and_null_bytes(fake):
    fake.sim.one_byte_at_a_time = True
    fake.sim.null_bytes = 2
    with make(fake).open().console() as con:
        with open_link(con) as link:
            link.select(0x3F00)
            link.select(0x2FE2)
            data, sw = link.read_binary(10)
    assert data == ICCID and sw == 0x9000
    assert b"0x2F\r" in sent(fake) and b"0xE2\r" in sent(fake)


def test_read_record(fake):
    fake.sim.add_file(0x7F20, 0x6F99, records=[b"\x01\x02\x03", b"\x04\x05\x06"])
    with make(fake).open().console() as con:
        with open_link(con) as link:
            link.select(0x7F20)
            link.select(0x6F99)
            data, sw = link.read_record(2, 3)
    assert data == b"\x04\x05\x06" and sw == 0x9000
    assert fake.sim.apdus[-1][:5] == bytes([0xA0, 0xB2, 2, 4, 3])


def test_missing_file_returns_its_status(fake):
    with make(fake).open().console() as con:
        with open_link(con) as link:
            data, sw = link.select(0x6F42)
    assert data == b"" and sw == 0x9404


def test_class_not_supported(fake):
    fake.sim.classes = (0x00,)
    with make(fake).open().console() as con:
        with open_link(con) as link:
            data, sw = link.select(0x3F00)
    assert sw == 0x6E00


@pytest.mark.parametrize("ins", [0xD6, 0xDC, 0x20, 0x88, 0x24, 0x2C, 0xE4])
def test_instructions_outside_the_allow_list_are_refused_before_sending(fake, ins):
    with make(fake).open().console() as con:
        with open_link(con) as link:
            lines = list(fake.lines_received())
            apdus = list(fake.sim.apdus)
            with pytest.raises(ValueError):
                link.command(0xA0, ins, 0, 0, b"\x00")
            assert fake.lines_received() == lines
            assert fake.sim.apdus == apdus


def test_card_that_stops_answering(fake):
    fake.sim.silent_after = 2  # SELECT 3F00 and its GET RESPONSE
    with make(fake).open().console() as con:
        link = open_link(con)
        link.select(0x3F00)
        mark = len(sent(fake))
        with pytest.raises(TerminalError) as exc:
            link.select(0x2FE2)
        assert "card" in str(exc.value)
        later = sent(fake)[mark:]
        assert b"]\r" in later and b"g 1\r" in later
        assert fake.pwm == {}
        with pytest.raises(TerminalError):
            link.select(0x3F00)


def test_close_runs_both_steps_and_keeps_the_first_error():
    class _Con:
        def __init__(self):
            self.lines = []

        def command(self, line, timeout=3.0, answers=(), until=None):
            self.lines.append(line)
            if line == "]":
                raise TerminalError("close failed")
            return Reply("", "HDUART", None)

    con = _Con()
    link = SimLink(con)
    with pytest.raises(TerminalError):
        link.close()
    assert con.lines == ["]", "g 1"]
    link.close()  # a second close sends nothing
    assert con.lines == ["]", "g 1"]


# -- the PIN -------------------------------------------------------------------

def test_pin_status_gsm_route(fake):
    fake.sim.attempts = 2
    with make(fake).open().console() as con:
        with open_link(con) as link:
            status = link.pin_status()
    assert status["needed"] is True and status["attempts_left"] == 2
    assert status["blocked"] is False and status["source"] == "DF_GSM"
    assert 0x20 not in instructions(fake)


def test_pin_status_gsm_disabled(fake):
    fake.sim.pin_enabled = False
    with make(fake).open().console() as con:
        with open_link(con) as link:
            status = link.pin_status()
    assert status["needed"] is False


def test_pin_status_uicc_route(fake):
    with make(fake).open().console() as con:
        with open_link(con) as link:
            link.cla = 0x00
            status = link.pin_status()
    assert status == {"needed": True, "attempts_left": 3, "blocked": False,
                      "source": "VERIFY", "sw": "63C3"}
    assert fake.sim.apdus[-1] == bytes([0x00, 0x20, 0x00, 0x01, 0x00])


def test_pin_status_uicc_blocked(fake):
    fake.sim.attempts = 0
    with make(fake).open().console() as con:
        with open_link(con) as link:
            link.cla = 0x00
            status = link.pin_status()
    assert status["blocked"] is True and status["attempts_left"] == 0


def test_verify_pin_once_right(fake):
    with make(fake).open().console() as con:
        with open_link(con) as link:
            out = link.verify_pin_once("1234")
    assert out["verified"] is True
    verifies = [a for a in fake.sim.apdus if a[1] == 0x20]
    assert verifies == [bytes([0xA0, 0x20, 0x00, 0x01, 0x08]) + b"1234\xff\xff\xff\xff"]
    assert sim.verify_line(0xA0).encode() + b"\r" in sent(fake)
    assert "1234" not in repr(out)


@pytest.mark.parametrize("cla,attempts", [(0xA0, 2), (0x00, 2)])
def test_verify_pin_once_wrong_is_tried_once(fake, cla, attempts):
    with make(fake).open().console() as con:
        with open_link(con) as link:
            link.cla = cla
            out = link.verify_pin_once("9999")
    assert out["verified"] is False
    assert [a[1] for a in fake.sim.apdus].count(0x20) == 1
    assert fake.sim.attempts == 2
    if cla == 0x00:
        assert out["attempts_left"] == attempts
    assert "9999" not in repr(out)


@pytest.mark.parametrize("pin", ["12a4", "123", "123456789", "", " 1234"])
def test_verify_refuses_a_bad_pin_without_sending(fake, pin):
    with make(fake).open().console() as con:
        with open_link(con) as link:
            lines = list(fake.lines_received())
            with pytest.raises(ValueError) as exc:
                link.verify_pin_once(pin)
            assert fake.lines_received() == lines
    if pin.strip():
        assert pin.strip() not in str(exc.value)
