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

# The ESP32 Bit Pirate Dock (github.com/AndreiVladescu/ESP32-Bit-Pirate-Hardware)
# with an ESP32-S3-DevKitC-1 seated in it, photographed as
# static/img/board-bitpirate-dock.jpg (700x661). Its 10-pin header copies the
# Bus Pirate 6's: GND, IO0..IO7, then VIO, with IO0..IO7 wired to GPIO15, 16,
# 17, 18, 10, 11, 12 and 13 (dock schematic, J3/CN1). The silkscreen names
# them by GPIO, so the diagram does too. The holes sit at x=150 from y=251 in
# steps of 21.16, measured on the photo with markers drawn over it.
DOCK_HEADER = ["GND", "IO15", "IO16", "IO17", "IO18", "IO10", "IO11", "IO12", "IO13", "VIO"]
DOCK_GEOMETRY = {"width": 700, "height": 661, "x": 150, "first_y": 251.2, "pitch": 21.16}


def _dock_pins():
    g = DOCK_GEOMETRY
    pins = {
        name: [g["x"], round(g["first_y"] + i * g["pitch"])]
        for i, name in enumerate(DOCK_HEADER)
    }
    # The header is at the photo's left edge, so every callout goes left.
    side = {name: "left" for name in DOCK_HEADER}
    return pins, side


_DOCK_PINS, _DOCK_SIDE = _dock_pins()


def _wire(signal: str, target: str, note: str = "") -> Dict[str, str]:
    # No colour: the dock takes any Bus Pirate 5/6 style cable or adapter.
    return {"signal": signal, "colour": "", "target": target, "note": note}


_BITPIRATE_GND = _wire("GND", "GND", "always connect this first")
_BITPIRATE_VIO = _wire(
    "VIO", "VCC", "the voltage set on the dock's slide switch: 5V, 3V3 or 1V8"
)
_BITPIRATE_PINS_NOTE = (
    "The dashboard sets these pins itself each time it enters a mode: the Bus "
    "Pirate 6 layout of the dock's header, not the firmware's own defaults. "
    "Bus Pirate 5/6 adapters plug straight in."
)
_BITPIRATE_VOLTAGE_NOTE = (
    "Set the dock's slide switch (5V / 3V3 / 1V8) to the target's voltage "
    "before wiring it: the level shifters and VIO follow it, and its LED "
    "shows which one is selected."
)

_BOARD_BITPIRATE = {
    "image": "/static/img/board-bitpirate-dock.jpg",
    "width": DOCK_GEOMETRY["width"],
    "height": DOCK_GEOMETRY["height"],
    "gutter": 290,
    "gutter_left": 290,
    "label": "ESP32 Bit Pirate in its dock",
    "pins": _DOCK_PINS,
    "side": _DOCK_SIDE,
    # The DevKit's red power LED, right of the regulator.
    "leds": {"PWR": [572, 336]},
    #: Not a Bus Pirate: there is no probe cable, so no cable colours and no
    #: Dangerous Prototypes reference cards.
    "cable": False,
    "caveat": (
        "This is the ESP32 Bit Pirate Dock. Its header follows the Bus Pirate "
        "6, labelled by GPIO: IO15 is the Bus Pirate's IO0 through to IO13 as "
        "IO7. Check the silkscreen beside the header if yours differs."
    ),
    #: What replaces a panel's Bus Pirate wording on this board. See
    #: server._panels_json.
    "panels": {
        "terminal": {
            "blurb": "The Bit Pirate's own command line \u2014 the `HIZ>` prompt.",
            "actions": {
                "open_terminal": {
                    "confirm": "",
                    "help": "Gives you the Bit Pirate's own command line. "
                    "Nothing is reset. Everything else in the dashboard is "
                    "unavailable until you close it.",
                },
            },
        },
        "i2c": {
            "wiring": [
                _wire("IO15", "SDA", "data, both directions"),
                _wire("IO16", "SCL", "clock"),
                _BITPIRATE_GND,
                _BITPIRATE_VIO,
            ],
            "notes": [
                "I2C needs pull-ups on SDA and SCL. The ESP32's internal ones "
                "(the pull-up switch) are weak \u2014 about 45 k\u03a9 \u2014 "
                "and fine for a short bus at 100 kHz; fit 4.7 k\u03a9 to VIO "
                "for anything longer or faster.",
                "Writes are checked by pinging the address first: the Bit "
                "Pirate does not report an ACK for each byte the way a Bus "
                "Pirate does.",
                _BITPIRATE_VOLTAGE_NOTE,
                _BITPIRATE_PINS_NOTE,
            ],
        },
        "spi": {
            "wiring": [
                _wire("IO12", "SCK / CLK", "clock"),
                _wire("IO13", "DI / MOSI", "Bit Pirate out, chip in"),
                _wire("IO10", "DO / MISO", "chip out, Bit Pirate in"),
                _wire("IO11", "CS / SS", "active low"),
                _BITPIRATE_GND,
                _BITPIRATE_VIO,
            ],
            "notes": [
                "Serial flash chips also have WP and HOLD pins. Tie both high, "
                "or the chip may never respond.",
                "Reading and dumping flash work here; writing and erasing are "
                "left to the Bus Pirates for now \u2014 the Bit Pirate's command "
                "line cannot carry a whole 256-byte page in one transfer.",
                "The clock is set in whole MHz: 1, 2, 4 or 8 MHz from the list.",
                "A reply of all 0x00 or all 0xFF almost always means MISO is "
                "not connected, not that the chip is blank.",
                _BITPIRATE_VOLTAGE_NOTE,
                _BITPIRATE_PINS_NOTE,
            ],
        },
        "uart": {
            "wiring": [
                _wire("IO10", "RX", "the Bit Pirate's TX drives the target's receive pin"),
                _wire("IO11", "TX", "the Bit Pirate's RX listens to the target's transmit pin"),
                _BITPIRATE_GND,
            ],
            "notes": [
                "TX and RX cross over. If you see nothing, swapping IO10 and "
                "IO11 is the first thing to try.",
                "Garbled characters mean the baud rate is wrong, not the wiring.",
                _BITPIRATE_VOLTAGE_NOTE,
                _BITPIRATE_PINS_NOTE,
            ],
        },
    },
}

