"""The recipe engine: when the target supply may switch on, and when a recipe may re-run."""

import dataclasses

import pytest

from buspirate.mcp.confirm import ConfirmStore
from buspirate.mcp.session import BoardSession
from buspirate.mcp_bp6 import engine
from buspirate.mcp_bp6.recipes import REGISTRY, Recipe, find_recipes, register

LCD = 0x27


def _check(bp, opts):
    with bp.i2c() as m:
        first = m.read(opts["address"], 1)
    return {"ok": True, "first_byte": first[0]}


def _action(bp, opts):
    """Write one byte to the backpack."""
    with bp.i2c() as m:
        m.write(opts["address"], bytes([opts["byte"]]))
    return {"wrote": opts["byte"]}


def _toy(**changes):
    fields = dict(
        name="toy-backpack", title="Toy I2C backpack", words=("toy", "backpack", "pcf8574"),
        bus="i2c", default_mv=5000, min_mv=2500, max_mv=5000, pullups=True,
        wiring=(("VCC", "VOUT"), ("GND", "GND"), ("SDA", "IO0"), ("SCL", "IO1")),
        check=_check, action=_action, options={"address": LCD, "byte": 0x08},
        source="https://docs.buspirate.com/docs/devices/i2c-lcd",
    )
    fields.update(changes)
    return Recipe(**fields)


@pytest.fixture
def recipes():
    added = []

    def add(**changes):
        r = register(_toy(**changes))
        added.append(r.name)
        return r

    yield add
    for name in added:
        REGISTRY.pop(name, None)


@pytest.fixture
def session():
    s = BoardSession(simulated="bp6")
    s.connect()
    fake = s.board.serial.owner
    fake.add_i2c_device(LCD)
    yield s
    s.disconnect()


def _fake(session):
    return session.board.serial.owner


@pytest.fixture
def confirm():
    return ConfirmStore()


# -- the model --------------------------------------------------------------------

def test_register_refuses_a_duplicate_name(recipes):
    recipes()
    with pytest.raises(ValueError):
        register(_toy())


def test_find_recipes_by_name_word_and_title(recipes):
    recipes()
    recipes(name="toy-sensor", title="Toy temperature sensor", words=("thermometer",))
    assert find_recipes("toy-backpack")[0]["name"] == "toy-backpack"
    assert [r["name"] for r in find_recipes("pcf8574")] == ["toy-backpack"]
    assert [r["name"] for r in find_recipes("temperature")] == ["toy-sensor"]
    assert {r["name"] for r in find_recipes("toy")} >= {"toy-backpack", "toy-sensor"}
    assert find_recipes("toy")[0] == {"name": "toy-backpack", "title": "Toy I2C backpack",
                                      "bus": "i2c"}
    assert {"toy-backpack", "toy-sensor"} <= {r["name"] for r in find_recipes(None)}
    assert find_recipes("no-such-thing") == []


# -- planning ---------------------------------------------------------------------

def test_plan_unpowered_target_gives_one_yes(session, confirm, recipes):
    recipes()
    plan = engine.plan_recipe(session, confirm, "toy-backpack", {})
    assert "error" not in plan
    assert plan["power"]["millivolts"] == 5000 and plan["power"]["milliamps"] == 100
    assert plan["needs_extra_confirmation"] is False  # 5 V is the recipe's own default
    assert plan["target_powered"] is False and plan["token"]
    assert {"pin": "VOUT", "colour": "red", "target": "VCC"}.items() <= plan["wiring"][0].items()
    assert plan["action"] == "Write one byte to the backpack."
    assert _fake(session).psu_enabled is False  # planning switches nothing on


def test_override_above_default_asks_twice(session, confirm, recipes):
    recipes(default_mv=3300)
    plan = engine.plan_recipe(session, confirm, "toy-backpack", {"millivolts": 5000})
    assert plan["power"]["millivolts"] == 5000 and plan["needs_extra_confirmation"] is True


