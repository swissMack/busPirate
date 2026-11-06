"""The ESP32 Bit Pirate's own modes and commands that the menu offers.

Every command line and its arguments come from the firmware, geo-tp/
ESP32-Bit-Pirate v1.8, ``src/Controllers/<Mode>Controller.cpp``
``handleCommand`` and the handlers it calls (named next to each mode). Every
line is sent with all its arguments, so the firmware never stops to ask.

Not offered, and left to the Terminal: commands that jam, flood, spoof or
otherwise disturb other people's equipment, and the interactive shells and
adapter modes (``eeprom``, ``smartcard``, ``wizard``, ``openocd``).
"""

from __future__ import annotations

from typing import Dict, Tuple

from ._modes import CliCommand, CliMode, CliParam

#: The dock header's GPIOs in header order, IO0..IO7 of the Bus Pirate 6
#: layout (see bitpirate.DOCK_HEADER).
DOCK_GPIOS = (15, 16, 17, 18, 10, 11, 12, 13)

_PIN = CliParam(
    "pin", "enum", "Pin",
    default=15,
    choices=[{"value": g, "label": f"IO{g}"} for g in DOCK_GPIOS],
    help="A pin on the dock's header",
)


def _num(name: str, label: str, default: int, minimum: int, maximum: int,
         help: str = "") -> CliParam:
    return CliParam(name, "int", label, default=default, minimum=minimum,
                    maximum=maximum, help=help)


# Controllers/OneWireController.cpp. Its config asks one question, "Data
# GPIO" (handleConfig); IO15 is the Bus Pirate 6's 1-Wire pin, IO0.
ONEWIRE = CliMode(
    id="onewire_cli",
    title="1-Wire",
    cli_name="1wire",
    group="Buses",
    blurb="Find 1-Wire parts on IO15, read their ROM codes and a DS18B20's temperature.",
    doc="bitpirate-wiki/02-1wire",
    pins={"Data GPIO": "15"},
    wires=(("IO15", "DATA", "with a 4k7 pull-up to VIO; most parts need one"),),
    commands=(
        CliCommand("scan", "Find devices", "scan",
                   help="Searches the bus and lists every ROM code"),
        CliCommand("ping", "Ping", "ping", help="Is anything answering a reset?"),
        # handleRead loops until a part answers or Enter is pressed.
        CliCommand("read", "Read the ROM", "read", timeout=5.0,
                   help="ROM code and scratchpad of the one part on the bus"),
        CliCommand("temp", "Read DS18B20 temperature", "temp", timeout=5.0),
        CliCommand("sniff", "Sniff", "sniff", streams=True,
                   help="Shows resets, presence pulses and bits as they happen"),
    ),
)

# Controllers/DioController.cpp. DIO has no config; every command names its pin.
DIO = CliMode(
    id="dio",
    title="DIO",
    cli_name="dio",
    group="Buses",
    blurb="Drive, read and time the header pins one at a time: levels, PWM, pulses, servos.",
    doc="bitpirate-wiki/09-dio",
    wires=(("IO15 … IO13", "the target pin", "whichever header pin you pick in each action"),),
    commands=(
        CliCommand("read", "Read a pin", "read {pin}", (_PIN,)),
        CliCommand("set", "Set a pin", "set {pin} {level}", (
            _PIN,
            CliParam("level", "enum", "To", default="H", choices=[
                {"value": "H", "label": "High"}, {"value": "L", "label": "Low"},
                {"value": "I", "label": "Input"}, {"value": "O", "label": "Output"},
            ]),
        )),
        CliCommand("pullup", "Pull-up", "pullup {pin}", (_PIN,)),
        CliCommand("pulldown", "Pull-down", "pulldown {pin}", (_PIN,)),
        CliCommand("pwm", "PWM", "pwm {pin} {freq} {duty}", (
            _PIN,
            _num("freq", "Frequency (Hz)", 1000, 1, 40_000_000),
            _num("duty", "Duty (%)", 50, 0, 100),
        ), help="Runs until 'Reset a pin'"),
        # handleMeasure caps the window at 5000 ms.
        CliCommand("measure", "Measure frequency", "measure {pin} {ms}", (
            _PIN, _num("ms", "For (ms)", 1000, 1, 5000),
        ), timeout=8.0),
        CliCommand("pulse", "Pulse", "pulse {pin} {us}", (
            _PIN, _num("us", "Length (µs)", 100, 1, 1_000_000),
        ), help="Flips the pin for this long, then back"),
        CliCommand("servo", "Servo", "servo {pin} {angle}", (
            _PIN, _num("angle", "Angle (°)", 90, 0, 180),
        ), help="Runs until 'Reset a pin'"),
        CliCommand("reset", "Reset a pin", "reset {pin}", (_PIN,),
                   help="Back to input: no pull, no PWM"),
    ),
)

