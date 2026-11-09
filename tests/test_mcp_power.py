import pytest

from buspirate.connect import open_simulated
from buspirate.mcp.power import (
    SOURCE_OWNER, Measurement, PowerRefused, measure, plan_power, suggest_level,
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
