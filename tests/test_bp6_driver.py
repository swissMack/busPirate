"""The Bus Pirate 6 driver against the simulated board."""

import pytest

from buspirate.bp6 import BusPirate6
from buspirate.exceptions import ModeError
from buspirate.simulator_bp6 import FakeBp6


def make(fake, **kw):
    kw.setdefault("reply_timeout", 0.2)
    kw.setdefault("connect_timeout", 0.1)
    return BusPirate6(FakeBp6.BINARY, terminal_port=FakeBp6.TERMINAL,
                      serial_factory=fake.factory(), **kw)


def test_connect_reads_the_status():
    fake = FakeBp6()
    bp = make(fake).open()
    assert bp.profile.describe() == "Bus Pirate 6, firmware 2026-10-12"
    assert bp.last_status.mode == "HiZ"
    assert fake.terminal.written == b""  # BPIO2 was on, the terminal was left alone


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
        BusPirate6(FakeBp6.BINARY, serial_factory=fake.factory(), connect_timeout=0.05).open()


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
