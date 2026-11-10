import pytest

from buspirate.devices import onewire_eeprom as oe
from buspirate.exceptions import BusPirateError
from buspirate.simulator_bp6 import FakeDs2431


def test_read():
    chip = FakeDs2431()
    assert oe.read(chip, 0x2D, 4, 10) == bytes(chip.mem[4:14])
    assert oe.read(chip, 0x2D, 0, 128) == bytes(chip.mem)


def test_read_ds2433_spans_chunks():
    chip = FakeDs2431(family=0x23)
    assert oe.read(chip, 0x23, 0, 512) == bytes(chip.mem)


def test_read_beyond_chip_raises():
    with pytest.raises(ValueError):
        oe.read(FakeDs2431(), 0x2D, 120, 16)


def test_write_partial_row_merges():
    chip = FakeDs2431()
    old = bytes(chip.mem)
    oe.write(chip, 0x2D, 6, b"\xaa\xbb\xcc", wait=0)
    assert bytes(chip.mem[6:9]) == b"\xaa\xbb\xcc"
    assert bytes(chip.mem[:6]) == old[:6] and bytes(chip.mem[9:]) == old[9:]


def test_write_ds2433_row32():
    chip = FakeDs2431(family=0x23)
    old = bytes(chip.mem)
    data = bytes(range(40))
    oe.write(chip, 0x23, 30, data, wait=0)
    assert bytes(chip.mem[30:70]) == data
    assert bytes(chip.mem[:30]) == old[:30] and bytes(chip.mem[70:]) == old[70:]


def test_copy_fails_raises():
    chip = FakeDs2431()
    chip.copy_fails = True
    old = bytes(chip.mem)
    with pytest.raises(oe.CopyError) as exc:
        oe.write(chip, 0x2D, 0, b"\x01\x02", wait=0)
    assert "2.2 kΩ pull-up" in str(exc.value)
    assert isinstance(exc.value, BusPirateError) and bytes(chip.mem) == old


def test_scratchpad_mismatch_raises():
    class Bad(FakeDs2431):
        def read(self, count):
            data = bytearray(super().read(count))
            if bytes(self._cmd[:2]) == b"\xcc\xaa":
                data[-1] ^= 0xFF
            return bytes(data)

    chip = Bad()
    old = bytes(chip.mem)
    with pytest.raises(oe.ScratchpadError) as exc:
        oe.write(chip, 0x2D, 0, b"\x01\x02", wait=0)
    assert isinstance(exc.value, BusPirateError) and bytes(chip.mem) == old
