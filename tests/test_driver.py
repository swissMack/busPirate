import pytest

from buspirate import I2C, ModeError, NackError
from buspirate.exceptions import ProtocolError
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


def test_onewire_search_reads_up_to_the_end_marker(bp):
    with bp.onewire() as ow:
        assert ow.search_rom() == [b"\x28\x11\x22\x33\x44\x55\x66\x77"]


def test_onewire_search_on_an_empty_bus_is_an_empty_list(bp, fake):
    # The exact reply a real v4 on firmware 7.0 gave with nothing found:
    # 01 ff ff ff ff ff ff ff ff. The old driver waited for 256 bytes.
    fake.onewire_roms = []
    with bp.onewire() as ow:
        assert ow.search_rom() == []


def test_onewire_search_returns_every_device(bp, fake):
    roms = [bytes([0x28, i, 0, 0, 0, 0, 0, i]) for i in range(1, 4)]
    fake.onewire_roms = roms + [b"\x00" * 8]
    with bp.onewire() as ow:
        assert ow.search_rom() == roms


# -- terminal ----------------------------------------------------------


def test_reset_hardware_returns_the_fake_to_its_terminal(bp, fake):
    with bp.i2c():
        pass
    bp.reset_hardware()
    bp.write(b"i\n")
    assert "Bus Pirate" in bp.read_text(settle=0.05)


def test_the_terminal_answers_the_help_command(bp, fake):
    bp.reset_hardware()
    bp.write(b"?\n")
    reply = bp.read_text(settle=0.05)
    # The bare "HiZ>" fallback never spans more than one line; the help
    # listing does, which is what actually distinguishes it.
    assert reply.count("\r\n") >= 2


def test_the_terminal_answers_the_voltage_command(bp, fake):
    bp.reset_hardware()
    bp.write(b"v\n")
    reply = bp.read_text(settle=0.05)
    # Specific to the voltage table: neither the fallback nor the help
    # listing mentions the ADC.
    assert "ADC" in reply
    assert "General commands" not in reply


def test_binary_mode_can_be_re_entered_after_the_terminal(bp, fake):
    bp.reset_hardware()
    bp.write(b"i\n")
    bp.read_text(settle=0.05)
    bp.enter_binary_mode()
    assert bp.bitbang_version >= 1


def test_hardware_reset_clears_aux_and_pin_state_on_both_boards(bp, fake):
    # Reach into the fake directly: the fake IS the thing under test here.
    # Both boards reset on 0x0F. The v4 was once modelled as surviving it;
    # a real v4 (firmware 6.0-a3) switched its supplies off and dropped off
    # USB instead.
    fake.pins = 0xFF
    fake._aux_pin = "cs"
    fake._aux_levels = {"aux": 1, "cs": 1}

    bp.reset_hardware()
    bp.enter_binary_mode()

    assert fake.pins == 0x00
    assert fake._aux_pin == "aux"
    assert fake._aux_levels == {"aux": 0, "cs": 0}


# -- a board that re-enumerates when reset ----------------------------------


def _counting_factory(opened):
    def factory(port, baudrate, timeout):
        fake = FakeSerial(variant="v4")
        opened.append(fake)
        return fake

    return factory


def test_a_board_that_drops_off_usb_after_reset_is_reopened(monkeypatch):
    """A real v4 (firmware 6.0-a3) resets on 0x0F and re-enumerates on USB:
    measured, its device node vanished 188 ms after the command and came back
    at 463 ms. The old handle is dead from then on, so the dashboard's
    terminal lost the board outright. Waiting for the node to return and
    reopening it keeps the session.
    """
    from buspirate import base
    from buspirate.base import BusPirate

    opened = []
    bp = BusPirate("/dev/cu.usbmodem-test", serial_factory=_counting_factory(opened))
    bp.open(identify=False)
    # The node is there, vanishes, stays gone a moment, then returns.
    presence = iter([True, False, False, True])
    monkeypatch.setattr(base.os.path, "exists", lambda path: next(presence, True))
    bp.reset_hardware()
    assert bp.reopen_if_reenumerated(watch=1.0, timeout=1.0, poll=0) is True
    assert len(opened) == 2
    assert bp.serial is opened[1]


