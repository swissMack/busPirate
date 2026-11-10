"""TSL2561 / TSL2560 light-to-digital sensor (I2C, 0x29, 0x39 or 0x49).

Two photodiodes: CH0 sees visible + infrared, CH1 infrared only. Lux comes
from the datasheet's piecewise formula for the T/FN/CL package, at the
power-on defaults (1x gain, 402 ms integration), so no scaling is needed.
Every register access sets the command bit (0x80); ``AC``/``AE`` are the
word reads of CH0 and CH1.
"""

from __future__ import annotations

import time

from . import Device, Meaning, Reading

ADDRESSES = (0x29, 0x39, 0x49)
POWER_ON = bytes([0x80, 0x03])
READ_CH0 = bytes([0xAC])
READ_CH1 = bytes([0xAE])
READ_ID = bytes([0x8A])
#: Upper nibble of the ID register: 0x5 is the TSL2561, 0x1 the TSL2560.
PART_NUMBERS = (0x5, 0x1)


def probe(i2c, address: int) -> bool:
    try:
        i2c.write(address, READ_ID)
        reply = i2c.read(address, 1)
    except Exception:  # a NACK: not one of these chips
        return False
    return len(reply) == 1 and (reply[0] >> 4) in PART_NUMBERS


def lux(ch0: int, ch1: int) -> float:
    """The datasheet's T/FN/CL package formula, 1x gain and 402 ms."""
    if ch0 == 0:
        return 0.0
    ratio = ch1 / ch0
    if ratio <= 0.50:
        return 0.0304 * ch0 - 0.062 * ch0 * ratio ** 1.4
    if ratio <= 0.61:
        return 0.0224 * ch0 - 0.031 * ch1
    if ratio <= 0.80:
        return 0.0128 * ch0 - 0.0153 * ch1
    if ratio <= 1.30:
        return 0.00146 * ch0 - 0.00112 * ch1
    return 0.0


def decode(raw: bytes) -> Meaning:
    if len(raw) < 4:
        return [("TSL2561", "needs 4 bytes: CH0 then CH1, little-endian")]
    ch0 = raw[0] | (raw[1] << 8)
    ch1 = raw[2] | (raw[3] << 8)
    meaning = [("Visible + IR (CH0)", str(ch0)), ("Infrared (CH1)", str(ch1))]
    if ch0 >= 0xFFFF or ch1 >= 0xFFFF:
        meaning.append(("Note", "a channel is saturated; the lux figure is not valid"))
    meaning.append(("Illuminance", f"{lux(ch0, ch1):.1f} lux"))
    return meaning


def measure(i2c, address: int) -> Reading:
    i2c.write(address, POWER_ON)
    time.sleep(0.45)  # one 402 ms integration
    i2c.write(address, READ_CH0)
    ch0 = bytes(i2c.read(address, 2))
    i2c.write(address, READ_CH1)
    ch1 = bytes(i2c.read(address, 2))
    return Reading("TSL2561", f"0x{address:02X}", ch0 + ch1, decode(ch0 + ch1))


DEVICES = [
    Device(
        name="TSL2561",
        bus="i2c",
        summary="ambient light (visible + infrared), lux (also TSL2560)",
        addresses=ADDRESSES,
        probe=probe,
        measure=measure,
    ),
]
