"""The Bus Pirate 6 driver against the simulated board."""

import pytest

from buspirate.bp6 import BusPirate6
from buspirate.exceptions import ModeError, ProtocolError
from buspirate.simulator_bp6 import FakeBp6


def make(fake, **kw):
    kw.setdefault("reply_timeout", 0.2)
    kw.setdefault("connect_timeout", 0.1)
    kw.setdefault("bpio2_settle", 0.25)
    kw.setdefault("first_reply_timeout", 0.4)
    kw.setdefault("drain_seconds", 0.1)
    return BusPirate6(FakeBp6.BINARY, terminal_port=FakeBp6.TERMINAL,
                      serial_factory=fake.factory(), **kw)


def test_connect_reads_the_status():
    fake = FakeBp6()
    bp = make(fake).open()
    assert bp.profile.describe() == "Bus Pirate 6, firmware 2026-10-12"
    assert bp.last_status.mode == "HiZ"
    # BPIO2 was already on: the terminal was asked, and nothing was changed.
    assert b"i\r" in fake.terminal.written and b"binmode" not in fake.terminal.written


def test_connect_switches_bpio2_on_through_the_terminal_when_it_is_off():
    fake = FakeBp6(bpio_active=False, color_prompt=True)
    bp = make(fake).open()
    assert fake.bpio_active
    assert b"n\r" in fake.terminal.written and b"binmode\r" in fake.terminal.written
    assert bp.profile.variant == "bp6"
    assert not fake.terminal.is_open  # handed back after use


def test_connect_fails_clearly_without_a_terminal_port():
    fake = FakeBp6(bpio_active=False)
    with pytest.raises(ModeError, match="BPIO2"):
        BusPirate6(FakeBp6.BINARY, serial_factory=fake.factory(), connect_timeout=0.05,
                   first_reply_timeout=0.1, drain_seconds=0.05).open()


def test_power_on_off_and_limits():
    fake = FakeBp6()
    bp = make(fake).open()
    status = bp.set_power(True, millivolts=1800, milliamps=100)
    assert status.psu_enabled and status.psu_mv == 1800
    assert (bp.psu_mv, bp.psu_ma) == (1800, 100)
    assert not bp.set_power(False).psu_enabled
    with pytest.raises(ValueError):
        bp.set_power(True, millivolts=5500)
    with pytest.raises(ValueError):
        bp.set_power(True, milliamps=600)


def test_a_supply_that_will_not_start_says_why_in_plain_words():
    fake = FakeBp6(load_ma=4)
    bp = make(fake).open()
    with pytest.raises(ModeError) as refused:
        bp.set_power(True, millivolts=3300, milliamps=1)
    message = str(refused.value)
    assert "would not start" in message and "1 mA limit" in message
    assert "initialization failed" not in message


def test_a_bus_panels_power_tick_says_why_too():
    fake = FakeBp6(load_ma=4)
    bp = make(fake).open()
    bp.psu_mv, bp.psu_ma = 3300, 2
    with bp.i2c() as i2c:
        with pytest.raises(ModeError, match="would not start"):
            i2c.configure_peripherals(power=True)


def test_a_board_error_is_a_mode_error():
    bp = make(FakeBp6()).open()
    with pytest.raises(ModeError, match="Invalid mode name"):
        bp.configure(mode="JTAG")


def test_pullups():
    bp = make(FakeBp6()).open()
    assert bp.set_pullups(True).pullups
    assert not bp.set_pullups(False).pullups


def test_hiz_releases_everything():
    fake = FakeBp6()
    bp = make(fake).open()
    bp.set_power(True)
    bp.set_pullups(True)
    bp.configure(mode="I2C")
    bp.hiz()
    assert (fake.mode, fake.psu_enabled, fake.pullups) == ("HiZ", False, False)


def test_close_leaves_the_board_in_hiz():
    fake = FakeBp6()
    bp = make(fake).open()
    bp.set_power(True)
    bp.close()
    assert fake.mode == "HiZ" and not fake.psu_enabled
    assert bp.serial is None


def test_the_terminal_borrows_the_port_and_gives_it_back():
    fake = FakeBp6()
    bp = make(fake).open()
    bp.release_to_terminal(0)
    assert bp.serial is fake.terminal
    bp.write(b"i\r")
    assert b"Bus Pirate 6" in fake.terminal.read(4096)
    bp.stop_stream()
    assert bp.serial is fake.binary
    assert not fake.terminal.is_open
    assert fake.requests[-1] == "status"  # re-read what the terminal may have changed


