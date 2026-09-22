# The dashboard as a desktop app — design

**Date:** 2026-09-22
**Status:** approved design, not yet implemented

## The problem

The dashboard is a web page. `bin/dashboard.command` double-clicks to a
Terminal window that bootstraps `.venv`, starts the server and opens your
browser. That works, but it is two windows — a Terminal you must leave open
and a browser tab that looks like a website — for a tool that drives hardware
on a bench.

## Decisions taken

| Question | Decision |
|---|---|
| What is "an app"? | **Its own window** — a real application window, no browser chrome, no Terminal behind it. Same Python server inside, wrapped in pywebview |
| Closing the window mid-session | **Shut down cleanly.** Stop any stream, disconnect, release the port. No confirmation dialog, no background process |
| Packaging | **Repoint `bin/dashboard.command`.** No `.app` bundle, no build step |
| Architecture | **One process**: uvicorn in a daemon thread, the window on the main thread |

Rejected: a `.app` bundle via py2app (a build step that rots on Python
upgrades, for a tool used on one bench); a hand-written bundle (hardcodes a
repo path); Tauri or Electron (a whole toolchain, only justified if other
people install it); a confirmation on close (a dialog on every close gets
clicked through, which is how confirmations stop working); staying resident
after the window closes (a hidden process holding the serial port is exactly
what makes the *next* connection fail mysteriously); and a two-process design
where the window spawns `buspirate dashboard` and kills it (teardown becomes a
kill, losing the clean shutdown that was the point).

## What already exists

| Piece | Where |
|---|---|
| The server, loopback-only | `server.py:222` `serve()` — refuses any non-loopback host |
| **Hardware teardown on shutdown** | `server.py` lifespan — stops the stream, disconnects, suppresses the refusal a wedged reader raises |
| The venv bootstrap and first-run install | `bin/dashboard.command` |
| CLI arg shapes to copy | `cli.py` — `--demo`, `--variant`, `--port-number` |

The lifespan already does the hardware teardown this design needs. "Close the
window cleanly" therefore reduces mostly to "stop uvicorn gracefully".

## The dependency

pywebview 6.2.1, `requires-python >=3.8`, which matches this project's floor.
On macOS it pulls six packages as hard dependencies:
`pyobjc-core`, `pyobjc-framework-Cocoa`, `pyobjc-framework-Quartz`,
`pyobjc-framework-WebKit`, `pyobjc-framework-security`,
`pyobjc-framework-UniformTypeIdentifiers`.

That weight is why it goes in its own extra:

```toml
app = ["pywebview>=5"]
```

**Not** in `web`, **not** in `dev`. `pip install -e .[web]` must stay as light
as it is today, or a GUI toolkit lands in every test and CI path for a
dependency none of them use.

## Design

### 1. Entry point

A new `buspirate app` subcommand in `cli.py`, sharing `dashboard`'s
`--demo`, `--variant` and `--port-number`. No `--no-browser` — meaningless
here. `--host` is not offered either: the window connects to loopback, and
`serve()`'s loopback-only guard stays the single place that rule lives.

`serve()` and `buspirate dashboard` are untouched. This adds a way to run the
dashboard; it never replaces one. That is not only a preference — the jsdom
suite drives the HTTP server headlessly, so the browser path is load-bearing
for the tests.

### 2. Running the server off the main thread

macOS requires the GUI on the main thread, so uvicorn goes on another one.
uvicorn installs signal handlers during `serve()`, which only works on the
main thread, so it needs a subclass:

```python
class _WindowServer(uvicorn.Server):
    """uvicorn on a worker thread: signal handlers only work on the main one."""

    def install_signal_handlers(self) -> None:
        pass
```

### 3. The readiness handshake

Creating the window before the server is listening shows an error page. So:
poll `server.started` until true, with a timeout, and watch the thread — if it
has died before `started`, the server failed and the reason must reach the
user.

The likely failure is **port 8765 already in use**, which is easy to hit
because the same person may have left `buspirate dashboard` running. That case
gets a sentence naming the port and the likely cause, not a traceback and not
an empty window.

### 4. Shutdown

`webview.start()` blocks until the window closes, then returns. At that point:

1. `server.should_exit = True`
2. join the server thread
3. uvicorn's lifespan runs, which stops any stream, disconnects and releases
   the port

**The join timeout must respect the terminal work.** `stop_stream_blocking()`
joins the reader thread with `STREAM_STOP_TIMEOUT_SECONDS` (`session.py:40`,
currently 15.0) before refusing, so shutdown can legitimately take that long.

The window's join must therefore be **derived from that constant, not a second
hardcoded number** — import it and add a margin. Two independently hardcoded
timeouts would drift the moment either is tuned, and the failure would be a
close that hangs or gives up early.

If the join still does not finish, print why and exit anyway: the process is
ending and the OS releases the port regardless. What it must never do is hang
forever on close.

### 5. The launcher

`bin/dashboard.command` installs `[web,app]` instead of `[web]` and execs
`buspirate app` instead of `buspirate dashboard`.

**It falls back, and the split of responsibility is explicit:**

- `buspirate app` owns the diagnosis. If pywebview cannot be imported it says
  so — naming the `app` extra — and exits non-zero. It does not silently open
  a browser, because someone who typed `buspirate app` asked for a window.
- `bin/dashboard.command` owns the fallback. On a non-zero exit it reports
  that the window could not start and execs the browser dashboard instead.

A tool that drives hardware should not become unlaunchable because a GUI
toolkit failed to install — but the fallback belongs in the double-click
convenience path, not in the command someone typed deliberately.

### 6. Testing, and its limits

Testable headlessly, with no window at all:

- the server thread starts and reports ready
- a taken port produces the readable error, not a traceback
- `should_exit` stops it, and the lifespan teardown runs
- the join timeout is longer than `disconnect_blocking()`'s own

The window entry point gets a smoke test against a stubbed `webview` module —
enough to catch a wiring mistake in the call, not enough to prove a window
appears.

**The window itself is a manual check.** It cannot run in the suite. This is
stated plainly rather than papered over: the app layer will have thinner
coverage than the rest of this codebase, and that is a consequence of choosing
a GUI, not an oversight.

### 7. The spike comes first

Before any of the above: prove that a pywebview window can load the dashboard
from `127.0.0.1:8765` **and hold the websocket** the live log and the terminal
console depend on. WKWebView reaching loopback and upgrading a websocket is
the assumption the entire design rests on, and it is untested.

The spike's output is an answer, not code. Whatever it produces is deleted.

If the websocket does not work inside WKWebView, this design is wrong and the
alternatives are a different shell (Tauri/Electron) or abandoning the window.
Finding that out first costs an hour; finding it out last costs the build.

## Out of scope

- A `.app` bundle, an icon, signing, notarization, auto-update. All belong to
  "something you can give people", which was explicitly not chosen.
- Windows and Linux. pywebview is cross-platform, but nothing here is
  designed or tested for them, and the launcher is a macOS `.command`.
- Replacing the browser path. It stays, and the tests depend on it.
- A tray or menu-bar presence.

## Open items

1. **The spike's outcome** gates everything. See section 7.
2. ~~The exact join timeout.~~ **Resolved during spec review:** the value is
   already a named constant, `STREAM_STOP_TIMEOUT_SECONDS` at `session.py:40`.
   The window's join derives from it rather than duplicating the number.
3. **Dock identity.** Without a bundle the app shows as the Python interpreter,
   with a generic icon and name. Accepted as the cost of no build step, and
   recorded here so it is a known trade rather than a surprise.
