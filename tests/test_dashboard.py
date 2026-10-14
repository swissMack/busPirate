"""The dashboard API, driven against a simulated Bus Pirate."""

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")

from buspirate.web.params import ParamError, coerce  # noqa: E402
from buspirate.web.registry import Param, load_panels, show_as  # noqa: E402
from buspirate.web.server import create_app  # noqa: E402


@pytest.fixture(params=["v3", "v4"])
def client(request):
    app = create_app(use_fake=True, fake_variant=request.param)
    with fastapi_testclient.TestClient(app) as client:
        client.variant = request.param
        yield client


def run(client, panel, action, **params):
    response = client.post(
        "/api/run", json={"panel": panel, "action": action, "params": params}
    )
    return response.status_code, response.json()


def connect(client):
    status, body = run(client, "connection", "connect", port="")
    assert status == 200, body
    return body


# -- registry --------------------------------------------------------------


def test_every_panel_declares_usable_actions():
    for panel in load_panels():
        assert panel.title and panel.blurb, panel.id
        assert panel.actions, panel.id
        for action in panel.actions:
            assert callable(action.handler)
            names = [p.name for p in action.params]
            assert len(names) == len(set(names)), (panel.id, action.name)


def test_power_and_pullups_start_unticked():
    # A 3.3V-only target must never be powered or pulled up by default: the
    # v4's pull-ups follow VPU, which can be on the 5V rail.
    for panel in load_panels():
        for action in panel.actions:
            for param in action.params:
                if param.name in ("power", "pullups"):
                    assert param.default is False, (panel.id, action.name, param.name)


def test_state_lists_panels_before_connecting(client):
    body = client.get("/api/state").json()
    assert body["status"]["connected"] is False
    assert [p["id"] for p in body["panels"]][0] == "connection"


def test_terminal_is_its_own_panel_right_after_connection(client):
    # open_terminal and send_keys moved off the Connection panel onto their
    # own panel, grouped together, immediately after Connection in the nav.
    body = client.get("/api/state").json()
    panel_ids = [p["id"] for p in body["panels"]]
    assert "terminal" in panel_ids
    assert panel_ids.index("terminal") == panel_ids.index("connection") + 1
    panels = {p["id"]: p for p in body["panels"]}
    terminal_actions = {a["name"] for a in panels["terminal"]["actions"]}
    assert terminal_actions == {"open_terminal", "send_keys"}
    connection_actions = {a["name"] for a in panels["connection"]["actions"]}
    assert "open_terminal" not in connection_actions
    assert "send_keys" not in connection_actions


def test_ports_endpoint_offers_the_simulated_device(client):
    ports = client.get("/api/ports").json()["ports"]
    assert ports[0]["device"] == f"simulated-{client.variant}"
    assert ports[0]["likely"]


# -- the simulator as an option in a normal (hardware) launch -----------------


@pytest.fixture
def hardware_client(monkeypatch):
    """A dashboard started for real hardware, with nothing plugged in."""
    from buspirate import ports as ports_module
    from buspirate.web import session as session_module

    monkeypatch.setattr(ports_module, "discover", lambda include_unlikely=False: [])
    monkeypatch.setattr(session_module, "discover", lambda include_unlikely=False: [])
    app = create_app(use_fake=False)
    with fastapi_testclient.TestClient(app) as client:
        yield client


def test_hardware_launch_still_offers_every_simulator(hardware_client):
    ports = hardware_client.get("/api/ports").json()["ports"]
    simulated = {p["device"]: p for p in ports if p.get("simulated")}
    assert set(simulated) == {
        "simulated-v3", "simulated-v4", "simulated-bitpirate", "simulated-bp6"
    }
    # Offered, but never what "detect automatically" picks.
    assert not any(p["likely"] for p in simulated.values())


@pytest.mark.parametrize("variant", ["v3", "v4"])
def test_hardware_launch_can_connect_to_a_simulator(hardware_client, variant):
    status, body = run(
        hardware_client, "connection", "connect", port=f"simulated-{variant}"
    )
    assert status == 200, body
    assert body["status"]["simulated"] is True
    assert body["status"]["variant"] == variant
    assert body["status"]["usb"]["simulated"] is True
    # And it drives like the real thing.
    status, body = run(hardware_client, "i2c", "scan", power=True, pullups=True)
    assert status == 200, body


def test_disconnecting_a_simulator_returns_to_hardware(hardware_client):
    run(hardware_client, "connection", "connect", port="simulated-v3")
    run(hardware_client, "connection", "disconnect")
    state = hardware_client.get("/api/state").json()["status"]
    assert state["connected"] is False
    assert state["simulated"] is False


def test_auto_detect_never_falls_back_to_the_simulator(hardware_client):
    status, body = run(hardware_client, "connection", "connect", port="")
    assert status != 200
    assert "simulated" in str(body).lower()  # the error points at it
    state = hardware_client.get("/api/state").json()["status"]
    assert state["connected"] is False


# -- connecting ------------------------------------------------------------


def test_connect_reports_the_device(client):
    body = connect(client)
    assert body["status"]["connected"] is True
    assert body["status"]["variant"] == client.variant
    assert "Connected" in body["result"]["text"]


def test_actions_are_filtered_by_capability(client):
    body = connect(client)
    panels = {p["id"]: p for p in body["panels"]}
    i2c_actions = {a["name"] for a in panels["i2c"]["actions"]}
    connection_actions = {a["name"] for a in panels["connection"]["actions"]}
    if client.variant == "v4":
        assert "pullup_voltage" in i2c_actions
        assert "self_test" not in connection_actions
    else:
        assert "pullup_voltage" not in i2c_actions
        assert "self_test" in connection_actions


def test_running_an_action_before_connecting_explains_itself(client):
    status, body = run(client, "i2c", "scan", power=True, pullups=True, speed=2)
    assert status == 400
    assert "not connected" in body["error"]


