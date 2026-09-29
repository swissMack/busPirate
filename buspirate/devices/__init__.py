"""The device catalog: every chip the app can name, and those it can translate.

The Bus Pirate only ever sees bytes. Each module in this package describes
one chip (or a family of them) as a :class:`Device`: which bus it is on, how
to recognise it, how to make it measure, and the datasheet formula that turns
its bytes into real units. The panels ask the catalog; they keep no chip
tables of their own.

Adding a chip — see ``docs/extending.md`` for the full recipe:

1. Copy the closest existing module (``aht20.py`` for a simple I2C sensor,
   ``bmp280.py`` for one that needs an ID check or calibration,
   ``ds18x20.py`` for 1-Wire, ``max31855.py`` for SPI, ``ad595.py`` for
   an analog sensor read on the ADC lead).
2. Change the addresses, commands and formula.
3. Add it to ``_MODULES`` below, and a test with a known answer from the
   datasheet to ``tests/test_devices.py``.

A chip that only needs a *name* in scan results goes in ``names.py``.

Modules are listed explicitly rather than discovered, so the frozen app can
never silently leave one out; ``tests/test_devices.py`` fails if a module in
this package is missing from the list.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional, Tuple

#: A translation as label/value pairs, e.g. ``[("Temperature", "29.07 °C")]``.
Meaning = List[Tuple[str, str]]

#: "analog" is not a bus: the chip puts out a voltage the ADC lead measures.
BUSES = ("i2c", "onewire", "spi", "analog")


@dataclass
class Reading:
    """One measurement: the raw bytes, and what they mean."""

    device: str
    where: str  # "0x38", a 1-Wire ROM, or "CS" for SPI
    raw: bytes
    meaning: Meaning = field(default_factory=list)


@dataclass(frozen=True)
class Device:
    """One chip in the catalog.

    Only ``name`` and ``bus`` are required; a device with nothing else is a
    name for scan results. Every callable is optional:

    ``probe(bus, address) -> bool``
        I2C only. Confirms the chip when an address is shared — usually by
        reading an ID register. Without one, the address alone decides.
    ``measure(bus, where) -> Reading``
        Makes the chip measure and translates the reply. ``where`` is the
        I2C address or 1-Wire ROM; SPI sensors take no ``where``.
    ``explain_read(address, data) -> Meaning``
        Translates a plain read the user made by hand (no register).
    ``explain_register(bus, address, register, data) -> Meaning``
        Translates a register read the user made by hand. May read
        calibration from the chip, but must never start a measurement.
    ``from_volts(volts) -> Meaning``
        Analog only. Translates a voltage measured on the ADC lead.
    """

    name: str
    bus: str
    summary: str = ""
    addresses: Tuple[int, ...] = ()  # I2C 7-bit addresses
    families: Tuple[int, ...] = ()  # 1-Wire family codes (the ROM's first byte)
    probe: Optional[Callable[[Any, int], bool]] = None
    measure: Optional[Callable[..., Reading]] = None
    explain_read: Optional[Callable[[int, bytes], Meaning]] = None
    explain_register: Optional[Callable[[Any, int, int, bytes], Meaning]] = None
    from_volts: Optional[Callable[[float], Meaning]] = None
    #: True once it has been checked on real hardware, not just the datasheet.
    verified: bool = False

    def __post_init__(self):
        if self.bus not in BUSES:
            raise ValueError(f"{self.name}: bus must be one of {BUSES}")


from . import ad595, aht20, bmp280, ds18x20, max31855, names  # noqa: E402

_MODULES = (ad595, aht20, bmp280, ds18x20, max31855, names)

CATALOG: List[Device] = [device for module in _MODULES for device in module.DEVICES]

JEDEC_MANUFACTURERS = names.JEDEC_MANUFACTURERS


def devices(bus: Optional[str] = None) -> List[Device]:
    return [d for d in CATALOG if bus is None or d.bus == bus]


# -- I2C ---------------------------------------------------------------------


def i2c_label(address: int) -> str:
    """Every chip known to live at ``address``, for scan results."""
    seen: List[str] = []
    for device in devices("i2c"):
        if address in device.addresses and device.name not in seen:
            seen.append(device.name)
    return " / ".join(seen)


def identify_i2c(i2c, address: int) -> Optional[Device]:
    """The chip at ``address`` that the app can measure, or ``None``."""
    for device in devices("i2c"):
        if address not in device.addresses or device.measure is None:
            continue
        if device.probe is None or device.probe(i2c, address):
            return device
    return None


def read_i2c(i2c, address: int) -> Optional[Reading]:
    device = identify_i2c(i2c, address)
    return device.measure(i2c, address) if device else None


def explain_i2c_read(address: int, data: bytes) -> Meaning:
    for device in devices("i2c"):
        if address in device.addresses and device.explain_read:
            meaning = device.explain_read(address, data)
            if meaning:
                return meaning
    return []


def explain_i2c_register(i2c, address: int, register: int, data: bytes) -> Meaning:
    for device in devices("i2c"):
        if address in device.addresses and device.explain_register:
            meaning = device.explain_register(i2c, address, register, data)
            if meaning:
                return meaning
    return []


# -- 1-Wire ------------------------------------------------------------------


def onewire_device(family: int) -> Optional[Device]:
    """The catalog entry for a family code, preferring one that can measure."""
    matches = [d for d in devices("onewire") if family in d.families]
    matches.sort(key=lambda d: d.measure is None)
    return matches[0] if matches else None


def onewire_label(family: int) -> str:
    """Name and kind, e.g. "DS18B20 thermometer": one chip per family code."""
    device = onewire_device(family)
    return f"{device.name} {device.summary}".strip() if device else ""


def onewire_readable(family: int) -> bool:
    device = onewire_device(family)
    return device is not None and device.measure is not None


def read_onewire(onewire, rom: bytes) -> Optional[Reading]:
    device = onewire_device(rom[0])
    if device is None or device.measure is None:
        return None
    return device.measure(onewire, rom)


# -- SPI ---------------------------------------------------------------------


def spi_sensors() -> List[Device]:
    """SPI chips the app can read. SPI has no addresses, so the user picks."""
    return [d for d in devices("spi") if d.measure is not None]


def spi_sensor(name: str) -> Device:
    for device in spi_sensors():
        if device.name == name:
            return device
    raise KeyError(name)


# -- analog ------------------------------------------------------------------


def analog_sensors() -> List[Device]:
    """Sensors whose output voltage the app can translate."""
    return [d for d in devices("analog") if d.from_volts is not None]


def translate_volts(name: str, volts: float) -> Meaning:
    for device in analog_sensors():
        if device.name == name:
            return device.from_volts(volts)
    raise KeyError(name)
