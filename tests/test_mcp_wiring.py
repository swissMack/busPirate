import pytest

from buspirate.boards.bp6 import BP6_CABLE, BP6_HEADER
from buspirate.mcp.wiring import JOBS, cable_colour, job_notes, wiring_steps


def test_v3_i2c_uses_seeed_colours():
    steps = {s.pin: s for s in wiring_steps("v3", "i2c")}
    assert steps["CLK"].colour == "purple" and steps["CLK"].target == "SCL"
    assert steps["MOSI"].colour == "grey" and steps["GND"].colour == "brown"


def test_bp6_spi_uses_shrink_colours():
    steps = {s.pin: s for s in wiring_steps("bp6", "spi")}
    assert steps["IO4"].colour == "purple" and "MISO" in steps["IO4"].target
    assert steps["IO6"].colour == "grey" and steps["GND"].colour == "black"
    assert steps["VOUT"].colour == "red"


def test_bitpirate_dock_follows_bp6_positions():
    steps = {s.pin: s for s in wiring_steps("bitpirate", "i2c")}
    assert steps["IO15"].colour == "orange"   # dock position 1 == BP6 IO0
    assert steps["IO16"].colour == "yellow"
    assert steps["VIO"].colour == "red" and steps["GND"].colour == "black"


def test_every_step_has_pin_and_colour():
    for variant in ("v3", "v4", "bp6", "bitpirate"):
        for step in wiring_steps(variant, "i2c"):
            assert step.pin and step.colour, (variant, step)


def test_unknown_job_raises():
    with pytest.raises(KeyError):
        wiring_steps("bitpirate", "rawwire")
    with pytest.raises(KeyError):
        wiring_steps("bp6", "pins")


def test_bp6_cable_keys_are_the_header():
    assert set(BP6_CABLE) == set(BP6_HEADER)
    assert cable_colour("bp6", "IO7") == "white"


def test_step_to_dict():
    step = wiring_steps("bp6", "i2c")[0]
    assert set(step.to_dict()) == {"pin", "colour", "target", "note"}


def test_bp6_vout_note_names_the_mcp_power_step_not_the_dashboard():
    for job in ("i2c", "spi", "onewire"):
        vout = [s for s in wiring_steps("bp6", job) if s.pin == "VOUT"][0]
        assert "Power & pull-ups" not in vout.note
        assert "power_plan" in vout.note


DASHBOARD_WORDS = ("panel", "dashboard", "Power & pull-ups", "cable legend", "click", "tick")


@pytest.mark.parametrize("variant", ["v3", "v4", "bp6", "bitpirate"])
def test_job_notes_speak_mcp_not_dashboard(variant):
    for job in JOBS:
        for note in job_notes(variant, job):
            assert not any(w.lower() in note.lower() for w in DASHBOARD_WORDS), (variant, job, note)


@pytest.mark.parametrize("variant", ["bp6", "bitpirate"])
def test_v3_cable_note_never_reaches_other_boards(variant):
    for job in JOBS:
        assert not any("Seeed/Adafruit" in n for n in job_notes(variant, job)), job


def test_v3_keeps_its_cable_warning_and_bp6_its_pullup_note():
    assert any("Seeed/Adafruit" in n for n in job_notes("v3", "i2c"))
    assert any("power_plan" in n and "pull-up" in n for n in job_notes("bp6", "i2c"))
