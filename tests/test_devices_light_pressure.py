"""TSL2561, TCS3472x and MS5611 drivers, against fake I2C buses.

The MS5611 datasheet example is exact. The two light sensors have no worked
examples, so their expected values are computed from the datasheet formulas.
"""

import pytest

from buspirate import devices
from buspirate.devices import bmp280, ms5611, tcs3472x, tsl2561

PROM_COEFFS = [40127, 36924, 23317, 23282, 33464, 28312]


def prom_words(coeffs=PROM_COEFFS, factory=0x3132):
    words = [factory] + list(coeffs) + [0]
    words[7] = ms5611.crc4(words)
    return words


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


class FakeMS5611(FakeI2C):
    def __init__(self, words, d1=9085466, d2=8569150):
        answers = {bytes([0x1E]): b""}
        for i, w in enumerate(words):
            answers[bytes([0xA0 + 2 * i])] = w.to_bytes(2, "big")
        answers[bytes([0x48])] = b""
        answers[bytes([0x58])] = b""
        super().__init__(answers)
        self.d = {0x48: d1, 0x58: d2}
        self.convert = None

    def write(self, address, data):
        super().write(address, data)
        if bytes(data)[0] in self.d:
            self.convert = bytes(data)[0]
        elif bytes(data) == bytes([0x00]):
            pass

    def read(self, address, count):
        if self.last == bytes([0x00]):
            return self.d[self.convert].to_bytes(3, "big")[:count]
        return super().read(address, count)


class FakeMS5611Adc(FakeMS5611):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.answers[bytes([0x00])] = b""


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    for module in (tsl2561, tcs3472x, ms5611):
        monkeypatch.setattr(module.time, "sleep", lambda s: None)


def value(meaning, label):
    return dict(meaning)[label]


# -- MS5611 ------------------------------------------------------------------


def test_ms5611_matches_the_datasheet_example():
    temperature, pressure = ms5611.compensate(PROM_COEFFS, 9085466, 8569150)
    assert round(temperature, 2) == 20.07
    assert round(pressure, 2) == 1000.09


