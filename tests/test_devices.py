"""The device catalog, and each translator checked against a known answer."""

import importlib
import pkgutil
import struct

import pytest

from buspirate import devices
from buspirate.devices import ad595, aht20, bmp280, ds18x20, hd44780, max31855

# A real AHT20 reply, read from the bench board on 2026-09-29.
AHT20_REPLY = bytes.fromhex("0c 70 e2 a6 53 48 b9")

# The BMP280 datasheet's worked example (section 3.12): these calibration
# words with adc_T = 519888 and adc_P = 415148 give 25.08 °C, 100653.27 Pa.
BMP280_CAL = struct.pack(
    "<HhhHhhhhhhhh",
    27504, 26435, -1000, 36477, -10685, 3024, 2855, 140, -7, 15500, -14600, 6000,
)
BMP280_DATA = bytes([
    415148 >> 12, (415148 >> 4) & 0xFF, (415148 & 0x0F) << 4,
    519888 >> 12, (519888 >> 4) & 0xFF, (519888 & 0x0F) << 4,
])


def value(meaning, key):
    return dict(meaning)[key]


def scratchpad(temp_lsb, temp_msb, count_remain=0x0C, count_per_c=0x10):
    """A DS18x20 scratchpad with a correct CRC in byte 8."""
    body = bytes([temp_lsb, temp_msb, 0x4B, 0x46, 0x7F, 0xFF, count_remain, count_per_c])
    return body + bytes([ds18x20.crc8(body)])


def max31855_word(thermocouple_14, internal_12, fault_bits=0):
    word = (thermocouple_14 << 18) | (internal_12 << 4) | fault_bits
    if fault_bits:
        word |= 0x10000
    return word.to_bytes(4, "big")


# -- fakes: just enough of each bus for the translators ----------------------


class FakeI2C:
    def __init__(self, bmp_address=0x77, chip_id=0x58, aht_status=0x1C):
        self.bmp_address = bmp_address
        self.chip_id = chip_id
        self.aht_status = aht_status
        self.writes = []

    def scan(self):
        return [0x38, self.bmp_address, 0x50]

    def read(self, address, count):
        assert address == 0x38
        return bytes([self.aht_status]) if count == 1 else AHT20_REPLY[:count]

    def write(self, address, data):
        self.writes.append((address, bytes(data)))

    def read_register(self, address, register, count):
        if address != self.bmp_address:
            raise IOError("NACK")
        regs = {bmp280.REG_CHIP_ID: bytes([self.chip_id]),
                bmp280.REG_CALIBRATION: BMP280_CAL,
                bmp280.REG_DATA: BMP280_DATA}
        return regs[register][:count]


class FakeOneWire:
    def __init__(self, roms, pads):
        self.roms, self.pads, self.writes = roms, pads, []

    def configure_peripherals(self, **_):
        pass

    def search_rom(self):
        return self.roms

    def reset(self):
        pass

    def write(self, data):
        self.writes.append(bytes(data))

    def read(self, count):
        rom = self.writes[-1][1:9]
        return self.pads[rom][:count]


# -- the catalog itself ------------------------------------------------------


def test_every_module_in_the_package_is_in_the_catalog():
    # Modules are listed by hand so the frozen app cannot drop one; this is
    # the check that a new chip file was also added to that list.
    listed = {m.__name__ for m in devices._MODULES}
    for info in pkgutil.iter_modules(devices.__path__):
        name = f"{devices.__name__}.{info.name}"
        assert name in listed, f"{name} is not in devices._MODULES"
        assert importlib.import_module(name).DEVICES


def test_every_device_is_well_formed():
    for device in devices.CATALOG:
        assert device.name
        if device.bus == "i2c":
            assert device.addresses and all(0x08 <= a <= 0x77 for a in device.addresses), device
        if device.bus == "onewire":
            assert device.families, device
        if device.bus == "spi":
            assert device.measure, f"{device.name}: an SPI entry is only useful if it can read"
        if device.bus == "analog":
            assert device.from_volts, f"{device.name}: an analog entry needs from_volts"


