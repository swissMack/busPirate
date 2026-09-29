"""Recognise common I2C sensors and translate their bytes into real units.

The Bus Pirate only ever sees bytes. This module knows, per chip, which
bytes to ask for and the datasheet formula that turns them into °C, %RH or
hPa, so the dashboard can show the raw hex *and* what it means.

Two kinds of entry point:

* :func:`read_sensor` — identify the chip at an address, make it measure,
  and return the raw bytes with the translation. Talks to the bus.
* :func:`explain_read` / :func:`explain_register_read` — translate bytes
  the user already read by hand. They may read calibration data from the
  chip when a formula needs it, but never start a measurement.

Chips known so far: AHT20 / AHT21 (0x38) and BMP280 / BME280 (0x76, 0x77).
Adding one means a decoder here and an entry in :func:`identify`.
"""

from __future__ import annotations

import struct
import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

AHT20_ADDRESS = 0x38
BMP280_ADDRESSES = (0x76, 0x77)

AHT20_MEASURE = bytes([0xAC, 0x33, 0x00])
AHT20_CALIBRATE = bytes([0xBE, 0x08, 0x00])

BMP280_REG_CALIBRATION = 0x88
BMP280_REG_CHIP_ID = 0xD0
BMP280_REG_CTRL_MEAS = 0xF4
BMP280_REG_DATA = 0xF7
#: Temperature x1, pressure x1, forced mode: one measurement, then sleep.
BMP280_FORCED_X1 = 0x25

BMP280_CHIP_IDS = {
    0x56: "BMP280 (sample)",
    0x57: "BMP280 (sample)",
    0x58: "BMP280",
    0x60: "BME280",
}

#: A reading as label/value pairs, ready for a key-value table.
Meaning = List[Tuple[str, str]]


@dataclass
class SensorReading:
    chip: str
    address: int
    raw: bytes
    meaning: Meaning = field(default_factory=list)


# ---------------------------------------------------------------------------
# AHT20
# ---------------------------------------------------------------------------


def aht20_crc(data: bytes) -> int:
    """CRC-8, polynomial 0x31, initial 0xFF — the AHT20's checksum."""
    crc = 0xFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ 0x31) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


def decode_aht20(raw: bytes) -> Meaning:
    """Translate the AHT20's 6- or 7-byte measurement reply."""
    if len(raw) < 6:
        return [("AHT20", f"needs at least 6 bytes to translate, got {len(raw)}")]
    status = raw[0]
    humidity = ((raw[1] << 12) | (raw[2] << 4) | (raw[3] >> 4)) * 100.0 / (1 << 20)
    temperature = (((raw[3] & 0x0F) << 16) | (raw[4] << 8) | raw[5]) * 200.0 / (1 << 20) - 50
    state = []
    state.append("busy — the measurement was not finished" if status & 0x80 else "finished")
    state.append("calibrated" if status & 0x08 else "NOT calibrated")
    meaning = [
        ("Temperature", f"{temperature:.2f} °C"),
        ("Humidity", f"{humidity:.1f} %RH"),
        ("Status", f"0x{status:02x}: " + ", ".join(state)),
    ]
    if len(raw) >= 7:
        good = aht20_crc(raw[:6]) == raw[6]
        meaning.append(
            ("Checksum", f"0x{raw[6]:02x}: " + ("OK" if good else "WRONG — the bytes were damaged"))
        )
    if status & 0x80:
        meaning.append(("Note", "values above are stale; write AC 33 00, wait, read again"))
    return meaning


def read_aht20(i2c, address: int = AHT20_ADDRESS) -> SensorReading:
    status = i2c.read(address, 1)[0]
    if not status & 0x08:
        i2c.write(address, AHT20_CALIBRATE)
        time.sleep(0.01)
    i2c.write(address, AHT20_MEASURE)
    time.sleep(0.08)
    raw = i2c.read(address, 7)
    for _ in range(3):
        if not raw[0] & 0x80:
            break
        time.sleep(0.02)
        raw = i2c.read(address, 7)
    return SensorReading("AHT20", address, raw, decode_aht20(raw))


# ---------------------------------------------------------------------------
# BMP280
# ---------------------------------------------------------------------------

_BMP280_CAL_NAMES = ("T1", "T2", "T3", "P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8", "P9")


def bmp280_calibration(cal: bytes) -> Tuple[int, ...]:
    """The 12 calibration words from registers 0x88–0x9F (little-endian)."""
    return struct.unpack("<HhhHhhhhhhhh", bytes(cal[:24]))