def test_a_board_that_stays_on_usb_keeps_its_handle(monkeypatch):
    # A v3's FTDI chip stays enumerated through the board's reset.
    from buspirate import base
    from buspirate.base import BusPirate

    opened = []
    bp = BusPirate("/dev/cu.usbserial-test", serial_factory=_counting_factory(opened))
    bp.open(identify=False)
    monkeypatch.setattr(base.os.path, "exists", lambda path: True)
    bp.reset_hardware()
    assert bp.reopen_if_reenumerated(watch=0.05, timeout=1.0, poll=0.01) is False
    assert len(opened) == 1
    assert bp.serial is opened[0]


def test_a_board_that_never_comes_back_is_reported_in_a_sentence(monkeypatch):
    from buspirate import base
    from buspirate.base import BusPirate
    from buspirate.exceptions import BusPirateError

    opened = []
    bp = BusPirate("/dev/cu.usbmodem-test", serial_factory=_counting_factory(opened))
    bp.open(identify=False)
    # There at first, then gone for good.
    presence = iter([True])
    monkeypatch.setattr(base.os.path, "exists", lambda path: next(presence, False))
    bp.reset_hardware()
    with pytest.raises(BusPirateError) as caught:
        bp.reopen_if_reenumerated(watch=1.0, timeout=0.05, poll=0.01)
    assert "/dev/cu.usbmodem-test" in str(caught.value)
    assert bp.serial is None


def test_a_port_that_is_not_a_device_node_is_left_alone():
    # The simulator's ports are names, not files: nothing can vanish.
    from buspirate.base import BusPirate

    opened = []
    bp = BusPirate("simulated-v4", serial_factory=_counting_factory(opened))
    bp.open(identify=False)
    bp.reset_hardware()
    assert bp.reopen_if_reenumerated(watch=1.0, timeout=1.0, poll=0) is False
    assert bp.serial is opened[0]


def test_a_board_left_at_a_menu_question_still_connects():
    """Found on a real v4: disconnected half way through choosing SPI in the
    board's own terminal, it sat at a menu question and answered every 0x00
    with BEL (0x07). Connecting gave up after 25 attempts with a message
    about baud rates. Enter accepts a question's default, so answer each one
    until the board is back at a prompt.
    """
    from buspirate.base import BusPirate
    from buspirate.simulator import fake_factory

    fake = FakeSerial(variant="v4")
    fake.leave_at_menu(questions=3)
    bp = BusPirate("/dev/cu.test", serial_factory=fake_factory(fake), identify_timeout=0.05)
    bp.open()
    assert bp.bitbang_version >= 1
    assert bp.profile.variant == "v4"


def test_binary_mode_is_knocked_for_in_one_burst():
    """The firmware answers BBIO1 only after the 20th 0x00. Sending them one
    at a time and waiting for a reply after each cost a full read timeout
    per byte: on a real v3, leaving the terminal took 4.3 s every time, and
    `buspirate ping` paid the same. One burst of 20 gets there at once.
    """
    from buspirate.base import BusPirate
    from buspirate.simulator import fake_factory

    fake = FakeSerial(variant="v3")
    writes = []
    real_write = fake.write

    def counting_write(data):
        writes.append(bytes(data))
        return real_write(data)

    fake.write = counting_write
    bp = BusPirate("/dev/cu.test", serial_factory=fake_factory(fake))
    bp.open(identify=False)
    knocks = [w for w in writes if set(w) == {0}]
    assert knocks == [b"\x00" * 20], [len(k) for k in knocks]
    assert bp.bitbang_version >= 1


