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
    with pytest.raises(ModeError, match="Enter was pressed to stop it"):
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


# -- the panels (Task 3) ------------------------------------------------------------

MODE_IDS = {"onewire_cli", "dio", "jtag", "wifi", "bluetooth"}


@pytest.fixture
def client():
    fastapi_testclient = pytest.importorskip("fastapi.testclient")
    from buspirate.web.server import create_app

    with fastapi_testclient.TestClient(create_app(use_fake=True)) as c:
        yield c


def _connect(client, port):
    response = client.post("/api/run", json={
        "panel": "connection", "action": "connect", "params": {"port": port}})
    assert response.status_code == 200, response.text


def _panels(client):
    return {p["id"]: p for p in client.get("/api/state").json()["panels"]}


def _run(client, panel, action, **params):
    return client.post("/api/run", json={"panel": panel, "action": action, "params": params})


def test_a_bit_pirate_sees_its_mode_panels(client):
    _connect(client, "simulated-bitpirate")
    panels = _panels(client)
    assert MODE_IDS <= set(panels)
    assert {i: panels[i]["group"] for i in MODE_IDS} == {
        "onewire_cli": "Buses", "dio": "Buses", "jtag": "Buses",
        "wifi": "Wireless", "bluetooth": "Wireless",
    }
    assert panels["i2c"]["group"] == ""
    order = [p["id"] for p in client.get("/api/state").json()["panels"]]
    assert order.index("uart") < order.index("onewire_cli") < order.index("bluetooth")
    assert panels["onewire_cli"]["doc"] == "bitpirate-wiki/02-1wire"
    onewire_wires = {w["signal"]: w["target"] for w in panels["onewire_cli"]["wiring"]}
    assert "IO15" in onewire_wires and "GND" in onewire_wires


def test_a_bus_pirate_sees_none_of_them(client):
    _connect(client, "simulated-v3")
    panels = _panels(client)
    assert not (MODE_IDS & set(panels))
    assert "identify" not in {a["name"] for a in panels["i2c"]["actions"]}
    assert "autobaud" not in {a["name"] for a in panels["uart"]["actions"]}


def test_nothing_connected_shows_none_of_them(client):
    panels = _panels(client)
    assert not (MODE_IDS & set(panels))
    assert "identify" not in {a["name"] for a in panels["i2c"]["actions"]}


def test_running_a_mode_action_returns_lines(client):
    _connect(client, "simulated-bitpirate")
    response = _run(client, "onewire_cli", "temp")
    assert response.status_code == 200, response.text
    result = response.json()["result"]
    assert result["render"] == "lines"
    assert "Temperature: 23.50 °C" in result["lines"]


def test_a_firmware_refusal_is_shown_in_the_boards_words(client):
    _connect(client, "simulated-bitpirate")
    response = _run(client, "wifi", "ping", host="8.8.8.8")
    assert response.status_code == 200, response.text  # the board's own answer
    assert any("Use 'connect' first" in line for line in response.json()["result"]["lines"])


def test_out_of_range_input_is_refused_before_sending(client):
    _connect(client, "simulated-bitpirate")
    response = _run(client, "dio", "pwm", pin=15, freq=1000, duty=150)
    assert response.status_code == 400
    assert "at most 100" in response.json()["error"]
    response = _run(client, "i2c", "identify", address="90")
    assert response.status_code == 400


def test_an_empty_text_field_is_refused_before_sending(client):
    _connect(client, "simulated-bitpirate")
    response = _run(client, "wifi", "connect", ssid="", password="secret")
    assert response.status_code == 400
    assert "Network (SSID)" in response.json()["error"]


def test_the_i2c_panel_gains_identify_on_a_bit_pirate(client):
    _connect(client, "simulated-bitpirate")
    actions = {a["name"] for a in _panels(client)["i2c"]["actions"]}
    assert {"identify", "discovery", "dump", "recover", "sniff_traffic"} <= actions
    response = _run(client, "i2c", "identify", address="50")
    assert response.status_code == 200, response.text
    assert any("[EEPROM] AT24Cxx" in line for line in response.json()["result"]["lines"])


