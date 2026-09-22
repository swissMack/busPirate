# Bus Pirate Terminal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the dashboard a full interactive console onto the Bus Pirate's own terminal, entered and left deliberately, with the board's real state never misrepresented.

**Architecture:** The terminal is modelled as a `StreamState` — the same machinery sniffers use — with an input queue. `send_line` enqueues; the existing reader thread drains the queue and writes, so it remains the only thing touching the port. Entering calls `reset_hardware()`; leaving reuses `_finish_stream`, which already calls `stop_stream()`, which already re-enters binary mode.

**Tech Stack:** Python 3, FastAPI, pytest (`.venv/bin/python -m pytest`), vanilla ES modules, jsdom (`node tests/ui/frontend.mjs` against a running `--demo` server).

**Spec:** `docs/superpowers/specs/2026-09-22-bus-pirate-terminal-design.md`

## Global Constraints

- **`_read_stream` must remain the only thing touching the port while a stream runs.** That invariant is stated in its own docstring. `send_line` enqueues; it never writes. Drift here is a defect, not a shortcut.
- **A stream is stopped with `POST /api/stream/stop`** (`server.py:130`), not with a panel action. There is no `stop_stream` action; do not invent one.
- **`stream["kind"]` is a human display label**, not an identifier — existing values are `"I2C sniffer"` and `"UART bridge"`. Never branch on it. The terminal is discriminated by an explicit flag on the result (Task 2).
- **Where stream tests live:** `tests/test_streaming.py` has a fixture that auto-connects a **v3** and stops any stream on teardown, plus `run()`, `status()` and `wait_for_events()` helpers. Put stream-mechanics tests there. Put anything that must run against **both** variants in `tests/test_dashboard.py`, whose `client` fixture is parametrised `["v3","v4"]` and exposes `client.variant`.
- `app.js` knows nothing protocol-specific. It renders what it is served.
- Frontend suite: start `.venv/bin/python -m buspirate dashboard --demo --no-browser`, wait 5s, `node tests/ui/frontend.mjs`, then `pkill -f "buspirate dashboard"`. It disconnects on startup, so re-running is safe.
- Nothing here is verified against hardware. Every firmware claim gets a checklist entry in Task 7.
- Commit only the files each task names.

## What already exists — do not rebuild it

| Piece | Where |
|---|---|
| Terminal read — drain until quiet | `base.py:219` `read_text()` |
| Terminal write | `base.py:162` `write()` |
| Leave binary mode | `base.py:310` `reset_hardware()` (command `0x0F`) |
| **Return to binary mode** | `base.py:202` `stop_stream()` — writes `0x00`, drains, flushes, calls `enter_binary_mode()` |
| Stream lifecycle | `session.py:410` `_begin_stream`, `:427` `_read_stream`, `:473` `_finish_stream`, `:485` `stop_stream_blocking` |
| Stop endpoint | `server.py:130` `POST /api/stream/stop` |
| Text rendering | `decoders.py:98` `TextDecoder` |
| Panel lockout while streaming | `session.py:395` |
| Per-action escape hatch | `Action.allow_while_streaming` |
| Confirmation dialogs | `Action.confirm`, already used by `self_test` |

`_finish_stream` already calls `stop_stream()` and already clears `mode_name`
and `_mode`, so the terminal's exit is nearly free. `ModeError` subclasses
`BusPirateError` (`exceptions.py:12`), so `_finish_stream`'s existing
`except (BusPirateError, OSError)` already catches a failed re-entry.

---

### Task 1: Teach the fake a terminal

Test infrastructure first — every later task tests against this.

**Files:**
- Modify: `tests/fake_serial.py`
- Test: `tests/test_driver.py`

**Interfaces:**
- Consumes: nothing
- Produces: `FakeSerial` leaves binary mode on command `0x0F` and enters a terminal state that answers `?`, `i` and `v`; on `variant == "v3"` it also models the hardware reset.

- [ ] **Step 1: Read how the fake already models the terminal**

`identify()` works against the fake today, so the fake already serves a banner in a terminal-like state. Read `tests/fake_serial.py` end to end first, and record in your report which state it starts in and how `enter_binary_mode`'s null-knocking is handled. You are extending that, not inventing it.

- [ ] **Step 2: Write the failing tests**

