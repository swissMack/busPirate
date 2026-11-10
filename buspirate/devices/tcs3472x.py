"""TCS34721/3/5/7 colour sensor (I2C, 0x29).

Reads clear, red, green and blue counts; colour temperature and lux are the
approximations from TAOS design note DN40 (no glass attenuation, 1x gain,
24 ms integration). The 0x80 bit on every register address is the command bit.
"""

from __future__ import annotations

import time

from . import Device, Meaning, Reading

ADDRESS = 0x29
READ_ID = bytes([0x92])
IDS = (0x44, 0x4D)  # 0x44: TCS34721/5 (I2C 3.3 V), 0x4D: TCS34723/7 (1.8 V)
ENABLE = bytes([0x80, 0x03])  # power on + RGBC enable
ATIME = bytes([0x81, 0xF6])  # 256 - 10 cycles = 24 ms
READ_COLOURS = bytes([0xB4])  # 0x80 | 0x20 auto-increment | 0x14 (CDATA)
INTEGRATION_MS = 24.0
GAIN = 1.0
DEVICE_FACTOR = 310.0  # DN40's DF; glass attenuation GA taken as 1


def probe(i2c, address: int) -> bool:
    try:
        i2c.write(address, READ_ID)
        reply = i2c.read(address, 1)
    except Exception:  # a NACK: not one of these chips
        return False
    return len(reply) == 1 and reply[0] in IDS


def decode(raw: bytes) -> Meaning:
    if len(raw) < 8:
        return [("TCS3472x", "needs 8 bytes: clear, red, green, blue, little-endian")]
    c, r, g, b = (raw[i] | (raw[i + 1] << 8) for i in (0, 2, 4, 6))
    meaning = [("Clear", str(c)), ("Red", str(r)), ("Green", str(g)), ("Blue", str(b))]
    ir = (r + g + b - c) / 2 if r + g + b > c else 0.0
    r2, g2, b2 = r - ir, g - ir, b - ir
    if r2 > 0:
        meaning.append(("Colour temperature", f"{3810 * b2 / r2 + 1391:.0f} K"))
    g1 = 0.136 * r2 + g2 - 0.444 * b2
    counts_per_lux = INTEGRATION_MS * GAIN / DEVICE_FACTOR
    meaning.append(("Illuminance", f"{max(0.0, g1 / counts_per_lux):.1f} lux"))
    return meaning


def measure(i2c, address: int) -> Reading:
    i2c.write(address, ENABLE)
    i2c.write(address, ATIME)
    time.sleep(0.05)  # one 24 ms integration, with margin
    i2c.write(address, READ_COLOURS)
    raw = bytes(i2c.read(address, 8))
    return Reading("TCS3472x", f"0x{address:02X}", raw, decode(raw))


DEVICES = [
    Device(
        name="TCS3472x",
        bus="i2c",
        summary="colour (RGB + clear), colour temperature and lux (TCS34725 etc.)",
        addresses=(ADDRESS,),
        probe=probe,
        measure=measure,
    ),
]
