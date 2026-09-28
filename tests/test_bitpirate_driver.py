"""The ESP32 Bit Pirate driver, against the simulated firmware."""

import pytest

from buspirate.bitpirate import BitPirate
from buspirate.exceptions import (
    ModeError,
    NackError,
    UnsupportedFeatureError,
)
from buspirate.simulator import fake_factory
from buspirate.simulator_bitpirate import FakeBitPirateSerial
from buspirate.spiflash import SPIFlash
from buspirate.uart import UART


def make(fake, **kwargs):
    kwargs.setdefault("reply_timeout", 0.3)
    kwargs.setdefault("connect_timeout", 0.3)
    return BitPirate("/dev/fake-bitpirate", serial_factory=fake_factory(fake), **kwargs)


@pytest.fixture
def fake():
    return FakeBitPirateSerial()


@pytest.fixture
def bp(fake):
    with make(fake) as device:
        yield device


# -- connecting ----------------------------------------------------------


def test_a_board_at_its_prompt_connects_with_one_enter(fake):
    device = make(fake).open()
    assert fake.written == b"\r"
    assert device.profile.variant == "bitpirate"
    assert device.profile.firmware is None  # no banner mid-session


def test_a_freshly_booted_board_is_started_and_its_version_read():
    fake = FakeBitPirateSerial(booting=True)
    device = make(fake).open()
    assert device.profile.firmware == "1.7"
    assert device.profile.describe() == "ESP32 Bit Pirate, firmware 1.7"


def test_connecting_never_sends_the_bus_pirate_knock(fake):
    make(fake).open()
    assert b"\x00" not in fake.written
    assert b"\x0f" not in fake.written


def test_closing_releases_every_pin(fake):
    device = make(fake).open()
    device.i2c()
    device.close()
    assert fake.commands[-1] == "m hiz"
    assert fake.mode == "HIZ"
    assert fake.closed


# -- I2C -----------------------------------------------------------------


def test_the_first_i2c_entry_answers_the_config_questions_with_defaults(bp, fake):
    bp.i2c()
    assert fake.mode == "I2C"
    assert fake.settings["I2C"]["SDA GPIO"] == "6"


def test_scan_lists_what_answers(bp, fake):
    assert bp.i2c().scan() == [0x50, 0x68]


def test_scan_leaves_out_the_reserved_addresses(bp, fake):
    fake.i2c_devices[0x03] = bytearray(256)
    assert 0x03 not in bp.i2c().scan()


def test_a_register_read_is_one_instruction_with_a_7_bit_address(bp, fake):
    data = bp.i2c().read_register(0x68, 0x10, 4)
    assert data == bytes([0x10, 0x11, 0x12, 0x13])
    assert fake.commands[-1] == "[0x68 0x10 r:4]"


def test_long_reads_are_re_pointed_in_128_byte_pieces(bp, fake):
    data = bp.i2c().read_register(0x68, 0x00, 200)
    assert data == bytes(range(200))
    assert fake.commands[-2:] == ["[0x68 0x00 r:128]", "[0x68 0x80 r:72]"]


def test_an_eeprom_read_with_a_two_byte_pointer(bp, fake):
    fake.i2c_pointer_width[0x50] = 2
    fake.i2c_devices[0x50][0x10:0x14] = b"\xde\xad\xbe\xef"
    assert bp.i2c().read_after_write(0x50, b"\x00\x10", 4) == b"\xde\xad\xbe\xef"
    assert fake.commands[-1] == "[0x50 0x00 0x10 r:4]"


def test_a_read_from_nobody_is_a_nack(bp):
    with pytest.raises(NackError, match="0x33 did not answer"):
        bp.i2c().read(0x33, 1)


def test_a_write_checks_the_address_first(bp, fake):
    i2c = bp.i2c()
    i2c.write(0x50, b"\x00\x2a")
    assert fake.commands[-2:] == ["ping 0x50", "[0x50 0x00 0x2A]"]
    assert fake.i2c_devices[0x50][0] == 0x2A
    with pytest.raises(NackError, match="0x33 did not acknowledge"):
        i2c.write(0x33, b"\x00")


def test_speed_goes_through_config_once(bp, fake):
    i2c = bp.i2c()
    i2c.set_speed(3)
    i2c.set_speed(3)
    assert fake.settings["I2C"]["Frequency"] == "400000"
    assert fake.commands.count("config") == 1