Append to `tests/test_driver.py`:

```python
def test_reset_hardware_returns_the_fake_to_its_terminal(bp, fake):
    with bp.i2c():
        pass
    bp.reset_hardware()
    bp.write(b"i\n")
    assert "Bus Pirate" in bp.read_text(settle=0.05)


def test_the_terminal_answers_the_help_command(bp, fake):
    bp.reset_hardware()
    bp.write(b"?\n")
    assert bp.read_text(settle=0.05).strip() != ""


def test_binary_mode_can_be_re_entered_after_the_terminal(bp, fake):
    bp.reset_hardware()
    bp.write(b"i\n")
    bp.read_text(settle=0.05)
    bp.enter_binary_mode()
    assert bp.bitbang_version >= 1
```

- [ ] **Step 3: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_driver.py -k terminal -q`
Expected: FAIL. Report the exact failure. If one already passes, say so rather than forcing a change.

- [ ] **Step 4: Implement**

In `tests/fake_serial.py`, handle `0x0F` in the bitbang command path: leave binary mode, enter the terminal state. In the terminal state, respond to a completed line:

- `i` → the banner `identify()` already relies on
- `?` → a short menu, a few lines, enough to assert against
- `v` → a plausible pin-voltage table
- anything else → a short "unknown command" line plus the prompt

For `variant == "v3"`, `0x0F` must also model the reset: clear the peripheral state the fake tracks — the AUX/CS pin model (`_aux_pin`, `_aux_levels`) and any power or pull-up flags. For `v4`, leave that state alone. Record in your report exactly which fields you reset.

Keep the output short. These are assertions, not a firmware emulator.

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS, three new tests green, no regressions.

- [ ] **Step 6: Commit**

```bash
git add tests/fake_serial.py tests/test_driver.py
git commit -m "test: model the Bus Pirate terminal in the fake device"
```

---

### Task 2: The terminal stream and its input queue

**Files:**
- Modify: `buspirate/web/registry.py`
- Modify: `buspirate/web/session.py`
- Test: `tests/test_streaming.py`

**Interfaces:**
- Consumes: the fake's terminal from Task 1
- Produces: `live(..., input=True)`; `TerminalState(StreamState)` with `.inbox: queue.Queue`; `DeviceSession.enter_terminal()`; `DeviceSession.send_terminal_line(line)`; `TERMINAL_SETTLE_SECONDS`.

- [ ] **Step 1: Add the `input` flag to `live()`**

`stream["kind"]` is a display label, so the frontend cannot branch on it. Give the result an explicit flag instead. In `buspirate/web/registry.py`:

```python
def live(kind: str, *, decoder: str, caption: str = "", warning: str = "",
         input: bool = False) -> dict:
    """A live stream: the device now talks until it is told to stop.

    ``decoder`` names an entry in :mod:`buspirate.web.decoders`.
    ``input`` marks a stream that accepts typed lines back, which is what
    makes the pane render a console rather than a transcript.
    """
    return {
        "render": "stream",
        "kind": kind,
        "decoder": decoder,
        "caption": caption,
        "warning": warning,
        "input": input,
    }
```

- [ ] **Step 2: Write the failing test**

In `tests/test_streaming.py` (its fixture already connects a v3 and stops streams on teardown):

```python
def test_the_terminal_holds_the_port_as_a_stream(client):
    code, body = run(client, "connection", "open_terminal")
    assert code == 200, body
    assert body["result"]["input"] is True
    assert status(client)["stream"]["kind"] == "Board terminal"


def test_typing_into_the_terminal_reaches_the_board(client):
    run(client, "connection", "open_terminal")
    code, body = run(client, "connection", "send_line", line="i")
    assert code == 200, body
    found = wait_for_events(client, at_least=1)
    assert found["events"] >= 1
```

Both need Task 3's actions. They stay red until Task 3 — that is expected and is stated here so nobody "fixes" it early.

- [ ] **Step 3: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_streaming.py -k terminal -q`
Expected: FAIL — `panel 'connection' has no action 'open_terminal'`

- [ ] **Step 4: Add the state class**

In `buspirate/web/session.py`, beside `StreamState`, with `import queue` at the top:

