# Desktop App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the dashboard in its own window instead of a browser tab, closing cleanly so the board is never left held.

**Architecture:** One process. uvicorn runs on a daemon thread; `webview.start()` owns the main thread, because macOS requires the GUI there. Closing the window returns from `webview.start()`, which stops the server and lets its existing lifespan do the hardware teardown.

**Tech Stack:** Python 3, FastAPI, uvicorn, pywebview 6.x (new, macOS pulls six `pyobjc-*` packages), pytest.

**Spec:** `docs/superpowers/specs/2026-09-22-desktop-app-design.md`

## Global Constraints

- **`serve()` and `buspirate dashboard` are untouched.** This adds a way to run the dashboard; it never replaces one. The jsdom suite drives the HTTP server headlessly, so the browser path is load-bearing for the tests.
- **pywebview goes in a new `app` extra only** — never in `web`, never in `dev`. `pip install -e .[web]` must stay as light as it is today.
- **Never import `webview` at module scope** in anything the test suite imports. The suite runs without the `app` extra installed, and a top-level import would break collection.
- **The GUI must be on the main thread.** uvicorn goes on a worker, and that worker must not try to install signal handlers.
- Loopback only. `serve()`'s existing guard is where that rule lives; do not add a second copy with different wording.
- Errors the user should act on are raised as `BusPirateError` — `cli.py:174` already catches it and prints `error: <message>` without a traceback.
- Commit only the files each task names.

## What already exists — do not rebuild it

| Piece | Where |
|---|---|
| The app factory | `server.py` `create_app(use_fake=..., fake_variant=...)` |
| **Hardware teardown on shutdown** | `server.py` lifespan — stops the stream, disconnects, suppresses the refusal a wedged reader raises |
| The loopback guard | `server.py:231` inside `serve()` |
| The reader-thread join timeout | `session.py:40` `STREAM_STOP_TIMEOUT_SECONDS = 15.0` |
| CLI dispatch + error printing | `cli.py:160` `main()`, handlers dict at `:170`, `BusPirateError` catch at `:174` |
| `cmd_dashboard` — the shape to mirror | `cli.py:141` |
| The venv bootstrap and first-run install | `bin/dashboard.command` |

---

### Task 1: SPIKE — can a WKWebView window actually run this dashboard?

**This is a spike, not a feature.** It has no tests and its output is an answer. Everything you write here is deleted at the end of the task. Do not commit any of it.

The entire design assumes a pywebview window can reach `127.0.0.1:8765` **and hold a websocket**. The live traffic log and the terminal console both depend on that websocket. If WKWebView cannot do it, this plan is wrong and Tasks 2-5 are wasted work.

**Files:** none committed.

- [ ] **Step 1: Install pywebview into the existing venv**

```bash
.venv/bin/pip install 'pywebview>=5'
```
Record the resolved version and anything unexpected in the install output. On macOS it should pull six `pyobjc-*` packages.

- [ ] **Step 2: Start the dashboard by hand**

```bash
pkill -f "buspirate dashboard"; sleep 1
nohup .venv/bin/python -m buspirate dashboard --demo --no-browser >/tmp/spike.log 2>&1 &
sleep 5
```

- [ ] **Step 3: Open a window at it**

Write a throwaway script in the scratch directory (NOT in the repo):

```python
import webview
webview.create_window("Bus Pirate spike", "http://127.0.0.1:8765/",
                      width=1200, height=820)
webview.start()
```

Run it with `.venv/bin/python`. You need a GUI session for this; if the environment cannot open a window at all, stop and report that — it is a blocker on the whole plan, not a step to work around.

- [ ] **Step 4: Answer the three questions**

With the window open, determine and record:

1. **Does the page load?** Does the dashboard render, or an error page?
2. **Does the websocket connect?** This is the critical one. Click **Connect** (the demo simulates a v3), then run an action that produces traffic — the **I2C: Scan the bus** recipe is one click. The Traffic pane at the bottom fills from the websocket. If frames appear there, the websocket works. If the pane stays empty while the action succeeds, it does not.
3. **Does a stream work?** Start the I2C sniffer, confirm decoded events appear in the live pane, then stop it. This exercises the websocket under sustained load rather than one message.

Check `/tmp/spike.log` for server-side errors, and look for a WKWebView console error about the websocket if it fails.

- [ ] **Step 5: Clean up and report**

```bash
pkill -f "buspirate dashboard"
```
Delete the throwaway script. Leave pywebview installed — Task 2 needs it.

**Report a clear verdict: GO or NO-GO**, with the evidence for each of the three questions. If NO-GO, say specifically which part failed and what the error was. Do not start Task 2. Do not "work around" a failure — a websocket that does not work inside WKWebView means the controller needs to re-plan, and that decision is not yours to make silently.