def bmp280_compensate(data: bytes, cal: bytes) -> Tuple[float, float]:
    """Datasheet floating-point compensation: (°C, hPa) from 0xF7–0xFC."""
    t1, t2, t3, p1, p2, p3, p4, p5, p6, p7, p8, p9 = bmp280_calibration(cal)
    adc_p = (data[0] << 12) | (data[1] << 4) | (data[2] >> 4)
    adc_t = (data[3] << 12) | (data[4] << 4) | (data[5] >> 4)
    v1 = (adc_t / 16384.0 - t1 / 1024.0) * t2
    v2 = ((adc_t / 131072.0 - t1 / 8192.0) ** 2) * t3
    t_fine = v1 + v2
    temperature = t_fine / 5120.0
    v1 = t_fine / 2.0 - 64000.0
    v2 = v1 * v1 * p6 / 32768.0 + v1 * p5 * 2.0
    v2 = v2 / 4.0 + p4 * 65536.0
    v1 = (p3 * v1 * v1 / 524288.0 + p2 * v1) / 524288.0
    v1 = (1.0 + v1 / 32768.0) * p1
    if v1 == 0:
        return temperature, float("nan")
    p = 1048576.0 - adc_p
    p = (p - v2 / 4096.0) * 6250.0 / v1
    v1 = p9 * p * p / 2147483648.0
    v2 = p * p8 / 32768.0
    return temperature, (p + (v1 + v2 + p7) / 16.0) / 100.0


def decode_bmp280(data: bytes, cal: bytes, chip: str = "BMP280") -> Meaning:
    adc_p = (data[0] << 12) | (data[1] << 4) | (data[2] >> 4)
    if adc_p == 0x80000:
        # The reset value: the chip is asleep and has never measured.
        return [("Note", f"{chip} has not measured yet (it reads 80 00 00, its reset "
                         "value). Write F4 25 to it, then read again.")]
    temperature, pressure = bmp280_compensate(data, cal)
    meaning = [
        ("Temperature", f"{temperature:.2f} °C"),
        ("Pressure", f"{pressure:.2f} hPa"),
    ]
    if chip == "BME280":
        meaning.append(("Note", "a BME280 also measures humidity; that is not translated yet"))
    return meaning


def bmp280_chip(i2c, address: int) -> Optional[str]:
    try:
        chip_id = i2c.read_register(address, BMP280_REG_CHIP_ID, 1)[0]
    except Exception:
        return None
    return BMP280_CHIP_IDS.get(chip_id)


def read_bmp280(i2c, address: int, chip: str = "BMP280") -> SensorReading:
    cal = i2c.read_register(address, BMP280_REG_CALIBRATION, 24)
    i2c.write(address, bytes([BMP280_REG_CTRL_MEAS, BMP280_FORCED_X1]))
    time.sleep(0.02)
    data = i2c.read_register(address, BMP280_REG_DATA, 6)
    return SensorReading(chip, address, data, decode_bmp280(data, cal, chip))


# ---------------------------------------------------------------------------
# Identify, measure, explain
# ---------------------------------------------------------------------------


def identify(i2c, address: int) -> Optional[str]:
    """Name the chip at ``address``, or ``None`` if it is not one we know.

    Address alone decides the AHT20 (nothing else common lives at 0x38 and
    it has no ID register); 0x76/0x77 are shared, so those are asked for
    their chip ID.
    """
    if address == AHT20_ADDRESS:
        return "AHT20"
    if address in BMP280_ADDRESSES:
        return bmp280_chip(i2c, address)
    return None


def read_sensor(i2c, address: int) -> Optional[SensorReading]:
    """Identify, measure and translate. ``None`` if the chip is unknown."""
    chip = identify(i2c, address)
    if chip is None:
        return None
    if chip == "AHT20":
        return read_aht20(i2c, address)
    return read_bmp280(i2c, address, chip)


def explain_read(address: int, data: bytes) -> Meaning:
    """Translate a plain read (no register) from a known chip, if possible."""
    if address == AHT20_ADDRESS and len(data) >= 6:
        return [("Chip", "AHT20 (by its address, 0x38)")] + decode_aht20(data)
    return []


def explain_register_read(i2c, address: int, register: int, data: bytes) -> Meaning:
    """Translate a register read from a known chip, if possible.

    May read the chip's calibration block, because the BMP280's raw
    measurement means nothing without it.
    """
    if address not in BMP280_ADDRESSES:
        return []
    end = register + len(data)
    meaning: Meaning = []
    if register <= BMP280_REG_CHIP_ID < end:
        chip_id = data[BMP280_REG_CHIP_ID - register]
        name = BMP280_CHIP_IDS.get(chip_id)
        meaning.append(
            ("Chip ID", f"0x{chip_id:02x}: " + (name or "not a BMP280/BME280"))
        )
        if name is None:
            return meaning
    if register == BMP280_REG_CALIBRATION and len(data) >= 24:
        words = bmp280_calibration(data)
        meaning.append(
            ("Calibration", ", ".join(f"{n}={v}" for n, v in zip(_BMP280_CAL_NAMES, words)))
        )
    if register == BMP280_REG_DATA and len(data) >= 6:
        chip = bmp280_chip(i2c, address)
        if chip is None:
            return meaning
        cal = i2c.read_register(address, BMP280_REG_CALIBRATION, 24)
        meaning.append(("Chip", chip))
        meaning += decode_bmp280(data[:6], cal, chip)
    if register == BMP280_REG_CTRL_MEAS and len(data) >= 1:
        mode = {0: "sleep", 1: "forced", 2: "forced", 3: "normal (measuring continuously)"}
        meaning.append(("Mode", mode[data[0] & 0x03]))
    return meaning