```python
class TerminalState(StreamState):
    """The Bus Pirate's own terminal, held open as a stream.

    Typed input does not go to the port directly. ``send_terminal_line`` puts
    it here and the reader thread writes it, so that thread stays the only
    thing touching the port.
    """

    def __init__(self, decoder, result) -> None:
        super().__init__(
            "Board terminal", "connection", "open_terminal", decoder, result
        )
        self.inbox: "queue.Queue[bytes]" = queue.Queue()
```

- [ ] **Step 5: Drain the queue in the reader loop**

In `_read_stream`, as the first statement inside the `while` body, before the read:

```python
            if isinstance(stream, TerminalState):
                while True:
                    try:
                        line = stream.inbox.get_nowait()
                    except queue.Empty:
                        break
                    device.write(line)
```

`device.write()` already notifies the traffic hook, so typed input appears in the Traffic pane beside the board's replies.

- [ ] **Step 6: Build the right class in `_begin_stream`**

`_begin_stream` always constructs `StreamState`. Make it construct `TerminalState(decoder, result)` when `result.get("input")` is true, and `StreamState(...)` otherwise. Everything after the construction stays identical.

- [ ] **Step 7: Add the session methods and the constant**

Near the other module constants:

```python
#: How long to wait after leaving binary mode before reading. A v3 performs a
#: hardware reset here and has to boot; a v4 does not. Set conservatively for
#: the slower case — see the hardware checklist in docs/troubleshooting.md.
TERMINAL_SETTLE_SECONDS = 0.5
```

On `DeviceSession`:

```python
    def enter_terminal(self) -> Dict[str, Any]:
        """Leave binary mode and hold the board's own terminal open."""
        if self.bp is None or not self.bp.is_open:
            raise BusPirateError("not connected — pick a port and connect first")
        self.bp.reset_hardware()
        time.sleep(TERMINAL_SETTLE_SECONDS)
        self.bp.flush_input()
        return live(
            "Board terminal",
            decoder="text",
            caption="The Bus Pirate's own terminal. Type a command; '?' lists them.",
            input=True,
        )

    def send_terminal_line(self, line: str) -> None:
        stream = self.stream
        if not isinstance(stream, TerminalState):
            raise BusPirateError("the board's terminal is not open")
        stream.inbox.put((line + "\r\n").encode("ascii", errors="replace"))
```

Import `live` from `.registry` alongside the existing imports.

- [ ] **Step 8: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: the two Task 2 tests still fail on the missing actions; everything else passes. Report the counts.

- [ ] **Step 9: Commit**

```bash
git add buspirate/web/registry.py buspirate/web/session.py tests/test_streaming.py
git commit -m "feat: hold the Bus Pirate terminal open as a stream with an input queue"
```

---

### Task 3: The actions, and coming back clean

**Files:**
- Modify: `buspirate/web/panels/connection.py`
- Modify: `buspirate/web/session.py`
- Test: `tests/test_dashboard.py`, `tests/test_streaming.py`

**Interfaces:**
- Consumes: `enter_terminal()`, `send_terminal_line()` from Task 2
- Produces: `open_terminal` and `send_line` actions on the `connection` panel.

- [ ] **Step 1: Write the failing tests**

In `tests/test_dashboard.py` (runs against both variants):

```python
def test_the_terminal_warns_before_it_takes_the_board(client):
    body = connect(client)
    panels = {p["id"]: p for p in body["panels"]}
    action = next(a for a in panels["connection"]["actions"]
                  if a["name"] == "open_terminal")
    assert action["confirm"], "opening the terminal must confirm first"


def test_send_line_is_refused_when_the_terminal_is_not_open(client):
    connect(client)
    status, body = run(client, "connection", "send_line", line="i")
    assert status == 400
    assert "terminal" in body["error"]
```

In `tests/test_streaming.py`:

