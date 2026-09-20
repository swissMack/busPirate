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
