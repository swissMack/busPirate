"""SHT30 / SHT31 / SHT35 temperature + humidity (I2C, 0x44 or 0x45).

One command starts a measurement, the reply is two 16-bit words each followed
by a CRC-8. The SHT4x shares the address, so ``probe`` asks the question only
an SHT3x answers (the status register, ``F3 2D``).
"""

from __future__ import annotations

import time

from . import Device, Meaning, Reading
from .aht20 import crc8  # same polynomial (0x31) and start value (0xFF)

ADDRESSES = (0x44, 0x45)
MEASURE = bytes([0x24, 0x00])  # high repeatability, no clock stretching
STATUS = bytes([0xF3, 0x2D])


def words(raw: bytes, chip: str):
    """The two 16-bit values of a 6-byte reply, or ``ValueError`` on a bad CRC."""
    if len(raw) < 6:
        raise ValueError(f"{chip}: expected 6 bytes, got {len(raw)}")
    for start in (0, 3):
        if crc8(raw[start:start + 2]) != raw[start + 2]:
            raise ValueError(f"{chip}: CRC mismatch in bytes {start}-{start + 2} — the reply was damaged")
    return (raw[0] << 8) | raw[1], (raw[3] << 8) | raw[4]


def decode(raw: bytes) -> Meaning:
    t_raw, h_raw = words(raw, "SHT3x")
    return [
        ("Temperature", f"{-45 + 175 * t_raw / 65535:.2f} °C"),
        ("Humidity", f"{100 * h_raw / 65535:.1f} %RH"),
    ]


def probe(i2c, address: int) -> bool:
    try:
        i2c.write(address, STATUS)
        reply = i2c.read(address, 3)
    except Exception:  # a NACK: not an SHT3x
        return False
    return len(reply) == 3 and crc8(reply[:2]) == reply[2]


def measure(i2c, address: int) -> Reading:
    i2c.write(address, MEASURE)
    time.sleep(0.016)
    raw = i2c.read(address, 6)
    return Reading("SHT3x", f"0x{address:02X}", raw, decode(raw))


DEVICES = [
    Device(
        name="SHT3x",
        bus="i2c",
        summary="temperature + humidity (SHT30/31/35)",
        addresses=ADDRESSES,
        probe=probe,
        measure=measure,
    ),
]