def test_leaving_the_terminal_from_a_menu_question_still_reaches_binary_mode():
    # Stopping the dashboard's terminal while the board sits at a question
    # goes straight to enter_binary_mode(), with no identify() to clear it.
    from buspirate.base import BusPirate
    from buspirate.simulator import fake_factory

    fake = FakeSerial(variant="v4")
    bp = BusPirate("/dev/cu.test", serial_factory=fake_factory(fake))
    bp.open(identify=False)
    bp.reset_hardware()
    fake.leave_at_menu(questions=3)
    bp.enter_binary_mode()
    assert bp.bitbang_version >= 1


@pytest.mark.parametrize("variant", ["v3", "v4"])
def test_a_board_left_in_binary_mode_is_still_identified(variant):
    """Found on a real v4: a program that let go of the board without
    resetting it left it in binary mode, where `i` is not a command, and the
    next connect called it an "unidentified Bus Pirate". Reset it to the
    terminal and ask again.
    """
    from buspirate.base import BusPirate
    from buspirate.simulator import fake_factory

    fake = FakeSerial(variant=variant)
    fake.state = "bbio"
    bp = BusPirate("/dev/cu.test", serial_factory=fake_factory(fake), identify_timeout=0.05)
    bp.open()
    assert bp.profile.variant == variant
    assert bp.bitbang_version >= 1


def _stand_in_pyserial(monkeypatch, opened):
    import sys
    import types

    from buspirate import base

    def Serial(port, baudrate, timeout):
        # Like pyserial: a device node that is not there cannot be opened.
        if not base.os.path.exists(port):
            raise OSError(2, f"could not open port {port}: No such file or directory")
        fake = FakeSerial(variant="v4")
        opened.append(port)
        return fake

    monkeypatch.setitem(sys.modules, "serial", types.SimpleNamespace(Serial=Serial))


def test_connecting_while_the_port_is_coming_back_waits_for_it(monkeypatch):
    """Found on a real v4: Disconnect resets it and it leaves USB for about
    half a second. Connecting inside that window failed, blaming "something
    else holding" a port that simply was not there yet."""
    from buspirate import base
    from buspirate.base import BusPirate

    opened = []
    _stand_in_pyserial(monkeypatch, opened)
    presence = iter([False, False, True])
    monkeypatch.setattr(base.os.path, "exists", lambda path: next(presence, True))
    bp = BusPirate("/dev/cu.usbmodem-test")
    bp.open(identify=False)
    assert opened == ["/dev/cu.usbmodem-test"]


def test_a_port_that_never_appears_is_called_missing_not_busy(monkeypatch):
    from buspirate import base
    from buspirate.base import BusPirate
    from buspirate.exceptions import BusPirateError

    _stand_in_pyserial(monkeypatch, [])
    monkeypatch.setattr(base, "PORT_RETURN_SECONDS", 0.05)
    monkeypatch.setattr(base.os.path, "exists", lambda path: False)
    with pytest.raises(BusPirateError) as caught:
        BusPirate("/dev/cu.usbmodem-test").open(identify=False)
    message = str(caught.value)
    assert "not there" in message and "holding" not in message


def test_the_i2c_scan_command_warns_when_every_address_answers(monkeypatch, capsys):
    # The same stuck bus, from the command line: `buspirate i2c-scan` on the
    # real v3 printed "112 device(s)" and nothing else.
    import argparse

    from buspirate import cli
    from buspirate.base import BusPirate
    from buspirate.simulator import fake_factory

    fake = FakeSerial(variant="v3", i2c_devices=range(0x08, 0x78))
    monkeypatch.setattr(cli, "resolve", lambda port: "/dev/cu.test")
    monkeypatch.setattr(
        cli, "BusPirate",
        lambda port: BusPirate(port, serial_factory=fake_factory(fake), identify_timeout=0.05),
    )
    args = argparse.Namespace(port="auto", no_power=False, no_pullups=False, speed=2)
    assert cli.cmd_i2c_scan(args) == 1
    out = capsys.readouterr().out
    assert "VPU" in out and "device(s)" not in out


