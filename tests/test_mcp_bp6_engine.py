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
    toys = lambda query: [r["name"] for r in find_recipes(query)  # noqa: E731
                          if r["name"].startswith("toy-")]  # the real recipes share the registry
    assert toys("pcf8574") == ["toy-backpack"]
    assert toys("temperature") == ["toy-sensor"]
    assert {r["name"] for r in find_recipes("toy")} >= {"toy-backpack", "toy-sensor"}
    first = find_recipes("toy")[0]
    assert (first["name"], first["title"], first["bus"]) == (
        "toy-backpack", "Toy I2C backpack", "i2c")
    assert first["source"]
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


def _destructive(recipes, calls, identity=None, result=None):
    ident = identity if identity is not None else ["toy-1"]

    def check(bp, opts):
        return {"ok": True, "identity": ident[0]}

    def prepare(bp, opts):
        """Read what would change."""
        calls.append("prepare")
        return {"chip": "toy", "operation": "write", "start": 0, "length": 4,
                "summary": "s", "backup": None, "_data": b"abcd"}

    def commit(bp, opts, prepared):
        calls.append(("commit", prepared["_data"], prepared["_identity"]))
        return dict(result) if result is not None else {"written": 4}

    return recipes(name="toy-write", risk="destructive", check=check, action=prepare,
                   commit=commit, default_mv=3300, max_mv=3600)


def _prepared(session, confirm, **options):
    token = engine.plan_recipe(session, confirm, "toy-write", options)["token"]
    return engine.run_recipe(session, confirm, token, {})


def test_destructive_plan_warns(session, confirm, recipes):
    _destructive(recipes, [])
    plan = engine.plan_recipe(session, confirm, "toy-write", {})
    assert engine.PREPARE_NOTE in plan["warnings"] and "token" in plan
    assert engine.NO_BACKUP_NOTE not in plan["warnings"]
    plan = engine.plan_recipe(session, confirm, "toy-write", {"backup": False})
    assert engine.NO_BACKUP_NOTE in plan["warnings"]


def test_destructive_run_prepares_only(session, confirm, recipes):
    calls = []
    _destructive(recipes, calls)
    out = _prepared(session, confirm)
    assert out["commit"]["token"] and "_data" not in out["commit"]
    assert out["commit"]["chip"] == "toy" and out["stopped"] == "the change needs its own yes"
    assert calls == ["prepare"]


def test_commit_runs_once(session, confirm, recipes):
    calls = []
    _destructive(recipes, calls)
    token = _prepared(session, confirm)["commit"]["token"]
    out = engine.commit_recipe(session, confirm, token)
    assert out == {"recipe": "toy-write", "committed": True, "result": {"written": 4}}
    assert calls[-1] == ("commit", b"abcd", "toy-1")
    assert "error" in engine.commit_recipe(session, confirm, token)
    assert len(calls) == 2


def test_commit_unverified_not_committed(session, confirm, recipes):
    calls = []
    _destructive(recipes, calls, result={"verified": False})
    token = _prepared(session, confirm)["commit"]["token"]
    out = engine.commit_recipe(session, confirm, token)
    assert out["committed"] is False and out["result"] == {"verified": False}
    assert len(calls) == 2


def test_commit_error_not_committed(session, confirm, recipes):
    calls = []
    _destructive(recipes, calls, result={"error": "x", "verified": False})
    token = _prepared(session, confirm)["commit"]["token"]
    out = engine.commit_recipe(session, confirm, token)
    assert out["committed"] is False and out["result"] == {"error": "x", "verified": False}
    assert len(calls) == 2


def test_commit_refused_after_hiz(session, confirm, recipes):
    calls = []
    _destructive(recipes, calls)
    token = _prepared(session, confirm)["commit"]["token"]
    session.run(lambda bp: bp.hiz())
    assert "error" in engine.commit_recipe(session, confirm, token)
    assert _fake(session).psu_enabled is False and calls == ["prepare"]


def test_commit_never_powers(session, confirm, recipes, monkeypatch):
    calls = []
    _destructive(recipes, calls)
    token = _prepared(session, confirm)["commit"]["token"]

    def boom(*a, **k):
        raise AssertionError("commit switched something")

    monkeypatch.setattr(type(session.board), "set_power", boom, raising=False)
    monkeypatch.setattr(type(session.board), "set_pullups", boom, raising=False)
    assert engine.commit_recipe(session, confirm, token)["committed"] is True