def test_pullups_are_the_internal_ones(bp, fake):
    i2c = bp.i2c()
    i2c.configure_peripherals(power=True, pullups=True)
    assert fake.pullups
    assert i2c.peripherals["power"] is False  # nothing to switch on this board


# -- SPI -----------------------------------------------------------------


def test_the_jedec_id_is_one_instruction(bp, fake):
    assert bp.spi().write_then_read(b"\x9f", 3) == bytes([0xEF, 0x40, 0x18])
    assert fake.commands[-1] == "[0x9F r:3]"


def test_a_flash_dump_reads_through_the_bus_pirate_flash_helper(bp, fake):
    fake.flash.memory[:1024] = bytes(i & 0xFF for i in range(1024))
    data = SPIFlash(bp.spi()).read(0, 1024)
    assert data == bytes(i & 0xFF for i in range(1024))
    assert fake.commands[-1] == "[0x03 0x00 0x00 0x00 r:255 r:255 r:255 r:255 r:4]"


def test_spi_clocks_the_firmware_cannot_do_say_so(bp):
    spi = bp.spi()
    spi.set_speed(3)  # 1 MHz
    with pytest.raises(UnsupportedFeatureError, match="whole MHz"):
        spi.set_speed(0)  # 30 kHz
    with pytest.raises(UnsupportedFeatureError, match="mode 0"):
        spi.set_mode(1)


# -- UART ----------------------------------------------------------------


def test_uart_line_settings_go_through_config(bp, fake):
    uart = bp.uart()
    uart.set_baudrate(UART.BAUD_115200)
    uart.configure(databits_parity=1, stop_bits=2)
    settings = fake.settings["UART"]
    assert settings["Baud rate"] == "115200"
    assert settings["Parity (N/E/O)"] == "E"
    assert settings["Stop bits (1 or 2)"] == "2"


def test_nine_bit_framing_is_refused(bp):
    with pytest.raises(UnsupportedFeatureError, match="9-bit"):
        bp.uart().configure(databits_parity=3)


def test_uart_writes_are_raw_bytes(bp, fake):
    bp.uart().write(b"AT\r\n")
    assert fake.uart_tx == b"AT\r\n"


def test_watching_the_line_hands_over_the_port_and_enter_takes_it_back(fake):
    fake.uart_rx = b"boot ok\r\n"
    device = make(fake).open()
    device.uart().start_receive()
    assert device.streaming
    assert device.serial.read(256) == b"boot ok\r\n"  # nothing swallowed
    device.stop_stream()
    assert not device.streaming
    assert fake.mode == "UART"
    assert device.cli.mode == "UART"


# -- errors --------------------------------------------------------------


def test_a_mode_it_does_not_have_is_a_mode_error(bp):
    with pytest.raises(ModeError, match="Unknown mode"):
        bp.cli.enter_mode("warp")


def test_a_board_that_never_prompts_fails_to_connect_with_advice():
    class Silent:
        def write(self, data):
            return len(data)

        def read(self, count=1):
            return b""

        def reset_input_buffer(self):
            pass

        def close(self):
            pass

    with pytest.raises(ModeError, match="port marked USB"):
        make(Silent(), connect_timeout=0.05).open()


# -- the simulator's own terminal, as typed into the Terminal panel --------


def type_line(fake, line):
    fake.write(line.encode() + b"\r")
    from buspirate.bitpirate.cli import screen_lines

    return screen_lines(fake.read(100000).decode())


def test_mode_on_its_own_offers_the_numbered_menu(fake):
    screen = type_line(fake, "mode")
    assert "Select mode:" in screen
    assert "  2. HIZ" in screen  # "None" is first, as in the firmware
    assert screen[-1] == "Mode Number > "
    number = str(screen.index("  6. I2C") - screen.index("  1. None") + 1)
    screen = type_line(fake, number)
    assert "Mode changed to I2C" in screen
    assert screen[-1] == "SDA GPIO [6]: "  # first entry asks its questions


def test_a_mode_number_out_of_range_is_refused(fake):
    type_line(fake, "m")
    screen = type_line(fake, "99")
    assert "Invalid mode number." in screen
    assert screen[-1] == "HIZ> "


def test_help_lists_the_commands(fake):
    screen = type_line(fake, "help")
    assert "General commands:" in screen
    assert screen[-1] == "HIZ> "
