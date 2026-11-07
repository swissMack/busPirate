"""A Wi-Fi password never reaches the Traffic log, not even as the board's echo."""

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")

from buspirate.web.server import create_app  # noqa: E402

PASSWORD = "hunter2"


@pytest.fixture
def client():
    with fastapi_testclient.TestClient(create_app(use_fake=True)) as c:
        yield c


def _run(client, panel, action, **params):
    response = client.post("/api/run", json={"panel": panel, "action": action, "params": params})
    assert response.status_code == 200, response.text
    return response


def _traffic(client):
    return client.get("/api/state").json()["traffic"]


def test_the_password_is_in_no_traffic_entry(client):
    _run(client, "connection", "connect", port="simulated-bitpirate")
    _run(client, "wifi", "connect", network="new", ssid="HomeNet", password=PASSWORD)
    for entry in _traffic(client):
        assert "hunt" not in entry.get("text", ""), entry  # nor the echo's prefixes
        assert PASSWORD.encode().hex(" ") not in entry["hex"], entry
        assert "68 75 6e 74" not in entry["hex"], entry  # "hunt"


def test_the_command_is_logged_with_the_password_masked(client):
    _run(client, "connection", "connect", port="simulated-bitpirate")
    _run(client, "wifi", "connect", network="new", ssid="HomeNet", password=PASSWORD)
    texts = [e.get("text", "") for e in _traffic(client) if e["direction"] == "tx"]
    assert any("connect HomeNet ****" in t for t in texts), texts


def test_traffic_is_logged_again_after_the_password_command(client):
    _run(client, "connection", "connect", port="simulated-bitpirate")
    _run(client, "wifi", "connect", network="new", ssid="HomeNet", password=PASSWORD)
    before = len(_traffic(client))
    _run(client, "wifi", "status")
    after = _traffic(client)[before:]
    assert any("status" in e.get("text", "") for e in after if e["direction"] == "tx"), after
    assert any("Wi-Fi Status" in e.get("text", "") for e in after if e["direction"] == "rx"), after