def test_no_current_limit_asks_twice(session, confirm, recipes):
    recipes(default_mv=3300, milliamps=0)
    assert engine.plan_recipe(session, confirm, "toy-backpack", {})["needs_extra_confirmation"]


def test_out_of_range_refused_no_token(session, confirm, recipes):
    recipes(default_mv=3300, max_mv=3600)
    plan = engine.plan_recipe(session, confirm, "toy-backpack", {"millivolts": 5000})
    assert "error" in plan and "token" not in plan
    assert "3600" in plan["error"]
    assert confirm._items == {}


def test_unknown_recipe_refused(session, confirm):
    assert "error" in engine.plan_recipe(session, confirm, "no-such-recipe", {})


def test_target_powered_plans_no_supply(session, confirm, recipes):
    recipes()
    _fake(session).adc_mv = [3300] * 8
    plan = engine.plan_recipe(session, confirm, "toy-backpack", {})
    assert plan["power"] is None and plan["target_powered"] is True
    assert plan["target_mv"] == 3300 and plan["token"]
    assert plan["needs_extra_confirmation"] is False
    assert any("own" in w for w in plan["warnings"])


def test_target_powered_by_vout_alone(session, confirm, recipes):
    recipes()
    _fake(session).vout_mv = 3300  # simulator only: VOUT read while the supply is off
    plan = engine.plan_recipe(session, confirm, "toy-backpack", {})
    assert plan["target_powered"] is True and plan["target_mv"] == 3300


def test_target_powered_out_of_range_refused(session, confirm, recipes):
    recipes(default_mv=3300, max_mv=3600)
    _fake(session).adc_mv = [5000] * 8
    plan = engine.plan_recipe(session, confirm, "toy-backpack", {})
    assert "error" in plan and "token" not in plan
    assert "5000" in plan["error"] and "3600" in plan["error"]


def test_own_supply_already_on_is_not_target_power(session, confirm, recipes):
    recipes(default_mv=3300)
    session.run(lambda bp: (bp.set_power(True, 5000, 100), bp.set_pullups(True)))
    plan = engine.plan_recipe(session, confirm, "toy-backpack", {})
    assert plan["target_powered"] is False and plan["power"]["millivolts"] == 3300


def test_identify_needs_voltage(session, confirm, recipes):
    recipes(name="toy-identify", default_mv=0, min_mv=800, max_mv=5000)
    plan = engine.plan_recipe(session, confirm, "toy-identify", {})
    assert "token" not in plan and "3.3 V is usual" in plan["error"]
    plan = engine.plan_recipe(session, confirm, "toy-identify", {"millivolts": 3300})
    assert plan["power"]["millivolts"] == 3300 and plan["token"]
    assert plan["needs_extra_confirmation"] is False
    plan = engine.plan_recipe(session, confirm, "toy-identify", {"millivolts": 5000})
    assert plan["needs_extra_confirmation"] is True


def test_identify_on_a_powered_target_needs_no_voltage(session, confirm, recipes):
    recipes(name="toy-identify", default_mv=0, min_mv=800, max_mv=5000)
    _fake(session).adc_mv = [1800] * 8
    plan = engine.plan_recipe(session, confirm, "toy-identify", {})
    assert plan["target_powered"] is True and plan["token"]


def test_recipe_without_supply_skips_measuring(session, confirm, recipes):
    recipes(name="toy-led", bus="led", default_mv=0, min_mv=0, max_mv=0,
            wiring=(), options={})
    _fake(session).adc_mv = [5000] * 8  # would refuse anything if it were measured
    plan = engine.plan_recipe(session, confirm, "toy-led", {})
    assert plan["power"] is None and plan["target_powered"] is False
    assert plan["needs_extra_confirmation"] is False and plan["token"]


# -- running ----------------------------------------------------------------------

