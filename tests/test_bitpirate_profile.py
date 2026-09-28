"""The ESP32 Bit Pirate's profile: what it is, and what it cannot do."""

import pytest

from buspirate.device import (
    BUS_PIRATE_ONLY,
    CAP_BITBANG_PINS,
    CAP_SUPPLIES,
    capabilities_for,
    looks_like_bitpirate,
    parse_bitpirate_banner,
)
from buspirate.exceptions import UnsupportedFeatureError

# The welcome screen, as src/Views/SerialTerminalView.cpp prints it.
BANNER = (
    "    ____  _ _     ____  _           _       \r\n"
    "   | __ )(_) |_  |  _ \\(_)_ __ __ _| |_ ___ \r\n"
    "\r\n"
    "             ESP32 SWISS ARMY KNIFE\r\n"
    "\r\n"
    "     Version 1.7           Ready to board\r\n"
    "\r\n"
    " Type 'mode' to start or 'help' for commands\r\n"
)


def test_the_banner_names_the_firmware_version():
    profile = parse_bitpirate_banner(BANNER)
    assert profile.variant == "bitpirate"
    assert profile.firmware == "1.7"
    assert profile.describe() == "ESP32 Bit Pirate, firmware 1.7"


def test_a_board_met_mid_session_has_no_banner_but_is_still_a_bit_pirate():
    profile = parse_bitpirate_banner("")
    assert profile.variant == "bitpirate"
    assert profile.firmware is None
    assert profile.describe() == "ESP32 Bit Pirate"


@pytest.mark.parametrize("capability", sorted(BUS_PIRATE_ONLY))
def test_nothing_bus_pirate_only_is_offered(capability):
    assert capability not in capabilities_for("bitpirate")


@pytest.mark.parametrize("variant", ["v3", "v4", "unknown"])
def test_every_bus_pirate_keeps_the_bus_pirate_only_features(variant):
    assert BUS_PIRATE_ONLY <= capabilities_for(variant)


def test_asking_for_the_supplies_names_where_they_live():
    profile = parse_bitpirate_banner(BANNER)
    with pytest.raises(UnsupportedFeatureError, match="Bus Pirate v3 and v4"):
        profile.require(CAP_SUPPLIES)
    assert not profile.has(CAP_BITBANG_PINS)


@pytest.mark.parametrize(
    "text",
    [
        BANNER,
        "\rHIZ> i\x1b[K\r\nType 'help' or 'mode'\r\nHIZ> ",
        "\r\n\rPress any key to start...\r\n",
        "I2C> ",
    ],
)
def test_bit_pirate_output_is_recognised(text):
    assert looks_like_bitpirate(text)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "Bus Pirate v3.5\r\nFirmware v6.1 r1676  Bootloader v4.4\r\nHiZ>",
        "HiZ>",
        "I2C>",
    ],
)
def test_a_bus_pirate_is_not_mistaken_for_one(text):
    assert not looks_like_bitpirate(text)
