"""The window's server thread. No window is opened here — it cannot be."""

import socket
import sys

import pytest

pytest.importorskip("uvicorn")

from buspirate.exceptions import BusPirateError  # noqa: E402
from buspirate.web import window  # noqa: E402
from buspirate.web.session import STREAM_STOP_TIMEOUT_SECONDS  # noqa: E402


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


def test_a_hostname_is_refused_in_a_sentence():
    with pytest.raises(BusPirateError) as caught:
        window.start_server(host="localhost", port=_free_port(), use_fake=True)
    assert "127.0.0.1" in str(caught.value)


def test_the_loopback_wording_is_shared_with_the_server():
    from buspirate.web.server import loopback_refusal

    with pytest.raises(BusPirateError) as caught:
        window.start_server(host="0.0.0.0", port=_free_port(), use_fake=True)
    assert str(caught.value) == loopback_refusal("0.0.0.0")


def test_the_drain_is_bounded_so_the_lifespan_always_runs():
    server = window._build_server("127.0.0.1", _free_port(), True, "v3")
    assert server.config.timeout_graceful_shutdown == window.SHUTDOWN_MARGIN_SECONDS
    assert (
        window.SHUTDOWN_TIMEOUT_SECONDS
        >= server.config.timeout_graceful_shutdown + STREAM_STOP_TIMEOUT_SECONDS
    )


def test_a_window_that_will_not_open_is_a_sentence_and_stops_the_server(monkeypatch):
    from buspirate.exceptions import GuiUnavailableError

    class _BrokenWebview:
        @staticmethod
        def create_window(title, url, **kwargs):
            return None

        @staticmethod
        def start():
            raise RuntimeError("Cocoa refused to initialise")

    monkeypatch.setitem(sys.modules, "webview", _BrokenWebview)
    stopped = {}
    real_stop = window.stop_server

    def _watching_stop(server, thread):
        stopped["called"] = True
        return real_stop(server, thread)

    monkeypatch.setattr(window, "stop_server", _watching_stop)
    with pytest.raises(GuiUnavailableError) as caught:
        window.run_window(port=_free_port(), use_fake=True)
    message = str(caught.value)
    assert "could not open" in message
    assert "Cocoa refused to initialise" in message
    assert stopped["called"] is True


def test_a_broken_create_window_is_also_reported(monkeypatch):
    from buspirate.exceptions import GuiUnavailableError

    class _BrokenWebview:
        @staticmethod
        def create_window(title, url, **kwargs):
            raise RuntimeError("no display")

        @staticmethod
        def start():  # pragma: no cover - never reached
            raise AssertionError("start() must not run after create_window failed")

    monkeypatch.setitem(sys.modules, "webview", _BrokenWebview)
    with pytest.raises(GuiUnavailableError) as caught:
        window.run_window(port=_free_port(), use_fake=True)
    assert "no display" in str(caught.value)


def test_a_missing_gui_gets_its_own_exit_code(monkeypatch):
    from buspirate import cli

    class _Args:
        http_port = _free_port()
        demo = True
        variant = "v3"

    monkeypatch.setitem(sys.modules, "webview", None)
    assert cli.cmd_app(_Args()) == cli.EXIT_NO_GUI


def test_other_failures_keep_the_ordinary_error_exit(monkeypatch):
    from buspirate import cli

    with socket.socket() as taken:
        taken.bind(("127.0.0.1", 0))
        taken.listen(1)

        class _Args:
            http_port = taken.getsockname()[1]
            demo = True
            variant = "v3"

        class _FakeWebview:
            @staticmethod
            def create_window(title, url, **kwargs):  # pragma: no cover
                raise AssertionError("no window on a bind failure")

            @staticmethod
            def start():  # pragma: no cover
                raise AssertionError("no window on a bind failure")

        monkeypatch.setitem(sys.modules, "webview", _FakeWebview)
        assert cli.main(["app", "--port-number", str(_Args.http_port), "--demo"]) == 2
