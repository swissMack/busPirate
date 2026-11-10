import asyncio
import json

import pytest

pytest.importorskip("mcp")

from buspirate.connect import open_simulated  # noqa: E402
from buspirate.exceptions import PortGoneError  # noqa: E402
from buspirate.mcp import server as server_module  # noqa: E402
from buspirate.mcp.server import ALWAYS, BOARD_TOOLS, build_server  # noqa: E402
from buspirate.mcp.session import BoardSession  # noqa: E402


def names(server):
    return {t.name for t in asyncio.run(server.list_tools())}


def call(server, name, args=None):
    result = asyncio.run(server.call_tool(name, args or {}))
    return json.loads(result.content[0].text)


def _swappable():
    """A session whose port name picks the simulated board: connect(port='v3')."""
    return BoardSession(opener=open_simulated, discover=lambda include_unlikely=False: [])


# -- gating -------------------------------------------------------------------

def test_disconnected_lists_only_always():
    server = build_server(BoardSession(simulated="v3"))
    assert names(server) == set(ALWAYS)


@pytest.mark.parametrize("variant", ["v3", "v4", "bp6", "bitpirate"])
def test_connect_lists_board_tools(variant):
    server = build_server(BoardSession(simulated=variant))
    call(server, "connect")
    assert {"disconnect", "board_status", "wiring", "power_plan", "power_apply", "hiz"} <= names(server)
    assert ("measure_voltages" in names(server)) == (variant != "bitpirate")


def test_disconnect_returns_to_always():
    server = build_server(BoardSession(simulated="v3"))
    call(server, "connect")
    call(server, "disconnect")
    assert names(server) == set(ALWAYS)


def test_board_tools_table():
    assert BOARD_TOOLS["measure_voltages"] == (frozenset({"adc"}), frozenset({"psu_current_readout"}))
    for name in ("disconnect", "board_status", "wiring", "power_plan", "power_apply",
                 "power_off", "hiz"):
        assert BOARD_TOOLS[name] == (frozenset(),)


def test_connect_and_disconnect_carry_reconnect_hint():
    server = build_server(BoardSession(simulated="bp6"))
    hint = "If new tools don't appear, run /mcp → reconnect buspirate."
    assert call(server, "connect")["hint"] == hint
    assert call(server, "disconnect")["hint"] == hint


def test_connect_with_no_board_is_an_error():
    server = build_server(BoardSession(discover=lambda include_unlikely=False: []))
    assert "error" in call(server, "connect")
    assert names(server) == set(ALWAYS)


def test_find_boards():
    assert call(build_server(BoardSession(simulated="v4")), "find_boards") == {
        "ports": ["simulated-v4"]}


def test_instructions_state_the_rules():
    text = build_server(BoardSession(simulated="v3")).instructions
    for word in ("boards", "wiring", "measure_voltages", "power_apply",
                 "needs_extra_confirmation"):
        assert word in text


# -- two-step power -----------------------------------------------------------

def test_power_plan_then_apply_bp6():
    session = BoardSession(simulated="bp6")
    server = build_server(session)
    call(server, "connect")
    plan = call(server, "power_plan", {"millivolts": 3300, "voltage_source": "owner"})
    assert plan["milliamps"] == 100 and plan["token"]
    applied = call(server, "power_apply", {"token": plan["token"]})
    assert applied["psu_enabled"] is True
    assert "psu_mv" in applied and "psu_ma" in applied
    assert session.power is not None and session.power.millivolts == 3300
    assert "error" in call(server, "power_apply", {"token": plan["token"]})      # replay refused


def test_power_apply_rejects_garbage_token():
    session = BoardSession(simulated="v4")
    server = build_server(session)
    call(server, "connect")
    assert "error" in call(server, "power_apply", {"token": "deadbeef"})
    assert session.power is None


def test_refused_level_reported_not_raised():
    server = build_server(BoardSession(simulated="v3"))
    call(server, "connect")
    assert "refused" in call(server, "power_plan", {"millivolts": 1800, "voltage_source": "owner"})


def test_unknown_voltage_source_refused():
    server = build_server(BoardSession(simulated="bp6"))
    call(server, "connect")
    out = call(server, "power_plan", {"millivolts": 3300, "voltage_source": "guess"})
    assert "refused" in out and "token" not in out


