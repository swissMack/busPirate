"""Finding a Bus Pirate 6: one board, two ports, one entry."""

from types import SimpleNamespace

from buspirate import connect, ports
from buspirate.bp6 import BusPirate6
from buspirate.simulator_bp6 import FakeBp6


def info(device, location="1-1", vid=0x1209, pid=0x7331):
    return SimpleNamespace(device=device, location=location, vid=vid, pid=pid,
                           description="Bus Pirate 6", hwid="", manufacturer="Bus Pirate",
                           serial_number="6buspirate")


def test_the_two_ports_of_one_board_are_paired():
    pairs = ports.pair_bp6([info("/dev/cu.usbmodem6buspirate3"), info("/dev/cu.usbmodem6buspirate1")])
    expected = ("/dev/cu.usbmodem6buspirate1", "/dev/cu.usbmodem6buspirate3")
    assert pairs["/dev/cu.usbmodem6buspirate1"] == expected
    assert pairs["/dev/cu.usbmodem6buspirate3"] == expected


def test_two_boards_are_kept_apart_by_location():
    pairs = ports.pair_bp6([
        info("/dev/ttyACM0", "1-1"), info("/dev/ttyACM1", "1-1"),
        info("/dev/ttyACM2", "1-2"), info("/dev/ttyACM3", "1-2"),
    ])
    assert pairs["/dev/ttyACM3"] == ("/dev/ttyACM2", "/dev/ttyACM3")


def test_discover_shows_one_entry(monkeypatch):
    from serial.tools import list_ports
    monkeypatch.setattr(list_ports, "comports", lambda: [
        info("/dev/cu.usbmodem6buspirate1"), info("/dev/cu.usbmodem6buspirate3")])
    found = ports.discover()
    assert [c.device for c in found] == ["/dev/cu.usbmodem6buspirate1"]
    assert found[0].partner == "/dev/cu.usbmodem6buspirate3"
    assert found[0].likely_bus_pirate
    assert "Bus Pirate 5/6" in found[0].note


def test_fallback_pairing_by_name(monkeypatch):
    from serial.tools import list_ports
    monkeypatch.setattr(list_ports, "comports", lambda: [])
    assert ports.bp6_ports_for("/dev/cu.usbmodem6buspirate1") == (
        "/dev/cu.usbmodem6buspirate1", "/dev/cu.usbmodem6buspirate3")


def test_open_device_routes_the_usb_id_to_the_bp6(monkeypatch):
    fake = FakeBp6()
    monkeypatch.setattr(ports, "bp6_ports_for", lambda device: (FakeBp6.TERMINAL, FakeBp6.BINARY))
    device = connect.open_device(FakeBp6.TERMINAL, usb_id="1209:7331",
                                 serial_factory=fake.factory())
    assert isinstance(device, BusPirate6)
    assert fake.terminal.written == b""  # never the v3/v4 nulls or BBIO reset


def test_the_cli_pings_a_bp6(monkeypatch, capsys):
    import argparse

    from buspirate import cli

    fake = FakeBp6()
    monkeypatch.setattr(cli, "resolve", lambda port: FakeBp6.TERMINAL)
    monkeypatch.setattr(cli, "usb_id_for", lambda device: "1209:7331")
    monkeypatch.setattr(ports, "bp6_ports_for", lambda device: (FakeBp6.TERMINAL, FakeBp6.BINARY))
    monkeypatch.setattr(cli, "open_device", lambda port, usb_id: connect.open_device(
        port, usb_id=usb_id, serial_factory=fake.factory()))
    assert cli.cmd_ping(argparse.Namespace(port="auto")) == 0
    out = capsys.readouterr().out
    assert "Bus Pirate 6, firmware 2026-10-12" in out and "protocol BPIO2" in out
    assert fake.mode == "HiZ" and not fake.binary.is_open  # closed once, left in HiZ


def test_linux_locations_carry_the_interface_and_still_pair():
    pairs = ports.pair_bp6([info("/dev/ttyACM1", "1-2:1.2"), info("/dev/ttyACM0", "1-2:1.0")])
    assert pairs["/dev/ttyACM1"] == ("/dev/ttyACM0", "/dev/ttyACM1")
