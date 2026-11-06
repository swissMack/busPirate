"""The probe cable colour reference, and the reference card geometry.

The colours and the per-protocol pin mapping here are read off the Dangerous
Prototypes reference cards bundled in ``static/img/`` — not from memory. The
Seeed Studio cable is the project's reference order and is what the firmware's
own ``i`` command prints.

**SparkFun cables are usually the reverse order and the v2go differs again**,
so every wiring block in the dashboard carries that warning and offers to read
the legend off the connected device.

Image credit: reference cards from the Dangerous Prototypes wiki
(dangerousprototypes.com), CC BY-SA. See ``static/img/CREDITS.md``.
"""

from __future__ import annotations

from typing import Any, Dict

# Probe cable, pin 1 first, with the colours sampled from the Seeed cable card.
# Pin 1 is MISO and pin 10 is GND — the opposite end from what you might guess.
SEEED_CABLE = [
    ("MISO", "#000000", "black"),
    ("CS", "#ffffff", "white"),
    ("MOSI", "#a9a9a9", "grey"),
    # Purple, not the pink once sampled from the cable card image: the
    # firmware's own pin table calls CLK "PU", and a real v3 cable's CLK
    # lead is purple.
    ("CLK", "#9b59d6", "purple"),
    ("AUX", "#0433ff", "blue"),
    ("VPU", "#00f900", "green"),
    ("ADC", "#fffb00", "yellow"),
    ("+5V", "#ff9300", "orange"),
    ("+3.3V", "#ff2600", "red"),
    ("GND", "#945200", "brown"),
]

COLOURS = {signal: hexcode for signal, hexcode, _ in SEEED_CABLE}
COLOUR_NAMES = {signal: name for signal, _, name in SEEED_CABLE}

# What each signal becomes on each bus, from the reference card.
SIGNAL_ROLES = {
    "MOSI": {"1-Wire": "OWD", "UART": "TX", "I2C": "SDA", "SPI": "MOSI", "JTAG": "TDI"},
    "CLK": {"I2C": "SCL", "SPI": "CLK", "JTAG": "TCK"},
    "MISO": {"UART": "RX", "SPI": "MISO", "JTAG": "TDO"},
    "CS": {"SPI": "CS", "JTAG": "TMS"},
}

SIGNAL_NOTES = {
    "AUX": "Auxiliary I/O, frequency probe, PWM",
    "AUX1": "Second auxiliary pin, v4 only. Terminal mode only — the binary "
            "protocol has no command for it, so the dashboard cannot drive it.",
    "AUX2": "Third auxiliary pin, v4 only. Terminal mode only — the binary "
            "protocol has no command for it, so the dashboard cannot drive it.",
    "VPU": "Input for the pull-up resistors, 0-5V",
    "ADC": "A/D converter, max 6V, 10-bit, 500 ksps",
    "+5V": "Switchable supply, max 150 mA",
    "+3.3V": "Switchable supply, max 150 mA",
    "GND": "Ground to the test circuit",
}

# Pixel geometry of static/img/refcard.png (490x286), measured from the file.
REFCARD = {
    "image": "/static/img/refcard.png",
    "width": 490,
    "height": 286,
    # Column x-ranges, from the vertical rules in the image.
    "columns": {
        "signal": [4, 76],
        "HiZ": [76, 126],
        "1-Wire": [126, 208],
        "UART": [208, 287],
        "I2C": [287, 345],
        "SPI": [345, 416],
        "JTAG": [416, 483],
    },
    # Row y-ranges. The first five come from the horizontal rules; the lower
    # block is one merged cell in the artwork, split evenly by its five labels.
    "rows": {
        "header": [4, 27],
        "MOSI": [27, 56],
        "CLK": [56, 85],
        "MISO": [85, 114],
        "CS": [114, 142],
        "AUX": [142, 170],
        "VPU": [170, 198],
        "ADC": [198, 225],
        "supplies": [225, 253],
        "GND": [253, 281],
    },
}

# Pixel geometry of static/img/seeed-cable.png (490x301).
CABLE_CARD = {
    "image": "/static/img/seeed-cable.png",
    "width": 490,
    "height": 301,
    "band": [228, 285],  # y range of the colour swatches
    "swatches": {
        "MISO": [128, 159],
        "CS": [160, 193],
        "MOSI": [195, 225],
        "CLK": [229, 258],
        "AUX": [262, 292],
        "VPU": [295, 326],
        "ADC": [328, 359],
        "+5V": [362, 392],
        "+3.3V": [396, 425],
        "GND": [429, 459],
    },
}

# Each board's picture, pin geometry, per-panel wording and LEDs live in its
# own module in buspirate.boards. These views keep the names the server,
# the session and the panels have always used.
from ..boards import DEFAULT_VARIANT, REGISTRY  # noqa: E402,F401
from ..boards.bitpirate import DOCK_GEOMETRY, DOCK_HEADER  # noqa: E402,F401
from ..boards.bp6 import BP6_GEOMETRY, BP6_HEADER  # noqa: E402,F401

#: Board geometry by variant. The dashboard serves one of these, chosen by
#: DeviceSession.effective_variant().
BOARDS: Dict[str, Dict[str, Any]] = {v: b.wiring for v, b in REGISTRY.items()}

#: What drives each LED, and how the dashboard should infer its state.
#:
#: ``inference`` is one of:
#:   "powered"          — lit whenever the port is open
#:   "connected"        — lit while the port is open and in binary mode; dark
#:                        while the board's own terminal holds the port
#:   "supplies"         — follows the on-board 3.3V/5V regulators
#:   "flash_on_traffic" — a pulse the client drives from the traffic feed
#:   "always_dark"      — never reported lit
LED_RULES: Dict[str, Dict[str, Dict[str, str]]] = {
    v: b.led_rules for v, b in REGISTRY.items()
}

LED_NOTES: Dict[str, str] = {v: b.led_note for v, b in REGISTRY.items()}


CABLE_CAVEAT = (
    "Colours and pin order are the Seeed/Adafruit cable, which is the "
    "firmware reference — pin 1 is MISO (black) and pin 10 is GND (brown). "
    "SparkFun cables are usually reversed and the v2go differs, so check "
    "“Show the cable legend” on the Connection panel against your own."
)

POWER_NOTE = (
    "The power switch turns on the 3.3V and 5V supplies together — there is "
    "no command to pick one, and each is good for about 150 mA. You choose the "
    "voltage by which probe wire you connect to the target's VCC. Never "
    "connect both."
)

PULLUP_RAIL_NOTE = (
    "On a Bus Pirate v4 the pull-up rail can be switched between 3.3V and 5V "
    "in software. On a v3 the pull-ups follow whatever you feed the VPU pin, "
    "so tie VPU to the target's own supply."
)


def colour(signal: str) -> str:
    """The cable colour for a signal, as a CSS hex value."""
    return COLOURS.get(signal, "")


def colour_name(signal: str) -> str:
    return COLOUR_NAMES.get(signal, "")