def test_measured_source_needs_a_measurement_first():
    server = build_server(BoardSession(simulated="bp6"))
    call(server, "connect")
    out = call(server, "power_plan", {"millivolts": 3300, "voltage_source": "measured"})
    assert "refused" in out and "measure_voltages" in out["refused"]
    measured = call(server, "measure_voltages")
    assert "pins_mv" in measured and "suggested_mv" in measured
    plan = call(server, "power_plan", {"millivolts": 3300, "voltage_source": "measured"})
    assert plan["source"] == "measured" and plan["token"]


def test_measurement_does_not_survive_reconnect():
    server = build_server(BoardSession(simulated="bp6"))
    call(server, "connect")
    call(server, "measure_voltages")
    call(server, "connect")
    out = call(server, "power_plan", {"millivolts": 3300, "voltage_source": "measured"})
    assert "refused" in out


def test_apply_refused_when_board_swapped_since_planning():
    session = _swappable()
    server = build_server(session)
    call(server, "connect", {"port": "v3"})
    plan = call(server, "power_plan", {"millivolts": 3300, "voltage_source": "owner"})
    call(server, "connect", {"port": "bp6"})
    out = call(server, "power_apply", {"token": plan["token"]})
    assert "error" in out
    assert session.power is None
    assert session.run(lambda bp: bp.status().psu_enabled) is False


def test_power_apply_v3_switches_supply_and_pullups():
    session = BoardSession(simulated="v3")
    server = build_server(session)
    call(server, "connect")
    plan = call(server, "power_plan", {"millivolts": 5000, "voltage_source": "owner"})
    applied = call(server, "power_apply", {"token": plan["token"]})
    assert applied["pins"]["power"] is True and applied["pins"]["pullups"] is True
    assert session.power.millivolts == 5000
    call(server, "power_off")
    assert session.power is None


def test_power_apply_bitpirate_records_only():
    session = BoardSession(simulated="bitpirate")
    server = build_server(session)
    call(server, "connect")
    plan = call(server, "power_plan", {"millivolts": 1800, "voltage_source": "owner"})
    applied = call(server, "power_apply", {"token": plan["token"]})
    assert "error" not in applied
    assert session.power is not None and session.power.millivolts == 1800
    call(server, "power_off")
    assert session.power is None


def test_power_off_and_hiz_bp6():
    session = BoardSession(simulated="bp6")
    server = build_server(session)
    call(server, "connect")
    plan = call(server, "power_plan", {"millivolts": 3300, "voltage_source": "owner"})
    call(server, "power_apply", {"token": plan["token"]})
    call(server, "power_off")
    assert session.power is None
    assert call(server, "board_status")["psu_enabled"] is False
    plan = call(server, "power_plan", {"millivolts": 3300, "voltage_source": "owner"})
    call(server, "power_apply", {"token": plan["token"]})
    call(server, "hiz")
    assert session.power is None
    assert call(server, "board_status")["psu_enabled"] is False


def test_hiz_v3_falls_back_to_power_off():
    session = BoardSession(simulated="v3")
    server = build_server(session)
    call(server, "connect")
    plan = call(server, "power_plan", {"millivolts": 3300, "voltage_source": "owner"})
    call(server, "power_apply", {"token": plan["token"]})
    assert "error" not in call(server, "hiz")
    assert session.power is None


# -- status, wiring, knowledge ------------------------------------------------

def test_board_status_bp6_has_supply_fields():
    server = build_server(BoardSession(simulated="bp6"))
    call(server, "connect")
    st = call(server, "board_status")
    assert st["variant"] == "bp6" and st["power"] is None
    for key in ("psu_enabled", "psu_mv", "psu_ma", "psu_tripped", "pullups", "adc_mv",
                "pin_labels"):
        assert key in st


def test_board_status_v3_has_no_bp6_fields():
    server = build_server(BoardSession(simulated="v3"))
    call(server, "connect")
    st = call(server, "board_status")
    assert st["variant"] == "v3" and "psu_enabled" not in st and "adc" in st["capabilities"]