```python
def test_send_line_is_refused_while_a_sniffer_runs(client):
    run(client, "i2c", "sniff", power=True, pullups=True, speed=2)
    code, body = run(client, "connection", "send_line", line="i")
    assert code == 400
    assert "terminal" in body["error"]


def test_other_panels_are_refused_while_the_terminal_holds_the_port(client):
    run(client, "connection", "open_terminal")
    code, body = run(client, "i2c", "scan", power=True, pullups=True, speed=2)
    assert code == 400


def test_leaving_the_terminal_returns_to_binary_with_nothing_held(client):
    run(client, "pins", "set_pins", power=True, pullups=False, aux=False,
        mosi=False, clk=False, miso=False, cs=False)
    run(client, "connection", "open_terminal")
    assert client.post("/api/stream/stop").status_code == 200
    state = status(client)
    assert state["stream"] is None
    assert state["mode"] is None
    assert state["leds"]["VREG"] is False
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/ -k "terminal or send_line" -q`
Expected: FAIL — the actions do not exist.

- [ ] **Step 3: Add the handlers**

In `buspirate/web/panels/connection.py`. Note the parameter is named `line`, not `text` — `text` is the imported result helper and would be shadowed:

```python
def _open_terminal(ctx):
    return ctx.session.enter_terminal()


def _send_line(ctx, line):
    ctx.session.send_terminal_line(line)
    return text(f"Sent {line!r}.")
```

Register both actions in the panel's action list:

```python
        Action(
            name="open_terminal",
            label="Open the board's terminal",
            help="Leaves binary mode and gives you the Bus Pirate's own "
            "command prompt. Everything else in the dashboard is unavailable "
            "until you close it.",
            confirm="This leaves binary mode. On a Bus Pirate v3 that resets "
            "the board: the supplies go off and the pins go to inputs. On a v4 "
            "the board is not reset, but the current protocol mode is dropped. "
            "Nothing is restored when you come back. Continue?",
            stream=True,
            handler=_open_terminal,
        ),
        Action(
            name="send_line",
            label="Send",
            help="Types one line into the board's terminal.",
            params=[Param("line", "text", "Command", default="")],
            allow_while_streaming=True,
            handler=_send_line,
        ),
```

`send_terminal_line` already raises when the running stream is not the
terminal, which is what makes the sniffer case above return 400 —
`allow_while_streaming` alone does not distinguish which stream is running.

- [ ] **Step 4: Clear the pin state on the way out**

`_finish_stream` already calls `stop_stream()` — which writes `0x00`, drains, flushes and calls `enter_binary_mode()` — and already clears `mode_name` and `_mode`. It does not clear `last_pins`, which `leds()` reads through `_supplies_on()`. After a terminal session the supplies are off (a v3 reset; a v4 dropped its mode), so stale `last_pins` would light VREG over a dark board.

In `_finish_stream`, when the finished stream is a `TerminalState`, reset `last_pins` the same way `disconnect_blocking()` does.

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS, including Task 2's two tests, now green.

- [ ] **Step 6: Commit**

```bash
git add buspirate/web/panels/connection.py buspirate/web/session.py tests/
git commit -m "feat: open, type into and leave the board's terminal"
```

---

### Task 4: The MODE LED in the terminal

**Files:**
- Modify: `buspirate/web/wiring.py`
- Modify: `buspirate/web/session.py`
- Test: `tests/test_streaming.py`

**Interfaces:**
- Consumes: `TerminalState` from Task 2, `LED_RULES` from the v4 work
- Produces: MODE reports dark while the terminal holds the port, on both variants.

- [ ] **Step 1: Write the failing tests**

In `tests/test_streaming.py`:

```python
def test_the_mode_led_goes_dark_in_the_terminal(client):
    assert status(client)["leds"]["MODE"] is True
    run(client, "connection", "open_terminal")
    assert status(client)["leds"]["MODE"] is False


def test_the_mode_led_comes_back_after_the_terminal(client):
    run(client, "connection", "open_terminal")
    client.post("/api/stream/stop")
    assert status(client)["leds"]["MODE"] is True
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_streaming.py -k mode_led -q`
Expected: FAIL — MODE stays lit in the terminal.

- [ ] **Step 3: Implement**

The firmware clears `BP_LEDMODE` when it leaves binary mode (`Firmware/binIO.c:150-158`), identically on both variants. Both variants' MODE entries in `LED_RULES` use the `"connected"` inference.

Change what `"connected"` computes in `leds()` so it means *connected and in binary mode* — which is what it always described: `live and not isinstance(self.stream, TerminalState)`. Update the `means` text on both variants' MODE entries so the tooltip mentions the board's terminal.

Do not add a per-variant special case; this is the same on v3 and v4.