- [ ] **Step 6: Commit**

Nothing to commit. Confirm `git status --porcelain` is clean.

---

### Task 2: The window module — start the server off the main thread

**Files:**
- Create: `buspirate/web/window.py`
- Create: `tests/test_window.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: `create_app` from `server.py`
- Produces: `SERVER_START_TIMEOUT_SECONDS`; `start_server(host, port, use_fake, fake_variant) -> tuple[server, thread]`, raising `BusPirateError` when the server does not come up.

- [ ] **Step 1: Add the extra**

In `pyproject.toml`, beside the existing extras:

```toml
app = ["pywebview>=5"]
```

Leave `web` and `dev` exactly as they are.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_window.py`:

```python
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
```

- [ ] **Step 3: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_window.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'buspirate.web.window'`

- [ ] **Step 4: Implement**

Create `buspirate/web/window.py`:

```python
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

#: How long to wait for uvicorn to report itself listening before giving up.
SERVER_START_TIMEOUT_SECONDS = 10.0


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
    thread = threading.Thread(target=server.run, daemon=True)
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
```

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS, with three new tests. Record the count.

- [ ] **Step 6: Commit**

```bash
git add buspirate/web/window.py tests/test_window.py pyproject.toml
git commit -m "feat: start the dashboard server on a worker thread for a window"
```

---

### Task 3: Shutdown, with a timeout derived from the session's own

**Files:**
- Modify: `buspirate/web/window.py`
- Modify: `tests/test_window.py`

**Interfaces:**
- Consumes: `start_server` from Task 2, `STREAM_STOP_TIMEOUT_SECONDS` from `session.py`
- Produces: `SHUTDOWN_TIMEOUT_SECONDS`; `stop_server(server, thread) -> str` returning a note, empty when it stopped cleanly.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_window.py`:

```python
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
```

The first test is the one that matters: it pins the derivation so the two timeouts cannot drift apart.

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_window.py -q`
Expected: FAIL — `module 'buspirate.web.window' has no attribute 'SHUTDOWN_TIMEOUT_SECONDS'`

- [ ] **Step 3: Implement**

In `buspirate/web/window.py`, beside `SERVER_START_TIMEOUT_SECONDS`:

```python
from .session import STREAM_STOP_TIMEOUT_SECONDS

#: Room beyond the session's own reader-thread join, so a legitimately slow
#: teardown is not cut short. Derived, never hardcoded: the two must move
#: together or a close will either hang or give up early.
SHUTDOWN_MARGIN_SECONDS = 5.0
SHUTDOWN_TIMEOUT_SECONDS = STREAM_STOP_TIMEOUT_SECONDS + SHUTDOWN_MARGIN_SECONDS
```

And the function:

```python
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
```

- [ ] **Step 4: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add buspirate/web/window.py tests/test_window.py
git commit -m "feat: stop the window's server without hanging on a wedged reader"
```

---

### Task 4: The `buspirate app` command, and the launcher

**Files:**
- Modify: `buspirate/web/window.py`
- Modify: `buspirate/cli.py`
- Modify: `bin/dashboard.command`
- Modify: `tests/test_window.py`

**Interfaces:**
- Consumes: `start_server`, `stop_server`
- Produces: `window.run_window(...)`; the `app` subcommand.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_window.py`:

```python
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
```

The second test proves the wiring — window opened at the right URL, server stopped afterwards — without ever opening a window. That is the limit of what is testable here, and the spec says so.

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_window.py -q`
Expected: FAIL — `run_window` does not exist.

- [ ] **Step 3: Implement `run_window`**

In `buspirate/web/window.py`:

```python
def run_window(
    host: str = "127.0.0.1",
    port: int = 8765,
    use_fake: Optional[bool] = None,
    fake_variant: str = "v3",
) -> str:
    """Open the dashboard in its own window and block until it is closed.

    Returns a note to print, empty when the shutdown was clean.
    """
    try:
        import webview
    except ImportError as exc:
        raise BusPirateError(
            "the window needs pywebview, which is not installed. Install it "
            "with:  pip install -e '.[app]'"
        ) from exc

    server, thread = start_server(host, port, use_fake, fake_variant)
    webview.create_window(
        "Bus Pirate", f"http://{host}:{port}/", width=1200, height=820
    )
    webview.start()
    return stop_server(server, thread)
```

- [ ] **Step 4: Add the subcommand**

In `buspirate/cli.py`, add a parser beside the `dashboard` one. Read how `dash` is built and mirror it, minus `--host` and `--no-browser`:

