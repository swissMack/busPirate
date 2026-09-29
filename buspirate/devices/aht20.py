"""AHT20 / AHT21 temperature + humidity (I2C, 0x38).

The simplest kind of sensor, and the one to copy: a fixed address, no ID
register, one "measure" command, then a 7-byte reply.
"""

from __future__ import annotations

import time

from . import Device, Meaning, Reading

ADDRESS = 0x38
MEASURE = bytes([0xAC, 0x33, 0x00])
CALIBRATE = bytes([0xBE, 0x08, 0x00])


def crc8(data: bytes) -> int:
    """CRC-8, polynomial 0x31, initial 0xFF — the AHT20's checksum."""
    crc = 0xFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ 0x31) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


def decode(raw: bytes) -> Meaning:
    """Translate the 6- or 7-byte measurement reply."""
    if len(raw) < 6:
        return [("AHT20", f"needs at least 6 bytes to translate, got {len(raw)}")]
    status = raw[0]
    humidity = ((raw[1] << 12) | (raw[2] << 4) | (raw[3] >> 4)) * 100.0 / (1 << 20)
    temperature = (((raw[3] & 0x0F) << 16) | (raw[4] << 8) | raw[5]) * 200.0 / (1 << 20) - 50
    state = [
        "busy — the measurement was not finished" if status & 0x80 else "finished",
        "calibrated" if status & 0x08 else "NOT calibrated",
    ]
    meaning = [
        ("Temperature", f"{temperature:.2f} °C"),
        ("Humidity", f"{humidity:.1f} %RH"),
        ("Status", f"0x{status:02x}: " + ", ".join(state)),
    ]
    if len(raw) >= 7:
        good = crc8(raw[:6]) == raw[6]
        meaning.append(
            ("Checksum", f"0x{raw[6]:02x}: " + ("OK" if good else "WRONG — the bytes were damaged"))
        )
    if status & 0x80:
        meaning.append(("Note", "values above are stale; write AC 33 00, wait, read again"))
    return meaning


def measure(i2c, address: int) -> Reading:
    if not i2c.read(address, 1)[0] & 0x08:
        i2c.write(address, CALIBRATE)
        time.sleep(0.01)
    i2c.write(address, MEASURE)
    time.sleep(0.08)
    raw = i2c.read(address, 7)
    for _ in range(3):
        if not raw[0] & 0x80:
            break
        time.sleep(0.02)
        raw = i2c.read(address, 7)
    return Reading("AHT20", f"0x{address:02X}", raw, decode(raw))


def explain_read(address: int, data: bytes) -> Meaning:
    if len(data) < 6:
        return []
    return [("Chip", "AHT20 (by its address, 0x38)")] + decode(data)


DEVICES = [
    Device(
        name="AHT20",
        bus="i2c",
        summary="temperature + humidity",
        addresses=(ADDRESS,),
        measure=measure,
        explain_read=explain_read,
        verified=True,  # v4 + AHT20/BMP280 module, 2026-09-29
    ),
]
