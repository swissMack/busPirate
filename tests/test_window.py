"""The window's server thread. No window is opened here — it cannot be."""

import socket
import sys

import pytest

pytest.importorskip("uvicorn")

from buspirate.exceptions import BusPirateError  # noqa: E402
from buspirate.web import window  # noqa: E402


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_the_server_thread_comes_up_and_serves():
    port = _free_port()
    server, thread = window.start_server(port=port, use_fake=True)
    try:
        assert server.started
        assert thread.is_alive()
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def test_a_taken_port_is_refused_in_a_sentence():
    with socket.socket() as taken:
        taken.bind(("127.0.0.1", 0))
        taken.listen(1)
        port = taken.getsockname()[1]
        with pytest.raises(BusPirateError) as caught:
            window.start_server(port=port, use_fake=True)
    message = str(caught.value)
    assert str(port) in message
    assert "Traceback" not in message


def test_a_non_loopback_host_is_refused():
    with pytest.raises(BusPirateError):
        window.start_server(host="0.0.0.0", port=_free_port(), use_fake=True)


def test_the_shutdown_timeout_outlasts_the_session_teardown():
    from buspirate.web.session import STREAM_STOP_TIMEOUT_SECONDS

    assert window.SHUTDOWN_TIMEOUT_SECONDS > STREAM_STOP_TIMEOUT_SECONDS


def test_stopping_the_server_returns_no_complaint():
    port = _free_port()
    server, thread = window.start_server(port=port, use_fake=True)
    assert window.stop_server(server, thread) == ""
    assert not thread.is_alive()


def test_a_thread_that_will_not_die_is_reported_not_hidden():
    class _Stuck:
        def join(self, timeout=None):
            return None

        def is_alive(self):
            return True

    class _Server:
        should_exit = False

    note = window.stop_server(_Server(), _Stuck())
    assert note
    assert "did not shut down" in note


def test_a_missing_pywebview_says_how_to_install_it(monkeypatch):
    # Binding a module name to None in sys.modules makes `import name` raise
    # ImportError. That is surgical; patching builtins.__import__ would also
    # intercept uvicorn and everything else start_server imports.
    monkeypatch.setitem(sys.modules, "webview", None)
    with pytest.raises(BusPirateError) as caught:
        window.run_window(port=_free_port(), use_fake=True)
    assert "[app]" in str(caught.value)


def test_the_window_is_opened_and_the_server_stopped(monkeypatch):
    calls = {}

    class _FakeWebview:
        @staticmethod
        def create_window(title, url, **kwargs):
            calls["title"] = title
            calls["url"] = url

        @staticmethod
        def start():
            calls["started"] = True

    monkeypatch.setitem(sys.modules, "webview", _FakeWebview)
    port = _free_port()
    assert window.run_window(port=port, use_fake=True) == ""
    assert calls["started"] is True
    assert str(port) in calls["url"]
    assert calls["url"].startswith("http://127.0.0.1:")
