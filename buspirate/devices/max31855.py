"""MAX31855 thermocouple converter (SPI).

The one to copy for SPI. SPI has no addresses and no scan, so the app cannot
find the chip: the user picks it from a list, and ``measure`` takes no
address. This chip has no commands either — take CS low and clock out 4
bytes.

Not yet tried on real hardware: the decoder is checked against the
datasheet's own example values only.
"""

from __future__ import annotations

from . import Device, Meaning, Reading

_FAULTS = (
    (0x01, "open circuit — no thermocouple connected"),
    (0x02, "thermocouple shorted to GND"),
    (0x04, "thermocouple shorted to VCC"),
)


def _signed(value: int, bits: int) -> int:
    return value - (1 << bits) if value & (1 << (bits - 1)) else value


def decode(raw: bytes) -> Meaning:
    if len(raw) < 4:
        return [("MAX31855", f"needs 4 bytes to translate, got {len(raw)}")]
    word = int.from_bytes(raw[:4], "big")
    if word in (0x00000000, 0xFFFFFFFF):
        return [("Note", f"all bits {'0' if word == 0 else '1'}: nothing is driving MISO. "
                         "Check MISO, CS and the chip's power.")]
    thermocouple = _signed(word >> 18, 14) * 0.25
    internal = _signed((word >> 4) & 0xFFF, 12) * 0.0625
    meaning = [
        ("Thermocouple", f"{thermocouple:.2f} °C"),
        ("Chip (cold junction)", f"{internal:.4f} °C"),
    ]
    if word & 0x10000:
        faults = [text for bit, text in _FAULTS if word & bit] or ["unspecified"]
        meaning.insert(0, ("Fault", "; ".join(faults) + " — the thermocouple reading is not valid"))
    return meaning


def measure(spi) -> Reading:
    raw = spi.write_then_read(b"", 4)
    return Reading("MAX31855", "CS", raw, decode(raw))


DEVICES = [
    Device(
        name="MAX31855",
        bus="spi",
        summary="K-type thermocouple → °C",
        measure=measure,
    ),
]
