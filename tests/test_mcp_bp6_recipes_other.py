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


# -- SPI flash writes, SPI EEPROM and FRAM --------------------------------------------

def _plan_prepare_commit(session, confirm, name, options):
    plan = engine.plan_recipe(session, confirm, name, options)
    assert "error" not in plan, plan
    out = engine.run_recipe(session, confirm, plan["token"], {})
    assert out.get("commit"), out
    return out, engine.commit_recipe(session, confirm, out["commit"]["token"])


def test_spi_write_recipes_registered():
    assert REGISTRY["spi-flash-write"].risk == "destructive"
    assert REGISTRY["spi-eeprom-write"].risk == "destructive"
    assert REGISTRY["spi-eeprom"].risk == "none"
    assert REGISTRY["spi-eeprom-write"].default_mv == 3300
    assert (REGISTRY["spi-eeprom-write"].min_mv, REGISTRY["spi-eeprom-write"].max_mv) == (1800, 5000)


def test_flash_write_keeps_sector_neighbours(session, confirm, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    flash = _fake(session).flash
    flash.memory[0:0x2000] = bytes((i * 5 + 1) & 0xFF for i in range(0x2000))
    old = bytes(flash.memory[0:0x2000])
    prepared, done = _plan_prepare_commit(
        session, confirm, "spi-flash-write",
        {"offset": 0x0FFC, "data_hex": "00 01 02 03 04 05 06 07 08 09"})
    result = done["result"]
    assert result["verified"] is True and done["committed"] is True
    assert (result["span_start"], result["span_length"]) == (0, 0x2000)
    assert Path(result["backup"]["path"]).read_bytes() == old
    now = bytes(flash.memory[0:0x2000])
    assert now[0xFFC:0x1006] == bytes(range(10))
    assert now[:0xFFC] == old[:0xFFC] and now[0x1006:] == old[0x1006:]


def test_flash_erase_range(session, confirm, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    flash = _fake(session).flash
    flash.memory[0:0x3000] = b"\x5a" * 0x3000
    _, done = _plan_prepare_commit(session, confirm, "spi-flash-write",
                                   {"operation": "erase", "offset": 0x1000, "length": 0x100})
    assert done["committed"] is True
    assert bytes(flash.memory[0x1000:0x1100]) == b"\xff" * 0x100
    assert bytes(flash.memory[0x1100:0x2000]) == b"\x5a" * 0xF00
    assert bytes(flash.memory[:0x1000]) == b"\x5a" * 0x1000


def _stops_at_check(session, confirm, options):
    plan = engine.plan_recipe(session, confirm, "spi-flash-write", {})
    out = engine.run_recipe(session, confirm, plan["token"], options)
    assert out["stopped"] == "check failed" and "commit" not in out
    return out["check"]["error"]


def test_flash_write_unknown_size_refused(session, confirm):
    _fake(session).flash.JEDEC = b"\xbf\x25\x41"
    error = _stops_at_check(session, confirm, {"offset": 0, "data_hex": "00", "length": 1 << 20})
    assert "bf 25 41".upper() in error and "chip_bytes" in error


def test_flash_write_chip_bytes_used(session, confirm, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    flash = _fake(session).flash
    flash.JEDEC = b"\xbf\x25\x41"
    flash.memory[0:0x3000] = b"\x5a" * 0x3000
    _, done = _plan_prepare_commit(session, confirm, "spi-flash-write",
                                   {"operation": "erase", "offset": 0x1000, "length": 0x100,
                                    "chip_bytes": 1 << 20})
    assert done["committed"] is True
    assert bytes(flash.memory[0x1000:0x1100]) == b"\xff" * 0x100
    assert bytes(flash.memory[0x1100:0x2000]) == b"\x5a" * 0xF00
    error = _stops_at_check(session, confirm, {"offset": 1 << 20, "data_hex": "00",
                                               "chip_bytes": 1 << 20})
    assert "offset" in error


def test_flash_write_chip_bytes_mismatch_refused(session, confirm):
    error = _stops_at_check(session, confirm, {"offset": 0, "data_hex": "00",
                                               "chip_bytes": 1 << 20})
    assert str(1 << 20) in error and str(1 << 24) in error
    for bad in (1000, 1 << 28, True, "1048576"):
        assert "chip_bytes" in _stops_at_check(session, confirm,
                                               {"offset": 0, "data_hex": "00", "chip_bytes": bad})


def test_flash_write_beyond_chip_stops(session, confirm):
    plan = engine.plan_recipe(session, confirm, "spi-flash-write", {})
    out = engine.run_recipe(session, confirm, plan["token"],
                            {"offset": 1 << 25, "data_hex": "00"})
    assert out["stopped"] == "check failed" and "commit" not in out


def test_spi_eeprom_full_flow(session, confirm, tmp_path, monkeypatch):
    from buspirate.simulator_bp6 import FakeEeprom25
    monkeypatch.setenv("HOME", str(tmp_path))
    chip = FakeEeprom25("25256", bytes((i * 3) & 0xFF for i in range(32768)))
    _fake(session).spi_device = chip
    old = bytes(chip.mem)
    prepared, done = _plan_prepare_commit(
        session, confirm, "spi-eeprom-write",
        {"part": "25LC256", "offset": 0x3E, "data_hex": "aa bb cc dd"})
    assert prepared["commit"]["chip"].startswith("25256")
    result = done["result"]
    assert result["verified"] is True and result["written"] == 4
    assert Path(result["backup"]["path"]).read_bytes() == old[0x3E:0x42]
    assert bytes(chip.mem[0x3E:0x42]) == bytes.fromhex("aabbccdd")
    assert bytes(chip.mem[:0x3E]) == old[:0x3E] and bytes(chip.mem[0x42:]) == old[0x42:]


def test_spi_eeprom_backup_reads_whole_part(session, confirm, tmp_path, monkeypatch):
    from buspirate.simulator_bp6 import FakeEeprom25
    monkeypatch.setenv("HOME", str(tmp_path))
    chip = FakeEeprom25("25040", bytes(i % 251 for i in range(512)))
    _fake(session).spi_device = chip
    _, out = _run(session, confirm, "spi-eeprom", run_options={"part": "25040"})
    assert Path(out["result"]["path"]).read_bytes() == bytes(chip.mem)


def test_spi_eeprom_missing_part(session, confirm):
    plan = engine.plan_recipe(session, confirm, "spi-eeprom-write", {})
    out = engine.run_recipe(session, confirm, plan["token"], {"data_hex": "00"})
    assert out["stopped"] == "check failed" and "commit" not in out
    assert "25256" in out["check"]["error"]


def test_spi_eeprom_protected_reports_the_error_and_is_not_committed(
        session, confirm, tmp_path, monkeypatch):
    from buspirate.simulator_bp6 import FakeEeprom25
    monkeypatch.setenv("HOME", str(tmp_path))
    chip = FakeEeprom25("25256", bytes(range(256)) * 128)
    chip.protect_bits = 0x0C
    _fake(session).spi_device = chip
    old = bytes(chip.mem)
    _, done = _plan_prepare_commit(session, confirm, "spi-eeprom-write",
                                   {"part": "25256", "data_hex": "ff 00 ff 00"})
    result = done["result"]
    assert "0x0c" in result["error"].lower()
    assert done["committed"] is False
    assert result["backup"] is not None
    assert bytes(chip.mem) == old


# -- Microwire 93Cxx ---------------------------------------------------------------------

def test_microwire_write_full_flow(session, confirm, tmp_path, monkeypatch):
    from buspirate.simulator_bp6 import FakeMicrowire
    monkeypatch.setenv("HOME", str(tmp_path))
    chip = FakeMicrowire("93C46", 16, bytes((i * 7 + 1) & 0xFF for i in range(128)))
    _fake(session).spi_device = chip
    old = bytes(chip.mem)
    assert REGISTRY["microwire-eeprom-write"].risk == "destructive"
    assert REGISTRY["microwire-eeprom"].risk == "none"
    prepared, done = _plan_prepare_commit(
        session, confirm, "microwire-eeprom-write",
        {"part": "93LC46B", "offset": 3, "data_hex": "aa bb cc"})
    assert prepared["commit"]["chip"].startswith("93C46")
    result = done["result"]
    assert result["verified"] is True and result["written"] == 3
    assert Path(result["backup"]["path"]).read_bytes() == old[2:6]
    assert bytes(chip.mem[3:6]) == bytes.fromhex("aabbcc")
    assert bytes(chip.mem[:3]) == old[:3] and bytes(chip.mem[6:]) == old[6:]
    assert _fake(session).spi_cs_idle is False


def test_microwire_backup_reads_whole_part(session, confirm, tmp_path, monkeypatch):
    from buspirate.simulator_bp6 import FakeMicrowire
    monkeypatch.setenv("HOME", str(tmp_path))
    chip = FakeMicrowire("93C56", 8, bytes((i * 3 + 2) & 0xFF for i in range(256)))
    _fake(session).spi_device = chip
    _, out = _run(session, confirm, "microwire-eeprom", run_options={"part": "93C56", "org": 8})
    assert Path(out["result"]["path"]).read_bytes() == bytes(chip.mem)


def test_microwire_check_fails_on_zeros_with_hint(session, confirm):
    from buspirate.simulator_bp6 import FakeMicrowire
    _fake(session).spi_device = FakeMicrowire("93C46", 16, bytes(128))
    plan = engine.plan_recipe(session, confirm, "microwire-eeprom", {"part": "93C46"})
    out = engine.run_recipe(session, confirm, plan["token"], {})
    assert out["stopped"] == "check failed"
    assert "cannot tell" in out["check"]["hint"]


def test_microwire_missing_part(session, confirm):
    plan = engine.plan_recipe(session, confirm, "microwire-eeprom", {})
    out = engine.run_recipe(session, confirm, plan["token"], {})
    assert out["stopped"] == "check failed" and "93C46" in out["check"]["error"]


# -- 1-Wire EEPROM -------------------------------------------------------------------

def test_onewire_eeprom_registered():
    assert REGISTRY["onewire-eeprom"].risk == "none"
    write = REGISTRY["onewire-eeprom-write"]
    assert write.risk == "destructive" and write.pullups is True
    assert (write.default_mv, write.min_mv, write.max_mv) == (3300, 3000, 5000)


def test_onewire_eeprom_full_flow(session, confirm, tmp_path, monkeypatch):
    from buspirate.simulator_bp6 import FakeDs2431
    monkeypatch.setenv("HOME", str(tmp_path))
    chip = FakeDs2431()
    _fake(session).onewire_device = chip
    old = bytes(chip.mem)
    prepared, done = _plan_prepare_commit(
        session, confirm, "onewire-eeprom-write", {"offset": 6, "data_hex": "aa bb cc"})
    assert prepared["commit"]["chip"].startswith("DS2431")
    result = done["result"]
    assert result["verified"] is True and result["written"] == 3
    assert Path(result["backup"]["path"]).read_bytes() == old[0:16]
    assert bytes(chip.mem[6:9]) == bytes.fromhex("aabbcc")
    assert bytes(chip.mem[:6]) == old[:6] and bytes(chip.mem[9:]) == old[9:]


def test_onewire_eeprom_backup_reads_whole_memory(session, confirm, tmp_path, monkeypatch):
    from buspirate.simulator_bp6 import FakeDs2431
    monkeypatch.setenv("HOME", str(tmp_path))
    chip = FakeDs2431(family=0x23)
    _fake(session).onewire_device = chip
    _, out = _run(session, confirm, "onewire-eeprom")
    assert Path(out["result"]["path"]).read_bytes() == bytes(chip.mem)


def test_onewire_eeprom_copy_failure_is_reported(session, confirm, tmp_path, monkeypatch):
    from buspirate.simulator_bp6 import FakeDs2431
    monkeypatch.setenv("HOME", str(tmp_path))
    chip = FakeDs2431()
    chip.copy_fails = True
    _fake(session).onewire_device = chip
    _, done = _plan_prepare_commit(
        session, confirm, "onewire-eeprom-write", {"offset": 0, "data_hex": "01"})
    assert "pull-up" in done["result"]["error"] and done["result"]["verified"] is False


def test_onewire_eeprom_refuses_thermometer(session, confirm):
    plan = engine.plan_recipe(session, confirm, "onewire-eeprom", {})
    out = engine.run_recipe(session, confirm, plan["token"], {})
    assert out["stopped"] == "check failed"
    assert "found family 0x28: that is a thermometer, not an EEPROM" in out["check"]["error"]


def test_midi_recipe_decodes(session, confirm):
    fake = _fake(session)
    fake.uart_echo = False
    fake.uart_receive(bytes.fromhex("903c64"))
    _, out = _run(session, confirm, "midi", run_options={"seconds": 0.3})
    result = out["result"]
    assert result["count"] == 1 and result["bytes"] == 3
    assert result["messages"][0]["type"] == "note on" and result["messages"][0]["note"] == "C4"


def test_destructive_commits_never_touch_power(session, confirm, tmp_path, monkeypatch):
    """Only the commit step is guarded: it must not switch power or touch the pull-ups."""
    from buspirate.simulator_bp6 import FakeEeprom25, FakeMicrowire, FakeDs2431
    from buspirate.bp6.modes import _Bp6Mode
    monkeypatch.setenv("HOME", str(tmp_path))
    fake = _fake(session)
    cases = {
        "i2c-eeprom-write": {"data_hex": "01 02"},
        "fram-write": {"data_hex": "01 02"},
        "spi-flash-write": {"offset": 0, "data_hex": "01 02"},
        "spi-eeprom-write": {"part": "25256", "data_hex": "01 02"},
        "microwire-eeprom-write": {"part": "93C46", "data_hex": "01 02"},
        "onewire-eeprom-write": {"data_hex": "01 02"},
    }
    destructive = {n for n, r in REGISTRY.items() if r.risk == "destructive"}
    assert destructive == set(cases)

    def forbid(what):
        def boom(*a, **k):
            raise AssertionError("commit called " + what)
        return boom

    committed = []
    for name, opts in cases.items():
        if name == "i2c-eeprom-write":
            fake.add_eeprom24(0x50, "24C02")
        elif name == "fram-write":
            fake.add_eeprom24(0x50, "24C256")
        elif name == "microwire-eeprom-write":
            fake.spi_device = FakeMicrowire("93C46", 16, bytes((i * 7 + 1) & 0xFF for i in range(128)))
        elif name == "spi-eeprom-write":
            fake.spi_device = FakeEeprom25("25256", bytes(range(256)) * 128)
        elif name == "onewire-eeprom-write":
            fake.onewire_device = FakeDs2431()
        session.last_recipe = None
        plan = engine.plan_recipe(session, confirm, name, opts)
        assert "error" not in plan, (name, plan)
        out = engine.run_recipe(session, confirm, plan["token"], {})
        if not out.get("commit"):
            continue  # a chip reason stopped it before any commit: nothing to guard
        committed.append(name)
        with monkeypatch.context() as inner:
            inner.setattr(BusPirate6, "set_power", forbid("set_power"))
            inner.setattr(BusPirate6, "set_pullups", forbid("set_pullups"))
            inner.setattr(_Bp6Mode, "configure_peripherals", forbid("configure_peripherals"))
            done = engine.commit_recipe(session, confirm, out["commit"]["token"])
        assert "result" in done and done["committed"] is True, (name, done)
    assert set(committed) == set(cases)


# -- signals (terminal) -----------------------------------------------------------

from buspirate.mcp_bp6 import state  # noqa: E402


def _sent(session, since=0):
    return [ln for ln in _fake(session).lines_received()[since:] if ln != b"\r"]


def test_signal_recipes_registered_as_terminal():
    for name in ("pwm-signal", "frequency-measure"):
        r = REGISTRY[name]
        assert (r.bus, r.transport, r.terminal_mode, r.default_mv) == ("pins", "terminal", "dio", 3300)
        assert (r.min_mv, r.max_mv, r.milliamps, r.pullups) == (1200, 5000, 100, False)


def test_pwm_signal_recipe_runs(session, confirm):
    _, out = _run(session, confirm, "pwm-signal", {"pin": 2, "hz": 2000, "duty": 25})
    assert out["check"]["ok"] and out["result"]["pin"] == 2
    assert out["result"]["actual_hz"] == 2000
    assert abs(out["result"]["actual_duty_percent"] - 25) < 0.5
    assert state.of(session).pwm_pins == {2}
    assert _fake(session).pwm == {2: (2000.0, 25.0)}
    assert any("pwm_off" in n for n in REGISTRY["pwm-signal"].notes)


def test_pwm_pair_partner_refused(session, confirm):
    # A re-run sends no m (which would switch IO2's PWM off), so IO2 still runs.
    _run(session, confirm, "pwm-signal", {"pin": 2})
    mark = len(_fake(session).lines_received())
    out = engine.run_recipe(session, confirm, None, {"pin": 3})
    assert out["check"]["ok"] is False
    assert "IO2 and IO3 share one PWM" in out["check"]["error"]
    assert b"G 3\r" not in _sent(session, mark)


def test_first_run_forgets_pwm_pins(session, confirm):
    state.of(session).pwm_pins.add(2)  # m dio switches IO2's PWM off
    _, out = _run(session, confirm, "pwm-signal", {"pin": 3})
    assert out["check"]["ok"] is True, out
    assert state.of(session).pwm_pins == {3}


def test_frequency_even_pin_refused(session, confirm):
    _, out = _run(session, confirm, "frequency-measure", {"pin": 2})
    assert out["check"]["ok"] is False
    assert "only IO1, IO3, IO5 and IO7" in out["check"]["error"]
    assert b"f 2\r" not in _sent(session)


def test_frequency_recipe_reads(session, confirm):
    _fake(session).signals[3] = (1000.0, 50.0)
    _, out = _run(session, confirm, "frequency-measure", {"pin": 3})
    assert out["result"] == {"pin": 3, "hz": 1000, "duty_percent": 50.0}
    assert b"f 3\r" in _sent(session)


# -- self-test (terminal ~) -------------------------------------------------------

def test_selftest_registered():
    r = REGISTRY["self-test"]
    assert (r.bus, r.transport, r.terminal_mode, r.wiring) == ("board", "terminal", None, ())
    assert (r.min_mv, r.max_mv, r.default_mv, r.options) == (0, 0, 0, {"button_s": 20})


def test_selftest_precheck_refuses_connected_pins(session, confirm):
    _fake(session).adc_mv = (0, 0, 0, 3300, 0, 0, 0, 0)
    plan = engine.plan_recipe(session, confirm, "self-test", {})
    mark = len(_fake(session).lines_received())
    out = engine.run_recipe(session, confirm, plan["token"], {})
    assert "disconnect everything from the Bus Pirate's pins first" in out["check"]["error"]
    assert b"~\r" not in _sent(session, mark)


def test_selftest_precheck_refuses_live_vout(session, confirm):
    _fake(session).vout_mv = 3300
    plan = engine.plan_recipe(session, confirm, "self-test", {})
    out = engine.run_recipe(session, confirm, plan["token"], {})
    assert "VOUT" in out["check"]["error"]


def test_selftest_precheck_refuses_while_the_supply_is_on(session, confirm):
    fake = _fake(session)
    fake.psu_enabled = True
    plan = engine.plan_recipe(session, confirm, "self-test", {})
    mark = len(fake.lines_received())
    out = engine.run_recipe(session, confirm, plan["token"], {})
    assert ("switch the supply off and disconnect everything from the Bus Pirate's pins "
            "first") in out["check"]["error"], out
    assert b"~\r" not in _sent(session, mark)


def test_selftest_plan_names_its_own_supply(session, confirm):
    plan = engine.plan_recipe(session, confirm, "self-test", {})
    assert plan["power"] is None and plan["wiring"] == []
    assert ("the self-test switches the Bus Pirate's own supply on at 3.3 V with no current "
            "limit") in plan["warnings"]
    assert any("press the board's button" in w for w in plan["warnings"])


def test_selftest_pass(session, confirm):
    session.power = object()
    _, out = _run(session, confirm, "self-test")
    res = out["result"]
    assert (res["passed"], res["button"], res["errors"]) == (True, "pressed", [])
    assert session.power is None
    assert not _fake(session).psu_enabled


def test_selftest_button_skipped(session, confirm):
    _fake(session).button_pressed = False
    _, out = _run(session, confirm, "self-test", run_options={"button_s": 0})
    res = out["result"]
    assert b" " in _sent(session)
    assert (res["passed"], res["button"], res["errors"]) == (False, "skipped", [])
    assert res["verdict"] == "every block passed; the button test was skipped"


def test_selftest_never_formats(session, confirm):
    _fake(session).nand_formatted = False
    _, out = _run(session, confirm, "self-test")
    assert b"n\r" in _sent(session)
    assert out["result"]["passed"] is True


def test_selftest_reports_error_lines(session, confirm):
    _fake(session).selftest_faults = ["BIO3 FLOAT: 1/0.92V ERROR!"]
    _, out = _run(session, confirm, "self-test")
    res = out["result"]
    assert res["passed"] is False and res["errors"] == ["BIO3 FLOAT: 1/0.92V ERROR!"]
    assert "BIO3 FLOAT: 1/0.92V ERROR!" in res["verdict"]


def test_selftest_bad_button_s_stops(session, confirm):
    _, out = _run(session, confirm, "self-test", run_options={"button_s": 99})
    assert out["check"]["ok"] is False


# -- blueTag (terminal) -----------------------------------------------------------

def test_jtag_recipes_registered():
    for name, channels in (("jtag-pinout", 6), ("swd-pinout", 4)):
        r = REGISTRY[name]
        assert (r.bus, r.transport, r.terminal_mode, r.default_mv) == ("jtag", "terminal", "jtag", 3300)
        assert (r.min_mv, r.max_mv, r.milliamps, r.pullups) == (1200, 5000, 100, False)
        assert r.options == {"channels": channels, "pulsing": True}
        assert [t for _, t in r.wiring].count("GND") == 1 and ("VREF", "VOUT") in r.wiring
        assert [p for _, p in r.wiring[:8]] == ["IO%d" % n for n in range(8)]
        assert not any("pin 1" in t for t, _ in r.wiring)


def test_wiring_follows_channels(session, confirm):
    def pins(name, opts):
        return [w["bp6_pin"] if "bp6_pin" in w else w for w in
                engine.plan_recipe(session, confirm, name, opts)["wiring"]]
    swd = pins("swd-pinout", {"channels": 4})
    jtag = pins("jtag-pinout", {})
    assert len(swd) == 6 and len(jtag) == 8, (swd, jtag)
    assert "IO4" not in str(swd) and "IO5" in str(jtag) and "IO6" not in str(jtag)


def test_plan_warns_disturbs_target(session, confirm):
    plan = engine.plan_recipe(session, confirm, "jtag-pinout", {})
    assert any("blueTag pulses the pins and can disturb a running target" in w
               for w in plan["warnings"])


def test_jtag_pinout_recipe_runs(session, confirm):
    _fake(session).bluetag_hit = {"jtag": type(_fake(session)).BLUETAG_JTAG_HIT}
    _, out = _run(session, confirm, "jtag-pinout", {"channels": 6})
    assert out["result"]["pinout"]["TCK"] == "IO4", out
    assert _fake(session).mode == "JTAG"


def test_swd_recipe_channel_range_refused(session, confirm):
    plan = engine.plan_recipe(session, confirm, "swd-pinout", {"channels": 1})
    out = engine.run_recipe(session, confirm, plan["token"], {})
    assert out["check"]["ok"] is False and "SWD needs 2 to 8 channels" in str(out)


def _sniff_lines(n):
    return ["[ [0xA0]+ [0x00]+ [0x%02X]-]\r\n" % (i % 256) for i in range(n)]


def test_i2c_sniff_recipe_runs(session, confirm):
    fake = _fake(session)
    fake.sniff_lines = _sniff_lines(3)
    _, result = _run(session, confirm, "i2c-sniff", {"millivolts": 3300, "seconds": 0.2})
    assert result["result"]["count"] == 3, result
    assert fake.mode == "I2C"
    assert b"m i2c -s 400\r" in fake.lines_received()
    assert fake.keys_seen[-1] == b"x"


def test_2wire_sniff_recipe_runs(session, confirm):
    fake = _fake(session)
    fake.sniff_lines = ["[ 0x30 0x00 0xFF]\r\n"]
    _, result = _run(session, confirm, "2wire-sniff", {"millivolts": 3300, "seconds": 0.2})
    assert result["result"]["transactions"][0]["data"] == "30 00 FF", result
    assert fake.mode == "2WIRE"


def test_sniff_truncates(session, confirm):
    fake = _fake(session)
    fake.sniff_lines = _sniff_lines(250)
    _, result = _run(session, confirm, "i2c-sniff", {"millivolts": 3300, "seconds": 1})
    r = result["result"]
    assert r["count"] == 250 and len(r["transactions"]) == 200 and r["truncated"] is True


def test_sniff_seconds_refused(session, confirm):
    plan = engine.plan_recipe(session, confirm, "i2c-sniff", {"millivolts": 3300, "seconds": 61})
    if "error" in plan:
        assert "60" in plan["error"]
        return
    out = engine.run_recipe(session, confirm, plan["token"], {})
    assert out["check"]["ok"] is False and "60" in out["check"]["error"]


def test_sniff_notes_name_driven_pins():
    for n in ("i2c-sniff", "2wire-sniff"):
        assert any("IO2 and IO3" in note for note in REGISTRY[n].notes)