def test_disconnect_leaves_a_clean_state(client):
    connect(client)
    run(client, "connection", "disconnect")
    assert client.get("/api/state").json()["status"]["connected"] is False


def test_the_terminal_warns_before_it_takes_the_board(client):
    body = connect(client)
    panels = {p["id"]: p for p in body["panels"]}
    action = next(a for a in panels["terminal"]["actions"]
                  if a["name"] == "open_terminal")
    assert action["confirm"], "opening the terminal must confirm first"


def test_send_keys_is_refused_when_the_terminal_is_not_open(client):
    connect(client)
    status, body = run(client, "terminal", "send_keys", keys="i")
    assert status == 400
    assert "terminal" in body["error"]


def test_send_keys_is_hidden_from_automatic_form_rendering(client):
    body = connect(client)
    panels = {p["id"]: p for p in body["panels"]}
    action = next(a for a in panels["terminal"]["actions"]
                  if a["name"] == "send_keys")
    assert action["hidden"] is True


def test_open_terminal_is_not_hidden(client):
    body = connect(client)
    panels = {p["id"]: p for p in body["panels"]}
    action = next(a for a in panels["terminal"]["actions"]
                  if a["name"] == "open_terminal")
    assert action["hidden"] is False


# -- HiZ: release everything, stay connected --------------------------------


def hiz_action(body):
    panels = {p["id"]: p for p in body["panels"]}
    return next(a for a in panels["connection"]["actions"] if a["name"] == "hiz")


def test_hiz_is_an_action_the_sidebar_draws_not_the_form(client):
    action = hiz_action(connect(client))
    assert action["label"] == "HiZ"
    assert action["hidden"] is True
    assert action["allow_while_streaming"] is True


def test_hiz_releases_every_pin_and_stays_connected(client):
    connect(client)
    run(client, "pins", "supplies", on=True)
    run(client, "pins", "set_pins", pullups=True, aux=True,
        mosi=True, clk=True, miso=True, cs=True)
    fake = client.app.state.session.bp.serial
    fake.directions = 0x00  # as if a script had made every pin an output
    status, body = run(client, "connection", "hiz")
    assert status == 200, body
    assert "HiZ" in body["result"]["text"]
    assert fake.pins == 0x00  # supplies, pull-ups and every pin off
    assert fake.directions == 0x1F  # and every pin an input
    state = client.get("/api/state").json()["status"]
    assert state["connected"] is True
    assert state["mode"] is None
    assert state["supplies"] is False


def test_hiz_leaves_a_protocol_mode(client):
    connect(client)
    run(client, "i2c", "scan", power=True, pullups=True, speed=2)
    status, body = run(client, "connection", "hiz")
    assert status == 200, body
    state = client.get("/api/state").json()["status"]
    assert state["mode"] is None
    assert state["supplies"] is False


def test_hiz_stops_pwm(client):
    connect(client)
    if "pwm" not in client.get("/api/state").json()["status"]["capabilities"]:
        pytest.skip("no PWM on this board")
    run(client, "pins", "pwm", frequency=1000, duty_cycle=50)
    fake = client.app.state.session.bp.serial
    assert fake.pwm_running
    run(client, "connection", "hiz")
    assert not fake.pwm_running


def live(client):
    return client.get("/api/state").json()["status"]["live"]


def test_a_fresh_connection_is_in_hiz(client):
    connect(client)
    assert live(client) == []


def test_each_live_thing_is_named_and_hiz_clears_them_all(client):
    connect(client)
    run(client, "pins", "supplies", on=True)
    assert live(client) == ["supplies on"]
    run(client, "pins", "set_pins", pullups=True, aux=False,
        mosi=False, clk=False, miso=False, cs=True)
    assert live(client) == ["supplies on", "pull-ups on", "pins driven"]
    run(client, "connection", "hiz")
    assert live(client) == []


def test_a_protocol_mode_is_live(client):
    connect(client)
    run(client, "i2c", "scan", power=False, pullups=False, speed=2)
    assert live(client) == ["I2C mode"]
    run(client, "connection", "hiz")
    assert live(client) == []


def test_pwm_is_live_until_stopped(client):
    connect(client)
    if "pwm" not in client.get("/api/state").json()["status"]["capabilities"]:
        pytest.skip("no PWM on this board")
    run(client, "pins", "pwm", frequency=1000, duty_cycle=50)
    assert live(client) == ["PWM on AUX"]
    run(client, "pins", "pwm_clear")
    assert live(client) == []
    run(client, "pins", "pwm", frequency=1000, duty_cycle=50)
    run(client, "connection", "hiz")
    assert live(client) == []


def test_nothing_is_live_before_connecting(client):
    assert "live" not in client.get("/api/state").json()["status"]


def test_hiz_before_connecting_explains_itself(client):
    status, body = run(client, "connection", "hiz")
    assert status == 400
    assert "not connected" in body["error"]


# -- the panels do what they say ------------------------------------------


def test_i2c_scan_finds_the_simulated_devices(client):
    connect(client)
    status, body = run(client, "i2c", "scan", power=True, pullups=True, speed=2)
    assert status == 200, body
    labels = [item["label"] for item in body["result"]["items"]]
    assert labels == ["0x50", "0x68"]
    assert "24Cxx EEPROM" in body["result"]["items"][0]["sub"]


def test_i2c_read_register_returns_a_hexdump(client):
    connect(client)
    status, body = run(client, "i2c", "read_register", address="0x50", register="0", count=8)
    assert status == 200, body
    assert body["result"]["render"] == "hex"
    assert len(body["result"]["data"]) == 8


def test_i2c_reads_can_be_shown_in_decimal(client):
    connect(client)
    status, body = run(client, "i2c", "read_register", address="0x50", register="0x10",
                       count=4, show="dec")
    assert status == 200, body
    assert body["result"]["render"] == "table"
    assert body["result"]["columns"] == ["Register", "Hex", "Decimal"]
    assert [row[0] for row in body["result"]["rows"]] == ["0x10", "0x11", "0x12", "0x13"]

    status, body = run(client, "i2c", "read", address="0x50", count=2, show="u16be")
    assert status == 200, body
    assert len(body["result"]["rows"]) == 1