def test_scan_labels_come_from_the_catalog():
    assert devices.i2c_label(0x38) == "AHT20"
    assert devices.i2c_label(0x77) == "BMP280 / BME280 / BMP180"
    assert devices.i2c_label(0x50) == "24Cxx EEPROM"
    assert devices.i2c_label(0x11) == ""
    assert devices.onewire_label(0x28) == "DS18B20 thermometer"
    assert devices.onewire_label(0x2D) == "DS2431 EEPROM"
    assert devices.JEDEC_MANUFACTURERS[0xEF] == "Winbond"


# -- AHT20 -------------------------------------------------------------------


def test_aht20_translates_a_real_reply():
    meaning = aht20.decode(AHT20_REPLY)
    assert value(meaning, "Temperature") == "29.07 °C"
    assert value(meaning, "Humidity") == "44.1 %RH"
    assert "finished" in value(meaning, "Status") and "calibrated" in value(meaning, "Status")
    assert value(meaning, "Checksum").endswith("OK")


def test_aht20_flags_a_damaged_or_unfinished_reply():
    assert "WRONG" in value(aht20.decode(AHT20_REPLY[:6] + b"\x00"), "Checksum")
    assert "busy" in value(aht20.decode(bytes([0x9C]) + AHT20_REPLY[1:]), "Status")
    assert "needs at least 6 bytes" in aht20.decode(b"\x1c\x00")[0][1]


def test_an_uncalibrated_aht20_is_calibrated_first():
    bus = FakeI2C(aht_status=0x10)
    devices.read_i2c(bus, 0x38)
    assert bus.writes[0] == (0x38, aht20.CALIBRATE)


# -- BMP280 ------------------------------------------------------------------


def test_bmp280_matches_the_datasheet_example():
    temperature, pressure = bmp280.compensate(BMP280_DATA, BMP280_CAL)
    assert temperature == pytest.approx(25.08, abs=0.01)
    assert pressure == pytest.approx(1006.53, abs=0.01)


def test_bmp280_says_when_it_has_never_measured():
    meaning = bmp280.decode(bytes.fromhex("80 00 00 80 00 00"), BMP280_CAL)
    assert "has not measured yet" in value(meaning, "Note")


def test_identify_uses_the_address_and_the_chip_id():
    assert devices.identify_i2c(FakeI2C(), 0x38).name == "AHT20"
    assert devices.identify_i2c(FakeI2C(), 0x77).name == "BMP280"
    assert devices.identify_i2c(FakeI2C(chip_id=0x60), 0x77).name == "BME280"
    assert devices.identify_i2c(FakeI2C(chip_id=0x11), 0x77) is None
    assert devices.identify_i2c(FakeI2C(), 0x50) is None  # named, but not readable


def test_read_i2c_measures_and_translates():
    bus = FakeI2C()
    aht = devices.read_i2c(bus, 0x38)
    assert aht.device == "AHT20" and aht.raw == AHT20_REPLY
    assert (0x38, aht20.MEASURE) in bus.writes

    bmp = devices.read_i2c(bus, 0x77)
    assert bmp.raw == BMP280_DATA
    assert value(bmp.meaning, "Temperature") == "25.08 °C"
    # Forced mode: one measurement, then the chip goes back to sleep.
    assert (0x77, bytes([bmp280.REG_CTRL_MEAS, bmp280.FORCED_X1])) in bus.writes


def test_hand_reads_are_explained():
    bus = FakeI2C()
    assert value(devices.explain_i2c_read(0x38, AHT20_REPLY), "Temperature") == "29.07 °C"
    assert devices.explain_i2c_read(0x50, AHT20_REPLY) == []

    assert value(devices.explain_i2c_register(bus, 0x77, 0xD0, b"\x58"), "Chip ID") == "0x58: BMP280"
    assert value(devices.explain_i2c_register(bus, 0x77, 0xF7, BMP280_DATA), "Pressure") == "1006.53 hPa"
    cal = devices.explain_i2c_register(bus, 0x77, 0x88, BMP280_CAL)
    assert value(cal, "Calibration").startswith("T1=27504, T2=26435, T3=-1000")
    assert devices.explain_i2c_register(bus, 0x68, 0x00, b"\x00") == []


