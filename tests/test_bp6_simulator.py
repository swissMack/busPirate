"""The simulated Bus Pirate 6 answers BPIO2 the way the real board did."""

from buspirate.bp6 import protocol
from buspirate.bp6.link import BpioLink
from buspirate.simulator_bp6 import FakeBp6


def link_to(fake):
    return BpioLink(fake.binary, lambda *a: None, timeout=0.2)


def test_status_matches_the_real_board():
    status = link_to(FakeBp6()).request(protocol.status_request()).status
    assert status.hardware == (6, 2)
    assert status.firmware_date == "Oct 12 2026 09:05:15"
    assert status.firmware_hash == "unknown"
    assert "I2C" in status.modes_available and status.mode == "HiZ"
    assert len(status.adc_mv) == 8
    assert status.max_read == 512


def test_power_and_trip():
    fake = FakeBp6(load_ma=50)
    link = link_to(fake)
    link.request(protocol.configuration_request(psu_enable=True, psu_mv=3300, psu_ma=300))
    status = link.request(protocol.status_request()).status
    assert status.psu_enabled and status.psu_mv == 3300 and status.psu_ma == 50
    link.request(protocol.configuration_request(psu_enable=True, psu_mv=3300, psu_ma=20))
    status = link.request(protocol.status_request()).status
    assert status.psu_tripped and not status.psu_enabled


def test_i2c_register_read():
    fake = FakeBp6()
    link = link_to(fake)
    link.request(protocol.configuration_request(mode="I2C"))
    reply = link.request(protocol.data_request(start=True, write=b"\xec\xd0", read=1, stop=True))
    assert reply.data == b"\x58"
    missing = link.request(protocol.data_request(start=True, write=b"\x20", stop=True))
    assert missing.error == "Protocol request failed"


def test_spi_jedec_id():
    link = link_to(FakeBp6())
    link.request(protocol.configuration_request(mode="SPI"))
    reply = link.request(protocol.data_request(start=True, write=b"\x9f", read=3, stop=True))
    assert reply.data == b"\xef\x40\x18"


def test_spi_write_only_commands_reach_the_flash():
    fake = FakeBp6()
    link = link_to(fake)
    link.request(protocol.configuration_request(mode="SPI"))
    link.request(protocol.data_request(start=True, write=b"\x06", stop=True))
    assert fake.flash.write_enabled


def test_uart_echo_is_async():
    fake = FakeBp6()
    link = link_to(fake)
    link.request(protocol.configuration_request(mode="UART"))
    link.request(protocol.data_request(write=b"hi"))
    assert link.poll_async(0.05) == b"hi"


def test_nothing_answers_while_bpio2_is_off():
    fake = FakeBp6(bpio_active=False)
    fake.binary.write(b"\x02\x11\x00")
    assert fake.binary.read(64) == b""


def test_the_terminal_switches_bpio2_on():
    fake = FakeBp6(bpio_active=False, color_prompt=True)
    for keys in (b"\x03", b"n\r", b"binmode\r", b"2\r", b"n\r"):
        fake.terminal.write(keys)
    assert fake.bpio_active
    assert fake.terminal.read(4096).endswith(b"HiZ> ")
