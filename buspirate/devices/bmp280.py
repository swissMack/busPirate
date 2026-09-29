"""BMP280 / BME280 temperature + pressure (I2C, 0x76 or 0x77).

The one to copy for a chip that shares its address with others (it is
confirmed by its chip-ID register) and whose raw reading means nothing
without the chip's own calibration numbers.
"""

from __future__ import annotations

import struct
import time
from typing import Optional, Tuple

from . import Device, Meaning, Reading

ADDRESSES = (0x76, 0x77)
REG_CALIBRATION = 0x88
REG_CHIP_ID = 0xD0
REG_CTRL_MEAS = 0xF4
REG_DATA = 0xF7
#: Temperature x1, pressure x1, forced mode: one measurement, then sleep.
FORCED_X1 = 0x25

CHIP_IDS = {
    0x56: "BMP280 (sample)",
    0x57: "BMP280 (sample)",
    0x58: "BMP280",
    0x60: "BME280",
}

_CAL_NAMES = ("T1", "T2", "T3", "P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8", "P9")


def calibration(cal: bytes) -> Tuple[int, ...]:
    """The 12 calibration words from registers 0x88–0x9F (little-endian)."""
    return struct.unpack("<HhhHhhhhhhhh", bytes(cal[:24]))


def compensate(data: bytes, cal: bytes) -> Tuple[float, float]:
    """The datasheet's floating-point compensation: (°C, hPa) from 0xF7–0xFC."""
    t1, t2, t3, p1, p2, p3, p4, p5, p6, p7, p8, p9 = calibration(cal)
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


def decode(data: bytes, cal: bytes, chip: str = "BMP280") -> Meaning:
    adc_p = (data[0] << 12) | (data[1] << 4) | (data[2] >> 4)
    if adc_p == 0x80000:
        # The reset value: the chip is asleep and has never measured.
        return [("Note", f"{chip} has not measured yet (it reads 80 00 00, its reset "
                         "value). Write F4 25 to it, then read again.")]
    temperature, pressure = compensate(data, cal)
    meaning = [
        ("Temperature", f"{temperature:.2f} °C"),
        ("Pressure", f"{pressure:.2f} hPa"),
    ]
    if chip == "BME280":
        meaning.append(("Note", "a BME280 also measures humidity; that is not translated yet"))
    return meaning


def chip_name(i2c, address: int) -> Optional[str]:
    try:
        chip_id = i2c.read_register(address, REG_CHIP_ID, 1)[0]
    except Exception:  # a NACK: nothing there that answers like a BMP280
        return None
    return CHIP_IDS.get(chip_id)


def _probe(wanted: str):
    def probe(i2c, address: int) -> bool:
        name = chip_name(i2c, address)
        return name is not None and name.startswith(wanted)
    return probe


def measure(i2c, address: int) -> Reading:
    chip = chip_name(i2c, address) or "BMP280"
    cal = i2c.read_register(address, REG_CALIBRATION, 24)
    # A plain write, not write_register: the Bit Pirate has no write_register.
    i2c.write(address, bytes([REG_CTRL_MEAS, FORCED_X1]))
    time.sleep(0.02)
    data = i2c.read_register(address, REG_DATA, 6)
    return Reading(chip, f"0x{address:02X}", data, decode(data, cal, chip))


def explain_register(i2c, address: int, register: int, data: bytes) -> Meaning:
    end = register + len(data)
    meaning: Meaning = []
    if register <= REG_CHIP_ID < end:
        chip_id = data[REG_CHIP_ID - register]
        name = CHIP_IDS.get(chip_id)
        meaning.append(("Chip ID", f"0x{chip_id:02x}: " + (name or "not a BMP280/BME280")))
        if name is None:
            return meaning
    if register == REG_CALIBRATION and len(data) >= 24:
        words = calibration(data)
        meaning.append(
            ("Calibration", ", ".join(f"{n}={v}" for n, v in zip(_CAL_NAMES, words)))
        )
    if register == REG_DATA and len(data) >= 6:
        chip = chip_name(i2c, address)
        if chip is None:
            return meaning
        cal = i2c.read_register(address, REG_CALIBRATION, 24)
        meaning.append(("Chip", chip))
        meaning += decode(data[:6], cal, chip)
    if register == REG_CTRL_MEAS and len(data) >= 1:
        mode = {0: "sleep", 1: "forced", 2: "forced", 3: "normal (measuring continuously)"}
        meaning.append(("Mode", mode[data[0] & 0x03]))
    return meaning


DEVICES = [
    Device(
        name="BMP280",
        bus="i2c",
        summary="temperature + pressure",
        addresses=ADDRESSES,
        probe=_probe("BMP280"),
        measure=measure,
        explain_register=explain_register,
        verified=True,  # v4 + AHT20/BMP280 module, 2026-09-29
    ),
    Device(
        name="BME280",
        bus="i2c",
        summary="temperature + pressure (humidity not translated yet)",
        addresses=ADDRESSES,
        probe=_probe("BME280"),
        measure=measure,
    ),
]
