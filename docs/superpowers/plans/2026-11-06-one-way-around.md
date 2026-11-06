# One Way Around Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The left column becomes the dashboard's only navigation, guide included; help follows the connected board; and the Bit Pirate's traffic reads as text.

**Architecture:** Frontend changes in `buspirate/web/static/app.js` and `index.html`. The guide's contents and search move into `#nav` while the guide is open, replacing the drop-down. Two `Board` fields (in `buspirate/boards`) carry what differs per board: `panel_docs`, which `server._panels_json` applies over each panel's `doc`, and `traffic_text`, which `session._on_traffic` uses to add decoded text to traffic events.

**Tech Stack:** Python 3.8+, FastAPI, vanilla JS, pytest, jsdom checks (`make ui-test`).

**Spec:** `docs/superpowers/specs/2026-11-06-board-driven-app-design.md` §4 (One way to get around), plus the user's screenshots of 2026-11-06: duplicated Guide and quick-action buttons, the guide drop-down in the main area, the Bus Pirate cable wiring shown for a Bit Pirate, "null" above every guide page, and hex traffic from a text board.

**Branch:** `one-way-around`, cut from `board-registry` (PR #28), because it uses `Board`.

## Global Constraints

- **One way to get around:** after this plan, the top bar holds status only (board, firmware, port, LEDs, the board-mismatch warning). No buttons there: no Guide button, no quick-action strip, no "Follow the board" select.
- The "Follow the board" choice still exists: it is the Connection panel's existing `set_variant` action (`panels/connection.py`), which already does the same job.
- Opening the guide never leaves the column's own controls behind. The column shows "← Back", a search box, then the guide's page list grouped by `group` (this app, then the board's manual) as collapsible sections, with the open page marked `aria-current="true"`.
- Python 3.8 compatible. Run the Python 3.8 check with the dev extra: `uv run --isolated --python 3.8 --with pytest --with-editable '.[dev]' python -m pytest -q tests`.
- Nothing changes for v3, v4 or the Bus Pirate 6 apart from the navigation above. Their `panel_docs` stay empty and `traffic_text` stays False.

## Review Focus

1. **A guide page opened from a panel** must mark that page in the column, and "← Back" must return to the same panel, not to Connection. Test in Task 3.
2. **A long or ANSI-laden Bit Pirate reply** (`\x1b[K`, `\r\n`, a prompt redraw) must show readable text in Traffic, with escape codes removed and line breaks shown as `⏎`, never raw `\x1b`. Test in Task 1.
3. **Switching boards while the guide is open** (Connect to a different board) must rebuild the column's page list for the new board's manual. Test in Task 3.
4. **Search with no results, or fewer than 2 characters,** shows the page list and no stale results. Test in Task 3.
5. **A guide page whose name the board overrides** (`bitpirate-wiki/05-i2c`) must exist on disk. Test in Task 2.

---

### Task 1: The Bit Pirate's traffic as text; no stray "null" in the guide

**Files:**
- Modify: `buspirate/boards/_board.py` (new field), `buspirate/boards/bitpirate.py`, `buspirate/web/session.py:269-283` (`_on_traffic`), `buspirate/web/static/app.js` (`addLogLine` ~948; `renderGuide` ~1375)
- Test: `tests/test_boards.py`, `tests/ui/frontend.mjs`

**Interfaces:**
- Produces: `Board.traffic_text: bool = False` (True for the Bit Pirate). A traffic event gains `"text": str` when the connected board's `traffic_text` is True. `session.traffic_text(data: bytes) -> str` is a module-level function: decode as UTF-8 with `errors="replace"`, remove ANSI CSI sequences (`\x1b\[[0-9;?]*[A-Za-z]`), show `\r\n`, `\n` and `\r` as `⏎`, and show other control bytes as `·`.

- [ ] **Step 1: Failing tests** in `tests/test_boards.py`:

```python
def test_text_traffic_drops_escapes_and_marks_line_breaks():
    from buspirate.web.session import traffic_text
    assert traffic_text(b"\rI2C> scan\x1b[K\r\nFound 0x68\r\n") == "⏎I2C> scan⏎Found 0x68⏎"
    assert traffic_text(b"\x00ok") == "·ok"

def test_only_text_boards_get_text_traffic():
    assert boards.REGISTRY["bitpirate"].traffic_text is True
    assert not any(b.traffic_text for v, b in boards.REGISTRY.items() if v != "bitpirate")

def test_a_bit_pirate_traffic_event_carries_its_text(client_bitpirate):
    # connect to simulated-bitpirate via /api/run connection/connect, run i2c scan,
    # then GET /api/state: some traffic entry has "text" containing "scan".
```

(`client_bitpirate`: a fixture like `client` that posts `connection/connect` with `port="simulated-bitpirate"`.)

In `tests/ui/frontend.mjs`, add: after opening any guide page, `!$("guide").textContent.trimStart().startsWith("null")`, and with a simulated Bit Pirate connected, the Traffic lines show `scan` as text.

- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_boards.py -q` and `make ui-test`. Expected: the new tests fail (no `traffic_text`; "null" present).
- [ ] **Step 3: Implement.** `_on_traffic` adds `entry["text"]` when `boards.get(self.bp.profile.variant).traffic_text`, but not while the Terminal holds the port (the terminal pane already shows the text). `addLogLine` shows `event.text` in place of `event.hex` when present, with the hex in the line's `title`. `renderGuide` filters null children before `replaceChildren`, as `renderPanel` already does.
- [ ] **Step 4: Run** the full suite and `make ui-test`. Expected: all pass.
- [ ] **Step 5: Commit** "Bit Pirate traffic reads as text; no 'null' above guide pages".

---

### Task 2: Help follows the board

**Files:**
- Modify: `buspirate/boards/_board.py`, `buspirate/boards/bitpirate.py`, `buspirate/web/server.py` (`_panels_json`)
- Test: `tests/test_boards.py`

**Interfaces:**
- Produces: `Board.panel_docs: Dict[str, str]` (default empty), panel id to guide page. In `_panels_json`, `data["doc"] = board.panel_docs.get(panel.id, data["doc"])`. Bit Pirate values: `connection` → `bitpirate`, `terminal` → `bitpirate-wiki/99-general`, `i2c` → `bitpirate-wiki/05-i2c`, `spi` → `bitpirate-wiki/06-spi`, `uart` → `bitpirate-wiki/03-uart`.

- [ ] **Step 1: Failing tests:**

```python
def test_every_board_panel_doc_exists():
    from buspirate.web import docs
    for board in boards.REGISTRY.values():
        for page in board.panel_docs.values():
            assert docs.read(page) is not None, (board.variant, page)

def test_a_bit_pirate_panel_links_to_its_own_reference(client_bitpirate):
    panels = {p["id"]: p for p in client_bitpirate.get("/api/state").json()["panels"]}
    assert panels["i2c"]["doc"] == "bitpirate-wiki/05-i2c"

def test_bus_pirate_panel_docs_are_unchanged(client):   # simulated v3
    panels = {p["id"]: p for p in client.get("/api/state").json()["panels"]}
    assert panels["i2c"]["doc"] == "i2c"
```

- [ ] **Step 2: Run.** Expected: FAIL (no `panel_docs`).
- [ ] **Step 3: Implement** as specified.
- [ ] **Step 4: Run** the full suite. Expected: all pass.
- [ ] **Step 5: Commit** "A panel's guide link follows the connected board".

---

### Task 3: The guide lives in the left column

**Files:**
- Modify: `buspirate/web/static/app.js` (`renderNav` ~276, `openGuide` ~1275, `renderGuide` ~1294), `buspirate/web/static/style.css` or the `<style>` in `index.html` (wherever `.nav` is styled)
- Test: `tests/ui/frontend.mjs` (replace the checks at ~617–650 that read `$("guide").querySelector("select")`)

**Interfaces:**
- Consumes: `state.guide.pages` (`{name, title, group}`), `openGuide(name, anchor)`.
- Produces: while `state.guide.open`, `renderNav` draws (in order) `button.nav__back` "← Back", `input.nav__search` (type=search), `div.nav__results`, and for each group a `details.nav__group[open]` with `summary` = group label and one `button` per page (`data-doc` = name, `aria-current="true"` on the open page). The `#guide` area holds only `.guide__banner` (when one applies) and `.guide__body`: no bar, no select, no search. `state.guide.from` remembers the panel id the guide was opened from, and Back restores it.

- [ ] **Step 1: Failing UI checks** in `tests/ui/frontend.mjs`, replacing the drop-down checks:
  - opening the guide from the I2C panel puts `.nav__back`, `.nav__search` and at least 2 `details.nav__group` in `#nav`, and `#guide select` is absent;
  - the page button for the open page has `aria-current="true"`;
  - clicking another page button opens it (`.guide__body` contains its title);
  - typing "pull" in `.nav__search` lists results in `.nav__results`; clearing it empties them;
  - `.nav__back` returns to the I2C panel (`#panel h1` is "I2C");
  - with the guide open, connecting `simulated-bitpirate` rebuilds the groups so one is "ESP32 Bit Pirate wiki".
- [ ] **Step 2: Run** `make ui-test`. Expected: the new checks FAIL.
- [ ] **Step 3: Implement.** Keep the search behaviour (2+ characters, `/api/docs-search`). Collapsing a group is native `<details>`. Long groups scroll inside `#nav`.
- [ ] **Step 4: Run** `make ui-test` and the full suite. Expected: all pass.
- [ ] **Step 5: Commit** "The guide's contents and search live in the left column".

---

### Task 4: Nothing to navigate in the top bar

**Files:**
- Modify: `buspirate/web/static/index.html` (remove `#recipes`, `#guide-btn`, the `#variant` select; keep `#variant-warning`), `buspirate/web/static/app.js` (delete `renderRecipes`, the `#guide-btn` listener and `renderVariant`'s select; keep the mismatch warning text and render it from `state`), `tests/ui/frontend.mjs` (~82 recipe strip, ~99–165 variant select)
- Test: `tests/ui/frontend.mjs`

**Interfaces:**
- Consumes: the Connection panel's `set_variant` action (unchanged).
- Produces: the header holds `#status`, `#usb`, `#leds` and `#variant-warning` only.

- [ ] **Step 1: Rewrite the UI checks.** The header has no `button` and no `select`. The variant checks drive the Connection panel's `set_variant` form (choose `v4`, submit), then assert that the warning appears, that choosing `auto` clears it, and that the form's options are `auto,v3,v4,bitpirate,bp6` with "ESP32 Bit Pirate" among the labels. Delete the "recipe strip appeared" check.
- [ ] **Step 2: Run** `make ui-test`. Expected: the header checks FAIL.
- [ ] **Step 3: Implement** the removals. The `recipe` flags on actions stay in the panel modules (unused by the frontend for now; deleting them is the docs/panels step's job).
- [ ] **Step 4: Run** `make ui-test`, the full suite and the Python 3.8 command from Global Constraints. Expected: all pass.
- [ ] **Step 5: Commit** "The top bar shows status only".

---

### Task 5: Check on the real board and open the PR

- [ ] Restart the dashboard (`.venv/bin/python -m buspirate dashboard --no-browser`) and connect the real Bit Pirate. Check that the top bar has no buttons, that Guide turns the column into contents with the wiki listed, that the I2C panel's guide link opens the wiki's I2C Mode page, that Back returns to I2C, that the Traffic panel reads `I2C> scan`, and that no "null" appears. Take a screenshot for the PR.
- [ ] Commit this plan, push `one-way-around`, and open a PR against `board-registry` titled "One way around: the left column is the only navigation".
