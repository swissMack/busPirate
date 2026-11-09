"""The Bus Pirate 6 (and, untested, the Bus Pirate 5), over BPIO2."""

from typing import Dict

from ..capabilities import (
    CAP_ONEWIRE, CAP_PSU_PROGRAMMABLE, CAP_PSU_READOUT, CAP_SPI_FLASH_PROGRAM, CAP_SPI_MODES,
    CAP_SUPPLIES, CAP_UART_BUFFERED,
)
from ._board import Board
from ._wiring import wire

# The Bus Pirate 6's 10-pin header, as drawn in static/img/board-bp6.svg by
# scripts/draw_bp6_board.py from this same list. Pin map from the firmware's
# src/pirate.h (M_I2C_SDA BIO0, M_SPI_CLK BIO6, M_UART_TX BIO4, ...).
BP6_HEADER = ["VOUT", "IO0", "IO1", "IO2", "IO3", "IO4", "IO5", "IO6", "IO7", "GND"]
#: The Bus Pirate 6 probe cable (and the Bit Pirate dock's, which follows it):
#: header pin label -> wire colour.
BP6_CABLE: Dict[str, str] = {
    "VOUT": "red", "IO0": "orange", "IO1": "yellow", "IO2": "green",
    "IO3": "blue", "IO4": "purple", "IO5": "brown", "IO6": "grey",
    "IO7": "white", "GND": "black",
}
BP6_GEOMETRY = {"width": 700, "height": 525, "x": 350, "first_y": 110, "pitch": 34}


def _bp6_pins():
    g = BP6_GEOMETRY
    pins = {name: [g["x"], g["first_y"] + i * g["pitch"]] for i, name in enumerate(BP6_HEADER)}
    side = {name: ("left" if i % 2 == 0 else "right") for i, name in enumerate(BP6_HEADER)}
    return pins, side


_BP6_PINS, _BP6_SIDE = _bp6_pins()
_BP6_GND = wire("GND", "GND", "always connect this first")
_BP6_VOUT = wire("VOUT", "VCC", "the adjustable supply — set it on Power & pull-ups")
_BP6_NOTE = ("Every IO pin is buffered and works from 1.2 to 5 V, following VOUT. "
             "Switch the supply on, or feed the target's own voltage into VOUT.")

#: On a Bus Pirate 6 the bus panels' boxes only switch things on; the Power
#: & pull-ups panel sets the voltage and switches them off.
_BP6_PARAM_LABELS = {
    "power": "Switch on the supply (as set on Power & pull-ups)",
    "pullups": "Switch on the pull-ups",
}

_BOARD_BP6 = {
    "image": "/static/img/board-bp6.svg",
    "width": BP6_GEOMETRY["width"],
    "height": BP6_GEOMETRY["height"],
    "gutter": 290,
    "gutter_left": 290,
    "label": "Bus Pirate 6",
    "pins": _BP6_PINS,
    "side": _BP6_SIDE,
    "leds": {},
    #: Its own probe cable, not the Seeed one: no cable colours.
    "cable": False,
    "caveat": ("Drawn from the firmware's pin map. Your probe cable's colours may "
               "differ — follow the labels printed on the Bus Pirate 6's case."),
    "panels": {
        "terminal": {
            "blurb": "The Bus Pirate 6's own terminal — the `HiZ>` prompt, on its first USB port.",
            "actions": {
                "open_terminal": {
                    "confirm": "",
                    "help": "Opens the Bus Pirate 6's terminal port. Nothing is "
                    "reset. Everything else in the dashboard is unavailable until you "
                    "close it; when you do, the dashboard re-reads the board.",
                },
            },
        },
        "i2c": {
            "param_labels": _BP6_PARAM_LABELS,
            "wiring": [wire("IO0", "SDA", "data, both directions"),
                       wire("IO1", "SCL", "clock"), _BP6_GND, _BP6_VOUT],
            "notes": ["I2C needs pull-ups: switch them on (10 kΩ) on Power & pull-ups.",
                      "The Bus Pirate 6 reports one ACK or NACK per transaction, not per byte.",
                      _BP6_NOTE],
        },
        "spi": {
            "param_labels": _BP6_PARAM_LABELS,
            "wiring": [wire("IO6", "SCK / CLK", "clock"),
                       wire("IO7", "DI / MOSI", "Bus Pirate out, chip in"),
                       wire("IO4", "DO / MISO", "chip out, Bus Pirate in"),
                       wire("IO5", "CS / SS", "active low"), _BP6_GND, _BP6_VOUT],
            "notes": ["Serial flash chips also have WP and HOLD pins. Tie both high.",
                      "A reply of all 0x00 or all 0xFF almost always means MISO is not "
                      "connected, not that the chip is blank.",
                      _BP6_NOTE],
        },
        "uart": {
            "param_labels": _BP6_PARAM_LABELS,
            "wiring": [wire("IO4", "RX", "the Bus Pirate's TX drives the target's receive pin"),
                       wire("IO5", "TX", "the Bus Pirate's RX listens to the target's transmit pin"),
                       _BP6_GND],
            "notes": ["TX and RX cross over. If you see nothing, swapping IO4 and IO5 is "
                      "the first thing to try.",
                      "8 data bits with no or even parity. Odd parity and 9 bits are only "
                      "in the board's own terminal.",
                      _BP6_NOTE],
        },
        "onewire": {
            "param_labels": _BP6_PARAM_LABELS,
            "wiring": [wire("IO0", "DQ", "data"), _BP6_GND, _BP6_VOUT],
            "notes": ["Switch the pull-ups on: 1-Wire needs one on the data line.",
                      "The dashboard finds one device. With several on the bus, type "
                      "'m 1wire' and then 'scan' in the Terminal panel.",
                      _BP6_NOTE],
        },
    },
}

#: What drives each LED; see the inference kinds in buspirate.web.wiring.
LED_RULES: Dict[str, Dict[str, str]] = {}

LED_NOTE = (
    "The Bus Pirate 6's 18 RGB LEDs belong to its firmware, and the "
    "dashboard does not know what they show. Its status bar shows the supply "
    "and current instead."
)


BOARD = Board(
    variant="bp6",
    name="Bus Pirate 6",
    # BPIO2: I2C, SPI (any mode, page writes fit in 512 bytes), UART with
    # its async receive, 1-Wire, and the programmable supply. No bitbang,
    # raw-wire, sniffers or bridge — see buspirate.bp6.
    capabilities=frozenset(
        {CAP_SUPPLIES, CAP_ONEWIRE, CAP_SPI_MODES, CAP_UART_BUFFERED,
         CAP_SPI_FLASH_PROGRAM, CAP_PSU_PROGRAMMABLE, CAP_PSU_READOUT}
    ),
    simulated_name="simulated Bus Pirate 6",
    terminal_caption=("The Bus Pirate 6's own terminal. Type a command; '?' lists them. "
                      "If it asks 'VT100 compatible color mode?', answer n."),
    guide_page="bus-pirate-6",
    manual="official",
    wiring=_BOARD_BP6,
    led_rules=LED_RULES,
    led_note=LED_NOTE,
)
