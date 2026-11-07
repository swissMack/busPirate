"""Wi-Fi without typing: the board keeps the network it last joined."""

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")

from buspirate.web.server import create_app  # noqa: E402


@pytest.fixture
def client():
    with fastapi_testclient.TestClient(create_app(use_fake=True)) as c:
        yield c


def _run(client, panel, action, **params):
    return client.post("/api/run", json={"panel": panel, "action": action, "params": params})


def _connect_board(client):
    assert _run(client, "connection", "connect", port="simulated-bitpirate").status_code == 200


def test_the_saved_network_is_joined_without_typing(client):
    _connect_board(client)
    assert _run(client, "wifi", "connect", network="new", ssid="HomeNet", password="hunter2").status_code == 200
    assert _run(client, "wifi", "disconnect").status_code == 200

    response = _run(client, "wifi", "connect", network="saved")

    assert response.status_code == 200, response.text
    assert "Connected successfully" in response.text
    assert client.get("/api/state").json()["status"]["web_cli"]["on_wifi"] is True


def test_with_nothing_saved_it_says_so_and_joins_nothing(client):
    _connect_board(client)

    response = _run(client, "wifi", "connect", network="saved")

    assert response.status_code == 400, response.text
    assert "No network is saved on the board yet" in response.json()["error"]
    fake = client.app.state.session.bp.serial
    assert fake.wifi_connected is None


def test_the_saved_network_needs_no_name_or_password(client):
    _connect_board(client)
    _run(client, "wifi", "connect", network="new", ssid="HomeNet", password="hunter2")
    _run(client, "wifi", "disconnect")

    response = _run(client, "wifi", "connect", network="saved", ssid="", password="")

    assert response.status_code == 200, response.text
    assert "Connected successfully" in response.text


def test_connect_offers_saved_or_new_and_shows_the_boxes_only_for_new(client):
    _connect_board(client)
    panels = {p["id"]: p for p in client.get("/api/state").json()["panels"]}
    actions = {a["name"]: a for a in panels["wifi"]["actions"]}
    assert "connect_saved" not in actions  # one Connect, with a choice
    fields = {p["name"]: p for p in actions["connect"]["params"]}
    assert [c["value"] for c in fields["network"]["choices"]] == ["saved", "new"]
    assert fields["network"]["default"] == "saved"
    assert fields["ssid"]["shown_when"] == {"network": "new"}
    assert fields["password"]["shown_when"] == {"network": "new"}


def test_a_password_field_is_marked_secret_for_the_page(client):
    _connect_board(client)
    panels = {p["id"]: p for p in client.get("/api/state").json()["panels"]}
    connect = next(a for a in panels["wifi"]["actions"] if a["name"] == "connect")
    fields = {p["name"]: p for p in connect["params"]}
    assert fields["password"]["secret"] is True
    assert not fields["ssid"].get("secret")
