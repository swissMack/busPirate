"""I2C: find what is on the bus, then talk to it."""

from __future__ import annotations

from ... import device as device_module
from ... import sensors
from ...exceptions import NackError
from ...i2c import (
    AUX_HIGH,
    AUX_HIZ,
    AUX_LOW,
    AUX_READ,
    AUX_USE_AUX,
    AUX_USE_CS,
    I2C,
    SCAN_RANGE,
    stuck_bus_warning,
)
from ..registry import (
    SHOW_AS_CHOICES,
    Action,
    Panel,
    Param,
    Wire,
    chips,
    hexdump,
    live,
    show_as,
    table,
    text,
    with_meaning,
)
from ..wiring import CABLE_CAVEAT, POWER_NOTE, PULLUP_RAIL_NOTE, colour

# Addresses common enough to be worth naming in the scan results.
WELL_KNOWN = {
    0x0C: "AK8963 magnetometer",
    0x1E: "HMC5883L magnetometer",
    0x20: "PCF8574 / MCP23017 I/O expander",
    0x27: "PCF8574 LCD backpack",
    0x38: "AHT20 / AHT21 temperature + humidity",
    0x39: "TSL2561 light sensor",
    0x3C: "SSD1306 OLED",
    0x40: "INA219 / HTU21D",
    0x48: "ADS1115 / LM75 temperature",
    0x50: "24Cxx EEPROM",
    0x51: "24Cxx EEPROM",
    0x53: "ADXL345 accelerometer",
    0x57: "24Cxx EEPROM (or DS3231 NVRAM)",
    0x5A: "MLX90614 / CCS811",
    0x68: "DS1307 / DS3231 RTC, or MPU-6050",
    0x76: "BMP280 / BME280",
    0x77: "BMP280 / BME280 / BMP180",
}

SPEED_CHOICES = [
    {"value": 0, "label": "5 kHz"},
    {"value": 1, "label": "50 kHz"},
    {"value": 2, "label": "100 kHz (usual)"},
    {"value": 3, "label": "400 kHz"},
]


def _configure(ctx, power, pullups, speed):
    ctx.mode.configure_peripherals(power=power, pullups=pullups)
    ctx.mode.set_speed(speed)
    rail = "on" if power else "off"
    return text(
        f"Bus set to {dict((c['value'], c['label']) for c in SPEED_CHOICES)[speed]}, "
        f"power {rail}, pull-ups {'on' if pullups else 'off'}.",
        tone="good",
    )


def _scan(ctx, power, pullups, speed):
    ctx.mode.configure_peripherals(power=power, pullups=pullups)
    ctx.mode.set_speed(speed)
    found = ctx.mode.scan()
    stuck = stuck_bus_warning(found, SCAN_RANGE)
    if stuck:
        return text(stuck, tone="warn")
    if not found:
        return text(
            "Nothing answered. The usual causes, in order: pull-ups are off, "
            "the target has no power, or SDA and SCL are swapped.",
            tone="warn",
        )
    return chips(
        [
            {
                "label": f"0x{address:02X}",
                "sub": WELL_KNOWN.get(address, ""),
                "detail": f"write 0x{address << 1:02X} / read 0x{(address << 1) | 1:02X}",
            }
            for address in found
        ],
        caption=f"{len(found)} device(s) acknowledged",
    )


def _read_register(ctx, address, register, count, show):
    data = ctx.mode.read_register(address, register, count)
    result = show_as(
        data,
        show,
        start=register,
        caption=f"0x{address:02X} register 0x{register:02X}, {count} byte(s)",
        where="Register",
    )
    return with_meaning(result, sensors.explain_register_read(ctx.mode, address, register, data))


def _write(ctx, address, data):
    ctx.mode.write(address, data)
    if getattr(ctx.mode, "reports_byte_acks", True):
        return text(
            f"Wrote {len(data)} byte(s) to 0x{address:02X} and every byte was "
            "acknowledged.",
            tone="good",
        )
    return text(
        f"Wrote {len(data)} byte(s) to 0x{address:02X}. It acknowledged its "
        "address; this board cannot report the bytes after it.",
        tone="good",
    )


def _read(ctx, address, count, show):
    data = ctx.mode.read(address, count)
    result = show_as(data, show, caption=f"{count} byte(s) from 0x{address:02X}")
    return with_meaning(result, sensors.explain_read(address, data))


