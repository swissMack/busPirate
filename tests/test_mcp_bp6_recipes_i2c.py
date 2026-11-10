"""The I2C recipes, planned and run through the engine on the simulated Bus Pirate 6."""

import hashlib
from pathlib import Path

import pytest

from buspirate.mcp import jobs
from buspirate.mcp.confirm import ConfirmStore
from buspirate.mcp.session import BoardSession
from buspirate.mcp_bp6 import engine
from buspirate.mcp_bp6.recipes import REGISTRY, find_recipes


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


def _run(session, confirm, name, plan_options=None, run_options=None):
    plan = engine.plan_recipe(session, confirm, name, plan_options or {})
    assert "error" not in plan, plan
    return plan, engine.run_recipe(session, confirm, plan["token"], run_options or {})


def test_every_i2c_recipe_is_registered():
    names = {"lcd", "aht20", "bmp280", "sht3x", "sht4x", "si7021", "tsl2561", "tcs3472x",
             "ms5611", "i2c-eeprom", "fram", "i2c-scan"}
    assert names <= set(REGISTRY)
    assert all(REGISTRY[n].bus == "i2c" and REGISTRY[n].pullups for n in names)
    assert all(REGISTRY[n].source for n in names)
    assert all(REGISTRY[n].source.startswith("https://docs.buspirate.com/")
               for n in names - {"lcd"})  # the LCD backpack is not in the docs


def test_lcd_end_to_end(session, confirm):
    plan, out = _run(session, confirm, "lcd", run_options={"message": "Hi"})
    assert plan["power"]["millivolts"] == 5000
    assert out["check"]["ok"] is True
    assert out["result"]["check"] == jobs.LCD_CHECK
    assert out["result"]["address"] == "0x27" and out["result"]["sent_bytes"] > 0
    fake = _fake(session)
    assert fake.psu_enabled and fake.pullups
    sent = [w for _, w, _, _ in fake.data_log if w[:1] == bytes([0x27 << 1]) and len(w) > 1]
    assert len(sent) == out["result"]["steps"]


def test_lcd_clamps_to_5000(session, confirm):
    assert REGISTRY["lcd"].max_mv == 5000 and REGISTRY["lcd"].min_mv == 3000
    assert "error" in engine.plan_recipe(session, confirm, "lcd", {"millivolts": 5500})


def test_lcd_bad_size_stops_with_a_reason(session, confirm):
    _, out = _run(session, confirm, "lcd", run_options={"size": "9x9"})
    assert out["stopped"] == "check failed" and "size" in out["check"]["error"]


def test_sht4x_capped_at_3600(session, confirm):
    assert REGISTRY["sht4x"].max_mv == 3600 and REGISTRY["sht4x"].default_mv == 3300
    plan = engine.plan_recipe(session, confirm, "sht4x", {"millivolts": 5000})
    assert "error" in plan and "token" not in plan
    assert _fake(session).psu_enabled is False


def test_sht31_reads_celsius(session, confirm):
    _, out = _run(session, confirm, "sht3x")
    assert out["check"]["ok"] is True
    values = out["result"]["values"]
    assert values["Temperature"] == "25.00 °C"
    assert values["Humidity"].endswith("%RH")


def test_bmp280_covers_the_fake_sensor(session, confirm):
    _, out = _run(session, confirm, "bmp280", plan_options={"millivolts": 3300})
    assert out["result"]["values"]["Temperature"].endswith("°C")


def test_eeprom_backup_file(session, confirm, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    plan, out = _run(session, confirm, "i2c-eeprom")
    assert plan["power"]["millivolts"] == 3300
    result = out["result"]
    data = bytes(_fake(session).i2c_devices[0x50])
    assert result["bytes"] == 256 and result["sha256"] == hashlib.sha256(data).hexdigest()
    saved = Path(result["path"])
    assert saved.read_bytes() == data and tmp_path in saved.parents
    assert result["first_64_hex"] == data[:64].hex(" ")


def test_eeprom_unknown_part_stops(session, confirm):
    _, out = _run(session, confirm, "i2c-eeprom", run_options={"part": "24C99"})
    assert out["stopped"] == "check failed" and "24C99" in out["check"]["error"]


def test_fram_uses_its_own_part(session, confirm, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    fake = _fake(session)
    fake.add_i2c_device(0x50, bytes(range(256)))
    _, out = _run(session, confirm, "fram")
    assert out["result"]["bytes"] == 32768 and "MB85RC256V" in Path(out["result"]["path"]).name


def test_scan_names_what_it_finds(session, confirm):
    _, out = _run(session, confirm, "i2c-scan")
    found = {d["address"]: d["label"] for d in out["result"]["devices"]}
    assert {"0x27", "0x44", "0x50", "0x76"} <= set(found)
    assert "BMP280" in found["0x76"] and "LCD" in found["0x27"]


def test_check_fails_lists_found(session, confirm):
    fake = _fake(session)
    del fake.i2c_devices[0x27]
    fake.add_i2c_device(0x3F)
    _, out = _run(session, confirm, "lcd")
    assert out["stopped"] == "check failed"
    assert "0x3F" in out["hint"] and "address" in out["hint"]
    assert {d["address"] for d in out["check"]["found"]} >= {"0x3F", "0x76"}
    assert "result" not in out
    assert fake.psu_enabled is True  # the power is left as the engine set it


def test_recipes_never_touch_power(session, confirm, monkeypatch):
    """The engine sets power and pull-ups; a recipe's check and action must not."""
    import dataclasses
    from buspirate.bp6.device import BusPirate6
    from buspirate.bp6.modes import _Bp6Mode

    def forbid(what):
        return lambda *a, **k: pytest.fail("a recipe called " + what)

    def guarded(fn):
        def call(bp, opts):
            with monkeypatch.context() as inner:
                inner.setattr(BusPirate6, "set_power", forbid("set_power"))
                inner.setattr(BusPirate6, "set_pullups", forbid("set_pullups"))
                inner.setattr(_Bp6Mode, "configure_peripherals", forbid("configure_peripherals"))
                return fn(bp, opts)
        return call

    for name in ("aht20", "lcd"):
        recipe = REGISTRY[name]
        monkeypatch.setitem(REGISTRY, name, dataclasses.replace(
            recipe, check=guarded(recipe.check), action=guarded(recipe.action)))
    _, out = _run(session, confirm, "aht20")  # nothing at 0x38: the check stops
    assert out["stopped"] == "check failed"
    _, out = _run(session, confirm, "lcd")
    assert out["check"]["ok"] is True


def test_find_recipes_ambiguous():
    found = {r["name"] for r in find_recipes("temperature")}
    assert found >= {"aht20", "bmp280", "sht3x", "sht4x", "si7021", "ms5611", "ds18b20",
                     "max31855"}
    assert [r["name"] for r in find_recipes("lcd")][0] == "lcd"
    assert [r["name"] for r in find_recipes("24c02")][:1] == ["i2c-eeprom"]
