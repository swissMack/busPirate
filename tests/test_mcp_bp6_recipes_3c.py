"""The phase 3c recipes (smart card, USB-PD, disk) on the simulated Bus Pirate 6."""

import pytest

from buspirate.mcp.confirm import ConfirmStore
from buspirate.mcp.session import BoardSession
from buspirate.mcp_bp6 import engine
from buspirate.mcp_bp6.recipes import REGISTRY


@pytest.fixture
def session():
    s = BoardSession(simulated="bp6")
    s.connect()
    yield s
    s.disconnect()


@pytest.fixture
def confirm():
    return ConfirmStore()


def _fake(session):
    return session.board.serial.owner


def _plan(session, confirm, name, options):
    return engine.plan_recipe(session, confirm, name, options)


def _run(session, confirm, name, options):
    plan = _plan(session, confirm, name, options)
    assert "error" not in plan, plan
    return plan, engine.run_recipe(session, confirm, plan["token"], {})


def test_smartcard_recipe_registered():
    r = REGISTRY["smartcard-atr"]
    assert (r.bus, r.transport, r.terminal_mode) == ("uart", "terminal", "hduart")
    assert r.terminal_flags == "-b 9600 -d 8 -p even -s 2 -l listen"
    assert (r.default_mv, r.min_mv, r.max_mv, r.milliamps) == (3000, 1800, 5000, 100)
    assert r.pullups is True and r.target_powered_ok is False and r.risk == "none"
    assert r.options == {"clock_hz": 3_571_200, "wait_s": 1.0}
    assert ("C3 CLK", "IO1") in r.wiring and ("C7 I/O", "IO0") in r.wiring


def test_smartcard_atr_runs(session, confirm):
    fake = _fake(session)
    fake.card_atr = bytes.fromhex("3B9F96801FC78031E073FE211B6407689A00820190")
    _, out = _run(session, confirm, "smartcard-atr", {"millivolts": 3000, "wait_s": 0.3})
    assert out["result"]["atr"]["convention"] == "direct", out
    assert b"m hduart -b 9600 -d 8 -p even -s 2 -l listen\r" in fake.lines_received()
    assert fake.pwm == {}


@pytest.mark.parametrize("clock_hz", [3_000_000, 900_000, 5_500_000, "3571200", True])
def test_smartcard_atr_refuses_bad_clock(session, confirm, clock_hz):
    _, out = _run(session, confirm, "smartcard-atr",
                  {"millivolts": 3000, "clock_hz": clock_hz, "wait_s": 0.3})
    assert out["check"]["ok"] is False and "clock_hz" in out["check"]["error"], out
    assert b"G 1\r" not in _fake(session).lines_received()
