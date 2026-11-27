"""The `bp6` MCP server: every tool listed up front, connect on first use, BP6 only."""

import asyncio
import json
from types import SimpleNamespace

import pytest

pytest.importorskip("mcp")

from buspirate.connect import open_simulated  # noqa: E402
from buspirate.mcp.session import BoardSession  # noqa: E402
from buspirate.mcp_bp6 import server as server_module  # noqa: E402
from buspirate.mcp_bp6.server import TOOL_NAMES, build_server  # noqa: E402

EXPECTED = {
    "recipes", "recipe_plan", "recipe_run", "recipe_commit", "board_status", "connect", "hiz", "power_off",
    "measure_voltages", "power_plan", "power_apply", "i2c_scan", "i2c_read", "i2c_write",
    "spi_transfer", "uart_send", "uart_listen", "onewire_scan", "pins", "bp6_notes", "wiring", "pwm", "pwm_off", "frequency",
}


def names(server):
    return {t.name for t in asyncio.run(server.list_tools())}


def call(server, name, args=None):
    result = asyncio.run(server.call_tool(name, args or {}))
    return json.loads(result.content[0].text)


def _fake(session):
    return session.board.serial.owner


def _two_bp6s():
    found = [SimpleNamespace(device=p, likely_bus_pirate=True) for p in ("/dev/bp-a", "/dev/bp-b")]
    return BoardSession(opener=lambda port: open_simulated("bp6"),
                        discover=lambda include_unlikely=False: found)


def test_tools_listed_without_board():
    session = BoardSession(simulated="bp6")
    server = build_server(session)
    assert names(server) == EXPECTED == set(TOOL_NAMES)
    assert session.board is None
    assert server.name == "bp6"


def test_first_use_connects():
    session = BoardSession(simulated="bp6")
    server = build_server(session)
    plan = call(server, "recipe_plan", {"name": "lcd"})
    assert "error" not in plan, plan
    assert plan["recipe"] == "lcd" and plan["token"]
    assert session.board is not None


def test_refuses_other_board():
    session = BoardSession(simulated="v4")
    server = build_server(session)
    out = call(server, "recipe_plan", {"name": "lcd"})
    assert out["error"] == ("this server only drives a Bus Pirate 6; use the buspirate "
                            "server for v4")
    assert session.board is None
    assert "only drives a Bus Pirate 6" in call(server, "connect")["error"]
    assert session.board is None


def test_lcd_plan_then_run_via_server():
    session = BoardSession(simulated="bp6")
    server = build_server(session)
    plan = call(server, "recipe_plan", {"name": "lcd"})
    assert plan["power"]["millivolts"] == 5000
    out = call(server, "recipe_run", {"token": plan["token"], "options": {"message": "Hi"}})
    assert out["check"]["ok"] is True, out
    assert out["result"]["address"] == "0x27"
    fake = _fake(session)
    assert fake.psu_enabled and fake.pullups
    # the recipe token is not a power token, and is single-use
    assert "error" in call(server, "power_apply", {"token": plan["token"]})


def test_exit_puts_board_in_hiz():
    session = BoardSession(simulated="bp6")
    server = build_server(session)
    plan = call(server, "recipe_plan", {"name": "lcd"})
    call(server, "recipe_run", {"token": plan["token"]})
    fake = _fake(session)
    assert fake.psu_enabled and fake.pullups
    session.disconnect()
    assert fake.psu_enabled is False and fake.pullups is False


def test_run_stdio_does_not_connect_and_disconnects(monkeypatch):
    seen = {}

    def fake_run(self, transport="stdio", **kwargs):
        seen["transport"] = transport
        seen["names"] = names(self)
        seen["session"] = server_module._SESSIONS[self]
        seen["board_at_start"] = seen["session"].board
        call(self, "board_status")            # connects on first use

    monkeypatch.setattr(server_module.MCPServer, "run", fake_run)
    server_module.run_stdio(demo=True)
    assert seen["transport"] == "stdio" and seen["names"] == EXPECTED
    assert seen["board_at_start"] is None
    assert seen["session"].board is None      # closed on exit