# The Bus Pirate 6's 10-pin header, as drawn in static/img/board-bp6.svg by
# scripts/draw_bp6_board.py from this same list. Pin map from the firmware's
# src/pirate.h (M_I2C_SDA BIO0, M_SPI_CLK BIO6, M_UART_TX BIO4, ...).
BP6_HEADER = ["VOUT", "IO0", "IO1", "IO2", "IO3", "IO4", "IO5", "IO6", "IO7", "GND"]
BP6_GEOMETRY = {"width": 700, "height": 525, "x": 350, "first_y": 110, "pitch": 34}


def _bp6_pins():
    g = BP6_GEOMETRY
    pins = {name: [g["x"], g["first_y"] + i * g["pitch"]] for i, name in enumerate(BP6_HEADER)}
    side = {name: ("left" if i % 2 == 0 else "right") for i, name in enumerate(BP6_HEADER)}
    return pins, side


_BP6_PINS, _BP6_SIDE = _bp6_pins()
_BP6_GND = _wire("GND", "GND", "always connect this first")
_BP6_VOUT = _wire("VOUT", "VCC", "the adjustable supply — set it on Power & pull-ups")
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
            "wiring": [_wire("IO0", "SDA", "data, both directions"),
                       _wire("IO1", "SCL", "clock"), _BP6_GND, _BP6_VOUT],
            "notes": ["I2C needs pull-ups: switch them on (10 kΩ) on Power & pull-ups.",
                      "The Bus Pirate 6 reports one ACK or NACK per transaction, not per byte.",
                      _BP6_NOTE],
        },
        "spi": {
            "param_labels": _BP6_PARAM_LABELS,
            "wiring": [_wire("IO6", "SCK / CLK", "clock"),
                       _wire("IO7", "DI / MOSI", "Bus Pirate out, chip in"),
                       _wire("IO4", "DO / MISO", "chip out, Bus Pirate in"),
                       _wire("IO5", "CS / SS", "active low"), _BP6_GND, _BP6_VOUT],
            "notes": ["Serial flash chips also have WP and HOLD pins. Tie both high.",
                      "A reply of all 0x00 or all 0xFF almost always means MISO is not "
                      "connected, not that the chip is blank.",
                      _BP6_NOTE],
        },
        "uart": {
            "param_labels": _BP6_PARAM_LABELS,
            "wiring": [_wire("IO4", "RX", "the Bus Pirate's TX drives the target's receive pin"),
                       _wire("IO5", "TX", "the Bus Pirate's RX listens to the target's transmit pin"),
                       _BP6_GND],
            "notes": ["TX and RX cross over. If you see nothing, swapping IO4 and IO5 is "
                      "the first thing to try.",
                      "8 data bits with no or even parity. Odd parity and 9 bits are only "
                      "in the board's own terminal.",
                      _BP6_NOTE],
        },
        "onewire": {
            "param_labels": _BP6_PARAM_LABELS,
            "wiring": [_wire("IO0", "DQ", "data"), _BP6_GND, _BP6_VOUT],
            "notes": ["Switch the pull-ups on: 1-Wire needs one on the data line.",
                      "The dashboard finds one device. With several on the bus, type "
                      "'m 1wire' and then 'scan' in the Terminal panel.",
                      _BP6_NOTE],
        },
    },
}

#: Board geometry by variant. The dashboard serves one of these, chosen by
#: DeviceSession.effective_variant().
BOARDS: Dict[str, Dict[str, Any]] = {
    "v3": _BOARD_V3,
    "v4": _BOARD_V4,
    "bitpirate": _BOARD_BITPIRATE,
    "bp6": _BOARD_BP6,
}

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
    "bitpirate": {
        "PWR": {
            "driver": "hardware",
            "inference": "powered",
            "means": "USB power is reaching the DevKit",
        },
    },
    # Its 18 RGB LEDs belong to the firmware; nothing to infer.
    "bp6": {},
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
    "bitpirate": "Only the DevKit's power LED is shown, lit while the port is "
    "open. Its RGB LED is the firmware's to drive, and the dock's 5V / 3V3 / "
    "1V8 LEDs follow its slide switch; the dashboard knows neither.",
    "bp6": "The Bus Pirate 6's 18 RGB LEDs belong to its firmware, and the "
    "dashboard does not know what they show. Its status bar shows the supply "
    "and current instead.",
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