def test_wiring_has_steps_and_board_notes():
    server = build_server(BoardSession(simulated="bp6"))
    call(server, "connect")
    out = call(server, "wiring", {"job": "i2c"})
    assert out["job"] == "i2c"
    assert {"pin": "IO0", "colour": "orange", "target": "SDA",
            "note": "data, both directions"} in out["steps"]
    assert any("pull-ups" in n for n in out["notes"])


def test_wiring_v3_uses_panel_notes():
    server = build_server(BoardSession(simulated="v3"))
    call(server, "connect")
    out = call(server, "wiring", {"job": "i2c"})
    assert out["steps"] and any("VPU" in n for n in out["notes"])


def test_wiring_unknown_job_is_an_error():
    server = build_server(BoardSession(simulated="bitpirate"))
    call(server, "connect")
    out = call(server, "wiring", {"job": "onewire"})
    assert "error" in out


def test_knowledge_tools():
    server = build_server(BoardSession(simulated="v3"))
    topics = call(server, "knowledge_topics")["topics"]
    assert any(t["topic"] == "power" for t in topics)
    assert "Bit Pirate" in call(server, "knowledge_read", {"topic": "power"})["text"]
    assert "error" in call(server, "knowledge_read", {"topic": "nope"})
    assert call(server, "knowledge_search", {"query": "pull-up"})["results"]


# -- unplug -------------------------------------------------------------------

def test_board_gone_regates_and_reports():
    session = BoardSession(simulated="bp6")
    server = build_server(session)
    call(server, "connect")

    def gone(*a, **k):
        raise PortGoneError("unplugged")

    session.board.status = gone
    out = call(server, "board_status")
    assert out == {"error": "board disconnected — plug it back in and call connect"}
    assert names(server) == set(ALWAYS)
    assert session.board is None


def test_not_connected_is_an_error():
    session = BoardSession(simulated="v3")
    server = build_server(session)
    call(server, "connect")
    session.disconnect()          # dropped behind the server's back
    assert "error" in call(server, "board_status")


# -- stdio startup ------------------------------------------------------------

def test_run_stdio_autoconnects_one_board_and_disconnects(monkeypatch):
    seen = {}

    def fake_run(self, transport="stdio", **kwargs):
        seen["transport"] = transport
        seen["names"] = names(self)
        seen["session"] = server_module._SESSIONS[self]

    monkeypatch.setattr(server_module.MCPServer, "run", fake_run)
    server_module.run_stdio(simulated="bp6")
    assert seen["transport"] == "stdio"
    assert "power_plan" in seen["names"] and "measure_voltages" in seen["names"]
    assert seen["session"].board is None      # closed on exit


def test_hiz_bitpirate_tells_owner_the_supply_is_still_on():
    session = BoardSession(simulated="bitpirate")
    server = build_server(session)
    call(server, "connect")
    plan = call(server, "power_plan", {"millivolts": 3300, "voltage_source": "owner"})
    call(server, "power_apply", {"token": plan["token"]})
    out = call(server, "hiz")
    assert out["hiz"] is True
    assert "VIO" in out["note"] and "switch the target off" in out["note"]


def test_hiz_bp6_has_no_owner_note():
    server = build_server(BoardSession(simulated="bp6"))
    call(server, "connect")
    assert "note" not in call(server, "hiz")


# -- bus tools ----------------------------------------------------------------

BUS_TOOLS = ("i2c_scan", "i2c_read", "i2c_sensor", "i2c_write", "lcd_write", "spi_identify", "spi_transfer",
             "spi_sensor_read", "uart_send", "uart_listen")


@pytest.mark.parametrize("variant", ["v3", "v4", "bp6", "bitpirate"])
def test_bus_tools_gated_by_capability(variant):
    server = build_server(BoardSession(simulated=variant))
    call(server, "connect")
    listed = names(server)
    assert set(BUS_TOOLS) <= listed
    assert ("onewire_scan" in listed) == (variant != "bitpirate")
    for name in ("pwm", "pwm_off", "pins_read_voltage", "frequency"):
        assert (name in listed) == (variant in ("v3", "v4"))


def test_bus_tools_hidden_when_disconnected():
    server = build_server(BoardSession(simulated="v3"))
    assert not set(BUS_TOOLS) & names(server)


