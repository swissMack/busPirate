"""The probe cable colour reference.

The Seeed Studio cable is the project's reference colour order and is what the
firmware's own ``i`` command prints. **SparkFun cables are usually the reverse
order, and the v2go differs again** — so every wiring block in the dashboard
carries that warning and offers to read the legend off the connected device.
"""

from __future__ import annotations

# Bus Pirate probe header, pin 1 first, with the Seeed cable colours.
SEEED_CABLE = [
    ("GND", "black"),
    ("+3.3V", "brown"),
    ("+5.0V", "red"),
    ("ADC", "orange"),
    ("VPU", "yellow"),
    ("AUX", "green"),
    ("CLK", "blue"),
    ("MOSI", "purple"),
    ("CS", "grey"),
    ("MISO", "white"),
]

COLOURS = dict(SEEED_CABLE)

CABLE_CAVEAT = (
    "Colours are the Seeed cable order, which is the firmware reference. "
    "SparkFun cables are usually reversed and the v2go differs — use "
    "“Show my device’s legend” on the Connection panel to confirm."
)


def colour(signal: str) -> str:
    return COLOURS.get(signal, "")
