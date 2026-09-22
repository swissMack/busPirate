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

# Pixel geometry of static/img/board-v4.jpg (700x525), measured from the file
# with sips crops and a brightness profile across the header and the LED strip.
#
# The IO header is a 2x6 on 0.1" pitch. Its columns fall on x=525 and x=545 and
# its rows on y=220..325 in steps of 21. Left column top to bottom is
# GND, +3.3V, ADC, AUX1, CS, CLK; right column is +5V, VPU, AUX2, AUX,
# MISO, MOSI. The four LEDs sit on y=134, each directly above its silkscreen
# label: PWR 193, USB 280, MODE 367, VREG 453.
_BOARD_V4 = {
    "image": "/static/img/board-v4.jpg",
    "width": 700,
    "height": 525,
    "gutter": 290,
    "gutter_left": 290,
    "label": "Bus Pirate v4.0",
    # Twelve pins: the v4 header is a 2x6, not the v3's 2x5, and it carries
    # three AUX lines. Confirmed against hardware/v4/BusPirate-v4e.brd.png and
    # the firmware's own pin list in procMenu.c.
    "pins": {
        "GND": [525, 220],
        "+5V": [545, 220],
        "+3.3V": [525, 241],
        "VPU": [545, 241],
        "ADC": [525, 262],
        "AUX2": [545, 262],
        "AUX1": [525, 283],
        "AUX": [545, 283],
        "CS": [525, 304],
        "MISO": [545, 304],
        "CLK": [525, 325],
        "MOSI": [545, 325],
    },
    "leds": {
        "PWR": [193, 134],
        "USB": [280, 134],
        "MODE": [367, 134],
        "VREG": [453, 134],
    },
    "side": {
        "GND": "left", "+3.3V": "left", "ADC": "left",
        "AUX1": "left", "CS": "left", "CLK": "left",
        "+5V": "right", "VPU": "right", "AUX2": "right",
        "AUX": "right", "MISO": "right", "MOSI": "right",
    },
    "caveat": (
        "This is a Bus Pirate v4.0. Its header is a 2x6 with three AUX lines, "
        "not the v3's 2x5 \u2014 check the silkscreen next to your own header "
        "before trusting the positions."
    ),
}

#: Board geometry by variant. The dashboard serves one of these, chosen by
#: DeviceSession.effective_variant().
BOARDS: Dict[str, Dict[str, Any]] = {"v3": _BOARD_V3, "v4": _BOARD_V4}

#: What to present when nothing is connected, or the banner was unreadable.
DEFAULT_VARIANT = "v3"

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
    "v3": {
        "PWR": {
            "driver": "hardware",
            "inference": "powered",
            "means": "USB power is reaching the board",
        },
        "USB": {
            "driver": "hardware",
            "inference": "flash_on_traffic",
            "means": "data arriving from the host — the FT232RL's RXLED#",
        },
        "MODE": {
            "driver": "firmware",
            "inference": "connected",
            "means": "binary mode is active — the firmware clears it on an "
            "overrun, and it goes dark while the board's own terminal is "
            "open, since opening it leaves binary mode",
        },
        "VREG": {
            "driver": "hardware",
            "inference": "supplies",
            "means": "the on-board 3.3V and 5V supplies are on",
        },
    },
    "v4": {
        "PWR": {
            "driver": "hardware",
            "inference": "powered",
            "means": "USB power is reaching the board",
        },
        "USB": {
            "driver": "firmware",
            "inference": "always_dark",
            "means": "lit only while enumerating — dark once configured, "
            "which is the healthy state",
        },
        "MODE": {
            "driver": "firmware",
            "inference": "connected",
            "means": "binary mode is active — the firmware clears it on an "
            "overrun, and it goes dark while the board's own terminal is "
            "open, since opening it leaves binary mode",
        },
        "VREG": {
            "driver": "hardware",
            "inference": "supplies",
            "means": "the on-board 3.3V and 5V supplies are on",
        },
    },
}

_LED_NOTE_COMMON = (
    "There is no command that reads the LEDs back, so these are inferred from "
    "what the dashboard believes it has asked the board to do, not measured. "
    "The firmware can change them on its own — an overrun turns MODE off — so "
    "trust the board over this picture."
)

LED_NOTES: Dict[str, str] = {
    "v3": _LED_NOTE_COMMON
    + " On a v3 only MODE is software-driven; USB is the FT232RL's receive "
    "indicator and flickers on traffic.",
    "v4": _LED_NOTE_COMMON
    + " On a v4 both MODE and USB are software-driven, and USB goes dark once "
    "the board has enumerated — dark is the healthy state, not a fault.",
}

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
