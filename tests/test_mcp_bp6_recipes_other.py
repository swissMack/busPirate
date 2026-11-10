"""The SPI, 1-Wire, UART, LED, pin and identify recipes on the simulated Bus Pirate 6."""

import hashlib
from pathlib import Path

import pytest

from buspirate.bp6.device import BusPirate6
from buspirate.mcp import jobs
from buspirate.mcp.confirm import ConfirmStore
from buspirate.mcp.session import BoardSession
from buspirate.mcp_bp6 import engine
from buspirate.mcp_bp6.recipes import REGISTRY


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


def _nmea(body):
    checksum = 0
    for char in body:
        checksum ^= ord(char)
    return "$%s*%02X\r\n" % (body, checksum)


def test_every_recipe_is_registered():
    names = {"spi-flash", "max31855", "ds18b20", "uart-console", "gps", "led-strip",
             "onboard-leds", "pins", "identify"}
    assert names <= set(REGISTRY)
    assert all(REGISTRY[n].source for n in names)
    assert all(r.max_mv <= 5000 for r in REGISTRY.values())
    assert REGISTRY["spi-flash"].default_mv == 3300 and REGISTRY["spi-flash"].risk == "none"
    assert (REGISTRY["led-strip"].default_mv, REGISTRY["led-strip"].milliamps) == (5000, 300)
    assert REGISTRY["ds18b20"].pullups is True
    assert (REGISTRY["ds18b20"].default_mv, REGISTRY["ds18b20"].min_mv) == (3300, 3000)
    for n in ("pins", "identify"):
        assert REGISTRY[n].default_mv == 0 and REGISTRY[n].max_mv > 0


def test_spi_flash_identify(session, confirm):
    plan, out = _run(session, confirm, "spi-flash")
    assert plan["power"]["millivolts"] == 3300
    assert out["check"]["ok"] is True
    result = out["result"]
    assert result["jedec"] == "ef 40 18" and "Winbond" in result["manufacturer"]
    assert result["capacity_bytes"] == 1 << 24
    assert "path" not in result


def test_spi_flash_blank_stops(session, confirm):
    _fake(session).flash.JEDEC = b"\xff\xff\xff"
    _, out = _run(session, confirm, "spi-flash")
    assert out["stopped"] == "check failed" and "result" not in out
    assert jobs.NOT_BLANK_WARNING in out["hint"]


