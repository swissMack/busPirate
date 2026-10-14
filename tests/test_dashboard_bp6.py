"""The dashboard against a simulated Bus Pirate 6."""

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")

from buspirate.web.server import create_app  # noqa: E402


@pytest.fixture
def client():
    app = create_app(use_fake=True, fake_variant="bp6")
    with fastapi_testclient.TestClient(app) as client:
        yield client


def run(client, panel, action, **params):
    response = client.post("/api/run", json={"panel": panel, "action": action, "params": params})
    return response.status_code, response.json()


def connect(client):
    status, body = run(client, "connection", "connect", port="")
    assert status == 200, body
    return body


def state(client):
    return client.get("/api/state").json()


def panels(client):
    return {p["id"]: p for p in state(client)["panels"]}


# -- connecting ------------------------------------------------------------


def test_the_demo_offers_the_bp6_first(client):
    ports = client.get("/api/ports").json()["ports"]
    assert ports[0]["device"] == "simulated-bp6"
    assert ports[0]["note"] == "simulated Bus Pirate 6, no hardware"


def test_connecting_shows_the_board_and_its_power(client):
    connect(client)
    data = state(client)
    assert data["status"]["description"] == "Bus Pirate 6, firmware 2026-10-12"
    assert data["status"]["power"]["on"] is False


def test_rawwire_and_bitbang_pins_are_hidden(client):
    connect(client)
    caps = state(client)["status"]["capabilities"]
    assert "rawwire" not in caps and "bitbang_pins" not in caps


def test_i2c_scan_finds_the_simulated_sensor(client):
    connect(client)
    status, body = run(client, "i2c", "scan", power=True, pullups=True, speed=2)
    assert status == 200, body
    assert "0x76" in str(body)
    assert state(client)["status"]["supplies"] is True


def test_traffic_carries_a_summary(client):
    connect(client)
    traffic = state(client)["traffic"]
    assert any(entry.get("summary") == "Status request" for entry in traffic)


def test_hiz_releases_the_bp6(client):
    connect(client)
    run(client, "i2c", "scan", power=True, pullups=True, speed=2)
    status, body = run(client, "connection", "hiz")
    assert status == 200, body
    data = state(client)["status"]
    assert data["live"] == []
    assert data["supplies"] is False and data["pullups"] is False


def test_the_terminal_opens_and_closing_it_rereads_the_board(client):
    connect(client)
    status, body = run(client, "terminal", "open_terminal")
    assert status == 200, body
    assert "answer n" in str(body)
    stopped = client.post("/api/stream/stop").json()
    assert stopped["result"]["stopped"] is True
    assert state(client)["status"]["connected"] is True


# -- power, pull-ups and the board -------------------------------------------


def test_the_power_panel_is_offered_and_the_bitbang_one_is_not(client):
    connect(client)
    ids = panels(client)
    assert "power6" in ids and "pins" not in ids
    status, body = run(client, "pins", "set_pins", pullups=False, aux=False, mosi=False,
                       clk=False, miso=False, cs=False)
    assert status != 200


def test_quick_voltage_buttons_switch_power_on(client):
    connect(client)
    status, body = run(client, "power6", "quick_3v3")
    assert status == 200, body
    power = state(client)["status"]["power"]
    assert power["on"] and power["set_mv"] == 3300 and power["mv"] == 3300


def test_high_voltage_needs_the_tick(client):
    connect(client)
    status, body = run(client, "power6", "set_supply", millivolts=5000, limit_ma=300, confirm_high=False)
    assert status == 200
    assert state(client)["status"]["power"]["on"] is False
    assert "tick" in str(body).lower()
    run(client, "power6", "set_supply", millivolts=5000, limit_ma=300, confirm_high=True)
    assert state(client)["status"]["power"]["mv"] == 5000


def test_no_limit_needs_the_tick_too(client):
    connect(client)
    run(client, "power6", "set_supply", millivolts=3300, limit_ma=0, confirm_high=False)
    assert state(client)["status"]["power"]["on"] is False


def test_a_tripped_supply_is_reported_with_a_re_enable_action(client):
    connect(client)
    run(client, "power6", "set_supply", millivolts=3300, limit_ma=5, confirm_high=False)
    power = state(client)["status"]["power"]
    assert power["tripped"] and not power["on"]
    status, body = run(client, "power6", "readings")
    assert "Current limit tripped" in str(body)
    actions = {a["name"] for a in panels(client)["power6"]["actions"]}
    assert "reenable" in actions


def test_the_pullups_switch_shows_its_state(client):
    connect(client)
    run(client, "power6", "pullups", on=True)
    assert state(client)["status"]["pullups"] is True


def test_the_board_is_the_bp6_header(client):
    connect(client)
    data = state(client)
    assert data["variant"] == "bp6"
    board = data["board"]
    assert board["image"] == "/static/img/board-bp6.svg"
    assert list(board["pins"]) == ["VOUT"] + [f"IO{i}" for i in range(8)] + ["GND"]
    i2c = {w["target"]: w["signal"] for w in panels(client)["i2c"]["wiring"]}
    assert i2c["SDA"] == "IO0" and i2c["SCL"] == "IO1"


def test_the_terminal_needs_no_reset_warning_on_the_bp6(client):
    connect(client)
    actions = {a["name"]: a for a in panels(client)["terminal"]["actions"]}
    assert actions["open_terminal"]["confirm"] == ""


def test_the_power_poll_stays_out_of_the_traffic_log(client):
    import time

    connect(client)
    before = len(state(client)["traffic"])
    time.sleep(0.9)  # past the refresh interval, so the next poll reads the board
    after = state(client)
    assert client.app.state.session._power_read_at > 0  # the poll did read the board
    assert len(after["traffic"]) == before
