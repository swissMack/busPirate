"""AD595 K-type thermocouple amplifier (analog, read on the ADC).

The one to copy for an analog sensor. It has no bus at all: it puts out a
voltage, the Bus Pirate's ADC lead measures it, and ``from_volts`` turns
that voltage into what it means.

The datasheet's transfer function is

    output = (K-type thermocouple voltage + 11 µV) × 247.3

so this undoes the gain and offset, then converts the thermocouple voltage
to °C with the NIST ITS-90 inverse polynomial for type K. That is more exact
than the "10 mV per °C" rule of thumb, which is only right near 25 °C.
"""

from __future__ import annotations

from . import Device, Meaning

GAIN = 247.3
OFFSET_MV = 0.011  # the 11 µV the datasheet adds before the gain

#: NIST ITS-90, type K, inverse coefficients for 0–500 °C (0–20.644 mV).
_K_INVERSE_0_500 = (
    0.0,
    2.508355e01,
    7.860106e-02,
    -2.503131e-01,
    8.315270e-02,
    -1.228034e-02,
    9.804036e-04,
    -4.413030e-05,
    1.057734e-06,
    -1.052755e-08,
)
K_MAX_MV = 20.644

#: With a 5 V supply the output tops out a little below the rail; a missing
#: or broken thermocouple drives it there too.
NEAR_RAIL_VOLTS = 4.8
#: The datasheet rounds its 0 °C output to 2.7 mV, and the ADC steps are
#: about 6 mV: treat anything within half a degree of zero as zero.
ZERO_TOLERANCE_MV = 0.02


def type_k_celsius(millivolts: float) -> float:
    """°C for a type K thermocouple voltage, 0–500 °C (NIST ITS-90)."""
    return sum(c * millivolts ** n for n, c in enumerate(_K_INVERSE_0_500))


def from_volts(volts: float) -> Meaning:
    thermocouple_mv = volts * 1000.0 / GAIN - OFFSET_MV
    # A flat 0 V could be 0 °C, below freezing, or no power at all; only a
    # reading just above it is close enough to call 0 °C.
    if volts > 0 and -ZERO_TOLERANCE_MV <= thermocouple_mv < 0:
        thermocouple_mv = 0.0
    if thermocouple_mv < 0:
        return [("Temperature", "0 °C or below"),
                ("Note", "on a single 5 V supply the AD595 cannot go below 0 °C; "
                         "a reading of 0 V can also mean it has no power")]
    if thermocouple_mv > K_MAX_MV:
        return [("Note", "above the 0–500 °C this translation covers")]
    meaning = [
        ("Temperature", f"{type_k_celsius(thermocouple_mv):.1f} °C"),
        ("Thermocouple", f"{thermocouple_mv:.3f} mV (type K)"),
    ]
    if volts >= NEAR_RAIL_VOLTS:
        meaning.append(("Note", "the output is near the 5 V rail: an open or "
                                "disconnected thermocouple reads like this"))
    return meaning


DEVICES = [
    Device(
        name="AD595",
        bus="analog",
        summary="K-type thermocouple amplifier",
        from_volts=from_volts,
        verified=True,  # v4 ADC, probe held in the fingers: 0.37 V = 36.9 °C, 2026-09-29
    ),
]