def test_spi_flash_backup_length(session, confirm, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    fake = _fake(session)
    fake.flash.memory[:8192] = bytes((i * 3) & 0xFF for i in range(8192))
    _, out = _run(session, confirm, "spi-flash", run_options={"backup": True, "length": 4096})
    result = out["result"]
    saved = Path(result["path"])
    assert saved.stat().st_size == 4096 and result["bytes"] == 4096
    assert saved.read_bytes() == bytes(fake.flash.memory[:4096])
    assert result["sha256"] == hashlib.sha256(saved.read_bytes()).hexdigest()
    assert tmp_path in saved.parents


def test_spi_flash_bad_length_stops(session, confirm):
    _, out = _run(session, confirm, "spi-flash", run_options={"backup": True, "length": 0})
    assert out["stopped"] == "check failed" and "length" in out["check"]["error"]


def test_max31855_reads(session, confirm):
    _, out = _run(session, confirm, "max31855")
    assert out["result"]["device"] == "MAX31855"
    assert out["result"]["values"]


def test_ds18b20_celsius(session, confirm):
    plan, out = _run(session, confirm, "ds18b20")
    assert plan["power"]["pullups"] is True
    assert out["check"]["ok"] is True
    device = out["result"]["devices"][0]
    assert device["rom"].startswith("28 ")
    assert device["celsius"] == 0.0 and "°C" in device["values"]["Temperature"]
    assert _fake(session).pullups


def test_ds18b20_without_a_chip_stops(session, confirm):
    _fake(session).onewire_rom = None
    _, out = _run(session, confirm, "ds18b20")
    assert out["stopped"] == "check failed" and "result" not in out


def test_uart_console_listens(session, confirm):
    _fake(session).uart_receive(b"login: ")
    _, out = _run(session, confirm, "uart-console", plan_options={"millivolts": 3300},
                  run_options={"seconds": 0.3})
    assert out["result"]["text"] == "login: " and out["result"]["baud"] == 115200


def test_gps_parses(session, confirm):
    rmc = _nmea("GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W")
    _fake(session).uart_receive(rmc.encode())
    _, out = _run(session, confirm, "gps", plan_options={"millivolts": 3300},
                  run_options={"seconds": 0.3})
    assert out["result"]["baud"] == 9600
    sentence = out["result"]["sentences"][0]
    assert sentence["type"] == "RMC"
    assert abs(sentence["latitude"] - 48.1173) < 1e-3


def test_uart_target_powered(session, confirm):
    _fake(session).adc_mv = [3300] * 8
    _fake(session).vout_mv = 3300
    plan, out = _run(session, confirm, "uart-console", run_options={"seconds": 0.2})
    assert plan["power"] is None and plan["target_powered"] is True
    assert _fake(session).psu_enabled is False
    assert out["check"]["ok"] is True
    pins = {w["target"]: w["pin"] for w in plan["wiring"]}
    assert pins["RX"] == "IO4" and pins["TX"] == "IO5"


def test_led_strip_bytes(session, confirm):
    plan, out = _run(session, confirm, "led-strip",
                     run_options={"count": 3, "color": 0x102030})
    assert plan["power"]["millivolts"] == 5000 and plan["power"]["milliamps"] == 300
    assert out["result"]["count"] == 3 and out["result"]["kind"] == "ws2812"
    assert _fake(session).pixel_log[-1] == bytes((0x20, 0x10, 0x30)) * 3  # GRB per pixel


def test_led_strip_colors_list(session, confirm):
    _, out = _run(session, confirm, "led-strip", run_options={"colors": [0xFF0000, 0x00FF00]})
    assert out["result"]["count"] == 2
    assert _fake(session).pixel_log[-1] == bytes((0x00, 0xFF, 0x00, 0xFF, 0x00, 0x00))


def test_led_strip_bad_kind_stops(session, confirm):
    _, out = _run(session, confirm, "led-strip", run_options={"kind": "neopixel"})
    assert out["stopped"] == "check failed" and "kind" in out["check"]["error"]


def test_onboard_leds_no_power(session, confirm):
    plan, out = _run(session, confirm, "onboard-leds", run_options={"color": 0x00FF00})
    assert plan["power"] is None and plan["needs_extra_confirmation"] is False
    assert plan["wiring"] == []
    fake = _fake(session)
    assert fake.psu_enabled is False and fake.pullups is False
    assert fake.led_log[-1] == [0x00FF00] * fake.led_count
    _, out = _run(session, confirm, "onboard-leds", run_options={"resume": True})
    assert fake.led_log[-1] == "resume" and out["result"]["resumed"] is True


def test_pins_set_and_read(session, confirm):
    assert "error" in engine.plan_recipe(session, confirm, "pins", {})  # asks for millivolts
    _, out = _run(session, confirm, "pins", plan_options={"millivolts": 3300},
                  run_options={"set": {"IO2": 1}})
    fake = _fake(session)
    assert fake.io_direction & 0b100 and fake.io_value & 0b100
    result = out["result"]
    assert result["set"] == {"IO2": 1} and "IO2" in result["mv"]
    assert result["levels"]["IO2"] == 1 and result["directions"]["IO2"] == "out"


def test_pins_bad_name_stops(session, confirm):
    _, out = _run(session, confirm, "pins", plan_options={"millivolts": 3300},
                  run_options={"set": {"IO9": 1}})
    assert out["stopped"] == "check failed" and "IO9" in out["check"]["error"]


def test_identify_reports_each_bus(session, confirm):
    plan, out = _run(session, confirm, "identify", plan_options={"millivolts": 3300})
    assert plan["power"]["millivolts"] == 3300
    result = out["result"]
    found = {d["address"]: d["label"] for d in result["i2c"]["devices"]}
    assert "BMP280" in found["0x76"]
    assert result["onewire"]["devices"][0]["label"].startswith("DS18B20")
    assert "Winbond" in result["spi"]["manufacturer"]
    assert set(result["answered"]) == {"i2c", "onewire", "spi"}
    assert "next" not in result or not result["next"]


def test_identify_nothing_answers_gives_wiring(session, confirm):
    fake = _fake(session)
    fake.i2c_devices.clear()
    fake.onewire_rom = None
    fake.flash.JEDEC = b"\x00\x00\x00"
    _, out = _run(session, confirm, "identify", plan_options={"millivolts": 3300})
    result = out["result"]
    assert result["answered"] == []
    assert "IO0" in result["next"] and "pull-up" in result["next"]
    assert result["spi"]["warning"] == jobs.NOT_BLANK_WARNING


def test_recipes_never_touch_power(session, confirm, monkeypatch):
    """The engine sets power and pull-ups; a recipe's check and action must not."""
    import dataclasses
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

    fake = _fake(session)
    fake.adc_mv = [3300] * 8
    fake.vout_mv = 3300  # the target powers itself: the engine leaves our supply off
    ran = []
    for name, opts in (("spi-flash", {}), ("max31855", {}), ("ds18b20", {}),
                       ("uart-console", {"seconds": 0.1}), ("gps", {"seconds": 0.1}),
                       ("led-strip", {}), ("onboard-leds", {}),
                       ("pins", {"set": {"IO3": 0}}), ("identify", {})):
        recipe = REGISTRY[name]
        monkeypatch.setitem(REGISTRY, name, dataclasses.replace(
            recipe, check=guarded(recipe.check), action=guarded(recipe.action)))
        session.last_recipe = None
        plan = engine.plan_recipe(session, confirm, name, {})
        assert "error" not in plan, (name, plan)
        out = engine.run_recipe(session, confirm, plan["token"], opts)
        assert out["check"]["ok"] is True and "result" in out, (name, out)
        ran.append(name)
    assert len(ran) == 9
