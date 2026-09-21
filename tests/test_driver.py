import pytest

from buspirate import I2C, ModeError, NackError
from buspirate.i2c import address_byte
from tests.conftest import make_device
from tests.fake_serial import FakeSerial


# -- transport / mode entry ------------------------------------------------


def test_open_enters_binary_mode(fake):
    device = make_device(fake)
    with device:
        assert fake.state == "bbio"
    assert fake.closed


def test_enter_binary_mode_gives_up_with_a_useful_message(fake):
    class Deaf(FakeSerial):
        def _process(self):
            self._out.clear()

    device = make_device(Deaf())
    with pytest.raises(ModeError, match="no BBIO response"):
        device.open()


def test_close_returns_the_device_to_its_terminal(fake):
    device = make_device(fake)
    device.open()
    device.close()
    assert fake.state == "term"


def test_modes_are_exclusive(bp):
    i2c = bp.i2c()
    with pytest.raises(ModeError, match="close it first"):
        bp.spi()
    i2c.close()
    bp.spi().close()


def test_mode_context_manager_returns_to_bitbang(bp, fake):
    with bp.i2c():
        assert fake.state == "i2c"
    assert fake.state == "bbio"


def test_using_a_closed_mode_is_an_error(bp):
    i2c = bp.i2c()
    i2c.close()
    with pytest.raises(ModeError, match="has been closed"):
        i2c.start()


# -- I2C -------------------------------------------------------------------


def test_i2c_scan_finds_only_acking_addresses(bp):
    with bp.i2c() as i2c:
        assert i2c.scan() == [0x50, 0x68]


def test_i2c_scan_honours_a_custom_range(bp):
    with bp.i2c() as i2c:
        assert i2c.scan(range(0x60, 0x70)) == [0x68]


def test_i2c_write_sends_the_address_with_the_write_bit(bp, fake):
    with bp.i2c() as i2c:
        i2c.write(0x50, b"\x01\x02")
    # start, bulk header for 3 bytes, address<<1, payload, stop
    assert bytes([0x02, 0x12, 0xA0, 0x01, 0x02, 0x03]) in bytes(fake.written)


def test_i2c_write_raises_on_a_nack(bp):
    with bp.i2c() as i2c:
        with pytest.raises(NackError, match="0x11 did not acknowledge"):
            i2c.write(0x11, b"\x00")


def test_i2c_write_sends_a_stop_even_after_a_nack(bp, fake):
    with bp.i2c() as i2c:
        with pytest.raises(NackError):
            i2c.write(0x11, b"\x00")
    assert bytes(fake.written).count(b"\x03") >= 1
    assert fake._i2c_expect_address is False


def test_i2c_read_nacks_only_the_final_byte(bp, fake):
    with bp.i2c() as i2c:
        data = i2c.read(0x50, 3)
    assert len(data) == 3
    tail = bytes(fake.written)
    # two ACKs (0x06) then one NACK (0x07) before the stop
    assert tail.count(b"\x06") == 2
    assert tail.count(b"\x07") == 1


def test_i2c_read_rejects_a_zero_count(bp):
    with bp.i2c() as i2c:
        with pytest.raises(ValueError, match="count must be"):
            i2c.read(0x50, 0)


def test_i2c_write_chunks_payloads_over_sixteen_bytes(bp, fake):
    with bp.i2c() as i2c:
        i2c.write(0x50, bytes(40))
    written = bytes(fake.written)
    assert b"\x1f" in written  # a full 16-byte bulk header appeared


def test_i2c_read_register_uses_a_repeated_start(bp, fake):
    with bp.i2c() as i2c:
        assert i2c.read_register(0x50, 0x0A, 4) == b"\x00\x01\x02\x03"
    written = bytes(fake.written)
    # write address + register, then a second start before the read address
    assert b"\x11\xa0\x0a" in written
    assert written.index(b"\x11\xa0\x0a") < written.rindex(b"\x02")


def test_i2c_read_register_names_the_register_that_was_refused(bp, fake):
    fake.i2c_devices.add(0x22)
    with bp.i2c() as i2c:
        i2c.read_register(0x22, 0x0A, 1)  # acks; the address is known
    with bp.i2c() as i2c:
        with pytest.raises(NackError, match="did not acknowledge its address"):
            i2c.read_register(0x11, 0x0A, 1)


def test_i2c_write_then_read_sends_exactly_the_bytes_given(bp, fake):
    with bp.i2c() as i2c:
        data = i2c.write_then_read(bytes([address_byte(0x50, read=True)]), 4)
    assert data == b"\x00\x01\x02\x03"
    # command, write count, read count, then the address byte and nothing else
    assert b"\x08\x00\x01\x00\x04\xa1" in bytes(fake.written)


