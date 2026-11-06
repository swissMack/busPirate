"""The Bit Pirate's own modes, described as data and offered from the menu."""

import string

from buspirate import boards
from buspirate.boards._modes import cli_mode_capability
from buspirate.boards.bitpirate_modes import EXTRA_ACTIONS, MODES
from buspirate.capabilities import CAP_CLI_EXTRAS
from buspirate.web import docs

DOCK_GPIOS = {"15", "16", "17", "18", "10", "11", "12", "13"}


def _all_commands():
    for mode in MODES:
        for cmd in mode.commands:
            yield mode.id, cmd
    for panel_id, cmds in EXTRA_ACTIONS.items():
        for cmd in cmds:
            yield panel_id, cmd


def test_the_first_batch_is_these_modes_in_menu_order():
    assert [m.id for m in MODES] == ["onewire_cli", "dio", "jtag", "wifi", "bluetooth"]
    assert {m.id: m.group for m in MODES} == {
        "onewire_cli": "Buses", "dio": "Buses", "jtag": "Buses",
        "wifi": "Wireless", "bluetooth": "Wireless",
    }
    assert set(EXTRA_ACTIONS) == {"i2c", "uart"}


def test_every_command_line_uses_only_its_own_params():
    for owner, cmd in _all_commands():
        names = {n for _, n, _, _ in string.Formatter().parse(cmd.line) if n}
        assert names == {p.name for p in cmd.params}, (owner, cmd.name)


def test_command_names_are_unique_within_their_owner():
    seen = set()
    for owner, cmd in _all_commands():
        assert (owner, cmd.name) not in seen
        seen.add((owner, cmd.name))


def test_mode_ids_are_unique_and_clash_with_no_panel():
    from buspirate.web.registry import load_panels

    taken = {p.id for p in load_panels() if not p.mode or not p.mode.startswith("cli:")}
    ids = [m.id for m in MODES]
    assert len(ids) == len(set(ids))
    assert not (set(ids) & taken)


def test_every_mode_doc_exists():
    for mode in MODES:
        assert docs.read(mode.doc) is not None, mode.doc


def test_only_the_bit_pirate_has_mode_capabilities():
    wanted = {CAP_CLI_EXTRAS} | {cli_mode_capability(m.id) for m in MODES}
    assert wanted <= boards.get("bitpirate").capabilities
    assert boards.get("bitpirate").modes == MODES
    for variant in ("v3", "v4", "bp6"):
        caps = boards.get(variant).capabilities
        assert not any(c == CAP_CLI_EXTRAS or c.startswith("cli_mode:") for c in caps)
        assert boards.get(variant).modes == ()


def test_no_excluded_command_is_offered():
    banned = {"jam", "flood", "glitch", "spam", "deauth", "spoof", "bruteforce",
              "repeater", "ap", "eeprom", "smartcard", "wizard", "openocd"}
    for owner, cmd in _all_commands():
        assert cmd.line.split()[0] not in banned, (owner, cmd.name)


def test_dock_pins_only():
    for mode in MODES:
        for label, value in mode.pins.items():
            assert set(value.split()) <= DOCK_GPIOS, (mode.id, label)
    for owner, cmd in _all_commands():
        for p in cmd.params:
            if p.name == "pin":
                assert p.type == "enum"
                assert {str(c["value"]) for c in p.choices} == DOCK_GPIOS, (owner, cmd.name)


def test_onewire_data_is_on_io15():
    onewire = next(m for m in MODES if m.id == "onewire_cli")
    assert onewire.cli_name == "1wire"
    assert onewire.pins == {"Data GPIO": "15"}
