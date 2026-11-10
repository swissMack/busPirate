"""The four bus modes over BPIO2, against the simulated board."""

import pytest

from buspirate.bp6 import BusPirate6
from buspirate.exceptions import ModeError, NackError, ProtocolError, UnsupportedFeatureError
from buspirate.simulator_bp6 import FakeBp6
from buspirate.spiflash import SPIFlash
from buspirate.uart import UART


@pytest.fixture
def fake():
    return FakeBp6()


@pytest.fixture
def bp(fake):
    with BusPirate6(FakeBp6.BINARY, terminal_port=FakeBp6.TERMINAL,
                    serial_factory=fake.factory(), reply_timeout=0.2) as device:
        yield device


# -- I2C ---------------------------------------------------------------------

def test_i2c_scan_and_register_read(bp, fake):
    with bp.i2c() as i2c:
        i2c.configure_peripherals(power=True, pullups=True)
        assert fake.mode == "I2C" and fake.psu_enabled and fake.pullups
        assert i2c.scan() == [0x27, 0x44, 0x50, 0x76]
        assert i2c.read_register(0x76, 0xD0) == b"\x58"


def test_a_nack_is_followed_by_a_stop_only_request(bp, fake):
    with bp.i2c() as i2c:
        before = len(fake.requests)
        with pytest.raises(NackError, match="0x20"):
            i2c.read_register(0x20, 0x00)
        assert fake.requests[before:] == ["data", "data"]  # the read, then the stop


def test_i2c_write_then_read_uses_the_address_byte(bp):
    with bp.i2c() as i2c:
        assert i2c.write_then_read(b"\xec\xd0", 1) == b"\x58"


def test_i2c_write_reaches_the_device(bp, fake):
    with bp.i2c() as i2c:
        i2c.write_register(0x76, 0xF4, b"\x27")
    assert fake.i2c_devices[0x76][0xF4] == 0x27


def test_aux_is_refused(bp):
    with bp.i2c() as i2c:
        with pytest.raises(UnsupportedFeatureError):
            i2c.configure_peripherals(aux=True)


# -- SPI ---------------------------------------------------------------------

def test_spi_flash_identifies_itself(bp):
    with bp.spi() as spi:
        spi.set_mode(0)
        assert SPIFlash(spi).jedec_id() == b"\xef\x40\x18"


def test_long_spi_reads_are_split_with_cs_held(bp, fake):
    fake.flash.memory[1000] = 0x42
    with bp.spi() as spi:
        data = spi.write_then_read(b"\x03\x00\x00\x00", 1200)
    assert len(data) == 1200
    assert data[1000] == 0x42


# -- UART --------------------------------------------------------------------

def test_uart_write_and_read_back(bp, fake):
    with bp.uart() as uart:
        uart.set_baudrate(UART.BAUD_115200)
        uart.configure()
        uart.write(b"hello")
        assert uart.read_available(64) == b"hello"


def test_odd_parity_and_nine_bits_are_refused(bp):
    with bp.uart() as uart:
        with pytest.raises(UnsupportedFeatureError):
            uart.configure(databits_parity=2)
        with pytest.raises(UnsupportedFeatureError):
            uart.configure(databits_parity=3)


def test_uart_receive_stream_reads_async_data(bp, fake):
    uart = bp.uart()
    uart.start_receive()
    fake.uart_receive(b"boot ok\r\n")
    got = b""
    for _ in range(20):
        got += bp.serial.read(256)
    assert got == b"boot ok\r\n"
    bp.stop_stream()
    assert bp.serial is fake.binary


# -- 1-Wire ------------------------------------------------------------------

def test_onewire_finds_the_one_device(bp, fake):
    with bp.onewire() as ow:
        assert ow.search_rom() == [fake.onewire_rom]


def test_onewire_with_nothing_on_the_bus(bp, fake):
    fake.onewire_rom = b""
    with bp.onewire() as ow:
        with pytest.raises(NackError, match="no 1-Wire device"):
            ow.reset()