def test_run_applies_power_then_action(session, confirm, recipes):
    recipes()
    token = engine.plan_recipe(session, confirm, "toy-backpack", {})["token"]
    result = engine.run_recipe(session, confirm, token, {})
    fake = _fake(session)
    assert result["recipe"] == "toy-backpack"
    assert result["power"]["applied"] is True and fake.psu_enabled and fake.psu_mv == 5000
    assert result["check"]["ok"] is True and result["result"] == {"wrote": 0x08}
    assert fake._pointer[LCD] == 0x08  # the action's byte reached the target
    assert session.power is not None and session.power.millivolts == 5000
    assert session.last_recipe["name"] == "toy-backpack" and session.last_recipe["mv"] == 5000


def test_token_single_use(session, confirm, recipes):
    recipes()
    token = engine.plan_recipe(session, confirm, "toy-backpack", {})["token"]
    assert "error" not in engine.run_recipe(session, confirm, token, {})
    assert "error" in engine.run_recipe(session, confirm, token, {})


def test_token_for_another_port_refused(session, confirm, recipes):
    recipes()
    token = engine.plan_recipe(session, confirm, "toy-backpack", {})["token"]
    session.port = "elsewhere"
    result = engine.run_recipe(session, confirm, token, {})
    assert "error" in result and _fake(session).psu_enabled is False


def test_run_refuses_when_a_voltage_appeared_since_planning(session, confirm, recipes):
    recipes()
    token = engine.plan_recipe(session, confirm, "toy-backpack", {})["token"]
    _fake(session).adc_mv = [3300] * 8  # the owner powered the target meanwhile
    result = engine.run_recipe(session, confirm, token, {})
    assert "plan again" in result["error"] and _fake(session).psu_enabled is False


def test_run_load_over_limit_leaves_power_off(session, confirm, recipes):
    recipes()
    token = engine.plan_recipe(session, confirm, "toy-backpack", {})["token"]
    _fake(session).load_ma = 200  # the board refuses to start into this
    result = engine.run_recipe(session, confirm, token, {})
    assert "100 mA" in result["error"] and "check" not in result and "result" not in result
    assert session.power is None and _fake(session).psu_enabled is False
    assert _fake(session)._pointer[LCD] == 0  # the action never ran
    assert session.last_recipe is None


def test_run_trip_after_enable_stops(session, confirm, recipes):
    recipes()
    token = engine.plan_recipe(session, confirm, "toy-backpack", {})["token"]
    bp = session.board
    real = bp.status
    bp.status = lambda *a, **k: dataclasses.replace(
        real(*a, **k), psu_tripped=True, psu_enabled=False)
    try:
        result = engine.run_recipe(session, confirm, token, {})
    finally:
        bp.status = real
    assert "error" in result and result["power"]["applied"] is False
    assert "check" not in result and "result" not in result
    assert session.power is None and _fake(session).psu_enabled is False
    assert _fake(session)._pointer[LCD] == 0


def test_check_failure_stops_and_leaves_power_on(session, confirm, recipes):
    recipes()
    token = engine.plan_recipe(session, confirm, "toy-backpack", {"address": 0x3F})["token"]
    result = engine.run_recipe(session, confirm, token, {})
    assert result["stopped"] == "check failed" and result["hint"]
    assert "result" not in result
    assert _fake(session).psu_enabled is True  # left on so the owner can fix and re-run


def test_check_returning_not_ok_stops(session, confirm, recipes):
    recipes(check=lambda bp, opts: {"ok": False, "hint": "turn the contrast pot"})
    token = engine.plan_recipe(session, confirm, "toy-backpack", {})["token"]
    result = engine.run_recipe(session, confirm, token, {})
    assert result["stopped"] == "check failed" and result["hint"] == "turn the contrast pot"
    assert _fake(session)._pointer[LCD] == 0


