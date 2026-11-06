"""The About page's facts, served in /api/state."""

import platform

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")

from buspirate import __version__  # noqa: E402
from buspirate.web.server import create_app  # noqa: E402


@pytest.fixture
def client():
    app = create_app(use_fake=True, fake_variant="v3")
    with fastapi_testclient.TestClient(app) as client:
        yield client


def test_state_says_which_app_and_python_this_is(client):
    about = client.get("/api/state").json()["about"]
    assert about["name"] == "busPirate"
    assert about["version"] == __version__
    assert about["python"] == platform.python_version()
    assert about["repo"] == "https://github.com/swissMack/busPirate"


def test_state_credits_the_boards_and_their_firmware(client):
    credits = client.get("/api/state").json()["about"]["credits"]
    links = {c["url"] for c in credits}
    assert "https://buspirate.com/" in links
    assert "https://github.com/geo-tp/ESP32-Bit-Pirate" in links
    assert all(c["name"] and c["by"] and c["what"] for c in credits)