def test_commit_refused_identity_changed(session, confirm, recipes):
    calls, ident = [], ["toy-1"]
    _destructive(recipes, calls, ident)
    token = _prepared(session, confirm)["commit"]["token"]
    ident[0] = "toy-2"
    assert "error" in engine.commit_recipe(session, confirm, token)
    assert calls == ["prepare"]


def test_commit_refused_other_port(session, confirm, recipes):
    calls = []
    _destructive(recipes, calls)
    token = _prepared(session, confirm)["commit"]["token"]
    session.port = "/dev/other"
    assert "error" in engine.commit_recipe(session, confirm, token)
    assert calls == ["prepare"]


def test_tokens_not_interchangeable(session, confirm, recipes):
    calls = []
    _destructive(recipes, calls)
    power_token = engine.plan_recipe(session, confirm, "toy-write", {})["token"]
    assert "error" in engine.commit_recipe(session, confirm, power_token)
    power_token = engine.plan_recipe(session, confirm, "toy-write", {})["token"]
    commit_token = engine.run_recipe(session, confirm, power_token, {})["commit"]["token"]
    assert "error" in engine.run_recipe(session, confirm, commit_token, {})


def test_rerun_destructive_new_token(session, confirm, recipes):
    calls = []
    _destructive(recipes, calls)
    first = _prepared(session, confirm)["commit"]["token"]
    again = engine.run_recipe(session, confirm, None, {})["commit"]["token"]
    assert again and again != first and calls == ["prepare", "prepare"]


def test_run_cannot_change_backup(session, confirm, recipes):
    calls = []
    _destructive(recipes, calls)
    token = engine.plan_recipe(session, confirm, "toy-write", {"backup": True})["token"]
    assert "error" in engine.run_recipe(session, confirm, token, {"backup": False})
    assert calls == []
    token = engine.plan_recipe(session, confirm, "toy-write", {"backup": True})["token"]
    assert "commit" in engine.run_recipe(session, confirm, token, {})
    assert "error" in engine.run_recipe(session, confirm, None, {"backup": False})


def test_destructive_without_identity_no_token(session, confirm, recipes):
    calls, ident = [], [None]
    _destructive(recipes, calls, ident)
    out = _prepared(session, confirm)
    assert "commit" not in out and out["stopped"] == "check failed" and calls == []
    ident[0] = ""
    assert "commit" not in _prepared(session, confirm)


def test_recipe_commit_required():
    with pytest.raises(ValueError):
        _toy(name="x", risk="destructive", commit=None)
    with pytest.raises(ValueError):
        _toy(name="y", risk="none", commit=lambda bp, o, p: {})


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


# -- fix round 1 ----------------------------------------------------------------------

def test_target_powered_run_clears_a_stale_power_plan(session, confirm, recipes):
    from buspirate.mcp.jobs import i2c_scan
    from buspirate.mcp.power import SOURCE_OWNER, plan_power

    recipes()
    fake = _fake(session)
    fake.adc_mv = [3300] * 8
    token = engine.plan_recipe(session, confirm, "toy-backpack", {})["token"]
    session.power = plan_power("bp6", 5000, SOURCE_OWNER)  # left over; supply is off
    assert "error" not in engine.run_recipe(session, confirm, token, {})
    assert session.power is None
    i2c_scan(session)  # a universal bus tool afterwards must not switch our supply on
    assert fake.psu_enabled is False


def test_identify_plan_has_no_above_default_warning(session, confirm, recipes):
    recipes(name="toy-identify", default_mv=0, min_mv=800, max_mv=5000)
    plan = engine.plan_recipe(session, confirm, "toy-identify", {"millivolts": 3300})
    assert not any("default" in w for w in plan["warnings"])


def test_millivolts_none_is_absent_and_non_integer_refused(session, confirm, recipes):
    recipes(default_mv=3300)
    plan = engine.plan_recipe(session, confirm, "toy-backpack", {"millivolts": None})
    assert plan["power"]["millivolts"] == 3300 and plan["token"]
    recipes(name="toy-identify", default_mv=0, min_mv=800, max_mv=5000)
    assert engine.plan_recipe(session, confirm, "toy-identify",
                              {"millivolts": None})["error"].startswith("ask the owner")
    for bad in ("3300", 3.3, True):
        plan = engine.plan_recipe(session, confirm, "toy-backpack", {"millivolts": bad})
        assert "error" in plan and "token" not in plan


