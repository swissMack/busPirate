"""DS18B20 and relatives: 1-Wire thermometers.

The one to copy for 1-Wire. A chip is recognised by its family code — the
first byte of the ROM it reports in a search — so there is no probing.

The DS18S20 (family 0x10) counts in 0.5 °C steps and the others in
1/16 °C, which is why each family carries its own decoder.
"""

from __future__ import annotations

import time
from typing import Tuple

from ..onewire import ROM_MATCH
from . import Device, Meaning, Reading

CONVERT_T = 0x44
READ_SCRATCHPAD = 0xBE
#: A 12-bit conversion takes up to 750 ms.
CONVERSION_TIME = 0.8


def crc8(data: bytes) -> int:
    """Dallas/Maxim CRC-8 (x^8 + x^5 + x^4 + 1), as used on ROMs and scratchpads."""
    crc = 0
    for byte in data:
        for _ in range(8):
            mix = (crc ^ byte) & 0x01
            crc >>= 1
            if mix:
                crc ^= 0x8C
            byte >>= 1
    return crc


def _checksum(scratchpad: bytes) -> Tuple[str, str]:
    good = crc8(scratchpad[:8]) == scratchpad[8]
    return ("Checksum", f"0x{scratchpad[8]:02x}: " + ("OK" if good else "WRONG — the bytes were damaged"))


def _celsius(celsius: float, reset_value: bool) -> Meaning:
    meaning = [("Temperature", f"{celsius:.2f} °C ({celsius * 9 / 5 + 32:.1f} °F)")]
    if reset_value:
        meaning.append(("Note", "85 °C is the power-on value: the conversion may not "
                                "have run. Check the chip has enough power, and read again."))
    return meaning


def decode_b(scratchpad: bytes) -> Meaning:
    """DS18B20 / DS1822 / DS1825: a signed 16-bit count of 1/16 °C."""
    raw = int.from_bytes(scratchpad[0:2], "little", signed=True)
    meaning = _celsius(raw / 16.0, raw == 0x0550)
    if len(scratchpad) >= 9:
        meaning.append(_checksum(scratchpad))
    return meaning


def decode_s(scratchpad: bytes) -> Meaning:
    """DS18S20: half-degree steps, refined with COUNT_REMAIN / COUNT_PER_C."""
    raw = int.from_bytes(scratchpad[0:2], "little", signed=True)
    celsius = raw / 2.0
    if len(scratchpad) >= 8 and scratchpad[7]:
        count_remain, count_per_c = scratchpad[6], scratchpad[7]
        celsius = (raw >> 1) - 0.25 + (count_per_c - count_remain) / count_per_c
    meaning = _celsius(celsius, raw == 0x00AA)
    if len(scratchpad) >= 9:
        meaning.append(_checksum(scratchpad))
    return meaning


def _measure_with(name: str, decode):
    def measure(onewire, rom: bytes) -> Reading:
        onewire.reset()
        onewire.write(bytes([ROM_MATCH]) + rom + bytes([CONVERT_T]))
        time.sleep(CONVERSION_TIME)
        onewire.reset()
        onewire.write(bytes([ROM_MATCH]) + rom + bytes([READ_SCRATCHPAD]))
        scratchpad = onewire.read(9)
        return Reading(name, rom.hex(":"), scratchpad, decode(scratchpad))
    return measure


DEVICES = [
    Device("DS18B20", "onewire", "thermometer", families=(0x28,),
           measure=_measure_with("DS18B20", decode_b),
           verified=True),  # v4 + probe with a 4k7 pull-up, 2026-09-29
    Device("DS1822", "onewire", "thermometer", families=(0x22,),
           measure=_measure_with("DS1822", decode_b)),
    Device("DS1825", "onewire", "thermometer", families=(0x3B,),
           measure=_measure_with("DS1825", decode_b)),
    Device("DS18S20", "onewire", "thermometer", families=(0x10,),
           measure=_measure_with("DS18S20", decode_s)),
]
