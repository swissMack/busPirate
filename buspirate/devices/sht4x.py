"""SHT40 / SHT41 / SHT43 / SHT45 temperature + humidity (I2C, 0x44).

1.08-3.6 V only — not 5 V tolerant. ``FD`` starts a high-precision
measurement; the reply has the same shape as the SHT3x's. ``probe`` asks for
the serial number (``89``), which an SHT3x does not answer.
"""

from __future__ import annotations

import time

from . import Device, Meaning, Reading
from .aht20 import crc8
from .sht3x import words

ADDRESSES = (0x44, 0x45, 0x46)
MEASURE = bytes([0xFD])  # high precision
SERIAL = bytes([0x89])


def decode(raw: bytes) -> Meaning:
    t_raw, h_raw = words(raw, "SHT4x")
    humidity = min(100.0, max(0.0, -6 + 125 * h_raw / 65535))
    return [
        ("Temperature", f"{-45 + 175 * t_raw / 65535:.2f} °C"),
        ("Humidity", f"{humidity:.1f} %RH"),
    ]


def probe(i2c, address: int) -> bool:
    try:
        i2c.write(address, SERIAL)
        time.sleep(0.002)
        reply = i2c.read(address, 6)
    except Exception:  # a NACK: not an SHT4x
        return False
    return len(reply) == 6 and crc8(reply[:2]) == reply[2] and crc8(reply[3:5]) == reply[5]


def measure(i2c, address: int) -> Reading:
    i2c.write(address, MEASURE)
    time.sleep(0.010)
    raw = i2c.read(address, 6)
    return Reading("SHT4x", f"0x{address:02X}", raw, decode(raw))


DEVICES = [
    Device(
        name="SHT4x",
        bus="i2c",
        summary="temperature + humidity (SHT40/41/43/45, 3.6 V max)",
        addresses=ADDRESSES,
        probe=probe,
        measure=measure,
    ),
]