def test_two_boards_uses_first_and_names_others():
    session = _two_bp6s()
    server = build_server(session)
    out = call(server, "board_status")
    assert session.port == "/dev/bp-a"
    assert out["other_boards"] == ["/dev/bp-b"]
    assert "/dev/bp-b" in out["board_note"]
    # once connected, later results do not repeat it
    assert "other_boards" not in call(server, "board_status")
    # connect(port) picks another
    assert call(server, "connect", {"port": "/dev/bp-b"})["connected"] is True
    assert session.port == "/dev/bp-b"


def test_connect_with_no_board_is_an_error():
    server = build_server(BoardSession(discover=lambda include_unlikely=False: []))
    assert "no board found" in call(server, "hiz")["error"]
    assert "error" in call(server, "connect")


def test_port_busy_message():
    def busy(port):
        raise OSError("[Errno 16] Resource busy")
    session = BoardSession(opener=busy, discover=lambda include_unlikely=False: [
        SimpleNamespace(device="/dev/bp-a", likely_bus_pirate=True)])
    out = call(build_server(session), "i2c_scan")
    assert "held by another program" in out["error"]


def test_recipes_tool_finds_lcd_without_a_board():
    session = BoardSession(simulated="bp6")
    out = call(build_server(session), "recipes", {"query": "lcd"})
    assert out["recipes"][0]["name"] == "lcd"
    assert session.board is None


def test_power_plan_then_apply_and_off():
    session = BoardSession(simulated="bp6")
    server = build_server(session)
    plan = call(server, "power_plan", {"millivolts": 3300, "voltage_source": "owner"})
    assert plan["token"]
    # a power token is not a recipe token
    assert "error" in call(server, "recipe_run", {"token": plan["token"]})
    plan = call(server, "power_plan", {"millivolts": 3300, "voltage_source": "owner"})
    assert call(server, "power_apply", {"token": plan["token"]})["applied"] is True
    assert _fake(session).psu_enabled
    assert call(server, "power_off")["psu_enabled"] is False
    assert "error" in call(server, "power_apply", {"token": "nope"})
    assert call(server, "hiz") == {"hiz": True}


def test_measured_source_needs_a_measurement_first():
    server = build_server(BoardSession(simulated="bp6"))
    assert "refused" in call(server, "power_plan", {"millivolts": 3300,
                                                    "voltage_source": "measured"})
    assert "pins_mv" in call(server, "measure_voltages")
    assert "token" in call(server, "power_plan", {"millivolts": 3300,
                                                  "voltage_source": "measured"})


def test_board_status_has_supply_fields():
    out = call(build_server(BoardSession(simulated="bp6")), "board_status")
    assert out["variant"] == "bp6"
    assert {"psu_enabled", "psu_mv", "pullups"} <= set(out)


def test_bus_tools_wrap_jobs():
    server = build_server(BoardSession(simulated="bp6"))
    assert "devices" in call(server, "i2c_scan")
    assert "error" in call(server, "i2c_read", {"address": 3, "register": 0})
    assert "error" not in call(server, "spi_transfer", {"write_hex": "9f", "read_count": 3})
    assert "error" not in call(server, "uart_send", {"text": "hi"})
    assert "error" not in call(server, "uart_listen", {"seconds": 0.1})
    assert "error" not in call(server, "onewire_scan")


def test_pins_set_and_read():
    session = BoardSession(simulated="bp6")
    server = build_server(session)
    out = call(server, "pins", {"set": {"IO2": 1, "IO3": 0, "IO4": "in"}})
    assert out["directions"]["IO2"] == "out" and out["directions"]["IO3"] == "out"
    assert out["directions"]["IO4"] == "in"
    assert out["levels"]["IO2"] == 1 and out["levels"]["IO3"] == 0
    assert set(out["mv"]) == {"IO%d" % n for n in range(8)}
    assert "levels" in call(server, "pins")
    assert "error" in call(server, "pins", {"set": {"IO9": 1}})
    assert "error" in call(server, "pins", {"set": {"IO2": "high"}})


