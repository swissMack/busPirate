"""PWM and frequency measurement through the terminal, on the simulated Bus Pirate 6."""

import pytest

from buspirate.bp6 import BusPirate6, signals
from buspirate.bp6.console import TerminalError
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


def test_pwm_start_sends_three_lines(fake):
    with make(fake).open().console() as con:
        con.command("m dio")
        mark = len(sent(fake))
        out = signals.pwm_start(con, 2, 1000, 50)
    assert sent(fake)[mark:] == [b"G 2\r", b"1000hz\r", b"50%\r"]
    assert out["pin"] == 2 and out["actual_hz"] == 1000
    assert abs(out["actual_duty_percent"] - 50) < 0.5
    assert fake.pwm == {2: (1000.0, 50.0)}


def test_pwm_high_frequency_has_no_exponent(fake):
    with make(fake).open().console() as con:
        con.command("m dio")
        signals.pwm_start(con, 0, 62_500_000, 25)
    assert b"62500000hz\r" in sent(fake)


@pytest.mark.parametrize("hz,duty", [(5, 50), (70e6, 50), (1000, 0), (1000, 101)])
def test_pwm_range(fake, hz, duty):
    with make(fake).open().console() as con:
        con.command("m dio")
        mark = len(sent(fake))
        with pytest.raises(ValueError) as err:
            signals.pwm_start(con, 0, hz, duty)
    assert sent(fake)[mark:] == []
    assert ("8 Hz to 62.5 MHz" in str(err.value)) or ("duty" in str(err.value))


def test_frequency_even_pin_refused(fake):
    with make(fake).open().console() as con:
        con.command("m dio")
        mark = len(sent(fake))
        with pytest.raises(ValueError, match="only IO1, IO3, IO5 and IO7"):
            signals.measure_frequency(con, 2)
    assert sent(fake)[mark:] == []


def test_frequency_parses(fake):
    fake.signals[1] = (1000.0, 50.0)
    with make(fake).open().console() as con:
        con.command("m dio")
        out = signals.measure_frequency(con, 1)
    assert out == {"pin": 1, "hz": 1000, "duty_percent": 50.0}


def test_frequency_refused_beside_running_pwm(fake):
    with make(fake).open().console() as con:
        con.command("m dio")
        signals.pwm_start(con, 0, 1000, 50)
        with pytest.raises(TerminalError, match="unavailable"):
            signals.measure_frequency(con, 1)


def test_pwm_stop(fake):
    with make(fake).open().console() as con:
        con.command("m dio")
        signals.pwm_start(con, 2, 1000, 50)
        assert signals.pwm_stop(con, 2) == {"pin": 2, "stopped": True}
        assert signals.pwm_stop(con, 2)["stopped"] is False
    assert fake.pwm == {}


def test_never_bare_f(fake):
    fake.signals[1] = (1000.0, 50.0)
    with make(fake).open().console() as con:
        con.command("m dio")
        signals.measure_frequency(con, 1)
        signals.pwm_start(con, 4, 500, 20)
    lines = [ln.strip() for ln in sent(fake)]
    assert b"f" not in lines and b"F" not in lines
    assert not any(ln.startswith(b"F") for ln in lines)