def _read_sensors(ctx):
    """Scan, then measure and translate every chip the app recognises."""
    found = ctx.mode.scan()
    if not found:
        return text(
            "Nothing answered. Tick Power the target and scan the bus first, "
            "then try again.",
            tone="warn",
        )
    rows = []
    for address in found:
        reading = sensors.read_sensor(ctx.mode, address)
        if reading is None:
            rows.append([f"0x{address:02X}", "not recognised", "",
                         "use Read bytes or Read a register"])
            continue
        rows.append([
            f"0x{address:02X}",
            reading.chip,
            reading.raw.hex(" "),
            "; ".join(f"{k} {v}" for k, v in reading.meaning if k != "Status"),
        ])
    return table(["Address", "Chip", "Raw bytes", "What it means"], rows,
                 caption=f"{len(found)} device(s) on the bus")


def _eeprom_read(ctx, address, offset, length, address_bytes):
    """24Cxx style: write the memory address, then read straight through."""
    pointer = (
        bytes([offset & 0xFF])
        if address_bytes == 1
        else bytes([(offset >> 8) & 0xFF, offset & 0xFF])
    )
    try:
        data = ctx.mode.read_after_write(address, pointer, length)
    except NackError:
        return text(
            f"0x{address:02X} did not acknowledge. If the chip is a 24C32 "
            "or larger it needs a 2-byte address.",
            tone="warn",
        )
    return hexdump(data, start=offset, caption=f"EEPROM 0x{address:02X}")


def _sniff(ctx, power, pullups, speed):
    ctx.mode.configure_peripherals(power=power, pullups=pullups)
    ctx.mode.set_speed(speed)
    ctx.mode.start_sniffer()
    return live(
        "I2C sniffer",
        decoder="i2c-sniffer",
        caption="Watching another master talk to the bus. Nothing is driven.",
    )


def _pullup_voltage(ctx, selection):
    ctx.mode.set_pullup_voltage(selection)
    names = {0: "disconnected", 1: "the 3.3V rail", 2: "the 5V rail"}
    return text(f"VPU is now connected to {names[selection]}.", tone="good")


_AUX_PINS = [{"value": "aux", "label": "AUX"}, {"value": "cs", "label": "CS"}]
_AUX_LEVELS = [
    {"value": "low", "label": "Drive low"},
    {"value": "high", "label": "Drive high"},
    {"value": "hiz", "label": "Release (HiZ)"},
    {"value": "read", "label": "Read"},
]

# Sub-command bytes from Firmware/I2C.c:935, named in buspirate/i2c.py.
_AUX_SELECT = {"aux": AUX_USE_AUX, "cs": AUX_USE_CS}
_AUX_ACTION = {"low": AUX_LOW, "high": AUX_HIGH, "hiz": AUX_HIZ, "read": AUX_READ}


def _extended_aux(ctx, pin, level):
    ctx.mode.extended_aux(_AUX_SELECT[pin])
    reply = ctx.mode.extended_aux(_AUX_ACTION[level])
    name = pin.upper()
    if level == "read":
        return text(f"{name} reads {'high' if reply else 'low'}.")
    return text(f"{name} set {level}.", tone="good")


_SHOW_AS = Param("show", "enum", "Show as", default="hex", choices=SHOW_AS_CHOICES)

_BUS_PARAMS = [
    Param("power", "bool", "Power the target (3.3V + 5V)", default=False,
          requires=device_module.CAP_SUPPLIES),
    Param("pullups", "bool", "Enable the on-board pull-ups", default=False),
    Param("speed", "enum", "Bus speed", default=2, choices=SPEED_CHOICES),
]