# -- DS18x20 -----------------------------------------------------------------


def test_onewire_crc_matches_maxim_application_note_27():
    # The worked ROM example: family 0x02, serial 00 00 00 01 B8 1C, CRC 0xA2.
    assert ds18x20.crc8(bytes.fromhex("02 1c b8 01 00 00 00")) == 0xA2


@pytest.mark.parametrize("lsb, msb, expected", [
    (0xD0, 0x07, "125.00 °C"),   # the DS18B20 datasheet's table
    (0x91, 0x01, "25.06 °C"),    # +25.0625
    (0x5E, 0xFF, "-10.12 °C"),   # -10.125
    (0x90, 0xFC, "-55.00 °C"),
])
def test_ds18b20_matches_the_datasheet_table(lsb, msb, expected):
    meaning = ds18x20.decode_b(scratchpad(lsb, msb))
    assert value(meaning, "Temperature").startswith(expected)
    assert value(meaning, "Checksum").endswith("OK")


def test_ds18b20_translates_a_real_reading():
    # Read from a probe on the bench (v4, firmware 7.0) on 2026-09-29; the
    # AHT20 beside it read about 29 °C.
    rom = bytes.fromhex("28 7f 4b 6e 00 00 00 be")
    assert ds18x20.crc8(rom[:7]) == rom[7]
    meaning = ds18x20.decode_b(bytes.fromhex("db 01 7f 80 7f ff 05 10 a8"))
    assert meaning == [("Temperature", "29.69 °C (85.4 °F)"), ("Checksum", "0xa8: OK")]


def test_ds18s20_counts_in_half_degrees_not_sixteenths():
    # DS18S20 datasheet: 0x0032 is +25.0 °C and 0xFFCE is -25.0 °C. The old
    # 1-Wire panel divided by 16 for every family and read these as 3.1 °C.
    assert value(ds18x20.decode_s(scratchpad(0x32, 0x00, count_per_c=0)), "Temperature").startswith("25.00 °C")
    assert value(ds18x20.decode_s(scratchpad(0xCE, 0xFF, count_per_c=0)), "Temperature").startswith("-25.00 °C")
    # Extended resolution: 25 - 0.25 + (16 - 12) / 16 = 25.0
    assert value(ds18x20.decode_s(scratchpad(0x32, 0x00)), "Temperature").startswith("25.00 °C")


def test_ds18x20_flags_the_power_on_value_and_damage():
    assert "power-on value" in value(ds18x20.decode_b(scratchpad(0x50, 0x05)), "Note")
    damaged = scratchpad(0x91, 0x01)[:8] + b"\x00"
    assert "WRONG" in value(ds18x20.decode_b(damaged), "Checksum")


# -- MAX31855 ----------------------------------------------------------------


@pytest.mark.parametrize("tc, internal, tc_text, internal_text", [
    (0x1900, 0x190, "1600.00 °C", "25.0000 °C"),   # datasheet Tables 2 and 3
    (0x0064, 0x190, "25.00 °C", "25.0000 °C"),
    (0x3C18, 0xC90, "-250.00 °C", "-55.0000 °C"),
])
def test_max31855_matches_the_datasheet_tables(tc, internal, tc_text, internal_text):
    meaning = max31855.decode(max31855_word(tc, internal))
    assert value(meaning, "Thermocouple") == tc_text
    assert value(meaning, "Chip (cold junction)") == internal_text


def test_max31855_names_its_faults():
    meaning = max31855.decode(max31855_word(0, 0x190, fault_bits=0x01))
    assert "open circuit" in value(meaning, "Fault")
    assert "nothing is driving MISO" in max31855.decode(b"\xff\xff\xff\xff")[0][1]


# -- AD595 -------------------------------------------------------------------


