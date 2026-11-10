"""SHT3x, SHT4x and Si7021 drivers, against fake I2C buses.

The datasheets give the CRC example (0xBEEF -> 0x92) but no full measurement
replies, so the replies below are built from raw counts and the expected
values are computed from the datasheet formulas, not read off a real chip.
"""

import pytest

from buspirate import devices
from buspirate.devices import sht3x, sht4x, si7021
from buspirate.devices.aht20 import crc8


def reply(t_raw, h_raw):
    t, h = t_raw.to_bytes(2, "big"), h_raw.to_bytes(2, "big")
    return t + bytes([crc8(t)]) + h + bytes([crc8(h)])


class FakeI2C:
    """Answers like one chip; NACKs (raises) any command it does not know."""

    def __init__(self, answers):
        self.answers = answers  # {command bytes: reply bytes}
        self.last = None
        self.writes = []

    def write(self, address, data):
        self.writes.append((address, bytes(data)))
        if bytes(data) not in self.answers:
            raise IOError("NACK")
        self.last = bytes(data)

    def read(self, address, count):
        return self.answers[self.last][:count]


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    for module in (sht3x, sht4x, si7021):
        monkeypatch.setattr(module.time, "sleep", lambda s: None)


def value(meaning, label):
    return dict(meaning)[label]


def test_crc_matches_the_datasheet_example():
    assert crc8(bytes([0xBE, 0xEF])) == 0x92


def test_sht3x_translates_a_reply():
    # T = 26241 -> -45 + 175*26241/65535 = 25.07 C; RH = 51358 -> 78.37 %
    bus = FakeI2C({sht3x.MEASURE: reply(26241, 51358)})
    r = sht3x.measure(bus, 0x44)
    assert r.device == "SHT3x" and r.raw == reply(26241, 51358)
    assert value(r.meaning, "Temperature") == "25.07 °C"
    assert value(r.meaning, "Humidity") == "78.4 %RH"
    assert bus.writes == [(0x44, bytes([0x24, 0x00]))]


def test_sht3x_rejects_a_bad_crc():
    bad = bytearray(reply(26241, 51358))
    bad[5] ^= 0xFF
    with pytest.raises(ValueError, match="CRC"):
        sht3x.measure(FakeI2C({sht3x.MEASURE: bytes(bad)}), 0x44)


def test_sht4x_translates_and_clamps():
    # T = 26241 -> 25.07 C; RH = 30000 -> -6 + 125*30000/65535 = 51.22 %
    bus = FakeI2C({sht4x.MEASURE: reply(26241, 30000)})
    r = sht4x.measure(bus, 0x44)
    assert value(r.meaning, "Temperature") == "25.07 °C"
    assert value(r.meaning, "Humidity") == "51.2 %RH"
    # RH raw 0 would be -6 %RH, raw 65535 would be 119 %RH: both clamp.
    assert value(sht4x.decode(reply(0, 0)), "Humidity") == "0.0 %RH"
    assert value(sht4x.decode(reply(0, 65535)), "Humidity") == "100.0 %RH"


def test_sht4x_rejects_a_bad_crc():
    bad = bytearray(reply(26241, 30000))
    bad[2] ^= 0x01
    with pytest.raises(ValueError, match="CRC"):
        sht4x.measure(FakeI2C({sht4x.MEASURE: bytes(bad)}), 0x44)


def sht3x_chip():
    status = bytes([0x80, 0x10]) + bytes([crc8(bytes([0x80, 0x10]))])
    return FakeI2C({sht3x.STATUS: status, sht3x.MEASURE: reply(26241, 51358)})


def sht4x_chip():
    return FakeI2C({sht4x.SERIAL: reply(0x1234, 0x5678), sht4x.MEASURE: reply(26241, 30000)})


def test_the_shared_address_is_told_apart():
    assert sht3x.probe(sht3x_chip(), 0x44) and not sht4x.probe(sht3x_chip(), 0x44)
    assert sht4x.probe(sht4x_chip(), 0x44) and not sht3x.probe(sht4x_chip(), 0x44)


def test_identify_picks_the_right_driver_at_0x44():
    assert devices.identify_i2c(sht3x_chip(), 0x44).name == "SHT3x"
    assert devices.identify_i2c(sht4x_chip(), 0x44).name == "SHT4x"
    assert devices.read_i2c(sht4x_chip(), 0x44).device == "SHT4x"


def test_si7021_translates_a_reply():
    # RH 0x7C80 = 31872 -> -6 + 125*31872/65536 = 54.79 %;
    # T 0x6600 = 26112 -> -46.85 + 175.72*26112/65536 = 23.16 C (formulas, not a bench value)
    bus = FakeI2C({si7021.MEASURE_HUMIDITY: bytes([0x7C, 0x80]),
                   si7021.READ_TEMPERATURE: bytes([0x66, 0x00])})
    r = devices.read_i2c(bus, 0x40)
    assert r.device == "Si7021" and r.raw == bytes([0x7C, 0x80, 0x66, 0x00])
    assert value(r.meaning, "Humidity") == "54.8 %RH"
    assert value(r.meaning, "Temperature") == "23.16 °C"
    assert [w[1] for w in bus.writes] == [bytes([0xF5]), bytes([0xE0])]
