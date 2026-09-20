"""Port discovery, including the macOS cu/tty trap."""

import pytest
from serial.tools import list_ports

from buspirate import ConnectionError, ports


class FakePort:
    def __init__(self, device, description="", vid=None, pid=None, manufacturer=None):
        self.device = device
        self.description = description
        self.hwid = f"USB VID:PID={vid:04X}:{pid:04X}" if vid else "n/a"
        self.vid = vid
        self.pid = pid
        self.manufacturer = manufacturer
        self.serial_number = None


FTDI = (0x0403, 0x6001)
BPV4 = (0x04D8, 0xFB00)


@pytest.fixture
def listing(monkeypatch):
    def install(*fakes):
        monkeypatch.setattr(list_ports, "comports", lambda: list(fakes))

    return install


@pytest.fixture(autouse=True)
def on_macos(monkeypatch):
    monkeypatch.setattr(ports.sys, "platform", "darwin")


def test_a_known_adapter_is_flagged(listing):
    listing(FakePort("/dev/cu.usbserial-A700eEoR", "FT232R USB UART", *FTDI))
    found = ports.discover()
    assert len(found) == 1
    assert found[0].likely_bus_pirate
    assert found[0].usb_id == "0403:6001"
    assert "FTDI" in found[0].note


def test_the_v4_cdc_device_is_recognised(listing):
    listing(FakePort("/dev/cu.usbmodem1421", "Bus Pirate v4", *BPV4))
    assert "Bus Pirate v4" in ports.discover()[0].note


def test_cu_is_preferred_over_tty(listing):
    listing(
        FakePort("/dev/tty.usbserial-A700eEoR", "FT232R USB UART", *FTDI),
        FakePort("/dev/cu.usbserial-A700eEoR", "FT232R USB UART", *FTDI),
    )
    found = ports.discover()
    assert found[0].device.startswith("/dev/cu.")
    assert "prefer the /dev/cu. device" in found[1].note


def test_bluetooth_and_the_debug_console_are_hidden(listing):
    listing(
        FakePort("/dev/cu.Bluetooth-Incoming-Port"),
        FakePort("/dev/cu.debug-console"),
        FakePort("/dev/cu.usbserial-A700eEoR", "FT232R USB UART", *FTDI),
    )
    assert [p.device for p in ports.discover()] == ["/dev/cu.usbserial-A700eEoR"]
    assert len(ports.discover(include_unlikely=True)) == 3


def test_an_unrecognised_adapter_is_listed_but_not_assumed(listing):
    listing(FakePort("/dev/cu.usbserial-1130", "USB Single Serial", 0x1234, 0x5678))
    candidate = ports.discover()[0]
    assert not candidate.likely_bus_pirate
    assert "unrecognised chip" in candidate.note


def test_a_self_describing_device_wins(listing):
    listing(
        FakePort("/dev/cu.usbserial-1130", "USB Single Serial", 0x1234, 0x5678),
        FakePort("/dev/cu.usbmodem1", "Bus Pirate v4", 0x1234, 0x9999),
    )
    assert ports.discover()[0].device == "/dev/cu.usbmodem1"


# -- resolve ---------------------------------------------------------------


def test_resolve_passes_an_explicit_port_straight_through(listing):
    listing()
    assert ports.resolve("/dev/cu.whatever") == "/dev/cu.whatever"


def test_resolve_picks_the_obvious_candidate(listing):
    listing(FakePort("/dev/cu.usbserial-A700eEoR", "FT232R USB UART", *FTDI))
    assert ports.resolve("auto") == "/dev/cu.usbserial-A700eEoR"


def test_resolve_explains_an_empty_bus(listing):
    listing()
    with pytest.raises(ConnectionError, match="no USB serial ports found"):
        ports.resolve("auto")


def test_resolve_lists_the_alternatives_when_unsure(listing):
    listing(FakePort("/dev/cu.usbserial-1130", "USB Single Serial", 0x1234, 0x5678))
    with pytest.raises(ConnectionError) as excinfo:
        ports.resolve(None)
    message = str(excinfo.value)
    assert "no port looks like a Bus Pirate" in message
    assert "/dev/cu.usbserial-1130" in message