def test_onewire_collision_points_to_the_terminal(bp, fake):
    fake.onewire_rom = bytes(8)[:7] + b"\x99"  # a bad CRC, as colliding ROMs give
    with bp.onewire() as ow:
        with pytest.raises(ProtocolError, match="scan"):
            ow.search_rom()


# -- the bus is released after a failure ---------------------------------------


def test_an_spi_error_raises_cs(bp, fake):
    with bp.spi() as spi:
        fake.data_faults = ["Protocol request failed"]
        with pytest.raises(ModeError):
            spi.write_then_read(b"\x9f", 3)
    assert fake.data_log[-1] == (False, b"", 0, True)  # a stop-only request: CS high


def test_an_spi_timeout_raises_cs_too(bp, fake):
    with bp.spi() as spi:
        fake.data_faults = [None]
        with pytest.raises(ProtocolError):
            spi.write_then_read(b"\x9f", 3)
    assert fake.data_log[-1] == (False, b"", 0, True)


def test_an_i2c_timeout_is_followed_by_a_stop(bp, fake):
    with bp.i2c() as i2c:
        fake.data_faults = [None]
        with pytest.raises(ProtocolError):
            i2c.read_register(0x76, 0xD0)
    assert fake.data_log[-1] == (False, b"", 0, True)


def test_a_failing_stop_does_not_hide_the_nack(bp, fake):
    with bp.i2c() as i2c:
        fake.data_faults = ["Protocol request failed", None]  # the NACK, then a silent STOP
        with pytest.raises(NackError):
            i2c.read_register(0x76, 0xD0)


# -- pins and LEDs -------------------------------------------------------------

def test_set_pins_then_read(bp, fake):
    bp.set_pins(0b100, 0b100, 0b100, 0b100)
    pins = bp.read_pins()
    assert pins["value"] & 0b100
    assert pins["direction"] & 0b100
    assert set(pins["mv"]) == {f"IO{n}" for n in range(8)}
    assert fake.pin_log == [(0b100, 0b100, 0b100, 0b100)]


def test_set_pins_changes_only_masked_bits(bp):
    bp.set_pins(0b11, 0b11, 0b11, 0b11)
    bp.set_pins(0b01, 0b00, 0b10, 0b00)
    pins = bp.read_pins()
    assert (pins["direction"], pins["value"]) == (0b10, 0b01)


def test_onboard_leds_and_resume(bp, fake):
    bp.set_onboard_leds([0xFF0000, 0x00FF00])
    bp.resume_onboard_leds()
    assert fake.led_log == [[0xFF0000, 0x00FF00], "resume"]


def test_onboard_leds_limit(bp):
    with pytest.raises(ValueError):
        bp.set_onboard_leds([0] * 19)


def test_ws2812_bytes(bp, fake):
    with bp.led() as led:
        led.write_pixels([0x112233])
    assert fake.pixel_log == [bytes([0x22, 0x11, 0x33])]
    assert fake.led_submode == 0


def test_apa102_frames(bp, fake):
    with bp.led() as led:
        led.configure("apa102")
        assert fake.led_submode == 1
        led.write_pixels([0x112233])
    assert fake.pixel_log == [bytes.fromhex("00 00 00 00 FF 33 22 11 FF")]


def test_led_rejects_an_unknown_strip(bp):
    with bp.led() as led:
        with pytest.raises(ValueError):
            led.configure("neopixel")


def test_spi_cs_idle_kept(bp, fake):
    with bp.spi() as spi:
        spi.set_cs_active_high(True)
        assert fake.spi_cs_idle is False
        spi.set_speed(2)
        assert fake.spi_cs_idle is False
        spi.set_mode(0)
        assert fake.spi_cs_idle is False
        spi.set_cs_active_high(False)
        assert fake.spi_cs_idle is True
