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
