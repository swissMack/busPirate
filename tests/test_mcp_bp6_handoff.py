"""Hand-offs: the BP6 lent to flashrom, avrdude (Legacy binmode) or PulseView (SUMP), and back."""

import asyncio
import json
import time
from types import SimpleNamespace

import pytest

from buspirate.bp6 import BusPirate6
from buspirate.mcp.confirm import ConfirmStore
from buspirate.mcp.session import BoardSession
from buspirate.mcp_bp6 import engine, handoff, state
from buspirate.simulator_bp6 import FakeBp6

LEGACY_REFUSAL = ("Legacy mode always switches the Bus Pirate's supply on; switch the "
                  "target's own supply off first")
SUMP_WARNING = ("the Bus Pirate switches its own 3.3 V supply on (100 mA) when PulseView "
                "opens the port")


@pytest.fixture(autouse=True)
def quick_reset(monkeypatch):
    # The real board needs seconds to vanish and come back; the fake needs less.
    monkeypatch.setattr(handoff, "GONE_WAIT_S", 1.0)


def _rig():
    holder = {"fake": FakeBp6()}

    def discover(include_unlikely=False):
        fake = holder["fake"]
        return ([SimpleNamespace(device=FakeBp6.BINARY, likely_bus_pirate=True)]
                if fake.present else [])

    def opener(port):
        fake = holder["fake"]
        return BusPirate6(FakeBp6.BINARY, terminal_port=FakeBp6.TERMINAL,
                          serial_factory=fake.factory(), connect_timeout=0.2,
                          bpio2_settle=0.3).open()

    session = BoardSession(opener=opener, discover=discover)
    session.connect()
    return SimpleNamespace(holder=holder, session=session, confirm=ConfirmStore())


@pytest.fixture
def rig():
    r = _rig()
    yield r
    state.of(r.session).lent = None
    r.session.disconnect()


def _fake(rig):
    return rig.holder["fake"]


def _sent(rig, since):
    return [ln for ln in _fake(rig).lines_received()[since:] if ln != b"\r"]


def _lend(rig, name, options=None):
    plan = engine.plan_recipe(rig.session, rig.confirm, name, options or {})
    assert "token" in plan, plan
    mark = len(_fake(rig).lines_received())
    out = engine.run_recipe(rig.session, rig.confirm, plan["token"], {})
    assert "error" not in out, out
    return plan, out, mark


# -- lending ---------------------------------------------------------------------

def test_flashrom_answers_legacy_prompts(rig):
    fake = _fake(rig)
    _, out, mark = _lend(rig, "flashrom")
    sent = _sent(rig, mark)
    assert sent[sent.index(b"binmode 5\r"):] == [
        b"binmode 5\r", b"y\r", b"y\r", b"y\r", b"n\r", b"3.30\r", b"100\r"]
    assert fake.legacy == {"aux": True, "hold": True, "wp": True, "clock": False,
                           "mv": 3300, "ma": 100}
    assert fake.psu_enabled and fake.psu_mv == 3300 and fake.psu_ma == 100
    # the BPIO2 port is closed, and nothing (no HiZ) was sent on it once Legacy began
    assert fake.binary.is_open is False and fake.binary_in_legacy == b""
    result = out["result"]
    assert result["command"] == ("flashrom -p buspirate_spi:dev=%s,serialspeed=115200,"
                                 "spispeed=1M -r backup.bin" % FakeBp6.BINARY)
    assert "connect" in result["how_to_return"]
    assert rig.session.power.millivolts == 3300 and rig.session.power.milliamps == 100
    assert state.of(rig.session).lent["to"] == "flashrom"


def test_avrdude_pins_are_inputs(rig):
    fake = _fake(rig)
    _, out, mark = _lend(rig, "avrdude")
    sent = _sent(rig, mark)
    assert sent[sent.index(b"binmode 5\r"):] == [
        b"binmode 5\r", b"n\r", b"n\r", b"3.30\r", b"100\r"]
    assert fake.legacy["aux"] is False
    assert out["result"]["command"] == "avrdude -c buspirate -P %s -p m328p" % FakeBp6.BINARY


