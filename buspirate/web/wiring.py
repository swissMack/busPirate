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
    ("CLK", "#ff85ff", "pink"),
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

# Pixel geometry of static/img/board-v3.png (700x525), measured from the file
# and checked against the board's own silkscreen.
#
# The IDC header is 2x5. The left column is labelled GND, +5V, VPU, CLK, CS
# from the top; the right column is +3.3V, ADC, AUX, MOSI, MISO, though the
# photo crops those labels, which is why the diagram redraws them.
_BOARD_V3 = {
    "image": "/static/img/board-v3.png",
    "width": 700,
    "height": 525,
    # Label space either side of the photo. Wide enough for the longest
    # callout, which is SPI's "CLK \u2192 SCK / CLK".
    "gutter": 290,
    "gutter_left": 290,
    "label": "Bus Pirate v3.6",
    "pins": {
        "GND": [570, 202],
        "+3.3V": [599, 202],
        "+5V": [570, 228],
        "ADC": [599, 228],
        "VPU": [570, 256],
        "AUX": [599, 256],
        "CLK": [570, 283],
        "MOSI": [599, 283],
        "CS": [570, 311],
        "MISO": [599, 311],
    },
    # The four indicator LEDs along the top edge, left to right, each sitting
    # just above its own silkscreen label.
    "leds": {
        "PWR": [198, 98],
        "USB": [300, 98],
        "MODE": [402, 98],
        "VREG": [505, 98],
    },
    #: Which side of the header each column sits on, for label placement.
    "side": {
        "GND": "left", "+5V": "left", "VPU": "left", "CLK": "left", "CS": "left",
        "+3.3V": "right", "ADC": "right", "AUX": "right", "MOSI": "right",
        "MISO": "right",
    },
    "caveat": (
        "This is a Bus Pirate v3.6. The v4 is laid out differently — check the "
        "silkscreen next to your own header before trusting the positions."
    ),
}

#: Board geometry by variant. The dashboard serves one of these, chosen by
#: DeviceSession.effective_variant().
BOARDS: Dict[str, Dict[str, Any]] = {"v3": _BOARD_V3}

#: What to present when nothing is connected, or the banner was unreadable.
DEFAULT_VARIANT = "v3"

LED_NOTE = (
    "There is no command that reads the LEDs back, so these are inferred from "
    "what the dashboard believes it has asked the board to do, not measured. "
    "The firmware can change them on its own — an overrun sniff turns MODE "
    "off — so trust the board over this picture."
)

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
