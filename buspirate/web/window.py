"""The dashboard in its own window.

macOS requires the GUI on the main thread, so uvicorn runs on a worker and
``webview.start()`` owns the main one. Nothing here changes how the server
behaves: ``serve()`` and ``buspirate dashboard`` are untouched.

``webview`` is imported lazily, inside the function that needs it, because the
test suite runs without the ``app`` extra installed.
"""

from __future__ import annotations

import ipaddress
import threading
import time
from typing import Optional, Tuple

from ..exceptions import BusPirateError
from .server import create_app
from .session import STREAM_STOP_TIMEOUT_SECONDS

#: How long to wait for uvicorn to report itself listening before giving up.
SERVER_START_TIMEOUT_SECONDS = 10.0

#: Room beyond the session's own reader-thread join, so a legitimately slow
#: teardown is not cut short. Derived, never hardcoded: the two must move
#: together or a close will either hang or give up early.
SHUTDOWN_MARGIN_SECONDS = 5.0
SHUTDOWN_TIMEOUT_SECONDS = STREAM_STOP_TIMEOUT_SECONDS + SHUTDOWN_MARGIN_SECONDS


def _build_server(host: str, port: int, use_fake: Optional[bool], fake_variant: str):
    import uvicorn

    class _WindowServer(uvicorn.Server):
        """uvicorn on a worker thread: signal handlers only work on the main one."""

        def install_signal_handlers(self) -> None:
            pass

    config = uvicorn.Config(
        create_app(use_fake=use_fake, fake_variant=fake_variant),
        host=host,
        port=port,
        log_level="warning",
    )
    return _WindowServer(config)


def _run_server(server) -> None:
    """uvicorn calls sys.exit() on a bind failure. Inside a thread that only
    ends the thread, but the default excepthook still prints a traceback over
    the clean message the caller is about to raise. The readiness handshake
    notices the dead thread either way.
    """
    try:
        server.run()
    except SystemExit:
        pass


def start_server(
    host: str = "127.0.0.1",
    port: int = 8765,
    use_fake: Optional[bool] = None,
    fake_variant: str = "v3",
) -> Tuple[object, threading.Thread]:
    """Start the dashboard on a worker thread, and wait until it is listening.

    Opening a window before the server answers shows an error page, so this
    does not return until it is up — or says why it never came.
    """
    if not ipaddress.ip_address(host).is_loopback:
        raise BusPirateError(
            f"refusing to serve on {host}: the dashboard drives hardware and "
            "has no authentication, so it binds the loopback address only"
        )

    server = _build_server(host, port, use_fake, fake_variant)
    thread = threading.Thread(target=_run_server, args=(server,), daemon=True)
    thread.start()

    deadline = time.monotonic() + SERVER_START_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if server.started:
            return server, thread
        if not thread.is_alive():
            raise BusPirateError(
                f"the dashboard could not start on port {port}. Something else "
                "is probably using it — a 'buspirate dashboard' left running is "
                "the usual cause. Pass --port-number to use a different one."
            )
        time.sleep(0.02)

    raise BusPirateError(
        f"the dashboard did not start within {SERVER_START_TIMEOUT_SECONDS:g}s "
        f"on port {port}."
    )


def stop_server(server, thread: threading.Thread) -> str:
    """Stop the server and wait for its lifespan to release the hardware.

    Returns an empty string on a clean stop, or a sentence to print if the
    thread outlasted the timeout. Never blocks forever: the process is on its
    way out and the OS releases the port regardless.
    """
    server.should_exit = True
    thread.join(timeout=SHUTDOWN_TIMEOUT_SECONDS)
    if thread.is_alive():
        return (
            f"the dashboard did not shut down within "
            f"{SHUTDOWN_TIMEOUT_SECONDS:g}s. Exiting anyway — the port is "
            "released when this process ends."
        )
    return ""
