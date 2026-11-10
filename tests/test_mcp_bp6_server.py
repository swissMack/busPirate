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
    "recipes", "recipe_plan", "recipe_run", "board_status", "connect", "hiz", "power_off",
    "measure_voltages", "power_plan", "power_apply", "i2c_scan", "i2c_read", "i2c_write",
    "spi_transfer", "uart_send", "uart_listen", "onewire_scan", "pins", "bp6_notes",
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
    call(server, "power_apply", {"token": "nope"})
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
    assert len(text.splitlines()) <= 60
    for word in ("5 V", "pull-up", "orange", "SHT4x", "SLE4442", "owner-only", "HiZ"):
        assert word in text


def test_instructions_are_short_and_state_the_rules():
    text = build_server(BoardSession(simulated="bp6")).instructions
    assert len(text.splitlines()) <= 10
    for word in ("recipes", "recipe_plan", "recipe_run", "needs_extra_confirmation",
                 "target-powered", "hint", "hiz"):
        assert word in text
