# Fix: terminal panel usability defect

**Commit:** e01c3c0 (branch `fix/terminal-panel`)

## State signal: how "this stream is a console" reaches `/api/state`

`StreamState.describe()` now returns `"input": False`, and `TerminalState`
(session.py) overrides `describe()` to set it `True`:

```python
class StreamState:
    def describe(self):
        return {..., "input": False}

class TerminalState(StreamState):
    def describe(self):
        data = super().describe()
        data["input"] = True
        return data
```

This is the same flag `enter_terminal()`'s result already carries
(`live(..., input=True)`), just surfaced through `status.stream` too, and
it keys off the real `TerminalState` class rather than `stream.kind` (a
display label, forbidden to branch on). `app.js` uses
`state.status.stream.panel === panel.id && state.status.stream.input` to
decide whether the panel being rendered should show the live pane — generic
(no "terminal" string anywhere in app.js), and true only for a console
stream on its own panel.

I also changed `TerminalState.__init__`'s hardcoded `panel_id` from
`"connection"` to `"terminal"`, since `open_terminal` now runs on the
Terminal panel — `stream.panel` has to name where the action actually lives
or the panel-match check above would never fire.

## Files changed

- **`buspirate/web/panels/terminal.py`** (new) — `open_terminal` and
  `send_line`, moved verbatim (same handlers, same `confirm` text, same
  help text) off `connection.py`. `Panel(id="terminal", order=15, mode=None)`
  — matches Connection's `mode=None`, since neither needs a protocol mode.
  `send_line` has `hidden=True`.
- **`buspirate/web/panels/connection.py`** — `_open_terminal`, `_send_line`
  and their two `Action` entries removed; nothing else touched.
- **`buspirate/web/registry.py`** — `Action.hidden: bool = False`, included
  in `to_json()`.
- **`buspirate/web/session.py`** — `StreamState.describe()` / `TerminalState.describe()`
  as above; `TerminalState`'s hardcoded `panel_id` updated to `"terminal"`.
- **`buspirate/web/static/app.js`**:
  - `renderPanel()`: computes `revived = streamPane({input:true})` when the
    running stream belongs to the panel being shown, and renders that
    instead of the action list (so Stop sits at the top with nothing else
    on the panel, satisfying D).
  - `actionBlock`'s click handler: when a run's result is a console stream
    (`render === "stream" && input`), it now calls `renderPanel()` instead
    of patching its own `output` div, so the *first* open of the terminal
    gets the same "nothing else on the panel" rendering as a revived one,
    not just after navigating away and back.
  - Action list building now filters `!action.hidden` before mapping to
    `actionBlock`, so `send_line` gets no automatic form.
- **`docs/dashboard.md`** — "Connection → Open the board's terminal" →
  "The Terminal panel's Open the board's terminal"; and the paragraph
  claiming "switching panels hides the console and its Stop button without
  closing the stream" rewritten to describe the fixed behaviour (pane is
  re-derived, not lost). Nothing else in the file touched.
  Note: `docs/user-guide.md:34` has the same now-stale "Connection →
  **Open the board's terminal**" reference; left alone since the brief
  scoped doc updates to `dashboard.md` only — flagging it here as a
  legitimate follow-up.

## Tests changed, and why each is legitimate

- **`tests/test_dashboard.py`**: `test_the_terminal_warns_before_it_takes_the_board`
  and `test_send_line_is_refused_when_the_terminal_is_not_open` now look up
  the action on `panels["terminal"]` and call `run(client, "terminal", ...)`
  — the action genuinely moved panels, so asserting it's still on
  `"connection"` would just be asserting the bug is unfixed. Added
  `test_terminal_is_its_own_panel_right_after_connection` (panel exists,
  sits immediately after Connection, holds exactly these two actions, and
  Connection no longer has them), `test_send_line_is_hidden_from_automatic_form_rendering`,
  and `test_open_terminal_is_not_hidden`.
- **`tests/test_streaming.py`**: every `run(client, "connection", "open_terminal"/"send_line", ...)`
  call became `run(client, "terminal", ...)` — same reasoning, mechanical
  rename, no assertions weakened. `connect`/`disconnect`/`set_variant`
  calls (still genuinely on Connection) were left untouched.