def test_spi_transfer_other_mode_on_bitpirate_is_an_error():
    server = build_server(BoardSession(simulated="bitpirate"))
    call(server, "connect")
    out = call(server, "spi_transfer", {"write_hex": "9f", "read_count": 3, "mode": 2})
    assert "spi_modes" in out["error"]


def test_i2c_scan_through_server_reports_power_note():
    server = build_server(BoardSession(simulated="bp6"))
    call(server, "connect")
    out = call(server, "i2c_scan")
    assert "0x76" in [d["address"] for d in out["devices"]]
    assert out["power"] is False and "approve power" in out["note"]


def test_bad_address_is_an_error_not_a_crash():
    server = build_server(BoardSession(simulated="v3"))
    call(server, "connect")
    out = call(server, "i2c_read", {"address": 0xA0, "register": 0})
    assert out == {"error": "that looks like an 8-bit address — use 0x50"}


def test_power_applied_then_bus_tool_reports_powered():
    session = BoardSession(simulated="bp6")
    server = build_server(session)
    call(server, "connect")
    plan = call(server, "power_plan", {"millivolts": 3300, "voltage_source": "owner"})
    call(server, "power_apply", {"token": plan["token"]})
    out = call(server, "spi_identify")
    assert out["power"] is True and "note" not in out
    assert session.board.status().psu_enabled is True


def test_board_gone_in_bus_tool_regates():
    session = BoardSession(simulated="v3")
    server = build_server(session)
    call(server, "connect")

    def gone(*a, **k):
        raise OSError(6, "Device not configured")

    session.board.serial.read = gone
    out = call(server, "i2c_scan")
    assert out == {"error": "board disconnected — plug it back in and call connect"}
    assert names(server) == set(ALWAYS)


# -- final review fixes ---------------------------------------------------------

def _tripped_status(session, **fields):
    """Make the simulated BP6 report a tripped (or dead) supply from now on."""
    import dataclasses
    real = session.board.status

    def status(*a, **k):
        return dataclasses.replace(real(*a, **k), **fields)

    session.board.status = status


@pytest.mark.parametrize("fields", [{"psu_tripped": True, "psu_enabled": False},
                                    {"psu_tripped": False, "psu_enabled": False}])
def test_power_apply_bp6_trip_is_an_error_not_applied(fields):
    session = BoardSession(simulated="bp6")
    server = build_server(session)
    call(server, "connect")
    off_calls = []
    real_set_power = session.board.set_power

    def set_power(on, *a, **k):
        if not on:
            off_calls.append(True)
        return real_set_power(on, *a, **k)

    session.board.set_power = set_power
    _tripped_status(session, **fields)
    plan = call(server, "power_plan", {"millivolts": 3300, "voltage_source": "owner"})
    out = call(server, "power_apply", {"token": plan["token"]})
    assert "error" in out and "tripped" in out["error"] and "100 mA" in out["error"]
    assert "short" in out["error"]
    assert out.get("applied") is False
    assert session.power is None
    assert off_calls                                  # switched back off
    assert call(server, "spi_identify")["power"] is False   # bus tools do not re-enable it


def test_power_apply_bp6_trip_clears_an_earlier_plan():
    session = BoardSession(simulated="bp6")
    server = build_server(session)
    call(server, "connect")
    plan = call(server, "power_plan", {"millivolts": 3300, "voltage_source": "owner"})
    call(server, "power_apply", {"token": plan["token"]})
    assert session.power is not None
    _tripped_status(session, psu_tripped=True, psu_enabled=False)
    plan = call(server, "power_plan", {"millivolts": 5000, "voltage_source": "owner"})
    assert "error" in call(server, "power_apply", {"token": plan["token"]})
    assert session.power is None


@pytest.mark.parametrize("variant", ["v3", "v4"])
def test_power_apply_v3_v4_says_supply_is_per_job(variant):
    server = build_server(BoardSession(simulated=variant))
    call(server, "connect")
    plan = call(server, "power_plan", {"millivolts": 3300, "voltage_source": "owner"})
    out = call(server, "power_apply", {"token": plan["token"]})
    assert "each bus job" in out["note"] and "approved and applied" in out["note"]


