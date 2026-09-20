"""I2C: find what is on the bus, then talk to it."""

from __future__ import annotations

from ... import device as device_module
from ...i2c import I2C
from ..registry import Action, Panel, Param, Wire, chips, hexdump, text
from ..wiring import CABLE_CAVEAT, POWER_NOTE, PULLUP_RAIL_NOTE, colour

# Addresses common enough to be worth naming in the scan results.
WELL_KNOWN = {
    0x0C: "AK8963 magnetometer",
    0x1E: "HMC5883L magnetometer",
    0x20: "PCF8574 / MCP23017 I/O expander",
    0x27: "PCF8574 LCD backpack",
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
    0x77: "BMP180 / BME280",
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


def _read_register(ctx, address, register, count):
    data = ctx.mode.read_register(address, register, count)
    return hexdump(
        data,
        start=register,
        caption=f"0x{address:02X} register 0x{register:02X}, {count} byte(s)",
    )


def _write(ctx, address, data):
    ctx.mode.write(address, data)
    return text(
        f"Wrote {len(data)} byte(s) to 0x{address:02X} and every byte was "
        "acknowledged.",
        tone="good",
    )


def _read(ctx, address, count):
    data = ctx.mode.read(address, count)
    return hexdump(data, caption=f"{count} byte(s) from 0x{address:02X}")


def _eeprom_read(ctx, address, offset, length, address_bytes):
    """24Cxx style: write the memory address, then read straight through."""
    pointer = (
        bytes([offset & 0xFF])
        if address_bytes == 1
        else bytes([(offset >> 8) & 0xFF, offset & 0xFF])
    )
    ctx.mode.start()
    try:
        acks = ctx.mode.write_bytes(bytes([address << 1]) + pointer)
        if not all(acks):
            return text(
                f"0x{address:02X} did not acknowledge. If the chip is a 24C32 "
                "or larger it needs a 2-byte address.",
                tone="warn",
            )
        ctx.mode.start()  # repeated start
        ctx.mode.write_bytes(bytes([(address << 1) | 1]))
        data = bytes(
            ctx.mode.read_byte(ack=(i < length - 1)) for i in range(length)
        )
    finally:
        ctx.mode.stop()
    return hexdump(data, start=offset, caption=f"EEPROM 0x{address:02X}")


def _pullup_voltage(ctx, selection):
    ctx.mode.set_pullup_voltage(selection)
    names = {0: "disconnected", 1: "the 3.3V rail", 2: "the 5V rail"}
    return text(f"VPU is now connected to {names[selection]}.", tone="good")


_BUS_PARAMS = [
    Param("power", "bool", "Power the target (3.3V + 5V)", default=True),
    Param("pullups", "bool", "Enable the on-board pull-ups", default=True),
    Param("speed", "enum", "Bus speed", default=2, choices=SPEED_CHOICES),
]

PANEL = Panel(
    id="i2c",
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
            name="read_register",
            label="Read a register",
            help="Writes the register number, then reads — the pattern nearly "
            "every sensor and RTC expects.",
            params=[
                Param("address", "hex", "Device address (7-bit)", default=0x68),
                Param("register", "hex", "Register", default=0x00),
                Param("count", "int", "Bytes to read", default=8, minimum=1, maximum=4096),
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
    ],
)
