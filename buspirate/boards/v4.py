"""The Bus Pirate v4."""

from typing import Dict

from ..capabilities import BUS_PIRATE_ONLY, CAP_ADC, CAP_FREQUENCY, CAP_PULLUP_VOLTAGE, CAP_PWM
from ._board import Board
from ._wiring import LED_NOTE_COMMON

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

#: What drives each LED; see the inference kinds in buspirate.web.wiring.
LED_RULES: Dict[str, Dict[str, str]] = {
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
    }

LED_NOTE = (
    LED_NOTE_COMMON
    + " On a v4 both MODE and USB are software-driven, and USB goes dark once "
    "the board has enumerated — dark is the healthy state, not a fault."
)


BOARD = Board(
    variant="v4",
    name="Bus Pirate v4",
    # The wiki notes binary self-tests are v2go/v3 hardware only.
    # No extended AUX: the firmware reads its sub-command from the PIC's
    # hardware UART, which on a v4 is not the host link — it waits
    # forever. Found on a real v4 on firmware 7.0, 2026-09-28.
    capabilities=BUS_PIRATE_ONLY
    | frozenset({CAP_PWM, CAP_ADC, CAP_FREQUENCY, CAP_PULLUP_VOLTAGE}),
    simulated_name="simulated Bus Pirate v4",
    terminal_caption="The Bus Pirate's own terminal. Type a command; '?' lists them.",
    guide_page="bus-pirate-v4",
    manual="official",
    wiring=_BOARD_V4,
    led_rules=LED_RULES,
    led_note=LED_NOTE,
)
