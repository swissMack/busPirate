import pytest

from buspirate.devices import spd
from buspirate.exceptions import NackError


def ddr4_image(part=b"M378A1K43DB2-CTD", serial=b"\x12\x34\x56\x78", module=2):
    data = bytearray(512)
    data[2], data[3] = 0x0C, module
    data[320], data[321] = 0x80, 0xCE  # bank 1, Samsung with its parity bit
    data[325:329] = serial
    data[329:329 + len(part)] = part
    data[329 + len(part):349] = b" " * (20 - len(part))
    for start, end in ((0, 126), (128, 254)):
        data[end:end + 2] = spd.crc16(bytes(data[start:end])).to_bytes(2, "little")
    return bytes(data)


def ddr5_image(part=b"M323R2GA3BB0-CQK", serial=b"\xde\xad\xbe\xef", module=2):
    data = bytearray(1024)
    data[2], data[3] = 0x12, module
    data[512], data[513] = 0x80, 0xCE
    data[517:521] = serial
    data[521:521 + len(part)] = part
    data[510:512] = spd.crc16(bytes(data[0:510])).to_bytes(2, "little")
    return bytes(data)


class FakeDdr4:
    """A DDR4 SPD on a bare I2C object: pages are chosen at 0x36/0x37."""

    def __init__(self, image, needs_dummy=False, switches=True):
        self.image, self.needs_dummy, self.switches = image, needs_dummy, switches
        self.page = 0
        self.writes = []

    def write(self, address, data=b""):
        self.writes.append((address, bytes(data)))
        if address in (0x36, 0x37):
            if self.switches and (len(data) == 1 or not self.needs_dummy):
                self.page = address - 0x36
        elif address != 0x50:
            raise NackError("no")

    def read(self, address, count):
        if address == 0x36 and self.page == 1:
            raise NackError("page 1")
        return bytes(count)

    def read_after_write(self, address, pointer, count):
        base = self.page * 256 + pointer[0]
        return self.image[base:base + count]


class FakeDdr5:
    def __init__(self, image):
        self.image, self.page, self.writes = image, 0, []

    def write(self, address, data=b""):
        self.writes.append((address, bytes(data)))
        if bytes(data[:1]) == b"\x0b":
            self.page = data[1]

    def read_after_write(self, address, pointer, count):
        if bytes(pointer) == b"\x00":
            return b"\x51\x18"[:count]  # MR0/MR1: SPD5118 hub
        base = self.page * 128 + (pointer[0] & 0x7F)
        return self.image[base:base + count]


def test_crc16_vector():
    assert spd.crc16(b"123456789") == 0x31C3


def test_read_ddr4_two_pages():
    image = ddr4_image()
    fake = FakeDdr4(image)
    assert spd.read_ddr4(fake) == image
    assert fake.page == 0
    assert spd.read_ddr4(FakeDdr4(image))[256:260] == image[256:260]


def test_read_ddr4_retries_with_dummy_byte():
    image = ddr4_image()
    fake = FakeDdr4(image, needs_dummy=True)
    assert spd.read_ddr4(fake) == image
    assert (0x37, b"\x00") in fake.writes


def test_read_ddr4_page_switch_fails():
    with pytest.raises(spd.SpdError, match="did not switch SPD pages"):
        spd.read_ddr4(FakeDdr4(ddr4_image(), switches=False))


def test_read_ddr5_eight_pages():
    image = bytes((i * 7) & 0xFF for i in range(1024))
    fake = FakeDdr5(image)
    assert spd.read_ddr5(fake) == image
    assert fake.writes[-1] == (0x50, b"\x0b\x00")


def test_decode_ddr4():
    out = spd.decode(ddr4_image())
    assert out["memory_type"] == "DDR4" and out["module_type"] == "UDIMM"
    assert out["manufacturer"].startswith("bank 1, 0xCE")
    assert out["part_number"] == "M378A1K43DB2-CTD"
    assert out["serial"] == "12345678"
    assert out["crc_ok"] == [True, True] and "warning" not in out


def test_decode_ddr5():
    out = spd.decode(ddr5_image(module=3))
    assert out["memory_type"] == "DDR5" and out["module_type"] == "SO-DIMM"
    assert out["part_number"] == "M323R2GA3BB0-CQK" and out["serial"] == "deadbeef"
    assert out["crc_ok"] == [True] and "warning" not in out


def test_decode_bad_crc_warns():
    image = bytearray(ddr4_image())
    image[200] ^= 0xFF
    out = spd.decode(bytes(image))
    assert out["crc_ok"] == [True, False] and "CRC" in out["warning"]


def test_decode_unknown():
    out = spd.decode(bytes([0, 0, 0x99, 0x09]) + bytes(60))
    assert out["memory_type"] == "unknown 0x99" and out["module_type"] == "type 0x09"


def test_ddr5_on_ddr4_module_never_writes():
    fake = FakeDdr4(ddr4_image())
    with pytest.raises(spd.SpdError, match="not a DDR5 SPD hub .*use ddr4-spd"):
        spd.read_ddr5(fake)
    assert not [w for w in fake.writes if w[1]], fake.writes