# Controllers/JtagController.cpp. Its config asks for the pins to scan as one
# space-separated list (handleConfig, UserInputManager readValidatedPinGroup);
# "scan" alone only prints its usage, so SWD and JTAG are separate commands.
JTAG = CliMode(
    id="jtag",
    title="JTAG",
    cli_name="jtag",
    group="Buses",
    blurb="Find which header pins a target's SWD or JTAG port is on, and its IDCODE.",
    doc="bitpirate-wiki/15-jtag",
    pins={"GPIOs to scan (SWD/JTAG)": " ".join(str(g) for g in DOCK_GPIOS)},
    wires=(("IO15 … IO13", "SWDIO, SWCLK or TDI, TDO, TCK, TMS",
            "any order on any header pins: the scan finds which is which"),),
    commands=(
        CliCommand("scan_swd", "Find SWD pins", "scan swd", timeout=60.0),
        CliCommand("scan_jtag", "Find JTAG pins", "scan jtag", timeout=120.0),
    ),
)

# Controllers/WifiController.cpp; ping is Abstracts/ANetworkController.cpp.
WIFI = CliMode(
    id="wifi",
    title="Wi-Fi",
    cli_name="wifi",
    group="Wireless",
    blurb="See the networks in reach, join one, and ping from the board.",
    doc="bitpirate-wiki/14-wifi",
    commands=(
        CliCommand("scan", "Scan for networks", "scan", timeout=15.0),
        CliCommand("status", "Status", "status"),
        # handleConnect splits at the last space: the SSID may hold spaces,
        # the password may not.
        CliCommand("connect", "Connect", "connect {ssid} {password}", (
            CliParam("ssid", "text", "Network (SSID)"),
            CliParam("password", "text", "Password", help="No spaces", spaces=False),
        ), timeout=25.0, help="The board remembers it for next time"),
        CliCommand("disconnect", "Disconnect", "disconnect"),
        CliCommand("ping", "Ping a host", "ping {host}", (
            CliParam("host", "text", "Host", default="8.8.8.8", spaces=False),
        ), timeout=15.0),
    ),
)

# Controllers/BluetoothController.cpp. handleScan listens for 10 s.
BLUETOOTH = CliMode(
    id="bluetooth",
    title="Bluetooth",
    cli_name="bluetooth",
    group="Wireless",
    blurb="List the Bluetooth LE devices in reach.",
    doc="bitpirate-wiki/13-bluetooth",
    commands=(
        CliCommand("scan", "Scan for devices", "scan", timeout=15.0),
        CliCommand("status", "Status", "status"),
    ),
)

#: In menu order.
MODES: Tuple[CliMode, ...] = (ONEWIRE, DIO, JTAG, WIFI, BLUETOOTH)

_ADDRESS = CliParam("address", "hex", "Address", default=0x50, minimum=0,
                    maximum=0x7F, help="7-bit, e.g. 50")

#: Extra actions for the panels every board has, by panel id.
EXTRA_ACTIONS: Dict[str, Tuple[CliCommand, ...]] = {
    # Controllers/I2cController.cpp.
    "i2c": (
        CliCommand("identify", "Identify", "identify {address}", (_ADDRESS,),
                   help="What parts commonly sit at this address"),
        CliCommand("discovery", "Discovery", "discovery", timeout=20.0,
                   help="Scans, then identifies each part found"),
        # handleDump reads at most 256 bytes.
        CliCommand("dump", "Dump", "dump {address} {length}", (
            _ADDRESS, _num("length", "Bytes", 256, 1, 256),
        ), timeout=15.0),
        CliCommand("recover", "Recover the bus", "recover",
                   help="16 clocks and a STOP, to free a part holding SDA low"),
        # Named apart from the Bus Pirate's own I2C "sniff" action.
        CliCommand("sniff_traffic", "Sniff", "sniff", streams=True,
                   help="Watches traffic between other controllers and parts"),
    ),
    # Controllers/UartController.cpp handleAutoBaud: listens until it finds a
    # rate, then saves it to the config.
    "uart": (
        CliCommand("autobaud", "Find the baud rate", "autobaud", timeout=20.0,
                   forgets=("Baud rate",),
                   help="Listens on RX until the target talks"),
    ),
}
