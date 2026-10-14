"""Device variants, firmware capabilities and the banner parser.

A Bus Pirate v3 and a v4 speak nearly the same binary protocol, but not
quite: the v4 adds pull-up voltage selection, the v3 has binary self-tests the
v4 does not, and only a v3 can use the extended AUX command, and firmware v4.2 redefined the I2C
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

# What every Bus Pirate's binary protocol offers and the ESP32 Bit Pirate's
# text command line does not. Offered to v3, v4 and unidentified boards alike,
# so nothing the dashboard showed a Bus Pirate before is hidden from it now.
CAP_BITBANG_PINS = "bitbang_pins"
CAP_SUPPLIES = "switchable_supplies"
CAP_ONEWIRE = "onewire"
CAP_RAWWIRE = "rawwire"
CAP_SNIFFER = "sniffer"
CAP_SPI_MODES = "spi_modes"
CAP_UART_BUFFERED = "uart_buffered_receive"
CAP_UART_BRIDGE = "uart_bridge"
CAP_SPI_FLASH_PROGRAM = "spi_flash_program"

# The Bus Pirate 6's programmable supply: set volts and a current limit, and
# read back what the target draws.
CAP_PSU_PROGRAMMABLE = "psu_programmable"
CAP_PSU_READOUT = "psu_current_readout"

BUS_PIRATE_ONLY = frozenset(
    {
        CAP_BITBANG_PINS,
        CAP_SUPPLIES,
        CAP_ONEWIRE,
        CAP_RAWWIRE,
        CAP_SNIFFER,
        CAP_SPI_MODES,
        CAP_UART_BUFFERED,
        CAP_UART_BRIDGE,
        CAP_SPI_FLASH_PROGRAM,
    }
)

# Which variant to name in an error when a capability is missing.
_CAPABILITY_HOME = {
    CAP_SELF_TEST: "Bus Pirate v3 (and v2go)",
    CAP_PULLUP_VOLTAGE: "Bus Pirate v4",
    CAP_EXTENDED_AUX: "Bus Pirate v3 with firmware v6.1 or newer",
    CAP_PSU_PROGRAMMABLE: "Bus Pirate 6",
    CAP_PSU_READOUT: "Bus Pirate 6",
    **{capability: "Bus Pirate v3 and v4" for capability in BUS_PIRATE_ONLY},
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

    variant: str = "unknown"  # "v3", "v4", "bitpirate", "bp6" or "unknown"
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
        if self.variant == "bp6":
            parts = (
                "Bus Pirate 5 (untested)" if (self.devid or "").startswith("hw 5.") else "Bus Pirate 6"
            )
        else:
            parts = {
                "v3": "Bus Pirate v3",
                "v4": "Bus Pirate v4",
                "bitpirate": "ESP32 Bit Pirate",
            }.get(self.variant, "unidentified Bus Pirate")
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
    if variant == "bitpirate":
        # A text command line, not the binary protocol: none of the binary
        # extras, and no supplies to switch. What it can do is I2C, SPI and
        # UART through its own commands — see buspirate.bitpirate.
        return frozenset()
    if variant == "bp6":
        # BPIO2: I2C, SPI (any mode, page writes fit in 512 bytes), UART with
        # its async receive, 1-Wire, and the programmable supply. No bitbang,
        # raw-wire, sniffers or bridge — see buspirate.bp6.
        return frozenset(
            {CAP_SUPPLIES, CAP_ONEWIRE, CAP_SPI_MODES, CAP_UART_BUFFERED,
             CAP_SPI_FLASH_PROGRAM, CAP_PSU_PROGRAMMABLE, CAP_PSU_READOUT}
        )
    if variant == "v4":
        # The wiki notes binary self-tests are v2go/v3 hardware only.
        # No extended AUX: the firmware reads its sub-command from the PIC's
        # hardware UART, which on a v4 is not the host link — it waits
        # forever. Found on a real v4 on firmware 7.0, 2026-09-28.
        return BUS_PIRATE_ONLY | frozenset(
            {CAP_PWM, CAP_ADC, CAP_FREQUENCY, CAP_PULLUP_VOLTAGE}
        )
    if variant == "v3":
        # On a v3 that UART is the FT232R link, so extended AUX works.
        return BUS_PIRATE_ONLY | frozenset(
            {CAP_PWM, CAP_ADC, CAP_FREQUENCY, CAP_SELF_TEST, CAP_EXTENDED_AUX}
        )
    # Unidentified: offer only what every documented variant shares.
    return BUS_PIRATE_ONLY | frozenset({CAP_PWM, CAP_ADC, CAP_FREQUENCY})


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

    firmware = _find(_RE_FIRMWARE)
    capabilities = capabilities_for(variant)
    if _firmware_tuple(firmware) < (6, 1):
        # The extended AUX command arrived in v6.1; older firmware answers
        # it as an unknown command (seen on a real v4 on 6.0-a3).
        capabilities -= {CAP_EXTENDED_AUX}
    return DeviceProfile(
        variant=variant,
        firmware=firmware,
        bootloader=_find(_RE_BOOTLOADER),
        devid=_find(_RE_DEVID),
        capabilities=capabilities,
        banner=text.strip(),
    )


UNKNOWN_PROFILE = DeviceProfile(capabilities=capabilities_for("unknown"))


# The ESP32 Bit Pirate's welcome screen (src/Views/SerialTerminalView.cpp):
#        ESP32 SWISS ARMY KNIFE
#   Version 1.7           Ready to board
# It is printed once, after the first key following boot, so a board met
# mid-session never shows it and its version stays unknown.
_RE_BITPIRATE_VERSION = re.compile(r"Version\s+(\d[\w.\-]*)")
# Its prompt is the mode in capitals, '>' and a space: "HIZ> ", "I2C> ". A Bus
# Pirate's is mixed case with no space ("HiZ>"), so the two never collide.
_RE_BITPIRATE_PROMPT = re.compile(r"(?m)^[A-Z0-9]*> ")


def looks_like_bitpirate(text: str) -> bool:
    """Whether terminal output came from an ESP32 Bit Pirate.

    Matches its banner, its "Press any key" boot pause, its line-redraw escape
    (every key it echoes is ``\\r<prompt><line>ESC[K``) or its prompt.
    """
    if any(mark in text for mark in ("SWISS ARMY", "Bit Pirate", "Press any key")):
        return True
    if "\x1b[K" in text:
        return True
    # Only what follows the last carriage return of each line is on screen.
    lines = [line.rsplit("\r", 1)[-1] for line in text.replace("\r\n", "\n").split("\n")]
    return bool(_RE_BITPIRATE_PROMPT.search("\n".join(lines)))


def parse_bitpirate_banner(text: str) -> DeviceProfile:
    """A Bit Pirate profile, with the firmware version if the banner was seen."""
    found = _RE_BITPIRATE_VERSION.search(text)
    return DeviceProfile(
        variant="bitpirate",
        firmware=found.group(1) if found else None,
        capabilities=capabilities_for("bitpirate"),
        banner=text.strip(),
    )


def _bp6_firmware(date: str, git_hash: str) -> Optional[str]:
    """``Oct 12 2026 09:05:15`` to ``2026-10-12``; CI builds say hash ``unknown``."""
    import datetime

    if not date:
        return None
    try:
        shown = datetime.datetime.strptime(date, "%b %d %Y %H:%M:%S").strftime("%Y-%m-%d")
    except ValueError:
        shown = date
    if git_hash and git_hash != "unknown":
        shown += f" ({git_hash})"
    return shown


def parse_bp6_status(status) -> DeviceProfile:
    """A Bus Pirate 6 profile from a BPIO2 StatusResponse (or None)."""
    if status is None:
        return DeviceProfile(variant="bp6", capabilities=capabilities_for("bp6"))
    major, minor = status.hardware
    return DeviceProfile(
        variant="bp6",
        firmware=_bp6_firmware(status.firmware_date, status.firmware_hash),
        devid=f"hw {major}.{minor}",
        capabilities=capabilities_for("bp6"),
        banner=(f"Bus Pirate hardware {major}.{minor}, firmware built "
                f"{status.firmware_date}, BPIO2 {status.flatbuffers_version[0]}."
                f"{status.flatbuffers_version[1]}"),
    )