- **`tests/ui/frontend.mjs`**:
  - "nav lists every panel plus the guide" count 8 → 9 (one more real panel
    now exists).
  - The terminal section now clicks the **Terminal** nav button instead of
    Connection, added a check that `send_line` has no `[data-action="send_line"]`
    form, and re-queries the pane from `$("panel")` rather than the old
    action-block reference (which the fix's re-render can detach).
  - **New**: the navigate-away-and-back regression test — opens the
    terminal, switches to I2C (asserts header still says the stream is
    running and the pane is gone from the DOM), switches back to Terminal
    (asserts the pane, a working un-disabled Stop button, and the input
    line are all present), types a line and confirms output still arrives
    (proves it's live, not a static leftover), stops it, and confirms no
    stale pane reappears afterward. Confirmed this failed pre-fix (pane
    `null` after returning) before implementing.

## Test runs

```
.venv/bin/python -m pytest tests/ -q
378 passed, 12 skipped
```
(Baseline 372 passed + 6 new backend tests = 378; no baseline test weakened.)

```
pkill -9 -f "buspirate dashboard"; sleep 1
nohup .venv/bin/python -m buspirate dashboard --demo --no-browser >/tmp/bpsrv.log 2>&1 &
sleep 5; node tests/ui/frontend.mjs; pkill -9 -f "buspirate dashboard"
```
`all frontend checks passed` (81 checks, 0 failures).

## Concerns / notes

- `enter_terminal`, `send_terminal_line`, `stop_stream_blocking`,
  `_finish_stream`, the LED rules and teardown paths were not touched —
  only `TerminalState`'s `panel_id` literal and the new `describe()`
  override.
- `docs/user-guide.md:34`'s stale reference (flagged above) is fixed below,
  under "Doc sweep".

## Doc sweep

**Commit:** 3a9... (see below) on branch `fix/terminal-panel`.

### `docs/user-guide.md:34`

Before:
```
| Get the board's own `HiZ>` prompt | Dashboard → Connection → **Open the board's terminal** | leaves binary mode; see [Dashboard](dashboard.md#the-boards-terminal) |
```
After:
```
| Get the board's own `HiZ>` prompt | Dashboard → Terminal → **Open the board's terminal** | leaves binary mode; see [Dashboard](dashboard.md#the-boards-terminal) |
```
Kept the row's terse "I want to…" shape — only the middle column's panel
name changed, and the existing link to `dashboard.md#the-boards-terminal`
was left to do the explaining, per the coordinator's instruction.

No pinning assertion added. This repo has no existing test that asserts
literal Markdown doc-file content (the jsdom suite tests the rendered
in-app guide pages via `/api/docs`, not this static table), so a one-off
string-match test here would be inventing a new testing convention for a
single terse table cell, not following one. The structural claim that
actually matters — that `open_terminal`/`send_line` live on the `terminal`
panel and not `connection` — is already pinned server-side by
`test_terminal_is_its_own_panel_right_after_connection` in
`tests/test_dashboard.py`, added during the original fix.

### Grep command and full output

```
grep -rniE "connection.*(open.the.board.s.terminal|open_terminal|send_line)|open_terminal|send_line" \
  --include="*.md" --include="*.py" --include="*.js" --include="*.mjs" --include="*.sh" --include="*.txt" --include="*.rst" \
  -- . \
  2>/dev/null | grep -v "^Binary" | grep -v "\.venv/" | grep -v "node_modules/" | grep -v "__pycache__" | grep -v "^./docs/superpowers/"
```
Followed by three narrower checks over what the first pass could not
phrase as a single regex: `grep -n -i "terminal" README.md`, a listing of
`bin/*` files grepped for "terminal", `grep -rn -i "terminal" buspirate/*.py`
plus `grep -rln -i "terminal" buspirate --include="*.py"`, then
`grep -rni "connection" docs/*.md | grep -vi superpowers | grep -i "terminal\|panel"`,
`grep -rn "Connection panel" buspirate --include="*.py" --include="*.js"`,
and `grep -n -i "terminal\|connection panel" buspirate/cli.py buspirate/__main__.py`
(no hits, omitted above).

Full matches from the main command (excluding `docs/superpowers/`, which is
a historical record left alone per the coordinator's instruction):

- `tests/test_dashboard.py`, `tests/test_streaming.py`, `tests/ui/frontend.mjs`,
  `buspirate/web/session.py`, `buspirate/web/panels/terminal.py`,
  `.superpowers/fix-terminal-panel-report.md` — all already correct: they
  name the `terminal` panel, not `connection`, from the original fix.
- **`buspirate/web/static/app.js:557`** — a code comment: `` `send_line`
  lives on the Connection panel and is `allow_while_streaming` `` — genuinely
  stale, missed in the original fix since it's prose inside a JS comment,
  not a string the frontend tests exercise. **Fixed**: now reads
  `` `send_line` lives on the Terminal panel and is `allow_while_streaming` ``.
  Comment-only change; no test covers comment text, so nothing to re-run
  beyond the full suite.

Additional targeted checks, all judged still correct and left alone:

- `docs/dashboard.md:193` — "**Disconnect** on the Connection panel is
  always available" — Disconnect is still on Connection and still the way
  out of a stuck stream; matches the coordinator's explicit "still true,
  should stay."
- `docs/dashboard.md:209` — "The **Board to show** picker (top bar and
  Connection panel)" — `set_variant` was never moved; still accurate.
- `buspirate/web/wiring.py:296` — "'Show the cable legend' on the
  Connection panel" — `legend` action was never moved; still accurate.
- `docs/pins-and-power.md:41-42` — mentions opening the board's own
  terminal from the dashboard but only links onward to
  `dashboard.md#the-boards-terminal`; never names a panel, so nothing to
  fix.
- `README.md` (lines 6, 15, 82), `docs/cli.md:98`, `docs/protocol-reference.md:22`,
  `docs/bus-pirate-v4.md:68`, `docs/troubleshooting.md` (terminal checklist
  items), `buspirate/base.py`, `buspirate/web/panels/i2c.py:311`,
  `bin/dashboard.command:5` — all use "terminal" for the board's own
  text-mode personality or the user's shell (`bin/dashboard.command`'s is
  literally macOS Terminal.app); none route to a panel, so none are stale.
- `docs/superpowers/plans/2026-09-22-bus-pirate-terminal.md` and
  `docs/superpowers/specs/2026-09-22-bus-pirate-terminal-design.md` — left
  untouched. These record the terminal feature's original design (which
  correctly put `open_terminal`/`send_line` on `connection` at the time);
  rewriting them to say `terminal` would falsify the historical record, per
  the coordinator's explicit instruction.

### Test run after the sweep

```
.venv/bin/python -m pytest tests/ -q
378 passed, 12 skipped
```
No jsdom run: the sweep's only functional-adjacent change was a JS comment
in `app.js`, not anything in `tests/ui/`.
