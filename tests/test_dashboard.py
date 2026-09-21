"""The dashboard API, driven against a simulated Bus Pirate."""

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")

from buspirate.web.params import ParamError, coerce  # noqa: E402
from buspirate.web.registry import Param, load_panels  # noqa: E402
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


def test_state_lists_panels_before_connecting(client):
    body = client.get("/api/state").json()
    assert body["status"]["connected"] is False
    assert [p["id"] for p in body["panels"]][0] == "connection"


def test_ports_endpoint_offers_the_simulated_device(client):
    ports = client.get("/api/ports").json()["ports"]
    assert ports[0]["device"] == "fake"
    assert ports[0]["likely"]


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
    assert "Sent 4 byte(s)" in body["result"]["text"]


def test_onewire_search_names_the_family(client):
    connect(client)
    status, body = run(client, "onewire", "search", power=True, pullups=True)
    assert status == 200, body
    assert body["result"]["rows"][0][2] == "DS18B20 thermometer"


def test_pins_panel_reports_the_state_it_set(client):
    connect(client)
    status, body = run(
        client, "pins", "set_pins", power=True, pullups=False, aux=False,
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
    run(client, "pins", "set_pins", power=False, pullups=False, aux=False,
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


# -- hook-up diagram data --------------------------------------------------


def test_the_cable_table_matches_the_reference_card(client):
    cable = client.get("/api/state").json()["cable"]
    assert [(c["pin"], c["signal"], c["colour_name"]) for c in cable] == [
        (1, "MISO", "black"),
        (2, "CS", "white"),
        (3, "MOSI", "grey"),
        (4, "CLK", "pink"),
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
    run(client, "pins", "set_pins", power=False, pullups=False,
        aux=False, mosi=False, clk=False, miso=False, cs=False)
    state = client.get("/api/state").json()["status"]
    assert state["mode"] is None
    assert state["leds"]["MODE"] is True


def test_switching_the_supplies_on_lights_the_vreg_led(client):
    connect(client)
    status, body = run(
        client, "pins", "set_pins", power=True, pullups=False,
        aux=False, mosi=False, clk=False, miso=False, cs=False,
    )
    assert status == 200, body
    assert client.get("/api/state").json()["status"]["leds"]["VREG"] is True


def test_switching_the_supplies_off_again_darkens_the_vreg_led(client):
    connect(client)
    status, body = run(client, "pins", "set_pins", power=True, pullups=False,
                       aux=False, mosi=False, clk=False, miso=False, cs=False)
    assert status == 200, body
    assert client.get("/api/state").json()["status"]["leds"]["VREG"] is True
    status, body = run(client, "pins", "set_pins", power=False, pullups=False,
                       aux=False, mosi=False, clk=False, miso=False, cs=False)
    assert status == 200, body
    assert client.get("/api/state").json()["status"]["leds"]["VREG"] is False


def test_the_led_caveat_says_the_states_are_inferred(client):
    note = client.get("/api/state").json()["led_note"]
    assert "cannot" in note.lower() or "no command" in note.lower()


def test_reconnecting_does_not_carry_the_old_vreg_state_over(client):
    connect(client)
    run(client, "pins", "set_pins", power=True, pullups=False,
        aux=False, mosi=False, clk=False, miso=False, cs=False)
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

    assert set(BOARDS) == {"v3", "v4"}
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
    assert body["variants"] == ["v3", "v4"]


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


def test_the_aux_control_is_offered_on_v4_only(client):
    body = connect(client)
    panels = {p["id"]: p for p in body["panels"]}
    actions = {a["name"] for a in panels["i2c"]["actions"]}
    if client.variant == "v4":
        assert "extended_aux" in actions
    else:
        assert "extended_aux" not in actions


def test_driving_aux_high_on_a_v4_reports_what_it_did(client):
    if client.variant != "v4":
        pytest.skip("extended AUX is a v4 command")
    connect(client)
    status, body = run(client, "i2c", "extended_aux", pin="aux", level="high")
    assert status == 200, body
    assert "AUX" in body["result"]["text"]


@pytest.mark.parametrize("pin", ["aux", "cs"])
@pytest.mark.parametrize("level", ["low", "high", "hiz"])
def test_driving_every_aux_pin_and_level_combination_on_a_v4(client, pin, level):
    if client.variant != "v4":
        pytest.skip("extended AUX is a v4 command")
    connect(client)
    status, body = run(client, "i2c", "extended_aux", pin=pin, level=level)
    assert status == 200, body
    assert pin.upper() in body["result"]["text"]


@pytest.mark.parametrize("pin", ["aux", "cs"])
@pytest.mark.parametrize("level", ["low", "high"])
def test_reading_an_aux_pin_back_on_a_v4_reports_the_level_just_driven(client, pin, level):
    if client.variant != "v4":
        pytest.skip("extended AUX is a v4 command")
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