def test_show_as_decodes_bytes_and_words():
    # A real AHT20 reply, and the start of a BMP280's calibration block.
    aht20 = bytes.fromhex("0c 74 79 16 3c 0f 81")
    rows = show_as(aht20, "dec")["rows"]
    assert [row[2] for row in rows] == [12, 116, 121, 22, 60, 15, 129]
    assert show_as(aht20, "hex")["render"] == "hex"

    cal = bytes.fromhex("70 6b 43 67 18 fc")
    assert [r[2] for r in show_as(cal, "u16le", start=0x88)["rows"]] == [27504, 26435, 64536]
    assert [r[2] for r in show_as(cal, "s16le", start=0x88)["rows"]] == [27504, 26435, -1000]
    assert [r[0] for r in show_as(cal, "s16le", start=0x88)["rows"]] == ["0x88", "0x8A", "0x8C"]
    assert [r[2] for r in show_as(cal, "u16be")["rows"]] == [0x706B, 0x4367, 0x18FC]

    odd = show_as(aht20, "u16be")
    assert len(odd["rows"]) == 3
    assert "0x81" in odd["caption"]


def test_i2c_write_to_a_missing_device_is_a_plain_sentence(client):
    connect(client)
    status, body = run(client, "i2c", "write", address="0x11", data="00")
    assert status == 400
    assert "did not acknowledge" in body["error"]
    assert "Traceback" not in body["error"]


def test_spi_identifies_a_chip(client):
    connect(client)
    status, body = run(client, "spi", "jedec_id", power=True, speed=3, spi_mode=0)
    assert status == 200, body
    pairs = dict(body["result"]["pairs"])
    assert pairs["Raw ID"] == "a5 a5 a5"