def test_bp6_notes():
    out = call(build_server(BoardSession(simulated="bp6")), "bp6_notes")
    text = out["text"]
    assert len(text.splitlines()) < 120
    for word in ("5 V", "pull-up", "orange", "SHT4x", "SLE4442", "owner-only", "HiZ"):
        assert word in text


def test_instructions_are_short_and_state_the_rules():
    text = build_server(BoardSession(simulated="bp6")).instructions
    assert len(text.splitlines()) <= 16
    for word in ("recipes", "recipe_plan", "recipe_run", "needs_extra_confirmation",
                 "target-powered", "hint", "hiz"):
        assert word in text


def test_power_plan_is_tied_to_its_board():
    session = _two_bp6s()
    server = build_server(session)
    plan = call(server, "power_plan", {"millivolts": 3300, "voltage_source": "owner"})
    assert session.port == "/dev/bp-a"
    call(server, "connect", {"port": "/dev/bp-b"})
    out = call(server, "power_apply", {"token": plan["token"]})
    assert "/dev/bp-a" in out["error"]
    assert _fake(session).psu_enabled is False


def test_wiring_tool():
    session = BoardSession(simulated="bp6")
    server = build_server(session)
    out = call(server, "wiring", {"job": "i2c"})
    pins = {s["pin"]: s["colour"] for s in out["steps"]}
    assert pins["IO0"] == "orange" and pins["IO1"] == "yellow"
    assert "notes" in out
    assert "jobs" in call(server, "wiring", {"job": "nope"})
    assert session.board is None    # wiring needs no board


def _powered(session, server):
    plan = call(server, "power_plan", {"millivolts": 3300, "voltage_source": "owner"})
    assert call(server, "power_apply", {"token": plan["token"]})["applied"] is True
    assert session.power is not None


@pytest.mark.parametrize("fault", ["tripped", "switched_off"])
def test_bus_tool_does_not_switch_a_lost_supply_back_on(fault):
    session = BoardSession(simulated="bp6")
    server = build_server(session)
    _powered(session, server)
    fake = _fake(session)
    fake.psu_enabled = False
    fake.psu_tripped = fault == "tripped"
    out = call(server, "i2c_scan")
    assert fake.psu_enabled is False
    assert session.power is None
    assert "supply_lost" in out and "power_plan" in out["supply_lost"]


def test_bus_tool_with_supply_on_keeps_the_plan():
    session = BoardSession(simulated="bp6")
    server = build_server(session)
    _powered(session, server)
    out = call(server, "i2c_scan")
    assert "supply_lost" not in out and session.power is not None
    assert _fake(session).psu_enabled is True


def test_run_stdio_exit_puts_board_in_hiz(monkeypatch):
    seen = {}

    def fake_run(self, transport="stdio", **kwargs):
        session = server_module._SESSIONS[self]
        _powered(session, self)
        seen["fake"] = _fake(session)
        assert seen["fake"].psu_enabled and seen["fake"].pullups

    monkeypatch.setattr(server_module.MCPServer, "run", fake_run)
    server_module.run_stdio(demo=True)
    assert seen["fake"].psu_enabled is False and seen["fake"].pullups is False


def test_commit_flow_demo():
    session = BoardSession(simulated="bp6")
    server = build_server(session)
    plan = call(server, "recipe_plan", {"name": "i2c-eeprom-write",
                                        "options": {"data_hex": "de ad"}})
    assert "error" not in plan, plan
    chip = _fake(session).i2c_devices[0x50]
    before = chip[0]
    assert before != 0xDE
    ran = call(server, "recipe_run", {"token": plan["token"]})
    assert ran["commit"]["summary"], ran
    assert _fake(session).i2c_devices[0x50][0] == before  # nothing changed yet
    done = call(server, "recipe_commit", {"token": ran["commit"]["token"]})
    assert done["committed"] is True and done["result"]["verified"] is True, done
    assert _fake(session).i2c_devices[0x50][0] == 0xDE


