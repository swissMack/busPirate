"""Open whatever board is on a port with the driver that speaks to it.

A Bus Pirate and an ESP32 Bit Pirate want very different first words: the
Bus Pirate is knocked into binary mode with nulls, the Bit Pirate only ever
needs Enter. So the choice is made *before* anything is sent, from the USB
identity, and only an unrecognised adapter is probed:

1. Espressif's VID (0x303A) — the ESP32-S3's own USB port — is a Bit Pirate.
2. Anything else gets the Bus Pirate's usual connect, unchanged. Its first
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


def _vid(usb_id: Optional[str]) -> Optional[int]:
    if not usb_id or ":" not in usb_id:
        return None
    try:
        return int(usb_id.split(":", 1)[0], 16)
    except ValueError:
        return None


def open_device(
    port: str,
    usb_id: Optional[str] = None,
    on_traffic: Optional[TrafficHook] = None,
    serial_factory=None,
    buspirate_options: Optional[Dict[str, Any]] = None,
    bitpirate_options: Optional[Dict[str, Any]] = None,
):
    """Return an opened :class:`BusPirate` or :class:`BitPirate`.

    ``usb_id`` is ``"VID:PID"`` as :mod:`buspirate.ports` reports it.
    """

    def bit_pirate():
        return BitPirate(
            port, serial_factory=serial_factory, on_traffic=on_traffic,
            **(bitpirate_options or {}),
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