def test_traffic_is_summarised():
    bp = make(FakeBp6()).open()
    seen = []
    bp.add_traffic_hook(lambda direction, data: seen.append(bp.summarize_traffic(direction, data)))
    bp.status()
    assert seen[0] == "Status request"
    assert seen[1].startswith("Status: HiZ")


def test_an_old_bpio_version_is_refused(monkeypatch):
    from dataclasses import replace
    import buspirate.bp6.link as link_module

    original = link_module.parse_response

    def older(payload):
        response = original(payload)
        if response.status is not None:
            response = replace(response, status=replace(response.status, flatbuffers_version=(1, 0)))
        return response

    monkeypatch.setattr(link_module, "parse_response", older)
    with pytest.raises(ModeError, match="update"):
        make(FakeBp6()).open()


def test_connecting_never_sends_ctrl_c():
    # Ctrl-C at the colour question wedges the real terminal until a replug.
    fake = FakeBp6(bpio_active=False, color_prompt=True)
    make(fake).open()
    assert b"\x03" not in fake.terminal.written


def test_a_silent_terminal_says_to_replug():
    fake = FakeBp6(bpio_active=False, color_prompt=True)
    fake.terminal_wedged = True
    with pytest.raises(ModeError, match="[Uu]nplug"):
        BusPirate6(FakeBp6.BINARY, terminal_port=FakeBp6.TERMINAL, serial_factory=fake.factory(),
                   connect_timeout=0.05, reply_timeout=0.05, first_reply_timeout=0.1,
                   drain_seconds=0.05).open()


def test_nothing_reaches_the_binary_port_before_bpio2_is_selected():
    # On the real board, BPIO2 bytes sent to the logic analyzer silenced the
    # terminal until a replug.
    fake = FakeBp6(bpio_active=False, color_prompt=True)
    bp = make(fake, reply_timeout=0.3).open()
    assert not fake.terminal_wedged
    assert bp.last_status.mode == "HiZ"


def test_nothing_is_sent_while_bpio2_is_starting_up():
    # The real board needs ~2.8 s after BPIO2 is selected; anything sent
    # sooner is lost, and has left its terminal silent until a replug.
    fake = FakeBp6(bpio_active=False, bpio_settle=0.3)
    make(fake, reply_timeout=0.3, bpio2_settle=0.4).open()
    assert not fake.terminal_wedged
    assert fake.requests == ["status"]


def test_bpio2_already_on_is_not_selected_again():
    fake = FakeBp6()
    make(fake).open()
    assert b"binmode" not in fake.terminal.written


def test_a_terminal_held_elsewhere_still_connects_when_bpio2_is_on():
    fake = FakeBp6()
    factory = fake.factory()

    def busy_terminal(port, baudrate, timeout):
        if port == FakeBp6.TERMINAL:
            raise ConnectionError("cannot open: Resource busy")
        return factory(port, baudrate, timeout)

    bp = BusPirate6(FakeBp6.BINARY, terminal_port=FakeBp6.TERMINAL, serial_factory=busy_terminal,
                    connect_timeout=0.1, reply_timeout=0.2).open()
    assert bp.last_status.mode == "HiZ"


def test_a_slow_first_reply_is_waited_for_not_sent_again():
    fake = FakeBp6(first_reply_delay=0.5)
    make(fake, first_reply_timeout=1.0).open()
    assert fake.requests == ["status"]
    assert not fake.terminal_wedged


def test_a_failed_connect_reads_the_late_reply_before_closing():
    # Closing the port on a reply still coming hangs the real board.
    fake = FakeBp6(first_reply_delay=0.6)
    with pytest.raises(ModeError):
        make(fake, first_reply_timeout=0.2, drain_seconds=1.0).open()
    assert not fake.terminal_wedged
    assert not fake.binary.is_open


def test_closing_the_terminal_waits_for_the_slow_reply_that_follows():
    fake = FakeBp6(terminal_reply_delay=0.5)
    bp = make(fake, first_reply_timeout=1.0).open()
    bp.release_to_terminal(0)
    bp.stop_stream()
    assert bp.serial is fake.binary
    assert not fake.terminal_wedged


def test_close_after_a_timeout_reads_the_late_reply_first():
    fake = FakeBp6()
    bp = make(fake, drain_seconds=1.0).open()
    fake._delay_next_reply = 0.5  # the next reply comes after the 0.2 s timeout
    with pytest.raises(ProtocolError):
        bp.status()
    bp.close()
    assert not fake.terminal_wedged