def test_avrdude_part_option(rig):
    _, out, _ = _lend(rig, "avrdude", {"part": "t85"})
    assert out["result"]["command"].endswith("-p t85")


def test_handoff_refuses_target_powered(rig):
    _fake(rig).adc_mv = [3300] * 8
    plan = engine.plan_recipe(rig.session, rig.confirm, "flashrom", {})
    assert "token" not in plan
    assert LEGACY_REFUSAL in plan["error"] and "3300" in plan["error"]


def test_pulseview_sump_and_warning(rig):
    fake = _fake(rig)
    plan = engine.plan_recipe(rig.session, rig.confirm, "pulseview", {})
    assert SUMP_WARNING in plan["warnings"]
    mark = len(fake.lines_received())
    out = engine.run_recipe(rig.session, rig.confirm, plan["token"], {})
    assert "error" not in out, out
    sent = _sent(rig, mark)
    assert sent[sent.index(b"binmode 1\r"):] == [b"binmode 1\r", b"n\r"]
    assert out["result"]["driver"] == "Openbench Logic Sniffer & SUMP compatible"
    assert out["result"]["serial_port"] == FakeBp6.BINARY
    assert fake.bpio_active is False and fake.binary.is_open is False
    assert fake.psu_enabled is False  # on only while PulseView has the port
    assert state.of(rig.session).lent["to"] == "pulseview"


def test_binmode_menu_must_match(rig):
    fake = _fake(rig)
    fake.binmode_names[5] = "IRMAN IR decoder (LIRC, etc)"
    plan = engine.plan_recipe(rig.session, rig.confirm, "flashrom", {})
    out = engine.run_recipe(rig.session, rig.confirm, plan["token"], {})
    assert "binmode menu" in out["error"] and "IRMAN" in out["error"]
    assert state.of(rig.session).lent is None
    assert b"binmode 5\r" not in fake.lines_received()
    assert rig.session.run(lambda bp: bp.status()) is not None  # BPIO2 still answers


# -- taking it back --------------------------------------------------------------

def test_reclaim_sump(rig):
    fake = _fake(rig)
    _lend(rig, "pulseview")
    mark = len(fake.lines_received())
    out = handoff.reclaim(rig.session)
    assert out["reclaimed"] == "pulseview", out
    sent = _sent(rig, mark)
    assert sent[sent.index(b"binmode 2\r"):] == [b"binmode 2\r", b"n\r"]
    assert fake.bpio_active and fake.psu_enabled is False
    assert state.of(rig.session).lent is None and rig.session.power is None
    assert rig.session.run(lambda bp: bp.status()).psu_enabled is False


def test_reclaim_legacy_resets(rig):
    fake = _fake(rig)
    _lend(rig, "flashrom")
    out = handoff.reclaim(rig.session)
    assert out["reclaimed"] == "flashrom" and out["reconnect"] is True
    assert fake.resets == 1 and fake.psu_enabled is False
    assert state.of(rig.session).lent is None and rig.session.board is None


# -- the server --------------------------------------------------------------------

@pytest.fixture
def server(rig):
    pytest.importorskip("mcp")
    from buspirate.mcp_bp6.server import build_server
    return build_server(rig.session)


def call(server, name, args=None):
    result = asyncio.run(server.call_tool(name, args or {}))
    return json.loads(result.content[0].text)


def _lend_by_server(server, name):
    plan = call(server, "recipe_plan", {"name": name})
    out = call(server, "recipe_run", {"token": plan["token"]})
    assert "error" not in out, out
    return out


def test_lent_board_refuses_tools(rig, server):
    _lend_by_server(server, "flashrom")
    out = call(server, "i2c_scan")
    assert out["error"].startswith("the board is lent to flashrom; call connect (or hiz) "
                                   "to take it back — ")
    assert call(server, "recipe_plan", {"name": "flashrom"})["error"] == out["error"]
    status = call(server, "board_status")
    assert status["lent"]["to"] == "flashrom" and "error" not in status
    assert call(server, "recipes", {"query": "flashrom"})["recipes"]
    assert "text" in call(server, "bp6_notes")