def test_a_mode_stream_stops_on_hiz_and_the_next_command_works(client):
    _connect(client, "simulated-bitpirate")
    response = _run(client, "onewire_cli", "sniff")
    assert response.status_code == 200, response.text
    assert response.json()["result"]["render"] == "stream"
    assert _run(client, "connection", "hiz").status_code == 200
    response = _run(client, "onewire_cli", "ping")
    assert response.status_code == 200, response.text
    assert response.json()["result"]["lines"] == ["OneWire Ping: Device present."]


def test_extra_actions_never_reuse_a_name_on_their_panel():
    from buspirate.web.registry import load_panels

    for panel in load_panels():
        names = [a.name for a in panel.actions]
        assert len(names) == len(set(names)), (panel.id, names)


def test_the_i2c_sniff_extra_streams_on_a_bit_pirate(client):
    _connect(client, "simulated-bitpirate")
    response = _run(client, "i2c", "sniff_traffic")
    assert response.status_code == 200, response.text
    assert response.json()["result"]["render"] == "stream"
    assert client.post("/api/stream/stop").status_code == 200


def test_the_simulator_can_have_no_wifi_in_reach(monkeypatch):
    monkeypatch.setenv("BUSPIRATE_SIM_WIFI", "none")
    assert FakeBitPirateSerial().wifi_networks == []
    monkeypatch.delenv("BUSPIRATE_SIM_WIFI")
    assert FakeBitPirateSerial().wifi_networks


# -- review fixes ------------------------------------------------------------------


def test_the_wifi_password_is_never_shown(client):
    _connect(client, "simulated-bitpirate")
    response = _run(client, "wifi", "connect", ssid="HomeNet", password="hunter2")
    assert response.status_code == 200, response.text
    assert "hunter2" not in response.text


def test_the_wifi_password_is_not_in_a_timeout_error(bp):
    mode = bp.cli_mode(_BY_ID["onewire_cli"])
    bp.serial.onewire_devices = []
    with pytest.raises(ModeError) as caught:
        mode.run("read", timeout=0.3, shown="read ****")
    assert "read ****" in str(caught.value)


def test_a_stopped_autobaud_still_forgets_the_baud_rate(client):
    from dataclasses import replace

    from buspirate.web.panels.cli_modes import action_for

    _connect(client, "simulated-bitpirate")
    session = _session(client)
    uart = session.ensure_mode("uart")
    session.bp.settings["UART"]["Baud rate"] = "115200"
    # No target talks, so it is stopped; the board is left at its last probe rate.
    quick = replace(EXTRA_ACTIONS["uart"][0], timeout=0.3)
    with pytest.raises(ModeError):
        action_for(quick).handler(type("Ctx", (), {"mode": uart})())
    assert "Baud rate" not in session.bp.settings["UART"]


def test_hiz_releases_pins_dio_drove(client):
    _connect(client, "simulated-bitpirate")
    assert _run(client, "dio", "set", pin=15, level="H").status_code == 200
    assert _run(client, "dio", "pwm", pin=16, freq=1000, duty=50).status_code == 200
    assert _run(client, "connection", "hiz").status_code == 200
    # The board's own record: nothing driven, no PWM.
    fake = _session(client).bp.serial
    assert fake.dio_levels == {} and fake.dio_pwm == {}
    assert fake.mode == "HIZ"


def test_a_bad_field_is_refused_before_the_mode_changes(client):
    _connect(client, "simulated-bitpirate")
    assert _run(client, "i2c", "scan").status_code == 200
    fake = _session(client).bp.serial
    response = _run(client, "wifi", "connect", ssid="", password="x")
    assert response.status_code == 400
    assert fake.mode == "I2C"
    assert not any(c.lower() == "m wifi" for c in fake.commands)


def _session(client):
    for route in client.app.routes:
        endpoint = getattr(route, "endpoint", None)
        cells = getattr(endpoint, "__closure__", None) or ()
        for cell in cells:
            value = cell.cell_contents
            if type(value).__name__ == "DeviceSession":
                return value
    raise AssertionError("no session")
