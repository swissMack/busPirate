"""The SPI flash layer, against a simulated 25-series chip."""

import pytest

from buspirate import BusPirate
from buspirate.spiflash import PAGE_SIZE, SECTOR_SIZE, FlashError, SPIFlash
from tests.conftest import make_device
from tests.fake_serial import FakeFlash, FakeSerial


@pytest.fixture
def chip():
    fake = FakeSerial()
    fake.flash = FakeFlash()
    device = make_device(fake)
    device.open()
    spi = device.spi()
    try:
        yield SPIFlash(spi), fake.flash
    finally:
        spi.close()
        device.close()


# -- identity --------------------------------------------------------------


def test_reads_the_jedec_id(chip):
    flash, _ = chip
    assert flash.jedec_id() == b"\xef\x40\x18"


def test_decodes_the_capacity(chip):
    flash, _ = chip
    assert flash.capacity() == 16 * 1024 * 1024


def test_an_unencoded_capacity_is_none(chip):
    flash, fake = chip
    fake.JEDEC = b"\xef\x40\x00"
    assert flash.capacity() is None


# -- reading ---------------------------------------------------------------


def test_an_erased_chip_reads_as_ones(chip):
    flash, _ = chip
    assert flash.read(0, 16) == b"\xff" * 16


def test_reads_longer_than_the_firmware_buffer_are_chunked(chip):
    flash, fake = chip
    fake.memory[0:5000] = bytes((i % 256) for i in range(5000))
    data = flash.read(0, 5000)
    assert len(data) == 5000
    assert data[4999] == 4999 % 256


# -- erasing ---------------------------------------------------------------


def test_erasing_a_sector_clears_the_whole_sector(chip):
    flash, fake = chip
    fake.memory[0:SECTOR_SIZE] = b"\x00" * SECTOR_SIZE
    flash.erase_sector(0x0800)  # an address inside the first sector
    assert bytes(fake.memory[0:SECTOR_SIZE]) == b"\xff" * SECTOR_SIZE
    assert fake.erases == 1


def test_erasing_a_range_covers_every_sector_it_touches(chip):
    flash, fake = chip
    fake.memory[0 : 3 * SECTOR_SIZE] = b"\x00" * (3 * SECTOR_SIZE)
    sectors = flash.erase_range(SECTOR_SIZE - 10, 20 + SECTOR_SIZE)
    assert sectors == 3  # it straddles three sectors
    assert bytes(fake.memory[0 : 3 * SECTOR_SIZE]) == b"\xff" * (3 * SECTOR_SIZE)


def test_erasing_the_chip_clears_everything(chip):
    flash, fake = chip
    fake.memory[:] = b"\x00" * fake.size
    flash.erase_chip()
    assert set(fake.memory) == {0xFF}


# -- programming -----------------------------------------------------------


def test_write_and_read_back(chip):
    flash, _ = chip
    payload = bytes(range(256)) * 3
    flash.erase_write_verify(0x1000, payload)
    assert flash.read(0x1000, len(payload)) == payload


def test_writes_are_split_on_page_boundaries(chip):
    flash, fake = chip
    flash.erase_range(0, 600)
    flash.write(0x80, b"\xa5" * 400)  # starts mid-page, spans three pages
    assert fake.programs == 3
    assert flash.read(0x80, 400) == b"\xa5" * 400


def test_a_single_page_program_may_not_cross_a_page(chip):
    flash, _ = chip
    with pytest.raises(ValueError, match="cross a page boundary"):
        flash.program_page(PAGE_SIZE - 4, b"\x00" * 8)


def test_programming_without_erasing_can_only_clear_bits(chip):
    """The physics of NOR flash, and the commonest surprise."""
    flash, _ = chip
    flash.erase_sector(0)
    flash.write(0, b"\xf0")
    flash.write(0, b"\x0f")  # no erase in between
    assert flash.read(0, 1) == b"\x00"  # 0xF0 AND 0x0F, not 0x0F


def test_verify_finds_the_first_bad_byte(chip):
    flash, fake = chip
    flash.erase_write_verify(0, b"\xaa" * 32)
    fake.memory[10] = 0x00
    assert flash.verify(0, b"\xaa" * 32) == 10


def test_verify_returns_none_when_it_matches(chip):
    flash, _ = chip
    flash.erase_write_verify(0, b"\x5a" * 64)
    assert flash.verify(0, b"\x5a" * 64) is None


def test_a_write_protected_chip_is_reported_not_silently_ignored(chip):
    flash, fake = chip
    fake.write_enabled = False
    original = fake.exchange

    def refuse(written, read_count):
        if written and written[0] == 0x06:
            return b""  # accept the command but never set the latch
        return original(written, read_count)

    fake.exchange = refuse
    with pytest.raises(FlashError, match="WP pin"):
        flash.write_enable()


def test_erase_write_verify_reports_a_bad_verify(chip):
    flash, fake = chip
    original = fake.exchange

    def corrupt(written, read_count):
        result = original(written, read_count)
        if written and written[0] == 0x03 and result:
            return bytes([result[0] ^ 0xFF]) + result[1:]
        return result

    fake.exchange = corrupt
    with pytest.raises(FlashError, match="verification failed"):
        flash.erase_write_verify(0, b"\x11" * 8)


def test_addresses_beyond_24_bits_are_refused(chip):
    flash, _ = chip
    with pytest.raises(ValueError, match="24-bit"):
        flash.read(0x1000000, 1)