@pytest.mark.parametrize("volts, expected", [
    (0.0027, "0.0 °C"),    # the datasheet's output at 0 °C
    (0.250, "25.0 °C"),    # its calibration point
    (1.0157, "100.0 °C"),  # (4.096 mV + 11 µV) x 247.3
    (0.37, "36.9 °C"),     # the bench probe, held in the fingers
])
def test_ad595_follows_its_datasheet_transfer_function(volts, expected):
    assert value(ad595.from_volts(volts), "Temperature") == expected


def test_ad595_says_when_it_cannot_be_trusted():
    assert "open or disconnected" in value(ad595.from_volts(4.9), "Note")
    assert "cannot go below 0 °C" in value(ad595.from_volts(0.0), "Note")
    assert "above the 0–500 °C" in value(ad595.from_volts(5.5), "Note")


# -- HD44780 LCD on a PCF8574 backpack ---------------------------------------


def lcd_bytes(steps):
    return b"".join(data for data, _ in steps)


def test_lcd_setup_matches_what_drove_the_real_display():
    # The first 24 bytes after the backlight byte are what a 16x2 at 0x27
    # accepted on the bench (v4, 2026-09-29) before showing text.
    sent = lcd_bytes(hd44780.compose("Hello, Bus Pirate\nLine 2 works"))
    assert sent[0] == 0x08
    assert sent[1:25].hex(" ") == (
        "3c 38 3c 38 3c 38 2c 28 2c 28 8c 88 0c 08 cc c8 0c 08 1c 18 0c 08 6c 68")


def test_lcd_text_is_written_as_characters_and_rows_advance():
    steps = hd44780.compose("Hi\nOK")
    meanings = [m for _, m in steps]
    assert meanings[-5:] == ["'H'", "'i'", "go to the start of line 2", "'O'", "'K'"]
    h = dict((m, d) for d, m in steps)["'H'"]
    assert h.hex(" ") == "4d 49 8d 89"  # RS set: a character, not a command


def test_lcd_commands_and_limits():
    steps = hd44780.compose("clear\nline 2\n29.7°C\nline 3\nline 1\n€uro 12345678901234567", "16x2")
    meanings = [m for _, m in steps]
    assert "go to the start of line 2" in meanings
    assert any("a 16x2 display has lines 1 to 2" in m for m in meanings)
    assert dict((m, d) for d, m in steps)["'°'"] == hd44780._byte(0xDF, 0x08, 1)
    assert any("not in the display's font" in m for m in meanings)
    assert any("cut to 16 characters" in m for m in meanings)

    dark = hd44780.compose("backlight off\nHi")
    after = lcd_bytes(dark[dark.index((b"\x00", "backlight off")) + 1:])
    assert after and all(not b & hd44780.BACKLIGHT for b in after)


def test_lcd_script_round_trips_and_rejects_bad_hex():
    steps = hd44780.compose("Hello\ncursor on")
    assert hd44780.parse_script(hd44780.script(steps)) == [d for d, _ in steps if d]
    with pytest.raises(ValueError, match="line 2"):
        hd44780.parse_script("08\n3c 3")


def test_lcd_is_named_in_scans():
    assert devices.i2c_label(0x27) == "LCD (PCF8574 backpack)"
    assert devices.i2c_label(0x3F) == "LCD (PCF8574 backpack)"


# -- the panels use the catalog ---------------------------------------------


class _Ctx:
    def __init__(self, mode):
        self.mode = mode

    def progress(self, *_):
        pass


def test_the_i2c_panel_shows_raw_bytes_then_the_translation():
    from buspirate.web.panels import i2c as panel

    result = panel._read_sensors(_Ctx(FakeI2C()))
    assert result["columns"] == ["Address", "Chip", "Raw bytes", "What it means"]
    rows = {row[0]: row for row in result["rows"]}
    assert rows["0x38"][2] == "0c 70 e2 a6 53 48 b9"
    assert "29.07 °C" in rows["0x38"][3] and "44.1 %RH" in rows["0x38"][3]
    assert "1006.53 hPa" in rows["0x77"][3]
    assert rows["0x50"][1] == "not recognised"

    hand = panel._read(_Ctx(FakeI2C()), 0x38, 7, "hex")
    assert hand["render"] == "hex"
    assert ["Temperature", "29.07 °C"] in hand["meaning"]