# -- terminal recipes -------------------------------------------------------------

from buspirate.mcp import jobs  # noqa: E402
from buspirate.mcp_bp6 import state  # noqa: E402


def _term_check(con, opts):
    assert con.mode  # the console, not the board
    return {"ok": True}


def _term_action(con, opts):
    """Ask the terminal for its info."""
    return {"mode": con.command("i").mode}


def _term(**changes):
    fields = dict(name="toy-term", transport="terminal", terminal_mode="dio",
                  default_mv=3300, check=_term_check, action=_term_action, options={})
    fields.update(changes)
    return fields


def _sent(session, since):
    """The terminal lines sent since ``since``, without the Enters that wake it."""
    return [ln for ln in _fake(session).lines_received()[since:] if ln != b"\r"]


def _mark(session):
    return len(_fake(session).lines_received())


def _term_ran(session, confirm):
    plan = engine.plan_recipe(session, confirm, "toy-term", {})
    result = engine.run_recipe(session, confirm, plan["token"], {})
    assert "error" not in result, result
    return plan, result


def test_terminal_recipe_powers_after_mode(session, confirm, recipes):
    recipes(**_term())
    plan = engine.plan_recipe(session, confirm, "toy-term", {})
    mark = _mark(session)
    result = engine.run_recipe(session, confirm, plan["token"], {})
    assert "error" not in result, result
    assert _sent(session, mark) == [b"m dio\r", b"W 3.30 100\r", b"P\r", b"i\r"]
    assert result["result"] == {"mode": "DIO"} and result["check"]["ok"] is True
    assert result["power"]["vout_mv"] == 3300 and result["power"]["applied"] is True
    assert session.power is not None and session.power.to_dict() == plan["power"]
    assert _fake(session).psu_enabled and _fake(session).pullups
    assert state.of(session).terminal_mode == "dio"


def test_terminal_recipe_target_powered_sends_no_W(session, confirm, recipes):
    recipes(**_term())
    _fake(session).adc_mv = [3300] * 8
    plan = engine.plan_recipe(session, confirm, "toy-term", {})
    assert plan["target_powered"] is True
    mark = _mark(session)
    result = engine.run_recipe(session, confirm, plan["token"], {})
    assert "error" not in result, result
    assert _sent(session, mark) == [b"m dio\r", b"P\r", b"i\r"]
    assert session.power is None and _fake(session).psu_enabled is False


def test_target_powered_refused_when_not_ok(session, confirm, recipes):
    recipes(**_term(target_powered_ok=False))
    _fake(session).adc_mv = [3300] * 8
    plan = engine.plan_recipe(session, confirm, "toy-term", {})
    assert "token" not in plan and "3300" in plan["error"]


def test_trip_during_W_clears_power(session, confirm, recipes):
    recipes(**_term())
    plan = engine.plan_recipe(session, confirm, "toy-term", {})
    _fake(session).trip_next_w = True
    mark = _mark(session)
    result = engine.run_recipe(session, confirm, plan["token"], {})
    assert "Current over limit" in result["error"]
    assert session.power is None and _fake(session).psu_enabled is False
    assert b"i\r" not in _sent(session, mark) and "result" not in result
    assert session.last_recipe is None


def test_rerun_wrong_mode_refused(session, confirm, recipes):
    recipes(**_term())
    _term_ran(session, confirm)
    jobs.i2c_scan(session, 100)
    mark = _mark(session)
    result = engine.run_recipe(session, confirm, None, {})
    assert result["error"] == "plan again: the board is in I2C mode now"
    assert not any(ln.startswith((b"m ", b"W")) for ln in _sent(session, mark))


def test_rerun_same_mode_sends_no_m_or_W(session, confirm, recipes):
    recipes(**_term())
    _term_ran(session, confirm)
    mark = _mark(session)
    result = engine.run_recipe(session, confirm, None, {})
    assert "error" not in result, result
    assert _sent(session, mark) == [b"i\r"]
    assert result["result"] == {"mode": "DIO"}


def test_terminal_destructive_refused():
    with pytest.raises(ValueError):
        _toy(**_term(risk="destructive", commit=lambda con, opts, prepared: {}))


