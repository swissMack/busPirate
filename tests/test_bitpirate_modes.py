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


# -- the driver: one generic mode (Task 2) -------------------------------------

import pytest  # noqa: E402

from buspirate.bitpirate import BitPirate  # noqa: E402
from buspirate.exceptions import ModeError  # noqa: E402
from buspirate.simulator import fake_factory  # noqa: E402
from buspirate.simulator_bitpirate import FakeBitPirateSerial  # noqa: E402

_BY_ID = {m.id: m for m in MODES}


@pytest.fixture
def fake():
    return FakeBitPirateSerial()


@pytest.fixture
def bp(fake):
    device = BitPirate("/dev/fake-bitpirate", serial_factory=fake_factory(fake),
                       reply_timeout=0.3, connect_timeout=0.3)
    with device.open():
        yield device


def test_running_a_command_returns_its_reply_lines(bp, fake):
    lines = bp.cli_mode(_BY_ID["onewire_cli"]).run("scan")
    assert any(line.startswith("Device 1: 28 ") for line in lines), lines
    assert not any(line.endswith("> ") or line == "scan" for line in lines)


def test_entering_a_mode_puts_its_pins_on_the_dock(bp, fake):
    bp.cli_mode(_BY_ID["onewire_cli"])
    assert fake.mode == "1WIRE"
    assert fake.settings["1WIRE"]["Data GPIO"] == "15"
    bp.mode.close()
    bp.cli_mode(_BY_ID["jtag"])
    assert fake.settings["JTAG"]["GPIOs to scan (SWD/JTAG)"] == "15 16 17 18 10 11 12 13"


def test_a_mode_without_config_is_entered_without_one(bp, fake):
    bp.cli_mode(_BY_ID["dio"])
    assert fake.mode == "DIO"
    assert "config" not in fake.commands


def test_an_unknown_command_raises_with_the_boards_words(bp):
    mode = bp.cli_mode(_BY_ID["dio"])
    with pytest.raises(ModeError, match="Unknown command"):
        mode.run("frobnicate")


def test_a_usage_reply_is_an_error_too(bp):
    mode = bp.cli_mode(_BY_ID["dio"])
    with pytest.raises(ModeError, match="Usage: read <gpio>"):
        mode.run("read")


def test_a_command_that_never_ends_is_stopped_and_reported(bp, fake):
    fake.onewire_devices = []  # "read" then waits for a part forever
    mode = bp.cli_mode(_BY_ID["onewire_cli"])
    with pytest.raises(ModeError, match="stopped"):
        mode.run("read", timeout=0.3)
    # Enter stopped it: the board is back at its prompt and takes commands.
    assert fake._state == "prompt"
    assert mode.run("ping") == ["OneWire Ping: No device found."]


def test_forgetting_drops_the_cached_answers(bp, fake):
    uart = bp.uart()
    assert bp.settings["UART"]["TX GPIO number"] == "10"
    bp.settings["UART"]["Baud rate"] = "9600"
    uart.forget(("Baud rate",))
    assert "Baud rate" not in bp.settings["UART"]
    assert bp.settings["UART"]["TX GPIO number"] == "10"


# -- the session (Task 2) ---------------------------------------------------------


@pytest.fixture
def session():
    pytest.importorskip("fastapi")
    from buspirate.web.session import DeviceSession

    s = DeviceSession(use_fake=True)
    s.connect_blocking("simulated-bitpirate")
    yield s
    s.disconnect_blocking()


def test_switching_between_cli_and_bus_modes_reenters_each(session):
    fake = session.bp.serial
    session.ensure_mode("cli:onewire_cli")
    assert fake.mode == "1WIRE"
    session.ensure_mode("i2c")
    assert fake.mode == "I2C"
    assert fake.settings["I2C"]["SDA GPIO"] == "15"
    session.ensure_mode("cli:onewire_cli")
    assert fake.mode == "1WIRE"
    assert fake.settings["1WIRE"]["Data GPIO"] == "15"
    session.ensure_mode("cli:dio")
    assert fake.mode == "DIO"


def test_an_unknown_cli_mode_is_refused(session):
    with pytest.raises(ModeError, match="no Bit Pirate mode"):
        session.ensure_mode("cli:nope")


def test_a_streaming_command_stops_and_the_next_command_works(bp, fake):
    mode = bp.cli_mode(_BY_ID["onewire_cli"])
    mode.start_stream("sniff")
    assert bp.streaming and fake._state == "stream"
    bp.stop_stream()  # what Stop, HiZ and Disconnect all call
    assert not bp.streaming and fake._state == "prompt"
    assert bp.cli_mode(_BY_ID["onewire_cli"]).run("ping") == ["OneWire Ping: Device present."]
