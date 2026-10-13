"""The dashboard against a simulated ESP32 Bit Pirate."""

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")

from buspirate.web.server import create_app  # noqa: E402


@pytest.fixture
def client():
    app = create_app(use_fake=True, fake_variant="bitpirate")
    with fastapi_testclient.TestClient(app) as client:
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


def panels(client):
    return {p["id"]: p for p in client.get("/api/state").json()["panels"]}


def actions(panel):
    return {a["name"]: a for a in panel["actions"]}


# -- connecting ------------------------------------------------------------


def test_the_demo_offers_the_bit_pirate_first(client):
    ports = client.get("/api/ports").json()["ports"]
    assert ports[0]["device"] == "simulated-bitpirate"
    assert ports[0]["note"] == "simulated ESP32 Bit Pirate, no hardware"


def test_connecting_identifies_it(client):
    body = connect(client)
    assert body["status"]["variant"] == "bitpirate"
    assert body["status"]["description"] == "ESP32 Bit Pirate, firmware 1.7"
    state = client.get("/api/state").json()
    assert state["variant"] == "bitpirate"
    assert state["board"]["cable"] is False


def test_identify_names_the_command_line(client):
    connect(client)
    status, body = run(client, "connection", "identify")
    assert status == 200, body
    assert ["Talks over", "text command line"] in body["result"]["pairs"]


# -- what is offered ---------------------------------------------------------


def test_panels_it_cannot_drive_are_not_offered(client):
    connect(client)
    offered = panels(client)
    assert {"connection", "terminal", "i2c", "spi", "uart"} <= set(offered)
    assert not {"pins", "onewire", "rawwire"} & set(offered)


def test_bus_pirate_only_actions_and_inputs_are_hidden(client):
    connect(client)
    offered = panels(client)
    i2c = actions(offered["i2c"])
    assert not {"sniff", "pullup_voltage", "extended_aux"} & set(i2c)
    assert "power" not in {p["name"] for p in i2c["scan"]["params"]}
    spi = actions(offered["spi"])
    assert not {"sniff", "flash_write", "flash_erase_sector", "flash_erase_chip"} & set(spi)
    assert {p["name"] for p in spi["jedec_id"]["params"]} == {"speed"}
    uart = actions(offered["uart"])
    assert not {"listen", "read", "bridge"} & set(uart)


def test_a_hidden_action_is_refused_if_asked_for_anyway(client):
    connect(client)
    status, body = run(client, "i2c", "sniff", pullups=True, speed=2)
    assert status == 400
    assert "Bus Pirate v3 and v4" in body["error"]


def test_the_wiring_is_the_devkit_pins(client):
    connect(client)
    i2c = panels(client)["i2c"]
    assert [(w["signal"], w["target"]) for w in i2c["wiring"][:2]] == [
        ("GPIO7", "SCL"), ("GPIO6", "SDA"),
    ]
    board = client.get("/api/state").json()["board"]
    for wire in i2c["wiring"]:
        assert wire["signal"] in board["pins"], wire


def test_opening_its_terminal_asks_for_no_confirmation(client):
    connect(client)
    terminal = actions(panels(client)["terminal"])
    assert terminal["open_terminal"]["confirm"] == ""


# -- doing things ------------------------------------------------------------


def test_scan_finds_the_simulated_devices(client):
    connect(client)
    status, body = run(client, "i2c", "scan", pullups=True, speed=2)
    assert status == 200, body
    assert [item["label"] for item in body["result"]["items"]] == ["0x50", "0x68"]


def test_a_register_read(client):
    connect(client)
    status, body = run(client, "i2c", "read_register", address="68", register="10", count=4)
    assert status == 200, body
    assert body["result"]["data"] == [0x10, 0x11, 0x12, 0x13]


def test_a_write_says_what_it_could_check(client):
    connect(client)
    status, body = run(client, "i2c", "write", address="50", data="00 01")
    assert status == 200, body
    assert "acknowledged its address" in body["result"]["text"]


def test_an_eeprom_read(client):
    connect(client)
    status, body = run(
        client, "i2c", "eeprom_read", address="50", offset=0, length=16, address_bytes=1
    )
    assert status == 200, body
    assert body["result"]["render"] == "hex"


def test_the_jedec_id(client):
    connect(client)
    status, body = run(client, "spi", "jedec_id", speed=3)
    assert status == 200, body
    assert ["Raw ID", "ef 40 18"] in body["result"]["pairs"]


def test_an_spi_clock_it_cannot_do_is_explained(client):
    connect(client)
    status, body = run(client, "spi", "jedec_id", speed=0)
    assert status == 400
    assert "whole MHz" in body["error"]


def test_uart_setup_and_send(client):
    connect(client)
    status, body = run(client, "uart", "configure", baud=10, framing=0, stop_bits=1)
    assert status == 200, body
    status, body = run(client, "uart", "send_text", message="AT", newline=True)
    assert status == 200, body
    fake = client.app.state.session.bp.serial
    assert fake.uart_tx == b"AT\r\n"


def test_the_uart_monitor_streams_and_stops(client):
    connect(client)
    fake = client.app.state.session.bp.serial
    fake.uart_rx = b"hello"
    status, body = run(client, "uart", "monitor")
    assert status == 200, body
    assert client.get("/api/state").json()["status"]["stream"]["kind"] == "UART monitor"
    stopped = client.post("/api/stream/stop").json()
    assert stopped["result"]["stopped"] is True
    assert stopped["result"]["note"] == ""
    assert client.get("/api/state").json()["status"]["connected"] is True


def test_the_terminal_opens_without_a_reset_and_closes_in_sync(client):
    connect(client)
    status, body = run(client, "terminal", "open_terminal")
    assert status == 200, body
    fake = client.app.state.session.bp.serial
    assert b"\x0f" not in fake.written
    status, body = run(client, "terminal", "send_keys", keys="m spi\r")
    assert status == 200, body
    stopped = client.post("/api/stream/stop").json()
    assert stopped["result"]["stopped"] is True
    # The session caught up with a mode changed behind its back.
    status, body = run(client, "i2c", "scan", pullups=True, speed=2)
    assert status == 200, body


def test_hiz_puts_it_in_hiz_and_stays_connected(client):
    connect(client)
    run(client, "i2c", "scan", pullups=True, speed=2)
    fake = client.app.state.session.bp.serial
    status, body = run(client, "connection", "hiz")
    assert status == 200, body
    assert fake.mode == "HIZ"
    state = client.get("/api/state").json()["status"]
    assert state["connected"] is True
    assert state["mode"] is None
    # The session must not think it is still in I2C: the next scan re-enters.
    status, body = run(client, "i2c", "scan", pullups=True, speed=2)
    assert status == 200, body
    assert fake.mode == "I2C"


def test_live_follows_its_mode(client):
    connect(client)
    assert client.get("/api/state").json()["status"]["live"] == []
    run(client, "i2c", "scan", pullups=True, speed=2)
    assert client.get("/api/state").json()["status"]["live"] == ["I2C mode", "pull-ups on"]
    run(client, "connection", "hiz")
    assert client.get("/api/state").json()["status"]["live"] == []


def test_disconnect_leaves_it_in_hiz(client):
    connect(client)
    run(client, "i2c", "scan", pullups=True, speed=2)
    fake = client.app.state.session.bp.serial
    status, _ = run(client, "connection", "disconnect")
    assert status == 200
    assert fake.mode == "HIZ"
