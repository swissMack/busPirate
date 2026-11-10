import pytest

from buspirate.devices import eeprom24


class FakeI2C:
    """Remembers a memory image; records every write/read it is given."""

    def __init__(self, size):
        self.mem = bytes(i % 251 for i in range(size))
        self.writes = []
        self.reads = []
        self._ptr = None

    def write(self, address, data=b""):
        self.writes.append((address, bytes(data)))
        block = address - 0x50
        self._ptr = (block, bytes(data))

    def read(self, address, count):
        self.reads.append((address, count))
        block, ptr = self._ptr
        pos = int.from_bytes(ptr, "big")
        if len(ptr) == 1:
            pos += block << 8
        else:
            pos += block << 16
        return self.mem[pos:pos + count]


def test_sizes_table():
    assert eeprom24.SIZES["24C02"] == (256, 1)
    assert eeprom24.SIZES["24C256"] == (32768, 2)
    assert eeprom24.SIZES["24C512"] == (65536, 2)
    assert eeprom24.SIZES["MB85RC256V"] == (32768, 2)
    assert "24C01" in eeprom24.SIZES and "24M02" in eeprom24.SIZES


def test_24c02_uses_one_byte_pointer():
    i2c = FakeI2C(256)
    data = eeprom24.read(i2c, 0x50, "24C02", offset=0x10, length=8)
    assert i2c.writes == [(0x50, bytes([0x10]))]
    assert data == i2c.mem[0x10:0x18]


def test_24c256_uses_two_byte_pointer():
    i2c = FakeI2C(32768)
    data = eeprom24.read(i2c, 0x50, "24C256", offset=0x1234, length=16)
    assert i2c.writes == [(0x50, bytes([0x12, 0x34]))]
    assert data == i2c.mem[0x1234:0x1244]


def test_24c16_crosses_blocks_with_addresses_50_to_57():
    i2c = FakeI2C(2048)
    data = eeprom24.read(i2c, 0x50, "24C16")
    assert data == i2c.mem
    assert sorted({a for a, _ in i2c.writes}) == [0x50 + b for b in range(8)]
    assert all(len(p) == 1 for _, p in i2c.writes)


def test_chunking_respects_chunk_size():
    i2c = FakeI2C(32768)
    data = eeprom24.read(i2c, 0x50, "24C256", offset=0, length=1000, chunk=300)
    assert data == i2c.mem[:1000]
    assert [c for _, c in i2c.reads] == [300, 300, 300, 100]


def test_whole_part_by_default_and_bounds():
    i2c = FakeI2C(256)
    assert eeprom24.read(i2c, 0x50, "24C02", offset=250) == i2c.mem[250:]
    with pytest.raises(ValueError):
        eeprom24.read(i2c, 0x50, "24C02", offset=250, length=10)
    with pytest.raises(ValueError):
        eeprom24.read(i2c, 0x50, "24C99")