def test_instructions_name_the_commit_step():
    assert "`recipe_commit` only after a second yes" in server_module.INSTRUCTIONS
    assert "Never pass backup=False unless the owner asked for no backup." \
        in server_module.INSTRUCTIONS


# -- pwm / frequency tools ------------------------------------------------------------

from buspirate.mcp import power as _power  # noqa: E402
from buspirate.mcp_bp6 import state as _state  # noqa: E402


def _sent(session, since=0):
    return [ln for ln in _fake(session).lines_received()[since:] if ln != b"\r"]


def _powered_server():
    session = BoardSession(simulated="bp6")
    server = build_server(session)
    call(server, "connect")
    session.power = _power.plan_power("bp6", 3300, _power.SOURCE_OWNER, False, 100)
    return session, server


def test_pwm_tool_needs_power_or_target():
    session = BoardSession(simulated="bp6")
    server = build_server(session)
    out = call(server, "pwm", {"pin": 2, "hz": 1000, "duty": 50})
    assert out == {"error": "plan power first (power_plan, then power_apply) or power the target"}
    assert call(server, "frequency", {"pin": 1}) == out
    assert _fake(session).pwm == {}


def test_pwm_tool_reasserts_confirmed_power():
    session, server = _powered_server()
    mark = len(_fake(session).lines_received())
    out = call(server, "pwm", {"pin": 2, "hz": 1000, "duty": 50})
    assert out["pin"] == 2 and out["actual_hz"] == 1000, out
    assert _sent(session, mark) == [b"m dio\r", b"W 3.30 100\r", b"G 2\r", b"1000hz\r", b"50%\r"]
    assert _fake(session).psu_enabled and _state.of(session).pwm_pins == {2}
    mark = len(_fake(session).lines_received())
    out = call(server, "pwm", {"pin": 4, "hz": 500, "duty": 10})
    assert out["pin"] == 4, out
    assert _sent(session, mark) == [b"G 4\r", b"500hz\r", b"10%\r"]


def test_pwm_tool_refuses_bad_range_and_partner():
    session, server = _powered_server()
    assert "8 Hz to 62.5 MHz" in call(server, "pwm", {"pin": 2, "hz": 5})["error"]
    assert "duty" in call(server, "pwm", {"pin": 2, "duty": 0})["error"]
    assert "error" not in call(server, "pwm", {"pin": 2})
    assert "share one PWM" in call(server, "pwm", {"pin": 3})["error"]


def test_pwm_off_tool():
    session, server = _powered_server()
    call(server, "pwm", {"pin": 2})
    mark = len(_fake(session).lines_received())
    out = call(server, "pwm_off", {"pin": 2})
    assert out == {"pin": 2, "stopped": True}
    assert _sent(session, mark) == [b"g 2\r"]
    assert _state.of(session).pwm_pins == set() and _fake(session).pwm == {}


def test_frequency_tool():
    session, server = _powered_server()
    _fake(session).signals[1] = (1000.0, 50.0)
    assert call(server, "frequency", {"pin": 1}) == {"pin": 1, "hz": 1000, "duty_percent": 50.0}
    assert "only IO1, IO3, IO5 and IO7" in call(server, "frequency", {"pin": 2})["error"]


def test_pwm_tool_keeps_confirmed_zero_milliamps():
    session = BoardSession(simulated="bp6")
    server = build_server(session)
    call(server, "connect")
    session.power = _power.plan_power("bp6", 3300, _power.SOURCE_OWNER, False, 0)
    assert session.power.milliamps == 0
    mark = len(_fake(session).lines_received())
    out = call(server, "pwm", {"pin": 2})
    assert "error" not in out, out
    assert _sent(session, mark)[:2] == [b"m dio\r", b"W 3.30 0\r"]


def test_pwm_off_reports_a_supply_trip():
    session, server = _powered_server()
    call(server, "pwm", {"pin": 2})
    fake = _fake(session)
    fake._cmd_pwm_off = lambda text, args: fake._finish(
        text, "Generate frequency: Disabled on IO2\r\n"
        "\x07\r\nError: Current over limit, power supply disabled\r\n")
    out = call(server, "pwm_off", {"pin": 2})
    assert "power supply disabled" in out["error"]
    assert session.power is None
    assert _state.of(session).pwm_pins == set()


