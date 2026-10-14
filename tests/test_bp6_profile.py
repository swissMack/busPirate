"""The Bus Pirate 6's profile: its name, firmware and capabilities."""

import pytest

from buspirate import device as d
from buspirate.bp6.protocol import Status
from buspirate.exceptions import UnsupportedFeatureError


def status(**kw):
    base = dict(hardware=(6, 2), firmware_date="Oct 12 2026 09:05:15", firmware_hash="unknown",
                flatbuffers_version=(2, 0))
    base.update(kw)
    return Status(**base)


def test_profile_from_status():
    profile = d.parse_bp6_status(status())
    assert profile.variant == "bp6"
    assert profile.firmware == "2026-10-12"
    assert profile.devid == "hw 6.2"
    assert profile.describe() == "Bus Pirate 6, firmware 2026-10-12"


def test_a_real_git_hash_is_kept():
    assert d.parse_bp6_status(status(firmware_hash="322c452")).firmware == "2026-10-12 (322c452)"


def test_a_bus_pirate_5_is_named_and_marked_untested():
    assert d.parse_bp6_status(status(hardware=(5, 10))).describe().startswith("Bus Pirate 5 (untested)")


def test_capabilities():
    caps = d.capabilities_for("bp6")
    for present in (d.CAP_SUPPLIES, d.CAP_ONEWIRE, d.CAP_SPI_MODES, d.CAP_UART_BUFFERED,
                    d.CAP_SPI_FLASH_PROGRAM, d.CAP_PSU_PROGRAMMABLE, d.CAP_PSU_READOUT):
        assert present in caps
    for absent in (d.CAP_BITBANG_PINS, d.CAP_RAWWIRE, d.CAP_SNIFFER, d.CAP_UART_BRIDGE,
                   d.CAP_PWM, d.CAP_FREQUENCY, d.CAP_PULLUP_VOLTAGE, d.CAP_SELF_TEST,
                   d.CAP_EXTENDED_AUX, d.CAP_ADC):
        assert absent not in caps


def test_missing_psu_capability_names_the_bp6():
    with pytest.raises(UnsupportedFeatureError, match="Bus Pirate 6"):
        d.parse_banner("Bus Pirate v4").require(d.CAP_PSU_PROGRAMMABLE)


def test_an_unknown_date_is_kept_as_is():
    assert d.parse_bp6_status(status(firmware_date="someday")).firmware == "someday"


def test_no_status_still_gives_a_bp6_profile():
    assert d.parse_bp6_status(None).variant == "bp6"