```python
    appcmd = sub.add_parser("app", help="open the dashboard in its own window")
    appcmd.add_argument("--port-number", type=int, default=8765, dest="http_port")
    appcmd.add_argument(
        "--demo",
        action="store_true",
        help="run against a simulated Bus Pirate, with no hardware",
    )
    appcmd.add_argument(
        "--variant",
        default="v3",
        choices=["v3", "v4"],
        help="which device the demo simulates (default: v3)",
    )
```

The handler, mirroring `cmd_dashboard`:

```python
def cmd_app(args) -> int:
    from .web.window import run_window

    note = run_window(
        port=args.http_port,
        use_fake=args.demo or None,
        fake_variant=args.variant,
    )
    if note:
        print(note)
    return 0
```

Register it in the handlers dict beside `"dashboard": cmd_dashboard`. `main()` already catches `BusPirateError` and prints it without a traceback, so the missing-pywebview message reaches the user properly with no extra work.

- [ ] **Step 5: Repoint the launcher**

In `bin/dashboard.command`, change the install line's extra from `[web]` to `[web,app]`, and replace the final `exec` with a window attempt that falls back:

```bash
echo
echo "Opening the Bus Pirate window. Close it to stop."
if ! "$VENV/bin/python" -m buspirate app "$@"; then
  echo
  echo "The window could not start — falling back to the browser dashboard."
  exec "$VENV/bin/python" -m buspirate dashboard "$@"
fi
```

Note the `exec` moves to the fallback: the window attempt must be able to return so the fallback can run. Check the `$@` forwarding still makes sense for both — `app` rejects `--no-browser` and `--host`, so a user passing those to the `.command` would now fail. Decide whether to strip them or document it, and say which you chose in your report.

- [ ] **Step 6: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS

Also check the CLI wires up: `.venv/bin/python -m buspirate app --help` must print the new options and exit 0.

- [ ] **Step 7: Commit**

```bash
git add buspirate/web/window.py buspirate/cli.py bin/dashboard.command tests/test_window.py
git commit -m "feat: add 'buspirate app' and point the launcher at the window"
```

---

### Task 5: Documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/dashboard.md`
- Test: `tests/test_dashboard.py`

- [ ] **Step 1: Write the failing test**

```python
def test_the_dashboard_guide_documents_the_window(client):
    page = client.get("/api/docs/dashboard").json()["markdown"]
    assert "window" in page.lower()
    assert "pywebview" in page.lower()
```

- [ ] **Step 2: Run to verify it fails, then write the docs**

`docs/dashboard.md` gains a short section: the dashboard can run in its own window with `buspirate app`, or in a browser with `buspirate dashboard`; the window needs the `app` extra (`pip install -e '.[app]'`); closing the window stops any stream, disconnects and releases the port; and the double-click launcher now opens the window, falling back to the browser if it cannot.

State plainly that without a `.app` bundle macOS shows it in the Dock as the Python interpreter — a known trade for having no build step, not a bug.

`README.md`'s quick-start mentions the window as the default double-click behaviour.

- [ ] **Step 3: Run the full suite and commit**

```bash
.venv/bin/python -m pytest tests/ -q
git add README.md docs/dashboard.md tests/test_dashboard.py
git commit -m "docs: document running the dashboard in its own window"
```

---

## Self-review notes

- **Spec coverage:** §1 entry point → Task 4; §2 server off the main thread → Task 2; §3 readiness → Task 2; §4 shutdown → Task 3; §5 launcher → Task 4; §6 testing → Tasks 2-4; §7 spike → Task 1.
- **Task 1 is a gate, not a formality.** A NO-GO invalidates Tasks 2-5. The task text tells the implementer to stop and report rather than work around a failure, because re-planning is the controller's call.
- **The derived-timeout test in Task 3 Step 1 is the important one** — it is what stops `SHUTDOWN_TIMEOUT_SECONDS` and `STREAM_STOP_TIMEOUT_SECONDS` drifting apart later.
- **Known limit, stated in the spec and repeated here:** no test opens a window. Task 4's second test proves the wiring against a stub and nothing more. The window is a manual check.
- **Corrected during self-review:** the missing-pywebview test originally patched `builtins.__import__`, which would have intercepted every import inside `start_server` — including uvicorn's — and could pass or fail for reasons unrelated to `webview`. Replaced with `monkeypatch.setitem(sys.modules, "webview", None)`, which raises `ImportError` for that one name only.
- **One open decision delegated deliberately:** Task 4 Step 5, whether the launcher strips `--no-browser`/`--host` before forwarding `$@` to `app`, which rejects them. The implementer decides and reports.
- **Type consistency:** `start_server`, `stop_server`, `run_window`, `SERVER_START_TIMEOUT_SECONDS`, `SHUTDOWN_MARGIN_SECONDS`, `SHUTDOWN_TIMEOUT_SECONDS` are named identically throughout.