def test_connect_reclaims_legacy(rig, server):
    old = _fake(rig)
    _lend_by_server(server, "flashrom")
    mark = len(old.lines_received())
    out = call(server, "connect")
    assert out["connected"] is True, out
    assert _sent(rig, mark)[:2] == [b"q\r", b"y\r"]
    assert old.resets == 1 and old.was_gone
    assert state.of(rig.session).lent is None
    status = call(server, "board_status")
    assert "error" not in status and status["psu_enabled"] is False


def test_hiz_reclaims_sump(rig, server):
    _lend_by_server(server, "pulseview")
    out = call(server, "hiz")
    assert out["hiz"] is True, out
    assert state.of(rig.session).lent is None and _fake(rig).bpio_active
    assert "error" not in call(server, "i2c_scan")


def test_exit_reclaims(rig, server):
    from buspirate.mcp_bp6 import server as server_module
    fake = _fake(rig)
    _lend_by_server(server, "flashrom")
    server_module.shut_down(rig.session)
    assert fake.psu_enabled is False and fake.resets == 1
    assert state.of(rig.session).lent is None and rig.session.board is None


def test_exit_reclaims_sump(rig, server):
    from buspirate.mcp_bp6 import server as server_module
    fake = _fake(rig)
    _lend_by_server(server, "pulseview")
    server_module.shut_down(rig.session)
    assert fake.psu_enabled is False and fake.bpio_active
    assert state.of(rig.session).lent is None and rig.session.board is None


def test_unplugged_while_lent(rig, server):
    _lend_by_server(server, "flashrom")
    _fake(rig).unplug()
    start = time.monotonic()
    out = call(server, "connect")
    assert time.monotonic() - start < 5
    assert out["error"] == "board disconnected — plug it back in and call connect"
    assert out["connected"] is False
    assert state.of(rig.session).lent is None


def test_replugged_while_lent_connects_fresh(rig, server):
    _lend_by_server(server, "flashrom")
    _fake(rig).unplug()
    rig.holder["fake"] = FakeBp6()  # plugged back in: a fresh board
    out = call(server, "connect")
    assert out["connected"] is True, out
    assert state.of(rig.session).lent is None
    assert "error" not in call(server, "i2c_scan")


# -- fix round 1 -------------------------------------------------------------------

def test_flashrom_plan_refuses_a_voltage_off_the_terminal_step(rig):
    mark = len(_fake(rig).lines_received())
    plan = engine.plan_recipe(rig.session, rig.confirm, "flashrom", {"millivolts": 3333})
    assert "token" not in plan
    assert "3333 mV" in plan["error"] and "3330 mV" in plan["error"]
    assert _fake(rig).lines_received()[mark:] == []


def test_supply_set_off_plan_is_recorded(rig):
    fake = _fake(rig)
    fake.legacy_psu = (3200, 100)
    plan = engine.plan_recipe(rig.session, rig.confirm, "flashrom", {})
    out = engine.run_recipe(rig.session, rig.confirm, plan["token"], {})
    assert "3200 mV" in out["error"] and "still lent" in out["error"]
    assert fake.psu_enabled
    assert rig.session.power is not None and rig.session.power.millivolts == 3200
    assert state.of(rig.session).lent["to"] == "flashrom"