PANEL = Panel(
    id="i2c",
    refcard_column='I2C',
    refcard_rows=['VPU', 'supplies', 'GND'],
    doc="i2c",
    title="I2C",
    blurb="Two wires, many devices. Start by scanning to see what answers.",
    mode="i2c",
    order=20,
    wiring=[
        Wire("CLK", colour("CLK"), "SCL", "clock"),
        Wire("MOSI", colour("MOSI"), "SDA", "data, both directions"),
        Wire("GND", colour("GND"), "GND", "always connect this first"),
        Wire("+3.3V", colour("+3.3V"), "VCC", "only if powering the target"),
        Wire("VPU", colour("VPU"), "VCC", "pull-up reference; tie to the bus rail"),
    ],
    notes=[
        "I2C needs pull-ups on both SDA and SCL. The Bus Pirate's are weak but "
        "usually enough — tie VPU to the bus voltage or the pull-ups do nothing.",
        PULLUP_RAIL_NOTE,
        POWER_NOTE,
        CABLE_CAVEAT,
    ],
    actions=[
        Action(
            name="scan",
            label="Scan the bus",
            primary=True,
            recipe=True,
            help="Probes every address from 0x08 to 0x77 and lists what answers.",
            params=list(_BUS_PARAMS),
            handler=_scan,
        ),
        Action(
            name="configure",
            label="Set speed and power",
            params=list(_BUS_PARAMS),
            handler=_configure,
        ),
        Action(
            name="read_sensors",
            label="Read the sensors",
            help="One click: finds the chips on the bus, makes each one it "
            "recognises measure, and shows the raw bytes with °C, %RH or hPa. "
            "Knows the AHT20 and BMP280/BME280 so far.",
            params=[],
            handler=_read_sensors,
        ),
        Action(
            name="read_register",
            label="Read a register",
            help="Writes the register number, then reads — the pattern nearly "
            "every sensor and RTC expects.",
            params=[
                Param("address", "hex", "Device address (7-bit)", default=0x68),
                Param("register", "hex", "Register", default=0x00),
                Param("count", "int", "Bytes to read", default=8, minimum=1, maximum=4096),
                _SHOW_AS,
            ],
            handler=_read_register,
        ),
        Action(
            name="read",
            label="Read bytes",
            help="Reads without writing a register first.",
            params=[
                Param("address", "hex", "Device address (7-bit)", default=0x50),
                Param("count", "int", "Bytes to read", default=16, minimum=1, maximum=4096),
                _SHOW_AS,
            ],
            handler=_read,
        ),
        Action(
            name="write",
            label="Write bytes",
            params=[
                Param("address", "hex", "Device address (7-bit)", default=0x50),
                Param(
                    "data",
                    "bytes",
                    "Bytes to write",
                    default="00 01 02",
                    help="Hex, spaces optional.",
                ),
            ],
            handler=_write,
        ),
        Action(
            name="eeprom_read",
            label="Read a 24Cxx EEPROM",
            recipe=True,
            help="The one-byte-address parts are 24C01 to 24C16; 24C32 and "
            "larger need two.",
            params=[
                Param("address", "hex", "Device address (7-bit)", default=0x50),
                Param("offset", "int", "Start offset", default=0, minimum=0),
                Param("length", "int", "Bytes to read", default=64, minimum=1, maximum=4096),
                Param(
                    "address_bytes",
                    "enum",
                    "Memory address width",
                    default=1,
                    choices=[
                        {"value": 1, "label": "1 byte (24C01-24C16)"},
                        {"value": 2, "label": "2 bytes (24C32 and up)"},
                    ],
                ),
            ],
            handler=_eeprom_read,
        ),
        Action(
            name="sniff",
            label="Sniff the bus",
            recipe=True,
            stream=True,
            requires=device_module.CAP_SNIFFER,
            help="Passively watch traffic between two other devices. Wire SDA "
            "and SCL in parallel with the existing bus and share the ground; "
            "leave power and pull-ups off if the bus already has them.",
            params=list(_BUS_PARAMS),
            handler=_sniff,
        ),
        Action(
            name="pullup_voltage",
            label="Set the pull-up rail",
            help="Bus Pirate v4 only. Connects the VPU pin to an on-board "
            "rail. It refuses if the target is already driving VPU — that is "
            "the short-circuit protection doing its job.",
            requires=device_module.CAP_PULLUP_VOLTAGE,
            params=[
                Param(
                    "selection",
                    "enum",
                    "Connect VPU to",
                    default=I2C.PULLUP_3V3,
                    choices=[
                        {"value": I2C.PULLUP_OFF, "label": "Off"},
                        {"value": I2C.PULLUP_3V3, "label": "3.3V"},
                        {"value": I2C.PULLUP_5V, "label": "5V"},
                    ],
                )
            ],
            handler=_pullup_voltage,
        ),
        Action(
            name="extended_aux",
            label="Drive AUX or CS",
            help="Bus Pirate v3 only, firmware v6.1 or newer. Drives or reads the AUX "
            "or CS pin directly while in I2C mode. On a v4 the firmware hangs "
            "on this command, so it is not offered; drive AUX from Pins & power "
            "instead.",
            requires=device_module.CAP_EXTENDED_AUX,
            params=[
                Param("pin", "enum", "Pin", default="aux", choices=_AUX_PINS),
                Param("level", "enum", "Do what", default="high", choices=_AUX_LEVELS),
            ],
            handler=_extended_aux,
        ),
    ],
)
