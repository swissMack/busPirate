"""Si7021 / HTU21D / SHT21 humidity + temperature (I2C, 0x40).

``F5`` measures humidity without holding the clock; the temperature taken for
that same measurement is then read back with ``E0`` — no second conversion.
Neither reply carries a CRC in this mode.
"""

from __future__ import annotations

import time

from . import Device, Meaning, Reading

ADDRESS = 0x40
MEASURE_HUMIDITY = bytes([0xF5])
READ_TEMPERATURE = bytes([0xE0])


def decode(humidity_raw: bytes, temperature_raw: bytes) -> Meaning:
    if len(humidity_raw) < 2 or len(temperature_raw) < 2:
        return [("Si7021", "needs 2 bytes each for humidity and temperature")]
    # The two lowest bits are status flags on the HTU21; they read 0 on the Si7021.
    h = ((humidity_raw[0] << 8) | humidity_raw[1]) & 0xFFFC
    t = ((temperature_raw[0] << 8) | temperature_raw[1]) & 0xFFFC
    return [
        ("Temperature", f"{-46.85 + 175.72 * t / 65536:.2f} °C"),
        ("Humidity", f"{min(100.0, max(0.0, -6 + 125 * h / 65536)):.1f} %RH"),
    ]


def measure(i2c, address: int) -> Reading:
    i2c.write(address, MEASURE_HUMIDITY)
    time.sleep(0.03)  # 12-bit conversion is at most ~23 ms
    humidity = i2c.read(address, 2)
    i2c.write(address, READ_TEMPERATURE)
    temperature = i2c.read(address, 2)
    return Reading(
        "Si7021", f"0x{address:02X}", bytes(humidity) + bytes(temperature),
        decode(humidity, temperature),
    )


DEVICES = [
    Device(
        name="Si7021",
        bus="i2c",
        summary="humidity + temperature (also HTU21D, SHT21)",
        addresses=(ADDRESS,),
        measure=measure,
    ),
]
