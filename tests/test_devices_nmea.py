from buspirate.devices import nmea

GGA = "$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47"
RMC = "$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A"


def test_gga():
    (s,) = nmea.parse(GGA)
    assert s["type"] == "GGA"
    assert s["time"] == "12:35:19"
    assert s["latitude"] == pytest_approx(48.1173)
    assert s["longitude"] == pytest_approx(11.516667)
    assert s["fix_quality"] == 1
    assert s["satellites"] == 8


def test_rmc():
    (s,) = nmea.parse(RMC)
    assert s["type"] == "RMC"
    assert s["valid"] is True
    assert s["latitude"] == pytest_approx(48.1173)
    assert s["speed_kmh"] == pytest_approx(22.4 * 1.852)


def test_southern_western_negative_and_no_fix():
    body = "GPGGA,000000,3351.000,S,15112.000,W,0,00,,,M,,M,,"
    cs = 0
    for ch in body:
        cs ^= ord(ch)
    (s,) = nmea.parse("$%s*%02X" % (body, cs))
    assert s["latitude"] < 0 and s["longitude"] < 0
    assert s["fix_quality"] == 0
    assert s["satellites"] == 0


def test_bad_checksum_flagged():
    bad = GGA[:-2] + "00"
    (s,) = nmea.parse(bad)
    assert s == {"sentence": bad, "error": "checksum"}


def test_multiple_lines_and_noise():
    out = nmea.parse("garbage\r\n%s\r\n$GPVTG,1,2*00\r\n%s\r\n" % (GGA, RMC))
    assert [s.get("type") for s in out] == ["GGA", "RMC"]


def pytest_approx(v):
    import pytest
    return pytest.approx(v, abs=1e-4)
