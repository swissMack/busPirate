"""Picking the right driver for whatever is on the port."""

from buspirate.base import BusPirate
from buspirate.bitpirate import BitPirate
from buspirate.connect import open_device
from buspirate.ports import KNOWN_ADAPTERS
from buspirate.simulator import FakeSerial, fake_factory
from buspirate.simulator_bitpirate import FakeBitPirateSerial


def test_an_espressif_port_is_a_bit_pirate_and_hears_only_its_command_line():
    fake = FakeBitPirateSerial()
    device = open_device(
        "/dev/cu.usbmodem1101", usb_id="303A:1002", serial_factory=fake_factory(fake),
        bitpirate_options={"connect_timeout": 0.2},
    )
    assert isinstance(device, BitPirate)
    # Enter to reach the prompt, then the system shell for the version:
    # never the Bus Pirate's nulls or reset byte.
    assert fake.written == b"\rsystem\r1\r\r"


def test_a_bus_pirate_port_is_opened_exactly_as_before():
    fake = FakeSerial(variant="v3")
    device = open_device(
        "/dev/cu.usbserial-A1", usb_id="0403:6001", serial_factory=fake_factory(fake),
        buspirate_options={"identify_timeout": 0.02},
    )
    assert isinstance(device, BusPirate)
    assert device.profile.variant == "v3"


def test_a_bit_pirate_behind_an_unknown_bridge_is_found_by_its_replies():
    # A board flashed to talk over a CH340 or CP2102: the VID says nothing,
    # so the Bus Pirate path runs first — its "\n" and "i\n" are harmless
    # commands to the Bit Pirate, and its nulls are ignored — and the
    # replies give it away.
    fake = FakeBitPirateSerial()
    device = open_device(
        "/dev/cu.wchusbserial1", usb_id="1A86:7523", serial_factory=fake_factory(fake),
        buspirate_options={"identify_timeout": 0.02},
        bitpirate_options={"connect_timeout": 0.2},
    )
    assert isinstance(device, BitPirate)
    assert fake.mode == "HIZ"


def test_the_espressif_native_usb_port_is_offered_as_likely():
    assert any(vid == 0x303A for vid, _ in KNOWN_ADAPTERS)


def test_a_false_alarm_keeps_the_bus_pirate_error():
    # Terminal output that merely looks like a Bit Pirate's (an ANSI line
    # clear) from a board that then answers neither protocol.
    import pytest

    from buspirate.exceptions import ModeError

    class Confusing:
        def __init__(self):
            self.pending = b""

        def write(self, data):
            if b"i\n" in data:
                self.pending += b"\x1b[K?\r\n"
            return len(data)

        def read(self, count=1):
            chunk, self.pending = self.pending[:count], self.pending[count:]
            return chunk

        def reset_input_buffer(self):
            self.pending = b""

        def close(self):
            pass

    with pytest.raises(ModeError, match="no BBIO response"):
        open_device(
            "/dev/cu.odd", usb_id="1A86:7523", serial_factory=fake_factory(Confusing()),
            buspirate_options={"identify_timeout": 0.02},
            bitpirate_options={"connect_timeout": 0.05},
        )