def test_reclaim_without_reset_stays_lent(rig, server, monkeypatch):
    monkeypatch.setattr(handoff, "EXIT_TIMEOUT_S", 0.5)
    fake = _fake(rig)
    _lend_by_server(server, "flashrom")
    fake.exit_answer_lost = True
    out = call(server, "connect")
    assert out["connected"] is False
    assert "button" in out["error"] and "again" in out["error"]
    assert state.of(rig.session).lent["to"] == "flashrom"
    assert rig.session.power is not None and fake.psu_enabled and fake.resets == 0
    assert "lent to flashrom" in call(server, "i2c_scan")["error"]
    out = call(server, "hiz")
    assert out["hiz"] is False and "button" in out["error"]
    # the answer gets through on the next try: q is sent again and the board resets
    fake.exit_answer_lost = False
    mark = len(fake.lines_received())
    out = call(server, "connect")
    assert out["connected"] is True, out
    assert _sent(rig, mark)[:2] == [b"q\r", b"y\r"]
    assert fake.resets == 1 and state.of(rig.session).lent is None
    assert rig.session.power is None


# -- final review: the lent board, not any board ------------------------------------

OTHER, OTHER_TERMINAL = "/dev/cu.usbmodemOTHER3", "/dev/cu.usbmodemOTHER1"


@pytest.fixture
def rig2():
    """The lent BP6 plus a second BP6 plugged in, listed first."""
    holder = {"fake": FakeBp6(), "other": FakeBp6()}
    opened = []

    def discover(include_unlikely=False):
        found = [SimpleNamespace(device=OTHER, likely_bus_pirate=True)]
        if holder["fake"].present:
            found.append(SimpleNamespace(device=FakeBp6.BINARY, likely_bus_pirate=True))
        return found

    def opener(port):
        if port == OTHER:
            opened.append((port, None))
            return BusPirate6(OTHER, terminal_port=OTHER_TERMINAL,
                              serial_factory=holder["other"].factory(OTHER_TERMINAL, OTHER),
                              connect_timeout=0.2, bpio2_settle=0.3).open()
        fake = holder["fake"]
        opened.append((port, fake.was_gone))
        return BusPirate6(FakeBp6.BINARY, terminal_port=FakeBp6.TERMINAL,
                          serial_factory=fake.factory(), connect_timeout=0.2,
                          bpio2_settle=0.3).open()

    session = BoardSession(opener=opener, discover=discover)
    session.connect(FakeBp6.BINARY)
    r = SimpleNamespace(holder=holder, session=session, confirm=ConfirmStore(), opened=opened)
    yield r
    state.of(session).lent = None
    session.disconnect()


def test_reclaim_reconnects_the_lent_board_after_its_ports_vanished(rig2):
    pytest.importorskip("mcp")
    from buspirate.mcp_bp6.server import build_server
    server = build_server(rig2.session)
    fake = _fake(rig2)
    fake.reset_lag_s = 0.3  # the real board's ports stay listed for a moment after "Resetting"
    _lend_by_server(server, "flashrom")
    del rig2.opened[:]
    out = call(server, "connect")
    assert out["connected"] is True and out["port"] == FakeBp6.BINARY, out
    assert rig2.opened == [(FakeBp6.BINARY, True)]  # opened once, after the ports vanished
    assert fake.resets == 1 and state.of(rig2.session).lent is None


def test_reset_with_another_board_present_is_not_stuck(rig2, monkeypatch):
    real = handoff._reclaim_legacy

    def reply_lost(bp):
        real(bp)  # the board resets ...
        raise handoff.TerminalError("the reply was lost")  # ... but the answer never came

    monkeypatch.setattr(handoff, "_reclaim_legacy", reply_lost)
    _lend(rig2, "flashrom")
    out = handoff.reclaim(rig2.session)
    assert "error" not in out, out
    assert out["reclaimed"] == "flashrom" and out["reconnect"] is True
    assert out["port"] == FakeBp6.BINARY
    assert _fake(rig2).resets == 1


def test_exit_reports_a_failed_reclaim(rig, server, monkeypatch, capsys):
    from buspirate.mcp_bp6 import server as server_module
    monkeypatch.setattr(handoff, "EXIT_TIMEOUT_S", 0.5)
    _lend_by_server(server, "flashrom")
    _fake(rig).exit_answer_lost = True
    server_module.shut_down(rig.session)
    err = capsys.readouterr().err
    assert "did not confirm that it left Legacy mode" in err
    assert rig.session.board is None
