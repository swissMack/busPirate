"""Device variants, firmware capabilities and the banner parser.

A Bus Pirate v3 and a v4 speak nearly the same binary protocol, but not
quite: the v4 adds pull-up voltage selection and an extended AUX command, the
v3 has binary self-tests the v4 does not, and firmware v4.2 redefined the I2C
speed table. Rather than scatter version checks through the modes, the device
is identified once at connect time and every conditional asks the profile.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, Optional

from .exceptions import UnsupportedFeatureError

# Capability names. Use the constants, not the strings.
CAP_SELF_TEST = "self_test"
CAP_PWM = "pwm"
CAP_ADC = "adc"
CAP_FREQUENCY = "frequency_count"
CAP_PULLUP_VOLTAGE = "pullup_voltage_select"
CAP_EXTENDED_AUX = "extended_aux"

# Which variant to name in an error when a capability is missing.
_CAPABILITY_HOME = {
    CAP_SELF_TEST: "Bus Pirate v3 (and v2go)",
    CAP_PULLUP_VOLTAGE: "Bus Pirate v4",
    CAP_EXTENDED_AUX: "Bus Pirate v4",
}

# I2C speed tables. Firmware v4.2 widened this from two speeds to four.
I2C_SPEEDS_MODERN = {0: 5_000, 1: 50_000, 2: 100_000, 3: 400_000}
I2C_SPEEDS_LEGACY = {0: 5_000, 1: 50_000}

SPI_SPEEDS = {
    0: 30_000,
    1: 125_000,
    2: 250_000,
    3: 1_000_000,
    4: 2_000_000,
    5: 2_600_000,
    6: 4_000_000,
    7: 8_000_000,
}


@dataclass(frozen=True)
class DeviceProfile:
    """What this particular Bus Pirate can do."""

    variant: str = "unknown"  # "v3", "v4" or "unknown"
    firmware: Optional[str] = None
    bootloader: Optional[str] = None
    devid: Optional[str] = None
    capabilities: FrozenSet[str] = field(default_factory=frozenset)
    banner: str = ""

    # -- capability queries -------------------------------------------------

    def has(self, capability: str) -> bool:
        return capability in self.capabilities

    def require(self, capability: str) -> None:
        """Raise a message that names where the feature *does* live."""
        if self.has(capability):
            return
        home = _CAPABILITY_HOME.get(capability)
        detail = f" It is a {home} feature." if home else ""
        raise UnsupportedFeatureError(
            f"this device ({self.describe()}) has no '{capability}'.{detail}"
        )

    def describe(self) -> str:
        parts = {"v3": "Bus Pirate v3", "v4": "Bus Pirate v4"}.get(
            self.variant, "unidentified Bus Pirate"
        )
        if self.firmware:
            parts += f", firmware {self.firmware}"
        return parts

    # -- version-dependent tables ------------------------------------------

    @property
    def i2c_speeds(self) -> Dict[int, int]:
        """Speed index to Hz. Two entries on firmware older than v4.2."""
        if _firmware_tuple(self.firmware) < (4, 2):
            return dict(I2C_SPEEDS_LEGACY)
        return dict(I2C_SPEEDS_MODERN)

    @property
    def spi_speeds(self) -> Dict[int, int]:
        return dict(SPI_SPEEDS)


def _firmware_tuple(firmware: Optional[str]) -> tuple:
    """``"v6.1"`` to ``(6, 1)``. Unknown firmware sorts as newest."""
    if not firmware:
        return (99, 99)
    match = re.search(r"(\d+)\.(\d+)", firmware)
    if not match:
        return (99, 99)
    return (int(match.group(1)), int(match.group(2)))


def capabilities_for(variant: str) -> FrozenSet[str]:
    if variant == "v4":
        # The wiki notes binary self-tests are v2go/v3 hardware only.
        return frozenset(
            {CAP_PWM, CAP_ADC, CAP_FREQUENCY, CAP_PULLUP_VOLTAGE, CAP_EXTENDED_AUX}
        )
    if variant == "v3":
        return frozenset({CAP_PWM, CAP_ADC, CAP_FREQUENCY, CAP_SELF_TEST})
    # Unidentified: offer only what every documented variant shares.
    return frozenset({CAP_PWM, CAP_ADC, CAP_FREQUENCY})


# The firmware's 'i' banner looks like:
#   Bus Pirate v3.5
#   Firmware v6.1 r1676  Bootloader v4.4
#   DEVID:0x0447 REVID:0x3046 (24FJ64GA002 B8)
_RE_VARIANT = re.compile(r"Bus\s+Pirate\s+v(\d)", re.IGNORECASE)
_RE_FIRMWARE = re.compile(r"Firmware\s+(v[\w.\-]+)", re.IGNORECASE)
_RE_BOOTLOADER = re.compile(r"Bootloader\s+(v[\d.]+)", re.IGNORECASE)
_RE_DEVID = re.compile(r"DEVID:\s*(0x[0-9A-Fa-f]+)")


def parse_banner(text: str) -> DeviceProfile:
    """Build a profile from the firmware's ``i`` output.

    Anything unrecognised yields the conservative ``unknown`` profile — a
    device that will not identify itself is still perfectly usable.
    """
    variant = "unknown"
    match = _RE_VARIANT.search(text)
    if match:
        major = match.group(1)
        if major in ("3", "4"):
            variant = f"v{major}"
        elif major == "2":
            variant = "v3"  # v2go shares the v3 command set

    def _find(pattern):
        found = pattern.search(text)
        return found.group(1) if found else None

    return DeviceProfile(
        variant=variant,
        firmware=_find(_RE_FIRMWARE),
        bootloader=_find(_RE_BOOTLOADER),
        devid=_find(_RE_DEVID),
        capabilities=capabilities_for(variant),
        banner=text.strip(),
    )


UNKNOWN_PROFILE = DeviceProfile(capabilities=capabilities_for("unknown"))
