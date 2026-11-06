"""Each board is described once, in buspirate.boards, and read from there.

The first tests record what every board did before the registry existed, so
moving its facts around cannot change them.
"""

import pytest

from buspirate import device as d

EXPECTED_CAPS = {
    "bitpirate": frozenset(),
    "bp6": frozenset({d.CAP_SUPPLIES, d.CAP_ONEWIRE, d.CAP_SPI_MODES, d.CAP_UART_BUFFERED,
                      d.CAP_SPI_FLASH_PROGRAM, d.CAP_PSU_PROGRAMMABLE, d.CAP_PSU_READOUT}),
    "v4": d.BUS_PIRATE_ONLY | {d.CAP_PWM, d.CAP_ADC, d.CAP_FREQUENCY, d.CAP_PULLUP_VOLTAGE},
    "v3": d.BUS_PIRATE_ONLY | {d.CAP_PWM, d.CAP_ADC, d.CAP_FREQUENCY, d.CAP_SELF_TEST,
                               d.CAP_EXTENDED_AUX},
    "unknown": d.BUS_PIRATE_ONLY | {d.CAP_PWM, d.CAP_ADC, d.CAP_FREQUENCY},
}


@pytest.mark.parametrize("variant", sorted(EXPECTED_CAPS))
def test_capabilities_are_unchanged(variant):
    assert d.capabilities_for(variant) == EXPECTED_CAPS[variant]


@pytest.mark.parametrize("variant, firmware, devid, text", [
    ("v3", "v6.1", None, "Bus Pirate v3, firmware v6.1"),
    ("v4", None, None, "Bus Pirate v4"),
    ("bitpirate", "1.8", None, "ESP32 Bit Pirate, firmware 1.8"),
    ("bp6", None, "hw 6.0", "Bus Pirate 6"),
    ("bp6", None, "hw 5.1", "Bus Pirate 5 (untested)"),
    ("unknown", None, None, "unidentified Bus Pirate"),
])
def test_descriptions_are_unchanged(variant, firmware, devid, text):
    assert d.DeviceProfile(variant=variant, firmware=firmware, devid=devid).describe() == text


def test_the_constants_are_also_in_their_own_module():
    from buspirate import capabilities as c

    assert c.CAP_ONEWIRE == d.CAP_ONEWIRE
    assert c.BUS_PIRATE_ONLY == d.BUS_PIRATE_ONLY
    assert c.CAPABILITY_HOME[c.CAP_SELF_TEST] == "Bus Pirate v3 (and v2go)"
