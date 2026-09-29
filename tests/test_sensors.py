"""The sensor translators, checked against known answers."""

import struct

import pytest

from buspirate import sensors

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


class FakeBus:
    """Just enough of the I2C mode for the translators: registers per chip."""

    def __init__(self, bmp_address=0x77, chip_id=0x58, aht_status=0x1C):
        self.bmp_address = bmp_address
        self.chip_id = chip_id
        self.aht_status = aht_status
        self.writes = []

    def scan(self):
        return [0x38, self.bmp_address, 0x50]

    def read(self, address, count):
        assert address == 0x38
        if count == 1:
            return bytes([self.aht_status])
        return AHT20_REPLY[:count]

    def write(self, address, data):
        self.writes.append((address, bytes(data)))

    def read_register(self, address, register, count):
        assert address == self.bmp_address
        regs = {sensors.BMP280_REG_CHIP_ID: bytes([self.chip_id]),
                sensors.BMP280_REG_CALIBRATION: BMP280_CAL,
                sensors.BMP280_REG_DATA: BMP280_DATA}
        return regs[register][:count]


def value(meaning, key):
    return dict(meaning)[key]


def test_aht20_translates_a_real_reply():
    meaning = sensors.decode_aht20(AHT20_REPLY)
    assert value(meaning, "Temperature") == "29.07 °C"
    assert value(meaning, "Humidity") == "44.1 %RH"
    assert "finished" in value(meaning, "Status") and "calibrated" in value(meaning, "Status")
    assert value(meaning, "Checksum").endswith("OK")


def test_aht20_flags_a_damaged_or_unfinished_reply():
    damaged = AHT20_REPLY[:6] + b"\x00"
    assert "WRONG" in value(sensors.decode_aht20(damaged), "Checksum")
    busy = bytes([0x9C]) + AHT20_REPLY[1:]
    assert "busy" in value(sensors.decode_aht20(busy), "Status")
    assert "needs at least 6 bytes" in sensors.decode_aht20(b"\x1c\x00")[0][1]


def test_bmp280_matches_the_datasheet_example():
    temperature, pressure = sensors.bmp280_compensate(BMP280_DATA, BMP280_CAL)
    assert temperature == pytest.approx(25.08, abs=0.01)
    assert pressure == pytest.approx(1006.53, abs=0.01)


def test_bmp280_says_when_it_has_never_measured():
    meaning = sensors.decode_bmp280(bytes.fromhex("80 00 00 80 00 00"), BMP280_CAL)
    assert "has not measured yet" in value(meaning, "Note")


def test_identify_uses_the_address_and_the_chip_id():
    assert sensors.identify(FakeBus(), 0x38) == "AHT20"
    assert sensors.identify(FakeBus(), 0x77) == "BMP280"
    assert sensors.identify(FakeBus(chip_id=0x60), 0x77) == "BME280"
    assert sensors.identify(FakeBus(chip_id=0x11), 0x77) is None
    assert sensors.identify(FakeBus(), 0x50) is None


def test_read_sensor_measures_and_translates():
    bus = FakeBus()
    aht = sensors.read_sensor(bus, 0x38)
    assert aht.chip == "AHT20" and aht.raw == AHT20_REPLY
    assert (0x38, sensors.AHT20_MEASURE) in bus.writes

    bmp = sensors.read_sensor(bus, 0x77)
    assert bmp.raw == BMP280_DATA
    assert value(bmp.meaning, "Temperature") == "25.08 °C"
    # Forced mode: one measurement, then the chip goes back to sleep.
    assert (0x77, bytes([0xF4, sensors.BMP280_FORCED_X1])) in bus.writes


def test_an_uncalibrated_aht20_is_calibrated_first():
    bus = FakeBus(aht_status=0x10)
    sensors.read_sensor(bus, 0x38)
    assert bus.writes[0] == (0x38, sensors.AHT20_CALIBRATE)


def test_hand_reads_are_explained():
    bus = FakeBus()
    assert value(sensors.explain_read(0x38, AHT20_REPLY), "Temperature") == "29.07 °C"
    assert sensors.explain_read(0x50, AHT20_REPLY) == []

    chip_id = sensors.explain_register_read(bus, 0x77, 0xD0, b"\x58")
    assert value(chip_id, "Chip ID") == "0x58: BMP280"
    data = sensors.explain_register_read(bus, 0x77, 0xF7, BMP280_DATA)
    assert value(data, "Pressure") == "1006.53 hPa"
    cal = sensors.explain_register_read(bus, 0x77, 0x88, BMP280_CAL)
    assert value(cal, "Calibration").startswith("T1=27504, T2=26435, T3=-1000")
    assert sensors.explain_register_read(bus, 0x68, 0x00, b"\x00") == []


def test_the_dashboard_shows_raw_bytes_then_the_translation():
    from buspirate.web.panels import i2c as panel

    class Ctx:
        mode = FakeBus()

    result = panel._read_sensors(Ctx())
    assert result["columns"] == ["Address", "Chip", "Raw bytes", "What it means"]
    rows = {row[0]: row for row in result["rows"]}
    assert rows["0x38"][2] == "0c 70 e2 a6 53 48 b9"
    assert "29.07 °C" in rows["0x38"][3] and "44.1 %RH" in rows["0x38"][3]
    assert "1006.53 hPa" in rows["0x77"][3]
    assert rows["0x50"][1] == "not recognised"

    hand = panel._read(Ctx(), 0x38, 7, "hex")
    assert hand["render"] == "hex"
    assert ["Temperature", "29.07 °C"] in hand["meaning"]