def test_precheck_runs_over_bpio2_first(session, confirm, recipes):
    seen = []

    def precheck(bp, opts):
        seen.append(bp.status().mode)  # BPIO2 answers: the console is not open
        return {"ok": False, "error": "no target found", "hint": "wire it up"}

    recipes(**_term(precheck=precheck))
    plan = engine.plan_recipe(session, confirm, "toy-term", {})
    mark = _mark(session)
    result = engine.run_recipe(session, confirm, plan["token"], {})
    assert seen and result["check"]["ok"] is False and result["stopped"] == "check failed"
    assert result["hint"] == "wire it up" and "result" not in result
    assert _fake(session).lines_received()[mark:] == []  # the terminal port was never opened
    assert _fake(session).psu_enabled is False and session.power is None


def test_hiz_returns_terminal_to_hiz(session, confirm, recipes):
    pytest.importorskip("mcp")
    import asyncio
    import json

    from buspirate.mcp_bp6.server import build_server

    recipes(**_term())
    _term_ran(session, confirm)
    fake = _fake(session)
    fake.pwm.update({0: (1000.0, 50.0), 2: (2000.0, 25.0)})  # as two G commands leave it
    state.of(session).pwm_pins.update({2, 0})
    mark = _mark(session)
    server = build_server(session)
    out = json.loads(asyncio.run(server.call_tool("hiz", {})).content[0].text)
    assert out["hiz"] is True
    assert _sent(session, mark) == [b"g 0\r", b"g 2\r", b"m hiz\r"]
    assert fake.mode == "HiZ" and not fake.pwm and fake.psu_enabled is False
    assert session.power is None
    assert state.of(session).pwm_pins == set() and state.of(session).terminal_mode is None
    # With no terminal mode recorded, hiz opens no console.
    mark = _mark(session)
    asyncio.run(server.call_tool("hiz", {}))
    assert _fake(session).lines_received()[mark:] == []


TRIP = "\x07\r\nError: Current over limit, power supply disabled\r\n"


def _tripping_action(session, on_call):
    calls = []

    def action(con, opts):
        """Trip the supply while the action runs."""
        calls.append(1)
        if len(calls) == on_call:
            fake = _fake(session)
            fake.psu_enabled, fake.psu_tripped = False, True
            fake._say(TRIP)  # printed by the board on its own, between commands
        return {"mode": con.command("i").mode}
    return action


def test_trip_during_action_clears_power(session, confirm, recipes):
    recipes(**_term(action=_tripping_action(session, 1)))
    plan = engine.plan_recipe(session, confirm, "toy-term", {})
    result = engine.run_recipe(session, confirm, plan["token"], {})
    assert "Current over limit" in result["error"] and "plan again" in result["error"]
    assert result["power"] is None and session.power is None
    assert session.last_recipe is None


def test_trip_during_rerun_action_clears_power(session, confirm, recipes):
    recipes(**_term(action=_tripping_action(session, 2)))
    _term_ran(session, confirm)
    assert session.power is not None
    result = engine.run_recipe(session, confirm, None, {})
    assert "Current over limit" in result["error"]
    assert result["power"] is None and session.power is None
    assert engine.run_recipe(session, confirm, None, {})["error"].startswith("plan again")


def test_terminal_recipe_refuses_a_voltage_off_the_10_mv_step(session, confirm):
    mark = _mark(session)
    plan = engine.plan_recipe(session, confirm, "pwm-signal", {"millivolts": 3333})
    assert "token" not in plan
    assert plan["error"].startswith("3333 mV cannot be set through the terminal")
    assert "3330 mV" in plan["error"]
    assert _fake(session).lines_received()[mark:] == []
    assert "token" in engine.plan_recipe(session, confirm, "pwm-signal", {"millivolts": 3330})


def test_bpio2_recipe_keeps_any_millivolt(session, confirm, recipes):
    recipes()
    assert "token" in engine.plan_recipe(session, confirm, "toy-backpack", {"millivolts": 3333})


def test_terminal_flags_on_m_line(session, confirm, recipes):
    recipes(**_term(terminal_mode="i2c", terminal_flags="-s 400"))
    plan = engine.plan_recipe(session, confirm, "toy-term", {})
    mark = _mark(session)
    result = engine.run_recipe(session, confirm, plan["token"], {})
    assert "error" not in result, result
    assert _sent(session, mark)[0] == b"m i2c -s 400\r"


def test_terminal_flags_only_for_terminal():
    with pytest.raises(ValueError):
        _toy(transport="bpio2", terminal_flags="-s 400")