def test_the_onewire_panel_reads_each_family_with_its_own_formula():
    from buspirate.web.panels import onewire as panel

    b20 = bytes.fromhex("28 ff 64 1e 0f 00 00 5b")
    s20 = bytes.fromhex("10 a1 b2 c3 d4 e5 f6 07")
    eeprom = bytes.fromhex("2d 00 00 00 00 00 00 11")
    bus = FakeOneWire([b20, s20, eeprom],
                      {b20: scratchpad(0x91, 0x01), s20: scratchpad(0x32, 0x00, count_per_c=0)})
    result = panel._read_sensors(_Ctx(bus), power=False, pullups=False)
    rows = {row[1]: row for row in result["rows"]}
    assert "25.06 °C" in rows["DS18B20"][3]
    assert "25.00 °C" in rows["DS18S20"][3]
    assert result["caption"] == "2 of 3 device(s) read"


def test_the_spi_panel_reads_the_chip_the_user_picked():
    from buspirate.web.panels import spi as panel

    class FakeSPI:
        def configure_peripherals(self, **_):
            pass

        def set_speed(self, _):
            pass

        def set_mode(self, _):
            pass

        def write_then_read(self, data, count):
            return max31855_word(0x0064, 0x190)

    result = panel._read_sensor(_Ctx(FakeSPI()), "MAX31855", False, 3, 0)
    assert result["render"] == "hex"
    assert ["Thermocouple", "25.00 °C"] in result["meaning"]


def test_every_package_is_listed_in_pyproject():
    # pyproject.toml names its packages by hand; one left out is missing from
    # every install and from the built app, while the tests still pass here.
    import os
    import re

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "pyproject.toml")) as f:
        listed = set(re.findall(r'"(buspirate[\w.]*)"', re.search(r"^packages = \[.*\]", f.read(), re.M).group(0)))
    on_disk = {
        os.path.relpath(folder, root).replace(os.sep, ".")
        for folder, _, files in os.walk(os.path.join(root, "buspirate"))
        if "__init__.py" in files
    }
    assert on_disk - listed == set(), "add these to packages in pyproject.toml"


def test_measure_a_voltage_translates_when_asked():
    from buspirate.web.panels import pins as panel

    class FakeBP:
        def read_voltage(self):
            return 0.37

    class Ctx:
        bp = FakeBP()
        profile = None  # no capabilities: no supplies note

    plain = panel._voltage(Ctx())
    assert plain["pairs"] == [["ADC probe", "0.370 V"]] and "meaning" not in plain
    translated = panel._voltage(Ctx(), translate="AD595")
    assert translated["pairs"] == [["ADC probe", "0.370 V"]]
    assert ["Temperature", "36.9 °C"] in translated["meaning"]


def test_the_lcd_tool_translates_then_sends_each_step(monkeypatch):
    from buspirate.web.panels import i2c as panel

    monkeypatch.setattr(hd44780, "STEP_PAUSE", 0)
    translated = panel._lcd_translate(_Ctx(None), "Hi", "16x2", True)
    assert translated["render"] == "fill"
    assert (translated["action"], translated["param"]) == ("lcd_send", "script")
    assert "# wake-up 1 of 3" in translated["value"]

    bus = FakeI2C()
    result = panel._lcd_send(_Ctx(bus), 0x27, translated["value"])
    assert result["tone"] == "good"
    assert [data for _, data in bus.writes] == hd44780.parse_script(translated["value"])
    assert all(address == 0x27 for address, _ in bus.writes)

    assert panel._lcd_send(_Ctx(bus), 0x27, "# only a comment")["tone"] == "warn"
    assert "line 1" in panel._lcd_send(_Ctx(bus), 0x27, "zz")["text"]