def test_tool_names_phase3a():
    i = TOOL_NAMES.index("pwm")
    assert TOOL_NAMES[i:i + 3] == ("pwm", "pwm_off", "frequency")
    server = build_server(BoardSession(simulated="bp6"))
    assert names(server) == set(TOOL_NAMES) == EXPECTED


def test_instructions_mention_terminal_rules():
    text = build_server(BoardSession(simulated="bp6")).instructions
    assert len(text) < 2000
    low = text.lower()
    assert "until" in low and "connect" in low and "lends" in low
    assert "self-test" in low and "nothing" in low
    assert "bluetag" in low and "minute" in low


def test_recipes_list_new():
    server = build_server(BoardSession(simulated="bp6"))
    listed = {r["name"]: r for r in call(server, "recipes")["recipes"]}
    for name in ("pwm-signal", "frequency-measure", "self-test", "jtag-pinout", "swd-pinout",
                 "flashrom", "avrdude", "pulseview"):
        assert listed[name]["source"].startswith("https://docs.buspirate.com/")


def test_pwm_and_frequency_descriptions_name_the_voltage():
    server = build_server(BoardSession(simulated="bp6"))
    desc = {t.name: t.description for t in asyncio.run(server.list_tools())}
    assert "3.3 V" in desc["pwm"] and "3.3 V" in desc["frequency"]


# -- final review: _in_dio power and the PWM pins ----------------------------------------

def test_pwm_tool_refuses_a_confirmed_voltage_off_the_terminal_step():
    session, server = _powered_server()
    session.power = _power.plan_power("bp6", 3333, _power.SOURCE_OWNER, False, 100)
    mark = len(_fake(session).lines_received())
    out = call(server, "pwm", {"pin": 2})
    assert "3333 mV" in out["error"] and "3330 mV" in out["error"], out
    assert "power_plan" in out["error"]
    assert _sent(session, mark) == []
    assert not _fake(session).psu_enabled


def test_pwm_tool_forgets_the_supply_when_switching_it_on_fails(monkeypatch):
    from buspirate.bp6.console import TerminalError
    from buspirate.mcp_bp6 import engine as _engine
    session, server = _powered_server()

    def refuse(con, mv, ma):
        raise TerminalError("W was not accepted")
    monkeypatch.setattr(_engine.console_power, "power_on", refuse)
    out = call(server, "pwm", {"pin": 2})
    assert "W was not accepted" in out["error"], out
    assert session.power is None


def test_mode_switch_forgets_the_pwm_pins():
    session, server = _powered_server()
    assert "error" not in call(server, "pwm", {"pin": 2})
    plan = call(server, "recipe_plan", {"name": "frequency-measure", "options": {"pin": 3}})
    assert "token" in plan, plan
    out = call(server, "recipe_run", {"token": plan["token"]})
    assert "error" not in out, out
    assert _state.of(session).pwm_pins == set()  # m dio switched the PWM off
    out = call(server, "pwm", {"pin": 2})
    assert "error" not in out, out


# -- phase 3b: sniffers and infrared ----------------------------------------------------

def test_recipes_list_phase3b():
    server = build_server(BoardSession(simulated="bp6"))
    listed = {r["name"]: r for r in call(server, "recipes")["recipes"]}
    for name in ("i2c-sniff", "2wire-sniff", "ps2-sniff", "ir-receive", "ir-send-nec",
                 "ir-send-rc5", "ir-send-raw"):
        assert listed[name]["source"].startswith("https://docs.buspirate.com/")
    assert "ir-send" not in listed


def test_instructions_mention_listening():
    text = server_module.INSTRUCTIONS
    assert len(text) < 2000
    low = text.lower()
    assert "sniffers" in low and "ir receive" in low and "`seconds`" in low
    assert "60" in low
    assert "ps/2" in low and "keyboard" in low and "confirm" in low
