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
from typing import List, Optional

from .exceptions import ConnectionError

# USB bridges the Bus Pirate has shipped with, plus the v4's own CDC device,
# and the ESP32-S3's own USB port, which is where the ESP32 Bit Pirate talks.
KNOWN_ADAPTERS = {
    (0x303A, 0x1001): "Espressif ESP32-S3 USB (ESP32 Bit Pirate)",
    (0x0403, 0x6001): "FTDI FT232R (Bus Pirate v3)",
    (0x0403, 0x6015): "FTDI FT231X",
    (0x04D8, 0xFB00): "Microchip CDC (Bus Pirate v4)",
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
        return "  ".join(bits)


def discover(include_unlikely: bool = False) -> List[PortCandidate]:
    """List serial ports, best Bus Pirate candidate first."""
    try:
        from serial.tools import list_ports
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise ConnectionError("pyserial is required: pip install pyserial") from exc

    candidates = []
    for info in list_ports.comports():
        candidate = _score(info)
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
