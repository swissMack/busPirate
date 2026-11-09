"""Open whatever board is on a port with the driver that speaks to it.

A Bus Pirate and an ESP32 Bit Pirate want very different first words: the
Bus Pirate is knocked into binary mode with nulls, the Bit Pirate only ever
needs Enter. So the choice is made *before* anything is sent, from the USB
identity, and only an unrecognised adapter is probed:

1. Espressif's VID (0x303A) — the ESP32-S3's own USB port — is a Bit Pirate.
2. VID 0x1209 / PID 0x7331 is a Bus Pirate 5/6, driven over BPIO2 on its
   second port (its first, the terminal, only switches BPIO2 on).
3. Anything else gets the Bus Pirate's usual connect, unchanged. Its first
   words ("\\n", "i\\n", then nulls) are harmless to a Bit Pirate — an empty
   line, an unknown command, and keys its line editor ignores — so if that
   connect fails and what came back is a Bit Pirate's, it is reopened as one.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from .base import BusPirate, TrafficHook
from .bitpirate import BitPirate
from .device import looks_like_bitpirate
from .exceptions import ModeError

ESPRESSIF_VID = 0x303A
BP6_VID, BP6_PID = 0x1209, 0x7331


def _vid(usb_id: Optional[str]) -> Optional[int]:
    if not usb_id or ":" not in usb_id:
        return None
    try:
        return int(usb_id.split(":", 1)[0], 16)
    except ValueError:
        return None


def _pid(usb_id: Optional[str]) -> Optional[int]:
    if not usb_id or ":" not in usb_id:
        return None
    try:
        return int(usb_id.split(":", 1)[1], 16)
    except ValueError:
        return None


def open_device(
    port: str,
    usb_id: Optional[str] = None,
    on_traffic: Optional[TrafficHook] = None,
    serial_factory=None,
    buspirate_options: Optional[Dict[str, Any]] = None,
    bitpirate_options: Optional[Dict[str, Any]] = None,
    bp6_options: Optional[Dict[str, Any]] = None,
):
    """Return an opened :class:`BusPirate`, :class:`BitPirate` or ``BusPirate6``.

    ``usb_id`` is ``"VID:PID"`` as :mod:`buspirate.ports` reports it.
    """

    def bit_pirate():
        return BitPirate(
            port, serial_factory=serial_factory, on_traffic=on_traffic,
            **(bitpirate_options or {}),
        ).open()

    if (_vid(usb_id), _pid(usb_id)) == (BP6_VID, BP6_PID):
        from . import ports
        from .bp6 import BusPirate6

        terminal, binary = ports.bp6_ports_for(port)
        return BusPirate6(
            binary or port, terminal_port=terminal, serial_factory=serial_factory,
            on_traffic=on_traffic, **(bp6_options or {}),
        ).open()

    if _vid(usb_id) == ESPRESSIF_VID:
        return bit_pirate()

    device = BusPirate(
        port, serial_factory=serial_factory, on_traffic=on_traffic,
        **(buspirate_options or {}),
    )
    try:
        return device.open()
    except ModeError as bus_pirate_error:
        if not looks_like_bitpirate(device.profile.banner):
            raise
        # Close without the reset byte: 0x0F means nothing to a Bit Pirate,
        # and nothing needs undoing.
        if device.serial is not None:
            device.serial.close()
            device.serial = None
        try:
            return bit_pirate()
        except ModeError:
            # It only looked like one. The Bus Pirate's own failure is the
            # one that explains what is wrong.
            raise bus_pirate_error from None


def open_simulated(variant: str, on_traffic: Optional[TrafficHook] = None):
    """Open a simulated board: ``"v3"``, ``"v4"``, ``"bp6"`` or ``"bitpirate"``."""
    if variant == "bp6":
        from .bp6 import BusPirate6
        from .simulator_bp6 import FakeBp6

        fake = FakeBp6()
        return BusPirate6(
            FakeBp6.BINARY,
            terminal_port=FakeBp6.TERMINAL,
            serial_factory=fake.factory(),
            on_traffic=on_traffic,
            connect_timeout=0.2,
        ).open()
    if variant == "bitpirate":
        from .simulator import fake_factory
        from .simulator_bitpirate import FakeBitPirateSerial

        return BitPirate(
            "simulated:bitpirate",
            serial_factory=fake_factory(FakeBitPirateSerial(booting=True)),
            on_traffic=on_traffic,
            connect_timeout=0.3,
        ).open()
    if variant in ("v3", "v4"):
        from .simulator import FakeSerial, fake_factory

        return BusPirate(
            "simulated:" + variant,
            serial_factory=fake_factory(FakeSerial(variant=variant)),
            on_traffic=on_traffic,
            identify_timeout=0.05,
        ).open()
    raise ValueError("unknown simulated variant: %r" % (variant,))
