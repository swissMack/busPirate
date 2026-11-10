import pytest

from buspirate.connect import open_simulated
from buspirate.mcp.power import (
    PSU_TRIPPED, SOURCE_OWNER, Measurement, PowerRefused, apply_plan, measure, plan_power,
    suggest_level,
)


def test_v3_refuses_1v8_and_names_alternative():
    with pytest.raises(PowerRefused, match="Bus Pirate 6|own supply"):
        plan_power("v3", 1800, SOURCE_OWNER)


def test_v4_3v3_tells_which_wire():
    plan = plan_power("v4", 3300, SOURCE_OWNER)
    assert any("red" in line and "+3.3V" in line for line in plan.instructions)
    assert any("not" in line.lower() and "+5V" in line for line in plan.instructions)


def test_bp6_default_limit_and_extra_confirmation():
    assert plan_power("bp6", 3300, SOURCE_OWNER).milliamps == 100
    assert plan_power("bp6", 5000, SOURCE_OWNER).needs_extra_confirmation
    assert plan_power("bp6", 3300, SOURCE_OWNER, milliamps=0).needs_extra_confirmation
    assert not plan_power("bp6", 3300, SOURCE_OWNER).needs_extra_confirmation


@pytest.mark.parametrize("mv", [700, 5100, 6000])
def test_bp6_out_of_range_refused(mv):
    with pytest.raises(PowerRefused):
        plan_power("bp6", mv, SOURCE_OWNER)


def test_bp6_limit_out_of_range_refused():
    with pytest.raises(PowerRefused):
        plan_power("bp6", 3300, SOURCE_OWNER, milliamps=501)


def test_bitpirate_names_dock_switch():
    plan = plan_power("bitpirate", 3300, SOURCE_OWNER)
    assert any("3V3" in line and "switch" in line for line in plan.instructions)


def test_bad_source_refused():
    with pytest.raises(ValueError):
        plan_power("bp6", 3300, "guessed")


def test_measure_bp6_and_suggest():
    bp = open_simulated("bp6")
    try:
        m = measure(bp)
        assert list(m.pins_mv) == ["IO%d" % i for i in range(8)]
        assert suggest_level(m) is None          # simulator reports 0 mV until powered
        bp.set_power(True, 3300)
        bp.set_pullups(True)
        m = measure(bp)
        assert all(isinstance(v, int) for v in m.pins_mv.values())
        assert suggest_level(m) == 3300
    finally:
        bp.close()


def test_measure_v3():
    bp = open_simulated("v3")
    try:
        m = measure(bp)
        assert list(m.pins_mv) == ["ADC"] and "yellow" in m.note
    finally:
        bp.close()


def test_measure_bitpirate_cannot():
    bp = open_simulated("bitpirate")
    try:
        m = measure(bp)
        assert m.pins_mv == {} and "cannot measure" in m.note
    finally:
        bp.close()


def test_suggest_none_when_unpowered():
    assert suggest_level(Measurement({"IO0": 12, "IO1": 0}, "")) is None


def test_suggest_nearest():
    assert suggest_level(Measurement({"IO0": 1750}, "")) == 1800
    assert suggest_level(Measurement({"IO0": 4700, "IO1": 3300}, "")) == 5000


def test_v4_pullups_one_path_only():
    text = " ".join(plan_power("v4", 3300, SOURCE_OWNER, pullups=True).instructions)
    assert "VPU (green) unconnected" in text and "set_pullup_voltage" in text
    assert "to the target's VCC" not in text.split("pull-ups:")[1]
    v3 = " ".join(plan_power("v3", 3300, SOURCE_OWNER, pullups=True).instructions)
    assert "wire VPU (green) to the target's VCC" in v3


class _Session:
    power = None


def test_apply_plan_bp6_records_power():
    bp = open_simulated("bp6")
    try:
        session = _Session()
        plan = plan_power("bp6", 3300, SOURCE_OWNER)
        result = apply_plan(bp, session, plan)
        assert session.power is plan
        assert result["psu_enabled"] is True and result["applied"] is True
    finally:
        bp.close()


def _bp6_with_load(load_ma):
    from buspirate.bp6 import BusPirate6
    from buspirate.simulator_bp6 import FakeBp6

    fake = FakeBp6(load_ma=load_ma)
    bp = BusPirate6(FakeBp6.BINARY, terminal_port=FakeBp6.TERMINAL,
                    serial_factory=fake.factory(), connect_timeout=0.2).open()
    return fake, bp


def test_apply_plan_trip_leaves_power_off():
    import dataclasses

    fake, bp = _bp6_with_load(12)
    try:
        real = bp.status
        bp.status = lambda *a, **k: dataclasses.replace(
            real(*a, **k), psu_tripped=True, psu_enabled=False)
        session = _Session()
        result = apply_plan(bp, session, plan_power("bp6", 3300, SOURCE_OWNER, milliamps=100))
        assert session.power is None
        assert result["error"] == PSU_TRIPPED % 100 and result["applied"] is False
        assert result["psu_enabled"] is False and result["psu_tripped"] is True
        assert fake.psu_enabled is False
    finally:
        bp.close()


def test_apply_plan_load_over_limit_raises_with_supply_off():
    from buspirate.exceptions import BusPirateError

    fake, bp = _bp6_with_load(200)  # the board refuses to start into this load
    try:
        session = _Session()
        with pytest.raises(BusPirateError, match="100 mA"):
            apply_plan(bp, session, plan_power("bp6", 3300, SOURCE_OWNER, milliamps=100))
        assert session.power is None
        assert fake.psu_enabled is False
    finally:
        bp.close()


def test_apply_plan_wrong_board_refused():
    bp = open_simulated("bp6")
    try:
        session = _Session()
        with pytest.raises(PowerRefused):
            apply_plan(bp, session, plan_power("v3", 3300, SOURCE_OWNER))
        assert session.power is None
    finally:
        bp.close()
