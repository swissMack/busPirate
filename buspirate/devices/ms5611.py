"""MS5611 barometric pressure + temperature (I2C, 0x76 or 0x77).

Shares its addresses with the BMP280, so the probe reads the factory PROM and
checks its CRC-4 (application note AN520): a BMP280 does not answer the PROM
commands, and its bytes would not make a valid CRC anyway. The reading is the
datasheet's first-order compensation plus the second-order step below 20 °C.
"""

from __future__ import annotations

import time
from typing import List, Sequence, Tuple

from . import Device, Meaning, Reading

ADDRESSES = (0x76, 0x77)
RESET = bytes([0x1E])
PROM_BASE = 0xA0  # word n is at 0xA0 + 2n; word 0 factory, 1-6 C1..C6, 7 CRC
CONVERT_D1 = bytes([0x48])  # pressure, OSR 4096
CONVERT_D2 = bytes([0x58])  # temperature, OSR 4096
ADC_READ = bytes([0x00])


def crc4(words: Sequence[int]) -> int:
    """The PROM CRC-4 from AN520, over the 8 words (the CRC nibble is ignored)."""
    prom = list(words[:8])
    prom[7] &= 0xFF00
    remainder = 0
    for count in range(16):
        if count % 2 == 1:
            remainder ^= prom[count >> 1] & 0x00FF
        else:
            remainder ^= prom[count >> 1] >> 8
        for _ in range(8):
            if remainder & 0x8000:
                remainder = ((remainder << 1) ^ 0x3000) & 0xFFFF
            else:
                remainder = (remainder << 1) & 0xFFFF
    return (remainder >> 12) & 0xF


def read_prom(i2c, address: int) -> List[int]:
    i2c.write(address, RESET)
    time.sleep(0.003)  # reload takes 2.8 ms
    words = []
    for n in range(8):
        i2c.write(address, bytes([PROM_BASE + 2 * n]))
        reply = i2c.read(address, 2)
        if len(reply) != 2:
            raise IOError("short PROM read")
        words.append((reply[0] << 8) | reply[1])
    return words


def probe(i2c, address: int) -> bool:
    try:
        words = read_prom(i2c, address)
    except Exception:  # a NACK: not an MS5611
        return False
    if all(w == 0 for w in words) or all(w == 0xFFFF for w in words):
        return False  # a floating bus reads as a valid-looking CRC of nothing
    return crc4(words) == (words[7] & 0xF)


def compensate(coefficients: Sequence[int], d1: int, d2: int) -> Tuple[float, float]:
    """(°C, hPa) from C1..C6 and the raw pressure and temperature, per the datasheet."""
    c1, c2, c3, c4, c5, c6 = coefficients[:6]
    dt = d2 - c5 * 256
    temp = 2000 + dt * c6 // 2 ** 23  # 0.01 °C
    off = c2 * 2 ** 16 + c4 * dt // 2 ** 7
    sens = c1 * 2 ** 15 + c3 * dt // 2 ** 8
    t2 = off2 = sens2 = 0
    if temp < 2000:
        t2 = dt * dt // 2 ** 31
        off2 = 5 * (temp - 2000) ** 2 // 2
        sens2 = off2 // 2
        if temp < -1500:
            off2 += 7 * (temp + 1500) ** 2
            sens2 += 11 * (temp + 1500) ** 2 // 2
    temp -= t2
    off -= off2
    sens -= sens2
    pressure = (d1 * sens // 2 ** 21 - off) // 2 ** 15  # 0.01 mbar
    return temp / 100.0, pressure / 100.0


def decode(coefficients: Sequence[int], d1: int, d2: int) -> Meaning:
    temperature, pressure = compensate(coefficients, d1, d2)
    return [
        ("Temperature", f"{temperature:.2f} °C"),
        ("Pressure", f"{pressure:.2f} hPa"),
    ]


def _convert(i2c, address: int, command: bytes) -> bytes:
    i2c.write(address, command)
    time.sleep(0.01)  # OSR 4096 takes up to 9.04 ms
    i2c.write(address, ADC_READ)
    return bytes(i2c.read(address, 3))


def measure(i2c, address: int) -> Reading:
    words = read_prom(i2c, address)
    raw1 = _convert(i2c, address, CONVERT_D1)
    raw2 = _convert(i2c, address, CONVERT_D2)
    d1, d2 = int.from_bytes(raw1, "big"), int.from_bytes(raw2, "big")
    return Reading(
        "MS5611", f"0x{address:02X}", raw1 + raw2, decode(words[1:7], d1, d2),
    )


DEVICES = [
    Device(
        name="MS5611",
        bus="i2c",
        summary="pressure + temperature",
        addresses=ADDRESSES,
        probe=probe,
        measure=measure,
    ),
]
