"""The ESP32 Bit Pirate (geo-tp firmware) on an ESP32-S3 DevKit in its dock."""

from typing import Dict

from ._board import Board
from ._wiring import wire

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


_BITPIRATE_GND = wire("GND", "GND", "always connect this first")
_BITPIRATE_VIO = wire(
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
                wire("IO15", "SDA", "data, both directions"),
                wire("IO16", "SCL", "clock"),
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
                wire("IO12", "SCK / CLK", "clock"),
                wire("IO13", "DI / MOSI", "Bit Pirate out, chip in"),
                wire("IO10", "DO / MISO", "chip out, Bit Pirate in"),
                wire("IO11", "CS / SS", "active low"),
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
                wire("IO10", "RX", "the Bit Pirate's TX drives the target's receive pin"),
                wire("IO11", "TX", "the Bit Pirate's RX listens to the target's transmit pin"),
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

#: What drives each LED; see the inference kinds in buspirate.web.wiring.
LED_RULES: Dict[str, Dict[str, str]] = {
        "PWR": {
            "driver": "hardware",
            "inference": "powered",
            "means": "USB power is reaching the DevKit",
        },
    }

LED_NOTE = (
    "Only the DevKit's power LED is shown, lit while the port is "
    "open. Its RGB LED is the firmware's to drive, and the dock's 5V / 3V3 / "
    "1V8 LEDs follow its slide switch; the dashboard knows neither."
)


BOARD = Board(
    variant="bitpirate",
    name="ESP32 Bit Pirate",
    # A text command line, not the binary protocol: none of the binary
    # extras, and no supplies to switch. What it can do is I2C, SPI and
    # UART through its own commands — see buspirate.bitpirate.
    capabilities=frozenset(),
    simulated_name="simulated ESP32 Bit Pirate",
    terminal_caption="The Bit Pirate's own command line. Type a command; 'help' lists them.",
    guide_page="bitpirate",
    manual="bitpirate-wiki",
    wiring=_BOARD_BITPIRATE,
    led_rules=LED_RULES,
    led_note=LED_NOTE,
)