def test_spi_dump_writes_a_file(client, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    connect(client)
    status, body = run(
        client, "spi", "flash_dump", length=2048, filename="dump.bin",
        power=True, speed=3, spi_mode=0,
    )
    assert status == 200, body
    written = tmp_path / "captures" / "dump.bin"
    assert written.exists() and written.stat().st_size == 2048


def test_a_dump_cannot_escape_the_captures_directory(client):
    connect(client)
    status, body = run(
        client, "spi", "flash_dump", length=16, filename="../../etc/passwd",
        power=True, speed=3, spi_mode=0,
    )
    assert status == 400
    assert "plain file name" in body["error"]


def test_uart_sends_text(client):
    connect(client)
    run(client, "uart", "configure", baud=10, framing=0, stop_bits=1, power=False)
    status, body = run(client, "uart", "send_text", message="AT", newline=True)
    assert status == 200, body
    assert "Sent 4 byte(s)" in body["result"]["caption"]
    assert body["result"]["rows"][0] == ["→ sent", "41 54 0d 0a", "AT.."]


def test_onewire_search_names_the_family(client):
    connect(client)
    status, body = run(client, "onewire", "search", power=True, pullups=True)
    assert status == 200, body
    assert body["result"]["rows"][0][2] == "DS18B20 thermometer"


def test_pins_panel_reports_the_state_it_set(client):
    connect(client)
    run(client, "pins", "supplies", on=True)
    status, body = run(
        client, "pins", "set_pins", pullups=False, aux=False,
        mosi=False, clk=False, miso=False, cs=True,
    )
    assert status == 200, body
    assert body["result"]["state"] == {
        "power": True, "pullups": False, "aux": False, "mosi": False,
        "clk": False, "miso": False, "cs": True,
    }


def test_switching_panels_switches_modes(client):
    connect(client)
    run(client, "i2c", "scan", power=True, pullups=True, speed=2)
    assert client.get("/api/state").json()["status"]["mode"] == "i2c"
    run(client, "spi", "jedec_id", power=True, speed=3, spi_mode=0)
    assert client.get("/api/state").json()["status"]["mode"] == "spi"
    # The pins panel works in bitbang mode, so it leaves the protocol mode.
    run(client, "pins", "set_pins", pullups=False, aux=False,
        mosi=False, clk=False, miso=False, cs=False)
    assert client.get("/api/state").json()["status"]["mode"] is None


def test_traffic_is_recorded_for_the_live_log(client):
    connect(client)
    run(client, "i2c", "scan", power=True, pullups=True, speed=2)
    traffic = client.get("/api/state").json()["traffic"]
    assert traffic
    assert {entry["direction"] for entry in traffic} == {"tx", "rx"}


def test_an_unknown_action_is_a_404(client):
    status, body = run(client, "i2c", "nope")
    assert status == 404


# -- parameter coercion ----------------------------------------------------


@pytest.mark.parametrize(
    "given,expected",
    [("0x50", 0x50), ("50", 0x50), (0x50, 0x50), (" 0X50 ", 0x50)],
)
def test_hex_params_accept_the_obvious_spellings(given, expected):
    assert coerce(Param("a", "hex", "Address"), given) == expected


@pytest.mark.parametrize(
    "given,expected",
    [
        ("de ad be ef", b"\xde\xad\xbe\xef"),
        ("DEADBEEF", b"\xde\xad\xbe\xef"),
        ("0xDE, 0xAD", b"\xde\xad"),
        ("de:ad", b"\xde\xad"),
        ("", b""),
    ],
)
def test_byte_params_accept_the_obvious_spellings(given, expected):
    assert coerce(Param("d", "bytes", "Data"), given) == expected


def test_a_bad_byte_string_says_what_was_wanted():
    with pytest.raises(ParamError, match="de ad be ef"):
        coerce(Param("d", "bytes", "Data"), "hello there")


def test_odd_hex_digits_are_rejected():
    with pytest.raises(ParamError, match="even number"):
        coerce(Param("d", "bytes", "Data"), "abc")


def test_numbers_are_range_checked():
    param = Param("n", "int", "Count", minimum=1, maximum=16)
    assert coerce(param, "8") == 8
    with pytest.raises(ParamError, match="at most 16"):
        coerce(param, "17")
    with pytest.raises(ParamError, match="at least 1"):
        coerce(param, "0")


def test_enum_params_accept_the_string_a_browser_sends():
    param = Param("s", "enum", "Speed", choices=[{"value": 2, "label": "100 kHz"}])
    assert coerce(param, "2") == 2
    with pytest.raises(ParamError, match="choose one of"):
        coerce(param, "9")


def test_the_power_control_says_what_it_actually_switches(client):
    body = connect(client)
    panels = {p["id"]: p for p in body["panels"]}
    scan = next(a for a in panels["i2c"]["actions"] if a["name"] == "scan")
    power = next(p for p in scan["params"] if p["name"] == "power")
    assert "3.3V + 5V" in power["label"]
    assert any("no command to pick one" in note for note in panels["i2c"]["notes"])


def test_the_v4_pullup_rail_refusal_reaches_the_user(client):
    if client.variant != "v4":
        pytest.skip("pull-up rail selection is a v4 feature")
    connect(client)
    session = client.app.state.session
    session.bp.serial.vextern_powered = True
    status, body = run(client, "i2c", "pullup_voltage", selection=2)
    assert status == 400
    assert "VPU" in body["error"] and "protection" in body["error"]


# -- the guide, served from docs/ -----------------------------------------


def test_the_guide_is_served_from_the_docs_directory(client):
    pages = client.get("/api/docs").json()["pages"]
    names = [p["name"] for p in pages]
    assert names[0] == "user-guide"
    assert {"i2c", "spi", "uart", "onewire", "troubleshooting"} <= set(names)
    assert all(p["title"] for p in pages)


def test_a_guide_page_returns_its_markdown(client):
    body = client.get("/api/docs/i2c").json()
    assert body["markdown"].startswith("# I2C")


def test_the_guide_cannot_be_used_to_read_other_files(client):
    # An empty name is the index route, not a traversal, so it is not here.
    for attempt in ["../pyproject", "../../etc/passwd", "..", "Makefile", "../README"]:
        assert client.get(f"/api/docs/{attempt}").status_code == 404, attempt


def test_every_panel_points_at_a_page_that_exists(client):
    names = {p["name"] for p in client.get("/api/docs").json()["pages"]}
    for panel in client.get("/api/state").json()["panels"]:
        if panel["doc"]:
            assert panel["doc"] in names, panel["id"]


def test_the_dashboard_guide_documents_the_terminal(client):
    page = client.get("/api/docs/dashboard").json()["markdown"]
    # "terminal" was already in this page before the feature and guards
    # nothing. The reset behaviour is what the branch added.
    assert "reset" in page.lower()


def test_the_led_guide_distinguishes_the_two_causes_of_a_dark_mode(client):
    # "terminal" alone is already in this page (procMenu.c is "the terminal
    # UI"), so it does not pin the fix. Pin the actual corrected claim: a
    # dark MODE has two distinct causes, one deliberate, one a fault.
    page = client.get("/api/docs/pins-and-power").json()["markdown"]
    assert "one of two things" in page.lower()


# -- hook-up diagram data --------------------------------------------------


def test_the_cable_table_matches_the_reference_card(client):
    cable = client.get("/api/state").json()["cable"]
    assert [(c["pin"], c["signal"], c["colour_name"]) for c in cable] == [
        (1, "MISO", "black"),
        (2, "CS", "white"),
        (3, "MOSI", "grey"),
        (4, "CLK", "purple"),
        (5, "AUX", "blue"),
        (6, "VPU", "green"),
        (7, "ADC", "yellow"),
        (8, "+5V", "orange"),
        (9, "+3.3V", "red"),
        (10, "GND", "brown"),
    ]


def test_signals_carry_their_per_bus_role(client):
    cable = {c["signal"]: c for c in client.get("/api/state").json()["cable"]}
    assert cable["MOSI"]["roles"]["I2C"] == "SDA"
    assert cable["CLK"]["roles"]["I2C"] == "SCL"
    assert cable["MISO"]["roles"]["UART"] == "RX"
    assert cable["MOSI"]["roles"]["1-Wire"] == "OWD"


def test_panels_name_a_column_that_the_card_actually_has(client):
    state = client.get("/api/state").json()
    columns = state["refcard"]["columns"]
    rows = state["refcard"]["rows"]
    for panel in state["panels"]:
        if panel["refcard_column"]:
            assert panel["refcard_column"] in columns, panel["id"]
        for row in panel["refcard_rows"]:
            assert row in rows, (panel["id"], row)


def test_the_card_geometry_is_ordered_and_inside_the_image(client):
    card = client.get("/api/state").json()["refcard"]
    for name, (left, right) in card["columns"].items():
        assert 0 <= left < right <= card["width"], name
    for name, (top, bottom) in card["rows"].items():
        assert 0 <= top < bottom <= card["height"], name


def test_the_reference_images_are_actually_served(client):
    for path in ["/static/img/refcard.png", "/static/img/seeed-cable.png"]:
        response = client.get(path)
        assert response.status_code == 200
        assert response.content[:4] == b"\x89PNG"


def test_wiring_signals_all_exist_on_the_cable(client):
    state = client.get("/api/state").json()
    known = {c["signal"] for c in state["cable"]} | {"+5.0V"}
    for panel in state["panels"]:
        for wire in panel["wiring"]:
            assert wire["signal"] in known, (panel["id"], wire["signal"])
            assert wire["colour"].startswith("#"), (panel["id"], wire["signal"])


# -- the board photo and its pin map --------------------------------------


def test_the_board_geometry_names_every_signal(client):
    board = client.get("/api/state").json()["board"]
    cable = {c["signal"] for c in client.get("/api/state").json()["cable"]}
    assert set(board["pins"]) == cable
    assert set(board["side"]) == cable


def test_board_pins_sit_inside_the_photo(client):
    board = client.get("/api/state").json()["board"]
    for signal, (x, y) in board["pins"].items():
        assert 0 < x < board["width"], signal
        assert 0 < y < board["height"], signal


def test_the_header_is_two_columns_of_five(client):
    board = client.get("/api/state").json()["board"]
    columns = {}
    for signal, (x, y) in board["pins"].items():
        columns.setdefault(x, []).append(signal)
    assert len(columns) == 2, "the IDC header has exactly two columns"
    assert sorted(len(v) for v in columns.values()) == [5, 5]


def test_the_columns_match_the_silkscreen(client):
    """Left column is GND/+5V/VPU/CLK/CS top to bottom; right is the other five."""
    board = client.get("/api/state").json()["board"]
    left = sorted(
        (y, s) for s, (x, y) in board["pins"].items() if board["side"][s] == "left"
    )
    right = sorted(
        (y, s) for s, (x, y) in board["pins"].items() if board["side"][s] == "right"
    )
    assert [s for _, s in left] == ["GND", "+5V", "VPU", "CLK", "CS"]
    assert [s for _, s in right] == ["+3.3V", "ADC", "AUX", "MOSI", "MISO"]


def test_the_rows_pair_up_across_the_header(client):
    board = client.get("/api/state").json()["board"]
    rows = {}
    for signal, (x, y) in board["pins"].items():
        rows.setdefault(y, []).append(signal)
    assert len(rows) == 5
    assert all(len(v) == 2 for v in rows.values())


def test_the_board_photo_is_served(client):
    response = client.get("/static/img/board-v3.png")
    assert response.status_code == 200
    assert response.content[:4] == b"\x89PNG"


def test_the_v4_photo_is_served(client):
    response = client.get("/static/img/board-v4.jpg")
    assert response.status_code == 200
    assert response.content[:3] == b"\xff\xd8\xff"  # JPEG magic


def test_the_v4_header_is_a_two_by_six_with_three_aux_lines():
    from buspirate.web.wiring import BOARDS

    pins = BOARDS["v4"]["pins"]
    assert len(pins) == 12
    assert {"AUX", "AUX1", "AUX2"} <= set(pins)
    rows = {}
    for signal, (x, y) in pins.items():
        rows.setdefault(y, []).append(signal)
    assert len(rows) == 6
    assert all(len(v) == 2 for v in rows.values())


def test_every_board_pin_sits_inside_its_image():
    from buspirate.web.wiring import BOARDS

    for variant, board in BOARDS.items():
        for signal, (x, y) in {**board["pins"], **board["leds"]}.items():
            assert 0 < x < board["width"], (variant, signal)
            assert 0 < y < board["height"], (variant, signal)


def test_the_board_caveat_names_the_variant(client):
    caveat = client.get("/api/state").json()["board_caveat"]
    assert "v3.6" in caveat and "v4" in caveat


# -- the indicator LEDs ----------------------------------------------------


def test_the_board_geometry_places_all_four_leds(client):
    board = client.get("/api/state").json()["board"]
    assert set(board["leds"]) == {"PWR", "USB", "MODE", "VREG"}
    for name, (x, y) in board["leds"].items():
        assert 0 < x < board["width"], name
        assert 0 < y < board["height"], name


def test_the_leds_sit_in_one_row_left_to_right(client):
    leds = client.get("/api/state").json()["board"]["leds"]
    ys = {y for _, y in leds.values()}
    assert len(ys) == 1
    order = [n for n, _ in sorted(leds.items(), key=lambda kv: kv[1][0])]
    assert order == ["PWR", "USB", "MODE", "VREG"]


def test_every_led_is_dark_before_the_device_is_connected(client):
    leds = client.get("/api/state").json()["status"]["leds"]
    assert leds == {"PWR": False, "USB": False, "MODE": False, "VREG": False}


def test_connecting_lights_power_and_mode_but_not_vreg(client):
    # binBB() in the firmware sets BP_LEDMODE = 1 the moment binary mode is
    # entered, which is what connecting does — so MODE is lit from connect,
    # not from entering a protocol.
    connect(client)
    leds = client.get("/api/state").json()["status"]["leds"]
    assert leds["PWR"] is True
    assert leds["MODE"] is True
    assert leds["VREG"] is False


def test_the_usb_led_is_never_steadily_lit(client):
    # It is the FT232RL's RXLED# pin, which pulses on traffic and is dark at
    # idle. The dashboard flashes it client-side instead.
    connect(client)
    assert client.get("/api/state").json()["status"]["leds"]["USB"] is False


def test_the_mode_led_stays_lit_in_a_bus_mode(client):
    connect(client)
    status, body = run(client, "i2c", "scan", power=True, pullups=True, speed=2)
    assert status == 200, body
    assert client.get("/api/state").json()["status"]["leds"]["MODE"] is True


def test_the_mode_led_stays_lit_with_no_protocol_mode(client):
    # The pins panel drops back to bitbang, which is still binary mode.
    connect(client)
    run(client, "pins", "set_pins", pullups=False,
        aux=False, mosi=False, clk=False, miso=False, cs=False)
    state = client.get("/api/state").json()["status"]
    assert state["mode"] is None
    assert state["leds"]["MODE"] is True


def test_switching_the_supplies_on_lights_the_vreg_led(client):
    connect(client)
    status, body = run(client, "pins", "supplies", on=True)
    assert status == 200, body
    assert client.get("/api/state").json()["status"]["leds"]["VREG"] is True


def test_switching_the_supplies_off_again_darkens_the_vreg_led(client):
    connect(client)
    status, body = run(client, "pins", "supplies", on=True)
    assert status == 200, body
    assert client.get("/api/state").json()["status"]["leds"]["VREG"] is True
    status, body = run(client, "pins", "supplies", on=False)
    assert status == 200, body
    assert client.get("/api/state").json()["status"]["leds"]["VREG"] is False


def test_the_led_caveat_says_the_states_are_inferred(client):
    note = client.get("/api/state").json()["led_note"]
    assert "cannot" in note.lower() or "no command" in note.lower()


def test_reconnecting_does_not_carry_the_old_vreg_state_over(client):
    connect(client)
    run(client, "pins", "supplies", on=True)
    assert client.get("/api/state").json()["status"]["leds"]["VREG"] is True
    status, body = run(client, "connection", "disconnect")
    assert status == 200, body
    connect(client)
    assert client.get("/api/state").json()["status"]["leds"]["VREG"] is False


def test_a_protocol_panel_powering_the_target_lights_vreg(client):
    connect(client)
    status, body = run(client, "i2c", "scan", power=True, pullups=True, speed=2)
    assert status == 200, body
    assert client.get("/api/state").json()["status"]["leds"]["VREG"] is True


def test_a_protocol_panel_leaving_the_power_off_keeps_vreg_dark(client):
    connect(client)
    status, body = run(client, "i2c", "scan", power=False, pullups=True, speed=2)
    assert status == 200, body
    assert client.get("/api/state").json()["status"]["leds"]["VREG"] is False


def test_the_led_rules_cover_every_led_on_every_board():
    from buspirate.web.wiring import BOARDS, LED_RULES

    for variant, board in BOARDS.items():
        assert set(LED_RULES[variant]) == set(board["leds"]), variant
        for name, rule in LED_RULES[variant].items():
            assert rule["driver"] in {"hardware", "firmware"}, (variant, name)
            assert rule["means"], (variant, name)


def test_the_v3_usb_led_is_traffic_driven_and_the_v4_one_is_not():
    from buspirate.web.wiring import LED_RULES

    assert LED_RULES["v3"]["USB"]["inference"] == "flash_on_traffic"
    assert LED_RULES["v4"]["USB"]["inference"] == "always_dark"


def test_the_led_note_is_per_variant(client):
    connect(client)
    note = client.get("/api/state").json()["led_note"]
    assert "no command" in note.lower()
    # The two notes share a prefix, so assert the tail that diverges.
    if client.variant == "v4":
        assert "goes dark once" in note and "enumerated" in note
        assert "FT232RL" not in note
    else:
        assert "FT232RL" in note and "receive" in note
        assert "enumerated" not in note


def test_the_board_registry_is_keyed_by_variant():
    from buspirate.web.wiring import BOARDS

    assert list(BOARDS) == ["v3", "v4", "bitpirate"]
    board = BOARDS["v3"]
    assert board["label"] == "Bus Pirate v3.6"
    assert len(board["pins"]) == 10
    assert set(board["leds"]) == {"PWR", "USB", "MODE", "VREG"}
    assert "v3.6" in board["caveat"]


# -- the effective variant --------------------------------------------------


def test_the_state_reports_the_detected_variant(client):
    connect(client)
    body = client.get("/api/state").json()
    assert body["variant"] == client.variant
    assert body["variant_detected"] == client.variant
    assert body["variant_source"] == "detected"
    assert body["variants"] == ["v3", "v4", "bitpirate"]


def test_an_unconnected_dashboard_defaults_to_v3_and_says_so(client):
    body = client.get("/api/state").json()
    assert body["variant"] == "v3"
    assert body["variant_detected"] is None
    assert body["variant_source"] == "default"


def test_overriding_the_variant_changes_what_is_served(client):
    connect(client)
    status, body = run(client, "connection", "set_variant", variant="v3")
    assert status == 200, body
    state = client.get("/api/state").json()
    assert state["variant"] == "v3"
    assert state["variant_source"] == "override"
    assert state["variant_detected"] == client.variant


def test_auto_restores_detection(client):
    connect(client)
    run(client, "connection", "set_variant", variant="v3")
    status, body = run(client, "connection", "set_variant", variant="auto")
    assert status == 200, body
    state = client.get("/api/state").json()
    assert state["variant"] == client.variant
    assert state["variant_source"] == "detected"


def test_an_unknown_variant_is_refused_in_a_sentence(client):
    connect(client)
    status, body = run(client, "connection", "set_variant", variant="v9")
    assert status == 400
    assert "auto" in body["error"] and "v3" in body["error"]
    assert "Traceback" not in body["error"]


def test_disconnecting_clears_the_override(client):
    connect(client)
    run(client, "connection", "set_variant", variant="v3")
    run(client, "connection", "disconnect")
    connect(client)
    state = client.get("/api/state").json()
    assert state["variant_source"] == "detected"


def test_set_variant_works_while_a_stream_is_running(client):
    # It only sets a display field, never touches the port, so it must not be
    # refused the way an action that does need the port would be.
    connect(client)
    status, body = run(client, "i2c", "sniff", power=False, pullups=False, speed=2)
    assert status == 200, body
    status, body = run(client, "connection", "set_variant", variant="v4")
    assert status == 200, body
    state = client.get("/api/state").json()
    assert state["variant"] == "v4"
    assert state["variant_source"] == "override"


def test_the_board_served_follows_the_detected_variant(client):
    connect(client)
    body = client.get("/api/state").json()
    assert body["board"]["label"] == (
        "Bus Pirate v4.0" if client.variant == "v4" else "Bus Pirate v3.6"
    )


def test_the_aux_control_is_offered_on_v3_only(client):
    body = connect(client)
    panels = {p["id"]: p for p in body["panels"]}
    actions = {a["name"] for a in panels["i2c"]["actions"]}
    # On a v4 the command hangs the board: see test_device.py,
    # test_extended_aux_is_never_offered_on_a_v4.
    if client.variant == "v3":
        assert "extended_aux" in actions
    else:
        assert "extended_aux" not in actions


def test_driving_aux_high_on_a_v3_reports_what_it_did(client):
    if client.variant != "v3":
        pytest.skip("extended AUX works on a v3 only")
    connect(client)
    status, body = run(client, "i2c", "extended_aux", pin="aux", level="high")
    assert status == 200, body
    assert "AUX" in body["result"]["text"]


@pytest.mark.parametrize("pin", ["aux", "cs"])
@pytest.mark.parametrize("level", ["low", "high", "hiz"])
def test_driving_every_aux_pin_and_level_combination_on_a_v3(client, pin, level):
    if client.variant != "v3":
        pytest.skip("extended AUX works on a v3 only")
    connect(client)
    status, body = run(client, "i2c", "extended_aux", pin=pin, level=level)
    assert status == 200, body
    assert pin.upper() in body["result"]["text"]


@pytest.mark.parametrize("pin", ["aux", "cs"])
@pytest.mark.parametrize("level", ["low", "high"])
def test_reading_an_aux_pin_back_on_a_v3_reports_the_level_just_driven(client, pin, level):
    if client.variant != "v3":
        pytest.skip("extended AUX works on a v3 only")
    connect(client)
    status, body = run(client, "i2c", "extended_aux", pin=pin, level=level)
    assert status == 200, body
    status, body = run(client, "i2c", "extended_aux", pin=pin, level="read")
    assert status == 200, body
    assert level in body["result"]["text"].lower()


def test_the_v4_aux_pins_say_they_are_terminal_only():
    from buspirate.web.wiring import SIGNAL_NOTES

    for signal in ("AUX1", "AUX2"):
        assert "terminal" in SIGNAL_NOTES[signal].lower(), signal


def test_the_v4_guide_page_documents_the_header_and_the_leds(client):
    page = client.get("/api/docs/bus-pirate-v4").json()["markdown"]
    assert "AUX2" in page
    assert "2x6" in page or "2×6" in page
    assert "VREG" in page


def test_the_dashboard_guide_documents_the_window(client):
    page = client.get("/api/docs/dashboard").json()["markdown"]
    assert "window" in page.lower()
    assert "pywebview" in page.lower()


def test_the_quick_start_reflects_the_window(client):
    # This page said "Your browser opens on the dashboard" until the window
    # shipped and made that false — caught only by a manual sweep, not a
    # test. Pin the corrected claim so the same page can't drift back to
    # browser-only without a test noticing.
    page = client.get("/api/docs/user-guide").json()["markdown"]
    assert "window" in page.lower()


def test_the_macos_setup_launcher_description_reflects_the_window(client):
    # Same drift, same fix, different page: this one independently said
    # "starts the dashboard and opens your browser" until this round. Both
    # pages fell out of sync from the same change once, so both get pinned.
    page = client.get("/api/docs/macos-setup").json()["markdown"]
    assert "window" in page.lower()


def test_the_cli_reference_documents_the_app_command(client):
    # The CLI reference listed every subcommand except `app` from the day it
    # shipped — the same failure mode as the other two pages (a command this
    # branch added going undocumented), just caught as an omission instead
    # of a stale claim. Pin it so a future reshuffle of this page can't drop
    # `app` again without a test noticing.
    page = client.get("/api/docs/cli").json()["markdown"]
    assert "buspirate app" in page


def test_a_server_with_a_departed_feed_client_still_shuts_down():
    """A browser that closes during a quiet spell must not pin the server.

    The feed used to wait only for the next event to send, so a client that
    left while nothing was happening was never noticed: the handler sat in
    ``queue.get()`` for good, and uvicorn's graceful shutdown waited on it
    forever — `buspirate dashboard` ignored Ctrl-C and SIGTERM once a page
    had been open. TestClient cancels the handler when the socket closes and
    so cannot see this; it takes a real uvicorn.
    """
    import asyncio
    import socket
    import threading
    import time

    uvicorn = pytest.importorskip("uvicorn")
    websockets = pytest.importorskip("websockets")

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]

    server = uvicorn.Server(
        uvicorn.Config(create_app(use_fake=True), host="127.0.0.1", port=port,
                       log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    while not server.started:
        assert time.monotonic() < deadline, "server never started"
        time.sleep(0.02)

    async def visit():
        async with websockets.connect(f"ws://127.0.0.1:{port}/ws"):
            pass  # connect, then leave without a single event arriving

    asyncio.run(visit())
    server.should_exit = True
    thread.join(5)
    assert not thread.is_alive(), "shutdown hung on the departed feed client"


def test_the_terminal_warning_says_both_boards_reset(client):
    # A real v4 reset on opening the terminal: supplies off, off USB and back.
    body = connect(client)
    panels = {p["id"]: p for p in body["panels"]}
    action = next(a for a in panels["terminal"]["actions"] if a["name"] == "open_terminal")
    assert "not reset" not in action["confirm"]
    assert "v4" in action["confirm"] and "supplies go off" in action["confirm"]


def test_a_scan_where_every_address_answers_says_the_bus_is_stuck(client):
    """Found on a real v3 with VPU floating: the pull-ups had nothing to pull
    up to, SDA sat low, and a low SDA in the ACK slot reads as an ACK — so
    all 112 addresses "answered", and the scan listed 112 devices without a
    word of warning."""
    connect(client)
    client.app.state.session.bp.serial.i2c_devices = set(range(0x08, 0x78))
    status, body = run(client, "i2c", "scan", power=True, pullups=True, speed=2)
    assert status == 200, body
    result = body["result"]
    assert result["render"] == "text" and result["tone"] == "warn"
    assert "VPU" in result["text"]


def test_the_stuck_bus_check_is_shared_with_the_command_line():
    from buspirate.i2c import stuck_bus_warning

    everything = list(range(0x08, 0x78))
    assert "VPU" in stuck_bus_warning(everything, everything)
    assert stuck_bus_warning([0x50, 0x68], everything) == ""


# -- the printable wiring card ---------------------------------------------


def _card_rows(html, board):
    """[(left, right), ...] as the card lays out one board's header."""
    import re

    section = re.search(rf'<section[^>]*data-board="{board}".*?</section>', html, re.S)
    assert section, f"no {board} card"
    rows = re.findall(r'<div class="row">(.*?)</div>\s*<!-- /row -->', section.group(0), re.S)
    return [tuple(re.findall(r'data-signal="([^"]+)"', row)) for row in rows], section.group(0)


def _header_rows(board):
    """The same rows derived from the geometry the dashboard draws with."""
    from buspirate.web.wiring import BOARDS

    geometry = BOARDS[board]
    by_row = {}
    for signal, (x, y) in geometry["pins"].items():
        by_row.setdefault(y, {})[geometry["side"][signal]] = signal
    return [(r["left"], r["right"]) for _, r in sorted(by_row.items())]


@pytest.mark.parametrize("board", ["v3", "v4"])
def test_the_wiring_card_matches_the_header_the_dashboard_draws(board):
    from pathlib import Path

    html = (Path(__file__).parent.parent / "docs" / "wiring-card.html").read_text()
    rows, _ = _card_rows(html, board)
    assert rows == _header_rows(board)


@pytest.mark.parametrize("board", ["v3", "v4"])
def test_the_wiring_card_uses_the_dashboards_colours(board):
    import re
    from pathlib import Path

    from buspirate.web.wiring import SEEED_CABLE

    html = (Path(__file__).parent.parent / "docs" / "wiring-card.html").read_text()
    _, section = _card_rows(html, board)
    shown = dict(re.findall(r'data-signal="([^"]+)" data-colour="([^"]*)"', section))
    for signal, hexcode, name in SEEED_CABLE:
        assert shown[signal] == hexcode, signal


# -- the supplies switch -----------------------------------------------------
# Found on a real v3: asked to switch the supplies on, the user could not see
# how. The only control was a checkbox that did nothing until a separate
# "Set the pins" button was pressed.


def _state(client):
    return client.get("/api/state").json()["status"]


def test_the_supplies_switch_turns_them_on_and_off_in_one_step(client):
    connect(client)
    status, body = run(client, "pins", "supplies", on=True)
    assert status == 200, body
    assert _state(client)["supplies"] is True
    assert _state(client)["leds"]["VREG"] is True
    run(client, "pins", "supplies", on=False)
    assert _state(client)["supplies"] is False
    assert _state(client)["leds"]["VREG"] is False


def test_the_supplies_switch_is_offered_first_and_as_a_switch(client):
    body = connect(client)
    panels = {p["id"]: p for p in body["panels"]}
    first = panels["pins"]["actions"][0]
    assert first["name"] == "supplies"
    assert first["switch"] == "supplies"


def test_applying_pins_leaves_the_supplies_as_they_are(client):
    # The pin card no longer carries a supplies box, so applying it must not
    # quietly switch off supplies the switch just turned on.
    connect(client)
    run(client, "pins", "supplies", on=True)
    status, body = run(client, "pins", "set_pins", pullups=False, aux=True,
                       mosi=False, clk=False, miso=False, cs=False)
    assert status == 200, body
    assert _state(client)["supplies"] is True


def test_the_pin_card_says_nothing_happens_until_it_is_applied(client):
    body = connect(client)
    panels = {p["id"]: p for p in body["panels"]}
    card = next(a for a in panels["pins"]["actions"] if a["name"] == "set_pins")
    assert "power" not in [p["name"] for p in card["params"]]
    assert card["button"] == "Apply to the board"
    assert "nothing changes" in card["help"].lower()


# -- warnings for the two traps of 2026-09-29 ------------------------------


def test_pullups_without_a_rail_are_flagged_on_a_v4(client):
    connect(client)
    status, body = run(client, "i2c", "scan", power=True, pullups=True, speed=2)
    assert status == 200, body
    caption = body["result"].get("caption") or body["result"].get("text")
    if client.variant == "v3":
        assert "⚠" not in caption  # a v3 has no rail to set
        return
    assert "only work when VPU has a voltage" in caption

    run(client, "i2c", "pullup_voltage", selection=0)
    _, body = run(client, "i2c", "configure", power=True, pullups=True, speed=2)
    assert "the pull-up rail is Off" in body["result"]["text"]
    assert body["result"]["tone"] == "warn"

    run(client, "i2c", "pullup_voltage", selection=1)
    _, body = run(client, "i2c", "configure", power=True, pullups=True, speed=2)
    assert "⚠" not in body["result"]["text"]

    _, body = run(client, "i2c", "configure", power=True, pullups=False, speed=2)
    assert "⚠" not in body["result"]["text"]


def test_measuring_with_the_supplies_off_says_so(client):
    connect(client)
    status, body = run(client, "pins", "voltage", translate="none")
    assert status == 200, body
    assert "The supplies are off" in body["result"]["caption"]

    run(client, "pins", "supplies", on=True)
    _, body = run(client, "pins", "voltage", translate="none")
    assert "The supplies are off" not in body["result"]["caption"]


def test_the_state_carries_the_app_version_for_the_top_bar():
    import buspirate

    app = create_app(use_fake=True)
    with fastapi_testclient.TestClient(app) as c:
        assert c.get("/api/state").json()["version"] == buspirate.__version__


def test_the_version_lives_in_one_place():
    # pyproject.toml and bin/build-dmg.sh both read buspirate.__version__; a
    # second copy is how the code said 0.2.0 while the app was 0.5.5.
    import os
    import re

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "pyproject.toml")) as f:
        pyproject = f.read()
    assert 'dynamic = ["version"]' in pyproject
    assert re.search(r"^version\s*=\s*\"", pyproject, re.M) is None
    assert 'attr = "buspirate.__version__"' in pyproject
