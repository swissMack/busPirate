import pytest

from buspirate.devices import eeprom93
from buspirate.exceptions import BusPirateError
from buspirate.simulator_bp6 import FakeMicrowire


class FakeSpi:
    """A SPI mode object over a FakeMicrowire; CS is active-high unless told otherwise."""

    def __init__(self, chip):
        self.chip = chip
        self.active_high = False

    def set_cs_active_high(self, value):
        self.active_high = value

    def write_then_read(self, data=b"", read_count=0):
        if not self.active_high:
            return b"\x00" * read_count
        return self.chip.exchange(bytes(data), read_count)


def _spi(chip):
    spi = FakeSpi(chip)
    spi.set_cs_active_high(True)
    return spi


def test_frame():
    assert eeprom93.frame("110" + "0000101") == bytes([0x03, 0x05])
    assert eeprom93.frame("1") == b"\x01"


def test_normalize():
    assert eeprom93.normalize("93LC46B") == "93C46"
    assert eeprom93.normalize("93aa66") == "93C66"
    assert eeprom93.normalize("93C86") == "93C86"
    with pytest.raises(ValueError):
        eeprom93.normalize("24C02")


def test_org_clash():
    with pytest.raises(ValueError):
        eeprom93.normalize("93LC46A", 16)
    with pytest.raises(ValueError):
        eeprom93.normalize("93LC46B", 8)
    assert eeprom93.normalize("93LC46A", 8) == "93C46"


@pytest.mark.parametrize("org", [8, 16])
def test_read_x16_and_x8(org):
    data = bytes((i * 5 + 1) & 0xFF for i in range(128))
    spi = _spi(FakeMicrowire("93C46", org, data))
    assert eeprom93.read(spi, "93C46", org, 0, 128) == data
    assert eeprom93.read(spi, "93C46", org, 10, 20) == data[10:30]


def test_read_x16_needs_even():
    spi = _spi(FakeMicrowire("93C46", 16))
    with pytest.raises(ValueError):
        eeprom93.read(spi, "93C46", 16, 1, 4)
    with pytest.raises(ValueError):
        eeprom93.read(spi, "93C46", 16, 0, 3)


def test_read_needs_active_high_cs():
    chip = FakeMicrowire("93C46", 16, bytes(range(1, 129)))
    spi = FakeSpi(chip)
    assert eeprom93.read(spi, "93C46", 16, 0, 4) == b"\x00" * 4


def test_write_round_trip():
    chip = FakeMicrowire("93C66", 8)
    spi = _spi(chip)
    payload = bytes(range(0xA0, 0xAA))
    eeprom93.write(spi, "93C66", 8, 5, payload)
    assert bytes(chip.mem[5:15]) == payload
    assert eeprom93.read(spi, "93C66", 8, 5, 10) == payload
    assert chip.write_enabled is False  # EWDS afterwards


def test_write_round_trip_x16():
    chip = FakeMicrowire("93C46", 16)
    spi = _spi(chip)
    eeprom93.write(spi, "93C46", 16, 4, b"\x12\x34\x56\x78")
    assert bytes(chip.mem[4:8]) == b"\x12\x34\x56\x78"


def test_write_needs_ewen():
    chip = FakeMicrowire("93C66", 8)
    chip.ewen_works = False
    spi = _spi(chip)
    eeprom93.write(spi, "93C66", 8, 0, b"\x00\x01")
    assert bytes(chip.mem[:2]) == b"\xff\xff"


def test_write_timeout_is_a_bus_pirate_error():
    chip = FakeMicrowire("93C46", 8)
    chip.busy_polls = 10 ** 9
    with pytest.raises(BusPirateError):
        eeprom93.write(_spi(chip), "93C46", 8, 0, b"\x01", timeout=0.01)
