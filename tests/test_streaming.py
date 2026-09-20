"""Sniffers and other streams: they take the port until stopped."""

import time

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")

from buspirate.web.decoders import make_decoder  # noqa: E402
from buspirate.web.server import create_app  # noqa: E402


@pytest.fixture
def client():
    app = create_app(use_fake=True, fake_variant="v3")
    with fastapi_testclient.TestClient(app) as client:
        client.post(
            "/api/run",
            json={"panel": "connection", "action": "connect", "params": {"port": ""}},
        )
        try:
            yield client
        finally:
            client.post("/api/stream/stop")


def run(client, panel, action, **params):
    response = client.post(
        "/api/run", json={"panel": panel, "action": action, "params": params}
    )
    return response.status_code, response.json()


def status(client):
    return client.get("/api/state").json()["status"]


def wait_for_events(client, at_least=1, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        current = status(client)["stream"]
        if current and current["events"] >= at_least:
            return current
        time.sleep(0.02)
    return status(client)["stream"]


# -- decoders --------------------------------------------------------------


def test_i2c_decoder_reads_a_whole_transaction():
    decoder = make_decoder("i2c-sniffer")
    events = decoder.feed(b"[\\\xa0+\\\x2a+]")
    assert [e["text"] for e in events] == ["START", "a0", "+", "2a", "+", "STOP"]


def test_i2c_decoder_survives_a_read_that_splits_an_escape():
    decoder = make_decoder("i2c-sniffer")
    first = decoder.feed(b"[\\")
    second = decoder.feed(b"\xa0+")
    assert [e["text"] for e in first] == ["START"]
    assert [e["text"] for e in second] == ["a0", "+"]


def test_spi_decoder_pairs_mosi_with_miso():
    decoder = make_decoder("spi-sniffer")
    events = decoder.feed(b"[\\\x9f\xff\\\x00\xef]")
    assert [e["text"] for e in events] == ["CS↓", "9f/ff", "00/ef", "CS↑"]
    assert events[1]["mosi"] == 0x9F and events[1]["miso"] == 0xFF


def test_voltage_decoder_holds_a_split_sample():
    decoder = make_decoder("voltage")
    assert decoder.feed(b"\x02") == []
    assert decoder.feed(b"\x00")[0]["volts"] == pytest.approx(3.3, abs=0.01)


def test_an_unknown_decoder_is_refused():
    with pytest.raises(ValueError, match="no decoder"):
        make_decoder("nope")


# -- the streaming lifecycle ----------------------------------------------


def test_starting_a_sniffer_takes_the_port(client):
    code, body = run(client, "i2c", "sniff", power=False, pullups=False, speed=2)
    assert code == 200, body
    assert body["result"]["render"] == "stream"
    assert body["result"]["decoder"] == "i2c-sniffer"
    assert "[ start" in body["result"]["legend"]
    assert status(client)["stream"]["kind"] == "I2C sniffer"


def test_a_running_sniffer_produces_decoded_events(client):
    run(client, "i2c", "sniff", power=False, pullups=False, speed=2)
    current = wait_for_events(client, at_least=5)
    assert current is not None and current["events"] >= 5


def test_other_actions_are_refused_while_a_sniffer_runs(client):
    run(client, "i2c", "sniff", power=False, pullups=False, speed=2)
    code, body = run(client, "i2c", "scan", power=True, pullups=True, speed=2)
    assert code == 400
    assert "has the port" in body["error"]


def test_stopping_returns_the_device_to_a_known_state(client):
    run(client, "i2c", "sniff", power=False, pullups=False, speed=2)
    wait_for_events(client, at_least=1)
    body = client.post("/api/stream/stop").json()
    assert body["result"]["stopped"] is True
    assert body["status"]["stream"] is None
    # Resynchronised to bitbang, so the next action re-enters cleanly.
    assert body["status"]["mode"] is None
    code, result = run(client, "i2c", "scan", power=True, pullups=True, speed=2)
    assert code == 200, result
    assert [item["label"] for item in result["result"]["items"]] == ["0x50", "0x68"]


def test_stopping_when_nothing_runs_says_so(client):
    body = client.post("/api/stream/stop").json()
    assert body["result"] == {"stopped": False, "reason": "nothing is streaming"}


def test_the_spi_sniffer_streams_too(client):
    code, body = run(
        client, "spi", "sniff", cs_low_only=True, power=False, speed=3, spi_mode=0
    )
    assert code == 200, body
    assert body["result"]["kind"] == "SPI sniffer"
    assert "10 MHz" in body["result"]["warning"]
    assert wait_for_events(client, at_least=3)["events"] >= 3


def test_the_voltage_monitor_streams(client):
    code, body = run(client, "pins", "voltage_stream")
    assert code == 200, body
    assert body["result"]["decoder"] == "voltage"
    assert wait_for_events(client, at_least=2)["events"] >= 2


def test_the_uart_bridge_warns_that_it_cannot_be_stopped(client):
    run(client, "uart", "configure", baud=10, framing=0, stop_bits=1, power=False)
    code, body = run(client, "uart", "bridge")
    assert code == 200, body
    assert "unplug" in body["result"]["warning"].lower()


def test_disconnecting_stops_a_running_sniffer(client):
    run(client, "i2c", "sniff", power=False, pullups=False, speed=2)
    wait_for_events(client, at_least=1)
    run(client, "connection", "disconnect")
    assert status(client)["connected"] is False


def test_the_bridge_action_asks_before_it_runs(client):
    panels = {p["id"]: p for p in client.get("/api/state").json()["panels"]}
    bridge = next(a for a in panels["uart"]["actions"] if a["name"] == "bridge")
    assert bridge["confirm"]
    assert bridge["stream"] is True