def test_ms5611_second_order_correction_below_20_degrees():
    # D2 chosen so dT is negative: TEMP < 20 C, so the second-order step applies.
    c = PROM_COEFFS
    d1, d2 = 9085466, 8400000
    dt = d2 - c[4] * 256
    temp = 2000 + dt * c[5] // 2 ** 23
    assert temp < 2000
    t2 = dt * dt // 2 ** 31
    off2 = 5 * (temp - 2000) ** 2 // 2
    sens2 = off2 // 2
    off = c[1] * 2 ** 16 + c[3] * dt // 2 ** 7 - off2
    sens = c[0] * 2 ** 15 + c[2] * dt // 2 ** 8 - sens2
    expected_p = (d1 * sens // 2 ** 21 - off) // 2 ** 15 / 100
    temperature, pressure = ms5611.compensate(c, d1, d2)
    assert temperature == pytest.approx((temp - t2) / 100)
    assert pressure == pytest.approx(expected_p, abs=0.01)


def test_ms5611_measure_reads_prom_and_converts():
    bus = FakeMS5611Adc(prom_words())
    r = ms5611.measure(bus, 0x76)
    assert r.device == "MS5611" and r.where == "0x76"
    assert value(r.meaning, "Temperature") == "20.07 °C"
    assert value(r.meaning, "Pressure") == "1000.09 hPa"
    sent = [w[1] for w in bus.writes]
    assert sent[0] == bytes([0x1E])
    assert bytes([0x48]) in sent and bytes([0x58]) in sent


def test_ms5611_probe_checks_the_prom_crc():
    assert ms5611.probe(FakeMS5611(prom_words()), 0x76) is True
    bad = prom_words()
    bad[3] ^= 0x0100
    assert ms5611.probe(FakeMS5611(bad), 0x76) is False
    assert ms5611.probe(FakeI2C({}), 0x76) is False  # NACK


class FakeBMP280(FakeI2C):
    """A BMP280 at 0x76: ID register D0 = 0x58; PROM reads NACK."""

    def __init__(self):
        super().__init__({bytes([0xD0]): bytes([0x58])})

    def read_register(self, address, register, count):
        return bytes([0x58])[:count]


def test_ms5611_and_bmp280_probes_reject_each_other():
    bmp = FakeBMP280()
    assert ms5611.probe(bmp, 0x76) is False
    assert bmp280.DEVICES[0].probe(bmp, 0x76) is True
    ms = FakeMS5611(prom_words())  # has no read_register: not a BMP280
    assert bmp280.DEVICES[0].probe(ms, 0x76) is False
    assert devices.identify_i2c(ms, 0x76).name == "MS5611"
    assert devices.identify_i2c(bmp, 0x76).name == "BMP280"


# -- TSL2561 -----------------------------------------------------------------


def test_tsl2561_lux_follows_the_datasheet_piecewise_formula():
    assert tsl2561.lux(1000, 0) == pytest.approx(0.0304 * 1000)  # r = 0
    assert tsl2561.lux(1000, 400) == pytest.approx(0.0304 * 1000 - 0.062 * 1000 * 0.4 ** 1.4)
    assert tsl2561.lux(1000, 550) == pytest.approx(0.0224 * 1000 - 0.031 * 550)
    assert tsl2561.lux(1000, 700) == pytest.approx(0.0128 * 1000 - 0.0153 * 700)
    assert tsl2561.lux(1000, 1000) == pytest.approx(0.00146 * 1000 - 0.00112 * 1000)
    assert tsl2561.lux(1000, 1400) == 0.0
    assert tsl2561.lux(0, 0) == 0.0


def test_tsl2561_measures_both_channels():
    bus = FakeI2C({
        bytes([0x80, 0x03]): b"", bytes([0xAC]): (13868).to_bytes(2, "little"),
        bytes([0xAE]): (6934).to_bytes(2, "little"),
    })
    r = tsl2561.measure(bus, 0x39)
    assert r.device == "TSL2561" and r.where == "0x39"
    assert r.raw == (13868).to_bytes(2, "little") + (6934).to_bytes(2, "little")
    assert value(r.meaning, "Visible + IR (CH0)") == "13868"
    assert value(r.meaning, "Infrared (CH1)") == "6934"
    assert value(r.meaning, "Illuminance") == f"{tsl2561.lux(13868, 6934):.1f} lux"
    assert bus.writes[0] == (0x39, bytes([0x80, 0x03]))


@pytest.mark.parametrize("chip_id", [0x50, 0x1A])
def test_tsl2561_probe_reads_the_id_register(chip_id):
    assert tsl2561.probe(FakeI2C({bytes([0x8A]): bytes([chip_id])}), 0x29) is True


def test_tsl2561_probe_rejects_other_chips():
    assert tsl2561.probe(FakeI2C({bytes([0x8A]): bytes([0x44])}), 0x29) is False
    assert tsl2561.probe(FakeI2C({}), 0x29) is False


# -- TCS3472x ----------------------------------------------------------------


def tcs_reply(c, r, g, b):
    return b"".join(v.to_bytes(2, "little") for v in (c, r, g, b))


def test_tcs3472x_translates_a_reply():
    c, r, g, b = 1000, 400, 500, 300
    bus = FakeI2C({
        bytes([0x80, 0x03]): b"", bytes([0x81, 0xF6]): b"",
        bytes([0xB4]): tcs_reply(c, r, g, b),
    })
    res = tcs3472x.measure(bus, 0x29)
    assert res.device == "TCS3472x" and res.raw == tcs_reply(c, r, g, b)
    assert value(res.meaning, "Clear") == "1000"
    assert value(res.meaning, "Red") == "400"
    # DN40: IR = (R+G+B-C)/2 = 100; R2=300 G2=400 B2=200
    assert value(res.meaning, "Colour temperature") == f"{3810 * 200 / 300 + 1391:.0f} K"
    g1 = 0.136 * 300 + 400 - 0.444 * 200
    cpl = 24 * 1 / 310
    assert value(res.meaning, "Illuminance") == f"{g1 / cpl:.1f} lux"
    assert bus.writes[:2] == [(0x29, bytes([0x80, 0x03])), (0x29, bytes([0x81, 0xF6]))]


def test_tcs3472x_survives_a_dark_reading():
    meaning = tcs3472x.decode(tcs_reply(0, 0, 0, 0))
    assert value(meaning, "Clear") == "0"
    assert "Colour temperature" not in dict(meaning)


@pytest.mark.parametrize("chip_id", [0x44, 0x4D])
def test_tcs3472x_probe_reads_the_id_register(chip_id):
    assert tcs3472x.probe(FakeI2C({bytes([0x92]): bytes([chip_id])}), 0x29) is True


def test_tcs3472x_and_tsl2561_tell_each_other_apart_at_0x29():
    tcs = FakeI2C({bytes([0x92]): bytes([0x44])})
    tsl = FakeI2C({bytes([0x8A]): bytes([0x50])})
    assert tcs3472x.probe(tsl, 0x29) is False and tsl2561.probe(tcs, 0x29) is False
    assert devices.identify_i2c(tcs, 0x29).name == "TCS3472x"
    assert devices.identify_i2c(tsl, 0x29).name == "TSL2561"


def test_the_names_list_no_longer_carries_a_bare_tsl2561():
    assert devices.i2c_label(0x39) == "TSL2561"