- [ ] **Step 4: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS, including the existing `test_the_mode_led_stays_lit_with_no_protocol_mode` — bitbang is still binary mode, so MODE stays lit there.

- [ ] **Step 5: Commit**

```bash
git add buspirate/web/wiring.py buspirate/web/session.py tests/test_streaming.py
git commit -m "feat: darken the MODE LED while the board is in its terminal"
```

---

### Task 5: The console in the browser

**Files:**
- Modify: `buspirate/web/static/app.js`
- Modify: `buspirate/web/static/app.css`
- Test: `tests/ui/frontend.mjs`

**Interfaces:**
- Consumes: a stream result carrying `input: true`, and the `send_line` action
- Produces: an input line in the live pane.

- [ ] **Step 1: Read first**

Read the whole of `tests/ui/frontend.mjs` and find how the existing sniffer checks open and stop a stream. Follow that exactly.

**There is no existing confirm pattern in the jsdom suite** — `self_test` is never exercised there, and `app.js:349` gates confirming actions behind `window.confirm(...)`, which jsdom does not implement. So you must stub it before clicking `open_terminal`:

```js
window.confirm = () => true;
```

Put the stub next to the other `window` setup at the top of the file (beside `window.fetch` and `window.WebSocket`), not inline, so any later confirming action is covered too. Note in your report that you added it.

- [ ] **Step 2: Write the failing checks**

Add, after the existing sniffer checks, a block that opens the terminal from the Connection panel, then:

```js
check("the terminal pane offers an input line",
  $("panel").querySelector(".stream__input") !== null);
```

Then type a line, submit it, and assert the pane gains output. Finally stop the stream and confirm the input line is gone, so later checks see a normal dashboard:

```js
check("the input line goes away when the stream stops",
  $("panel").querySelector(".stream__input") === null);
```

- [ ] **Step 3: Run to verify they fail**

```bash
pkill -f "buspirate dashboard"; sleep 1
nohup .venv/bin/python -m buspirate dashboard --demo --no-browser >/tmp/bpsrv.log 2>&1 &
sleep 5; node tests/ui/frontend.mjs; pkill -f "buspirate dashboard"
```
Expected: FAIL on the missing input line.

- [ ] **Step 4: Implement**

Find where the live stream pane is rendered in `app.js` (the `render === "stream"` branch) and add an input line **when the result's `input` flag is true** — never by testing the `kind` string, which is a display label. Submitting posts `send_line` with `{line: <typed text>}` and clears the field; Enter submits. Do not disable the field while the request is in flight: a console that swallows keystrokes is worse than one that queues them.

Give it the class `stream__input` so the checks above can find it, and style it in `app.css` with the existing tokens so it reads as part of the pane.

- [ ] **Step 5: Run both suites**

```bash
.venv/bin/python -m pytest tests/ -q
pkill -f "buspirate dashboard"; sleep 1
nohup .venv/bin/python -m buspirate dashboard --demo --no-browser >/tmp/bpsrv.log 2>&1 &
sleep 5; node tests/ui/frontend.mjs; pkill -f "buspirate dashboard"
```
Expected: both PASS.

- [ ] **Step 6: Commit**

```bash
git add buspirate/web/static/app.js buspirate/web/static/app.css tests/ui/frontend.mjs
git commit -m "feat: type into the board's terminal from the dashboard"
```

---

### Task 6: An honest state when the return fails

**Files:**
- Modify: `buspirate/web/session.py`
- Test: `tests/test_streaming.py`

**Interfaces:**
- Consumes: everything above
- Produces: a session that does not claim binary mode after a failed return.

- [ ] **Step 1: Write the failing test**

`ModeError` subclasses `BusPirateError` (`exceptions.py:12`), so `_finish_stream`'s existing `except (BusPirateError, OSError)` already catches a failed `enter_binary_mode()` and puts the message in `note`. The gap is what the session then reports about itself.

```python
def test_a_failed_return_from_the_terminal_does_not_claim_a_mode(client, monkeypatch):
    from buspirate.base import BusPirate
    from buspirate.exceptions import ModeError

    run(client, "connection", "open_terminal")

    def refuse(self, retries=25):
        raise ModeError("no BBIO response after 25 attempts on fake")

    monkeypatch.setattr(BusPirate, "enter_binary_mode", refuse)
    client.post("/api/stream/stop")

    state = status(client)
    assert state["stream"] is None
    assert state["mode"] is None
```