def test_target_powered_run_switches_no_supply(session, confirm, recipes):
    recipes()
    fake = _fake(session)
    fake.adc_mv = [3300] * 8
    token = engine.plan_recipe(session, confirm, "toy-backpack", {})["token"]
    result = engine.run_recipe(session, confirm, token, {})
    assert result["power"] is None and result["result"] == {"wrote": 0x08}
    assert fake.psu_enabled is False and session.power is None
    assert fake.pullups is True  # fed from the target's VOUT


def test_target_powered_run_refused_if_target_went_out_of_range(session, confirm, recipes):
    recipes(default_mv=3300, max_mv=3600)
    fake = _fake(session)
    fake.adc_mv = [3300] * 8
    token = engine.plan_recipe(session, confirm, "toy-backpack", {})["token"]
    fake.adc_mv = [5000] * 8
    assert "error" in engine.run_recipe(session, confirm, token, {})
    assert fake._pointer[LCD] == 0


def test_destructive_refused(session, confirm, recipes):
    recipes(name="toy-erase", risk="destructive")
    plan = engine.plan_recipe(session, confirm, "toy-erase", {})
    assert plan["error"] == "erase and write recipes arrive in phase 2" and "token" not in plan
    session.last_recipe = {"name": "toy-erase", "options": {"address": LCD, "byte": 8},
                           "mv": 0, "supply": "none", "until": float("inf")}
    result = engine.run_recipe(session, confirm, None, {})
    assert result == {"error": "erase and write recipes arrive in phase 2"}
    assert _fake(session).psu_enabled is False


# -- re-running without a token -----------------------------------------------------

def _ran(session, confirm, **options):
    token = engine.plan_recipe(session, confirm, "toy-backpack", options)["token"]
    assert "error" not in engine.run_recipe(session, confirm, token, {})


def test_rerun_without_token_runs_check_and_action(session, confirm, recipes):
    recipes()
    _ran(session, confirm)
    result = engine.run_recipe(session, confirm, None, {"byte": 0x0C})
    assert result["result"] == {"wrote": 0x0C} and result["check"]["ok"] is True
    assert _fake(session)._pointer[LCD] == 0x0C


def test_rerun_without_a_previous_run_refused(session, confirm, recipes):
    recipes()
    assert engine.run_recipe(session, confirm, None, {})["error"].startswith("plan again")


def test_rerun_without_token_after_power_off_refused(session, confirm, recipes):
    recipes()
    _ran(session, confirm)
    session.run(lambda bp: bp.hiz())
    session.power = None
    result = engine.run_recipe(session, confirm, None, {})
    assert result["error"].startswith("plan again")
    assert _fake(session).psu_enabled is False


def test_rerun_after_supply_tripped_refused(session, confirm, recipes):
    recipes()
    _ran(session, confirm)
    _fake(session).set_load(500)  # a short while it ran: the supply cut out
    result = engine.run_recipe(session, confirm, None, {})
    assert result["error"].startswith("plan again") and _fake(session).psu_enabled is False


def test_rerun_cannot_change_millivolts(session, confirm, recipes):
    recipes(default_mv=3300)
    _ran(session, confirm)
    for change in ({"millivolts": 5000}, {"address": 0x3F}):
        result = engine.run_recipe(session, confirm, None, change)
        assert result["error"].startswith("plan again")
    assert _fake(session).psu_mv == 3300


def test_rerun_after_the_window_refused(session, confirm, recipes):
    recipes()
    _ran(session, confirm)
    session.last_recipe["until"] = 0.0
    assert engine.run_recipe(session, confirm, None, {})["error"].startswith("plan again")


def test_rerun_after_a_different_supply_voltage_refused(session, confirm, recipes):
    recipes(default_mv=3300)
    _ran(session, confirm)
    session.power = dataclasses.replace(session.power, millivolts=5000)
    assert engine.run_recipe(session, confirm, None, {})["error"].startswith("plan again")


def test_disconnect_forgets_the_last_recipe(session, confirm, recipes):
    recipes()
    _ran(session, confirm)
    session.disconnect()
    assert session.last_recipe is None