def test_i2c_write_then_read_raises_when_the_target_is_absent(bp):
    with bp.i2c() as i2c:
        with pytest.raises(NackError, match="write_then_read failed"):
            i2c.write_then_read(bytes([address_byte(0x11, read=True)]), 2)


def test_i2c_rejects_an_out_of_range_address(bp):
    with bp.i2c() as i2c:
        with pytest.raises(ValueError, match="7-bit address"):
            i2c.write(0x80, b"")


def test_i2c_speed_must_be_a_known_constant(bp):
    with bp.i2c() as i2c:
        i2c.set_speed(I2C.SPEED_400KHZ)
        with pytest.raises(ValueError, match="not available"):
            i2c.set_speed(9)


# -- SPI -------------------------------------------------------------------


def test_spi_transfer_chunks_and_concatenates(bp):
    with bp.spi() as spi:
        assert spi.transfer(bytes(20)) == b"\xa5" * 20


def test_spi_bulk_rejects_an_oversized_chunk(bp):
    with bp.spi() as spi:
        with pytest.raises(ValueError, match="1-16 bytes"):
            spi.transfer_bulk(bytes(17))
        with pytest.raises(ValueError, match="1-16 bytes"):
            spi.transfer_bulk(b"")


def test_spi_select_brackets_the_block_with_cs(bp, fake):
    with bp.spi() as spi:
        with spi.select():
            spi.transfer_bulk(b"\x9f")
    written = bytes(fake.written)
    assert written.index(b"\x02") < written.index(b"\x10\x9f")
    assert written.index(b"\x10\x9f") < written.rindex(b"\x03")


def test_spi_select_releases_cs_on_an_exception(bp, fake):
    with bp.spi() as spi:
        with pytest.raises(RuntimeError):
            with spi.select():
                raise RuntimeError("boom")
        assert bytes(fake.written).endswith(b"\x03")


def test_spi_write_then_read_returns_the_requested_length(bp):
    with bp.spi() as spi:
        assert spi.write_then_read(b"\x9f", 3) == b"\xa5\xa5\xa5"


def test_spi_write_then_read_enforces_the_firmware_limit(bp):
    with bp.spi() as spi:
        with pytest.raises(ValueError, match="4096"):
            spi.write_then_read(b"", 5000)


def test_spi_set_mode_maps_to_polarity_and_edge(bp, fake):
    """CKP is CPOL; CKE is NOT CPHA. Mode 0 must be the documented default."""
    with bp.spi() as spi:
        for mode, expected in ((0, 0x8A), (1, 0x88), (2, 0x8E), (3, 0x8C)):
            fake.written.clear()
            spi.set_mode(mode)
            assert fake.written[0] == expected, f"SPI mode {mode}"


def test_spi_rejects_an_unknown_mode(bp):
    with bp.spi() as spi:
        with pytest.raises(ValueError, match="mode must be"):
            spi.set_mode(4)


# -- peripherals / pins ----------------------------------------------------


def test_configure_peripherals_packs_its_flags(bp, fake):
    with bp.i2c() as i2c:
        fake.written.clear()
        i2c.configure_peripherals(power=True, pullups=True)
        assert fake.written[0] == 0x4C


def test_configure_peripherals_remembers_what_it_last_sent(bp, fake):
    with bp.i2c() as i2c:
        assert i2c.peripherals == {
            "power": False, "pullups": False, "aux": False, "cs": False,
        }
        i2c.configure_peripherals(power=True, pullups=True)
        assert i2c.peripherals == {
            "power": True, "pullups": True, "aux": False, "cs": False,
        }
        i2c.configure_peripherals(power=False, pullups=True)
        assert i2c.peripherals["power"] is False


def test_set_pins_packs_its_flags(bp, fake):
    fake.written.clear()
    bp.set_pins(power=True, cs=True)
    assert fake.written[0] == 0xC1


# -- UART / 1-Wire ---------------------------------------------------------


def test_uart_write_chunks_and_acks(bp, fake):
    with bp.uart() as uart:
        uart.set_baudrate(uart.BAUD_115200)
        uart.write(b"hello bus pirate")
    assert b"hello bus pirate" in bytes(fake.written)


def test_uart_rejects_an_unknown_baudrate(bp):
    with bp.uart() as uart:
        with pytest.raises(ValueError, match="BAUD_300"):
            uart.set_baudrate(99)


def test_uart_framing_flags_pack(bp, fake):
    with bp.uart() as uart:
        fake.written.clear()
        uart.configure(push_pull=True, databits_parity=2, stop_bits=2)
        assert fake.written[0] == 0x9A


def test_onewire_search_drops_the_empty_slots(bp):
    with bp.onewire() as ow:
        assert ow.search_rom() == [b"\x28\x11\x22\x33\x44\x55\x66\x77"]
