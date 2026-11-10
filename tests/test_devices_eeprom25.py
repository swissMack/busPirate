import pytest

from buspirate.devices import eeprom25
from buspirate.exceptions import BusPirateError
from buspirate.simulator_bp6 import FakeEeprom25


class FakeSpi:
    """A SPI mode object over a FakeEeprom25: write_then_read replays one transaction."""

    def __init__(self, chip):
        self.chip = chip
        self.log = []

    def write_then_read(self, data=b"", read_count=0):
        self.log.append(bytes(data))
        return self.chip.exchange(bytes(data), read_count)


def test_normalize():
    assert eeprom25.normalize("25LC256") == "25256"
    assert eeprom25.normalize("AT25040") == "25040"
    assert eeprom25.normalize("M95M02") == "25M02"
    assert eeprom25.normalize("fm25v02") == "FM25V02"
    with pytest.raises(ValueError) as exc:
        eeprom25.normalize("24C02")
    assert "25256" in str(exc.value)


def test_read_25040_high_half():
    chip = FakeEeprom25("25040", bytes(i % 251 for i in range(512)))
    spi = FakeSpi(chip)
    data = eeprom25.read(spi, "25040", 0x100, 8)
    assert spi.log[0][0] == 0x0B and spi.log[0][1] == 0x00
    assert data == bytes(chip.mem[0x100:0x108])


def test_write_pages_and_polls():
    chip = FakeEeprom25("25256", b"\xff" * 32768)
    spi = FakeSpi(chip)
    payload = bytes(range(100))
    eeprom25.write(spi, "25256", 0x3F, payload)
    assert bytes(chip.mem[0x3F:0x3F + 100]) == payload
    assert chip.mem[0x3E] == 0xFF and chip.mem[0x3F + 100] == 0xFF
    assert len(chip.writes) == 3
    for offset, length in chip.writes:
        assert offset // 64 == (offset + length - 1) // 64
    assert any(w == b"\x05" for w in spi.log)  # RDSR polled


def test_write_protected_raises():
    chip = FakeEeprom25("25256")
    chip.protect_bits = 0x0C
    with pytest.raises(eeprom25.ProtectedError) as exc:
        eeprom25.write(FakeSpi(chip), "25256", 0, b"\x00")
    assert "0x0c" in str(exc.value).lower()
    assert issubclass(eeprom25.ProtectedError, BusPirateError)


def test_fram_write_single_page():
    chip = FakeEeprom25("FM25V02")
    spi = FakeSpi(chip)
    eeprom25.write(spi, "FM25V02", 0x10, bytes(range(200)))
    assert chip.writes == [(0x10, 200)]
    assert bytes(chip.mem[0x10:0x10 + 200]) == bytes(range(200))
