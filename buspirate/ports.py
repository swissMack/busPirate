"""Finding the Bus Pirate's serial port, with macOS's quirks handled.

macOS exposes every USB serial adapter twice: ``/dev/cu.*`` (call-out) and
``/dev/tty.*`` (call-in). The ``tty`` device blocks on open until it sees
carrier detect, which is the classic "it just hangs" report — so everything
here prefers ``cu``. Bluetooth and the kernel debug console also show up as
serial ports and are filtered out.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .exceptions import ConnectionError

# USB bridges the Bus Pirate has shipped with, plus the v4's own CDC device,
# and the ESP32-S3's own USB port, which is where the ESP32 Bit Pirate talks.
KNOWN_ADAPTERS = {
    (0x303A, 0x1001): "Espressif ESP32-S3 USB (ESP32 Bit Pirate)",
    # What an ESP32-S3-DevKitC-1 N16R8 on firmware v1.7 reported (2026-10-12).
    (0x303A, 0x1002): "Espressif ESP32-S3 USB (ESP32 Bit Pirate)",
    (0x0403, 0x6001): "FTDI FT232R (Bus Pirate v3)",
    (0x0403, 0x6015): "FTDI FT231X",
    (0x04D8, 0xFB00): "Microchip CDC (Bus Pirate v4)",
    # One board, two CDC ports: its terminal and its BPIO2 binary interface.
    (0x1209, 0x7331): "Bus Pirate 5/6 (terminal + BPIO2 ports)",
    (0x10C4, 0xEA60): "Silicon Labs CP2102",
    (0x1A86, 0x7523): "WCH CH340",
}

# Ports that are never a Bus Pirate, however tempting they look.
_NEVER = ("Bluetooth", "debug-console", "wlan-debug")


@dataclass
class PortCandidate:
    """One serial port, with a guess at whether it is the Bus Pirate."""

    device: str
    description: str = ""
    hwid: str = ""
    vid: Optional[int] = None
    pid: Optional[int] = None
    manufacturer: Optional[str] = None
    serial_number: Optional[str] = None
    score: int = 0
    note: str = ""
    #: A Bus Pirate 5/6's second port (BPIO2), shown under its terminal port.
    partner: Optional[str] = None

    @property
    def likely_bus_pirate(self) -> bool:
        return self.score >= 50

    @property
    def usb_id(self) -> Optional[str]:
        if self.vid is None or self.pid is None:
            return None
        return f"{self.vid:04X}:{self.pid:04X}"

    def describe(self) -> str:
        bits = [self.device]
        if self.usb_id:
            bits.append(f"[{self.usb_id}]")
        if self.note:
            bits.append(f"- {self.note}")
        if self.partner:
            bits.append(f"(BPIO2 on {self.partner})")
        return "  ".join(bits)


def discover(include_unlikely: bool = False) -> List[PortCandidate]:
    """List serial ports, best Bus Pirate candidate first."""
    try:
        from serial.tools import list_ports
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise ConnectionError("pyserial is required: pip install pyserial") from exc

    infos = list(list_ports.comports())
    pairs = pair_bp6(infos)
    candidates = []
    for info in infos:
        pair = pairs.get(info.device)
        if pair and info.device != pair[0]:
            continue  # shown once, under its terminal port
        candidate = _score(info)
        if pair:
            candidate.partner = pair[1]
        if candidate.score < 0 and not include_unlikely:
            continue
        candidates.append(candidate)
    candidates.sort(key=lambda c: (-c.score, c.device))
    return candidates


def _score(info) -> PortCandidate:
    device = info.device
    candidate = PortCandidate(
        device=device,
        description=info.description or "",
        hwid=info.hwid or "",
        vid=info.vid,
        pid=info.pid,
        manufacturer=info.manufacturer,
        serial_number=info.serial_number,
    )

    if any(token in device for token in _NEVER):
        candidate.score = -1
        candidate.note = "not a USB serial adapter"
        return candidate

    adapter = KNOWN_ADAPTERS.get((info.vid, info.pid))
    if adapter is None and info.vid == 0x303A:
        # Espressif's PID depends on the board and how the firmware was built.
        adapter = "Espressif ESP32 USB (ESP32 Bit Pirate)"
    if adapter:
        candidate.score = 60
        candidate.note = adapter
    elif info.vid is not None:
        candidate.score = 20
        candidate.note = "USB serial adapter, unrecognised chip"
    else:
        # No USB identity at all: a Bluetooth pairing or an on-board UART.
        # Return before the platform adjustments so it stays below zero.
        candidate.score = -1
        candidate.note = "not a USB serial adapter"
        return candidate

    if sys.platform == "darwin":
        if "/tty." in device:
            # Same hardware as the cu. device, but opening it can block.
            candidate.score -= 15
            candidate.note += " (prefer the /dev/cu. device)"
        elif "/cu." in device:
            candidate.score += 5

    text = f"{candidate.description} {candidate.manufacturer or ''}".lower()
    if "bus pirate" in text or "buspirate" in text:
        candidate.score += 40
        candidate.note = f"{candidate.note}; names itself a Bus Pirate".lstrip("; ")

    return candidate


BP6_ID = (0x1209, 0x7331)


def _natural(device: str):
    import re

    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", device)]


def pair_bp6(infos) -> Dict[str, Tuple[str, str]]:
    """Each Bus Pirate 5/6 port mapped to (terminal port, BPIO2 port).

    Its two CDC ports share a USB location (pyserial's ``location``, less any
    ``:interface`` suffix); the lower-numbered one is the terminal. The USB serial number is the same
    on every unit ("6buspirate"), so it cannot tell two boards apart.
    """
    groups: Dict[str, List[str]] = {}
    for item in infos:
        if (getattr(item, "vid", None), getattr(item, "pid", None)) == BP6_ID:
            # macOS gives "1-1" for both ports; Linux and Windows append the
            # interface ("1-2:1.0", "1-2:1.2"), which is not part of the board.
            key = (getattr(item, "location", None) or item.device).split(":")[0]
            groups.setdefault(key, []).append(item.device)
    pairs: Dict[str, Tuple[str, str]] = {}
    for devices in groups.values():
        devices.sort(key=_natural)
        if len(devices) >= 2:
            pair = (devices[0], devices[-1])
            for device in devices:
                pairs[device] = pair
    return pairs


def bp6_ports_for(device: str) -> Tuple[str, Optional[str]]:
    """``(terminal, binary)`` for a port of a plugged-in Bus Pirate 5/6."""
    from serial.tools import list_ports

    pair = pair_bp6(list_ports.comports()).get(device)
    if pair:
        return pair
    if device.endswith("1"):
        return device, device[:-1] + "3"
    if device.endswith("3"):
        return device[:-1] + "1", device
    return device, None


def usb_id_for(device: str) -> Optional[str]:
    """The ``VID:PID`` of the adapter behind ``device``, if it is plugged in."""
    for candidate in discover(include_unlikely=True):
        if candidate.device == device or candidate.partner == device:
            return candidate.usb_id
    return None


def resolve(port: Optional[str]) -> str:
    """Turn ``None`` or ``"auto"`` into a real device path.

    Raises a :class:`ConnectionError` that lists what *was* found, since "no
    port" and "the wrong port" need different fixes.
    """
    if port and port != "auto":
        return port

    candidates = discover()
    best = candidates[0] if candidates else None
    if best is not None and best.likely_bus_pirate:
        return best.device

    if not candidates:
        raise ConnectionError(
            "no USB serial ports found. Plug the Bus Pirate in, and if it is "
            "already plugged in see docs/troubleshooting.md — on macOS a "
            "missing port usually means a missing USB driver."
        )
    listed = "\n  ".join(c.describe() for c in candidates)
    raise ConnectionError(
        "no port looks like a Bus Pirate. Pick one explicitly with --port:\n  "
        + listed
    )
