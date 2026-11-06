"""The Bus Pirate v3 (and v2go, which shares its command set)."""

from typing import Dict

from ..capabilities import (
    BUS_PIRATE_ONLY, CAP_ADC, CAP_EXTENDED_AUX, CAP_FREQUENCY, CAP_PWM, CAP_SELF_TEST,
)
from ._board import Board
from ._wiring import LED_NOTE_COMMON

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

#: What drives each LED; see the inference kinds in buspirate.web.wiring.
LED_RULES: Dict[str, Dict[str, str]] = {
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
    }

LED_NOTE = (
    LED_NOTE_COMMON
    + " On a v3 only MODE is software-driven; USB is the FT232RL's receive "
    "indicator and flickers on traffic."
)


BOARD = Board(
    variant="v3",
    name="Bus Pirate v3",
    # On a v3 the PIC's hardware UART is the FT232R link, so extended AUX works.
    capabilities=BUS_PIRATE_ONLY
    | frozenset({CAP_PWM, CAP_ADC, CAP_FREQUENCY, CAP_SELF_TEST, CAP_EXTENDED_AUX}),
    simulated_name="simulated Bus Pirate v3",
    terminal_caption="The Bus Pirate's own terminal. Type a command; '?' lists them.",
    guide_page=None,
    manual="official",
    wiring=_BOARD_V3,
    led_rules=LED_RULES,
    led_note=LED_NOTE,
)