Then extend it with whatever "honest" turns out to mean once you have read `_finish_stream` and `status()` — at minimum the note must survive to the user rather than being swallowed. State in your report what you added and why.

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_streaming.py -k failed_return -q`

- [ ] **Step 3: Implement**

Make `_finish_stream` record the failure where the user can see it. Read what `status()` already exposes and prefer an existing field over inventing one. The requirement is only this: after a failed return the dashboard must not present itself as a working binary-mode session.

- [ ] **Step 4: Run the full suite and commit**

```bash
.venv/bin/python -m pytest tests/ -q
git add buspirate/web/session.py tests/test_streaming.py
git commit -m "fix: do not claim binary mode when the return from the terminal fails"
```

---

### Task 7: Documentation and the checklist

**Files:**
- Modify: `docs/dashboard.md`
- Modify: `docs/user-guide.md`
- Modify: `docs/troubleshooting.md`
- Test: `tests/test_dashboard.py`

- [ ] **Step 1: Write the failing test**

```python
def test_the_dashboard_guide_documents_the_terminal(client):
    page = client.get("/api/docs/dashboard").json()["markdown"]
    assert "terminal" in page.lower()
    assert "reset" in page.lower()
```

- [ ] **Step 2: Run to verify it fails, then write the docs**

`docs/dashboard.md` gains a section covering: what the board's terminal is and how it differs from the Traffic pane (protocol log vs console); that opening it leaves binary mode; that **a v3 is reset by this and a v4 is not**; that nothing is restored on return; and that the rest of the dashboard is unavailable while it is open.

`docs/user-guide.md`'s "I want to…" list gains a line pointing at it.

Match the house style: direct, specific, no hedging.

- [ ] **Step 3: Extend the hardware checklist**

Append to the `## Not yet verified against hardware` list at the end of `docs/troubleshooting.md`:

```markdown
- [ ] v3: opening the terminal really does reset the board — supplies off,
      pins to input
- [ ] v4: opening the terminal does **not** reset the board
- [ ] Both: MODE goes dark while the terminal is open, and comes back after
- [ ] The settle after leaving binary mode is long enough that the first
      prompt is not truncated — `TERMINAL_SETTLE_SECONDS` in session.py
- [ ] Returning to binary mode works reliably, including straight after a
      v3 reset
- [ ] `~` self-test runs to completion through the console, including the
      stages that expect input
```

- [ ] **Step 4: Run the full suite and commit**

```bash
.venv/bin/python -m pytest tests/ -q
git add docs/ tests/test_dashboard.py
git commit -m "docs: document the board terminal and what is still unverified"
```

---

## Self-review notes

- **Spec coverage:** §1 port ownership → Task 2; §2 session state → Tasks 2, 3; §3 actions → Task 3; §4 frontend → Tasks 2 (the `input` flag) and 5; §5 LEDs → Task 4; §6 failure paths → Task 6; §7 testing → Task 1 plus tests in every task. Verification list → Task 7.
- **Corrections made during self-review**, all against the real code: streams stop via `POST /api/stream/stop`, not an action; stream tests belong in `tests/test_streaming.py`, whose fixture auto-connects a v3 and stops streams on teardown; `stream["kind"]` is a display label (`"I2C sniffer"`, `"UART bridge"`), so the console is discriminated by a new `input` flag on the `live()` result rather than by the kind string; and `ModeError` already subclasses `BusPirateError`, so Task 6 is about what the session *reports*, not about catching an escape.
- **Ordering:** Task 1 first, because everything tests against the fake's terminal. Task 2's tests depend on Task 3's actions and are expected to stay red until then — stated in the step so nobody "fixes" it early.
- **Type consistency:** `TerminalState`, `.inbox`, `enter_terminal()`, `send_terminal_line(line)`, `TERMINAL_SETTLE_SECONDS`, the `input` flag and the `stream__input` class are named identically throughout.
- **Known risk:** `TERMINAL_SETTLE_SECONDS = 0.5` is a guess, deliberately a named constant with a comment pointing at the checklist, because it will need tuning against a real v3.