def test_power_apply_rechecks_variant_under_the_lock(monkeypatch):
    session = _swappable()
    server = build_server(session)
    call(server, "connect", {"port": "v3"})
    plan = call(server, "power_plan", {"millivolts": 3300, "voltage_source": "owner"})
    call(server, "connect", {"port": "bp6"})
    # The check before the lock sees a stale v3; the one inside session.run must not.
    monkeypatch.setattr(BoardSession, "variant", property(lambda self: "v3"))
    out = call(server, "power_apply", {"token": plan["token"]})
    assert "error" in out and "nothing was switched" in out["error"]
    assert session.power is None
    assert session.run(lambda bp: bp.status().psu_enabled) is False


def test_power_notes_say_v3_supply_is_per_job():
    from buspirate.mcp import knowledge
    text = " ".join(knowledge.read("power").split())
    assert "each bus job" in text and "approved and applied" in text


def _while_session_held(session, server, tool, args=None):
    """Call ``tool`` while another thread holds the session lock, as uart_listen
    does for up to 30 s. Returns (seconds the loop took to answer another tool
    meanwhile, whether ``tool`` had finished before the session was free, its
    result)."""
    import threading
    import time

    held, release = threading.Event(), threading.Event()

    def hold(bp):
        held.set()
        release.wait(10)

    holder = threading.Thread(target=session.run, args=(hold,))
    holder.start()
    assert held.wait(5)

    async def scenario():
        waiting = asyncio.ensure_future(server.call_tool(tool, args or {}))
        await asyncio.sleep(0.2)          # let the tool start and reach the lock
        started = time.monotonic()
        quick = await server.call_tool("knowledge_topics", {})
        took = time.monotonic() - started
        assert json.loads(quick.content[0].text)["topics"]
        early = waiting.done()
        release.set()
        result = await asyncio.wait_for(waiting, 5)
        return took, early, json.loads(result.content[0].text)

    try:
        return asyncio.run(scenario())
    finally:
        release.set()
        holder.join(5)


@pytest.mark.parametrize("tool", ["hiz", "power_off", "board_status", "measure_voltages",
                                  "disconnect"])
def test_board_tools_do_not_block_the_event_loop(tool):
    """While a worker holds the session, the loop keeps serving other tools, and
    the waiting tool finishes as soon as the session is free."""
    session = BoardSession(simulated="bp6")
    server = build_server(session)
    call(server, "connect")
    took, early, out = _while_session_held(session, server, tool)
    assert took < 2                       # the loop was not frozen
    assert not early                      # it did wait for the session
    assert "error" not in out


def test_connect_does_not_block_the_event_loop():
    session = BoardSession(simulated="v3")
    server = build_server(session)
    call(server, "connect")
    took, early, out = _while_session_held(session, server, "connect")
    assert took < 2 and not early
    assert out["connected"] is True


def test_power_apply_does_not_block_the_event_loop():
    session = BoardSession(simulated="bp6")
    server = build_server(session)
    call(server, "connect")
    plan = call(server, "power_plan", {"millivolts": 3300, "voltage_source": "owner"})
    took, early, out = _while_session_held(session, server, "power_apply",
                                           {"token": plan["token"]})
    assert took < 2 and not early
    assert out["applied"] is True


def test_lcd_write_and_i2c_write_through_the_server():
    server = build_server(BoardSession(simulated="bp6"))
    call(server, "connect")
    assert call(server, "i2c_write", {"address": 0x76, "data_hex": "f4 27"})["written_bytes"] == 2
    out = call(server, "lcd_write", {"message": "Hello World", "address": 0x76})
    assert out["sent_bytes"] > 0 and out["power"] is False and "note" in out
    assert "error" in call(server, "i2c_write", {"address": 0x76, "data_hex": "zz"})


def test_lcd_write_and_i2c_write_through_the_server():
    server = build_server(BoardSession(simulated="bp6"))
    call(server, "connect")
    assert call(server, "i2c_write", {"address": 0x76, "data_hex": "f4 27"})["written_bytes"] == 2
    out = call(server, "lcd_write", {"message": "Hello World", "address": 0x76})
    assert out["sent_bytes"] > 0 and out["power"] is False and "note" in out
    assert "error" in call(server, "i2c_write", {"address": 0x76, "data_hex": "zz"})