def test_read_after_write_is_a_pointer_write_then_a_repeated_start_read(bp, fake):
    """The EEPROM read the I2C panel used to spell out byte by byte."""
    from buspirate.exceptions import NackError

    i2c = bp.i2c()
    fake.written.clear()
    assert i2c.read_after_write(0x50, b"\x00\x10", 3) == b"\x00\x01\x02"
    # start, 3-byte bulk write (address+W, pointer), start, 1-byte bulk write
    # (address+R), read ACK read ACK read NACK, stop.
    assert bytes(fake.written) == bytes(
        [0x02, 0x12, 0xA0, 0x00, 0x10, 0x02, 0x10, 0xA1,
         0x04, 0x06, 0x04, 0x06, 0x04, 0x07, 0x03]
    )
    with pytest.raises(NackError, match="0x33"):
        i2c.read_after_write(0x33, b"\x00", 1)


def test_a_failed_exit_still_lets_the_mode_be_entered_again(bp, fake, monkeypatch):
    # On real hardware the reply to "leave this mode" can go missing. The
    # mode then counted as closed while the device still pointed at it, so
    # the dashboard failed with "already in OneWire; close it first" until
    # it reconnected.
    ow = bp.onewire()
    real_read = bp.read

    def lost_reply(count):
        raise ProtocolError(f"expected {count} byte(s), got 0: b''")

    monkeypatch.setattr(bp, "read", lost_reply)
    with pytest.raises(ProtocolError):
        ow.close()
    monkeypatch.setattr(bp, "read", real_read)
    ow.close()  # a second close, as the dashboard does, is a no-op
    # No resync here: in the dashboard that recovery can fail too, and the
    # device must not be left pointing at a mode that says it is closed.
    assert bp._mode is None


def test_uart_stray_received_bytes_are_not_taken_for_replies(bp, fake):
    # On a v4, listening on a floating line forwarded noise (0x18) that sat
    # in front of every reply: "UART bulk write: got 0x18, want 0x01".
    from buspirate.uart import UART

    with bp.uart() as uart:
        uart.configure()
        uart.start_receive()
        fake.uart_rx += b"\x18\x18\x18"
        uart.write(b"Hi\r\n")
        fake.uart_rx += b"\x18"
        uart.set_baudrate(UART.BAUD_115200)
        fake.uart_rx += b"\x18\x18"
        uart.stop_receive()
        # Nothing was lost: the stray bytes are there to be read, in order.
        assert uart.read_available(4096) == b"\x18" * 6


def test_listening_sets_the_line_up_first(bp, fake):
    from buspirate.web.panels import uart as panel

    with bp.uart() as uart:
        class Ctx:
            mode = uart

        fake.written.clear()
        result = panel._listen(Ctx(), True)
        assert "was not set up" in result["text"]
        # 115200 baud and a driven pin, before echo is switched on.
        assert list(fake.written) == [0x6A, 0x90, 0x02]

        fake.written.clear()
        panel._listen(Ctx(), False)
        result = panel._listen(Ctx(), True)
        assert "was not set up" not in result["text"]
        assert list(fake.written) == [0x03, 0x02]


def test_sending_sets_the_line_up_first(bp, fake):
    # After Watch the line stops, UART mode is entered afresh; a send then
    # went out at 300 baud from a pin that was not driving, yet every byte
    # was acknowledged.
    from buspirate.web.panels import uart as panel

    with bp.uart() as uart:
        class Ctx:
            mode = uart

        fake.written.clear()
        result = panel._send_text(Ctx(), "Hi", True)
        assert "was not set up" in result["text"]
        assert list(fake.written[:2]) == [0x6A, 0x90]
        fake.written.clear()
        assert "was not set up" not in panel._send_bytes(Ctx(), b"\x41")["text"]
