# Board Registry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Describe each board (v3, v4, Bus Pirate 6, ESP32 Bit Pirate) once, in one module, and have every other part of the app read it from there, with no visible change.

**Architecture:** A new `buspirate/boards/` package holds a frozen `Board` dataclass and one module per board, collected in a `REGISTRY` dict keyed by variant. Capability constants move to `buspirate/capabilities.py` so boards can use them without importing `device.py`, and `device.py` re-exports them. `device.py`, `web/wiring.py`, `web/docs.py`, `web/session.py`, `web/server.py`, `cli.py` and `app.js` stop keeping their own per-variant tables and read the registry. `wiring.py` keeps its public names (`BOARDS`, `LED_RULES`, `LED_NOTES`, `BP6_HEADER`, …) as views derived from the registry, so panels and scripts are untouched.

**Tech Stack:** Python 3.8+ (dataclasses, typing), FastAPI server, vanilla JS frontend, pytest, jsdom UI checks (`make ui-test`).

**Spec:** `docs/superpowers/specs/2026-11-06-board-driven-app-design.md`, section 1 and "Order of work" step 1.

**Branch:** `board-registry`, cut from `bitpirate-guide` (PR #27), because that branch's `web/docs.py` has the per-board `MANUALS` and `BOARD_PAGE` this plan moves into the registry. The PR targets `bitpirate-guide` until #27 merges.

## Global Constraints

- **No visible change.** Every `/api/state`, `/api/panels`, `/api/docs` response is the same as before for every board, apart from one new key, `variant_labels` (Task 4).
- **Python 3.8 compatible** (CI and the release build): `typing.Dict/List/Optional/FrozenSet`, no `list[str]`, no `X | Y`, no `match`.
- **Adding a board = adding one file** in `buspirate/boards/` plus its line in `REGISTRY`. No other per-variant table may remain in `device.py`, `wiring.py`, `docs.py`, `session.py`, `cli.py` or `app.js` (driver opening in `session._open_device` and the simulators are out of scope).
- `buspirate.device.CAP_*`, `buspirate.device.BUS_PIRATE_ONLY` and `buspirate.device.capabilities_for` stay importable; panels use `device_module.CAP_*`.
- Variant strings stay exactly `"v3"`, `"v4"`, `"bp6"`, `"bitpirate"`; `"unknown"` is not a board.
- Registry order is `v3, v4, bitpirate, bp6` (the order of today's `BOARDS`, which sets the "Follow the board" drop-down and the CLI choices).

## Review Focus

1. **An unidentified board (`variant == "unknown"`)** must still get the shared fallback capabilities `BUS_PIRATE_ONLY | {CAP_PWM, CAP_ADC, CAP_FREQUENCY}` and the v3 presentation (`DEFAULT_VARIANT`), not a `KeyError`. Test in Task 2.
2. **A Bus Pirate 5** (bp6 profile, `devid` starting `"hw 5."`) must still describe itself as "Bus Pirate 5 (untested)". Test in Task 2.
3. **The guide with nothing connected** (`docs.available(None)`) must still list the official BP5/6 manual and not the Bit Pirate wiki. Test in Task 4.
4. **A display override** ("Follow the board" set to a variant) must accept exactly the registry's variants and reject anything else with the existing message. Test in Task 4.
5. **Python 3.8 import** of the new package, run under `uv run --isolated --python 3.8`. Task 5.

---

### Task 1: Pin today's behaviour, and move the capability constants

**Files:**
- Create: `buspirate/capabilities.py`
- Modify: `buspirate/device.py` (lines 19–69: the `CAP_*` constants, `BUS_PIRATE_ONLY`, `_CAPABILITY_HOME`)
- Test: `tests/test_boards.py` (new)

**Interfaces:**
- Produces: `buspirate.capabilities` with every `CAP_*` name now in `device.py`, plus `BUS_PIRATE_ONLY: FrozenSet[str]` and `CAPABILITY_HOME: Dict[str, str]`. `device.py` re-exports all of them under their current names (`_CAPABILITY_HOME` stays as an alias).

- [ ] **Step 1: Write characterization tests** in `tests/test_boards.py`, recording today's values before anything moves:

```python
from buspirate import device as d

EXPECTED_CAPS = {
    "bitpirate": frozenset(),
    "bp6": frozenset({d.CAP_SUPPLIES, d.CAP_ONEWIRE, d.CAP_SPI_MODES, d.CAP_UART_BUFFERED,
                      d.CAP_SPI_FLASH_PROGRAM, d.CAP_PSU_PROGRAMMABLE, d.CAP_PSU_READOUT}),
    "v4": d.BUS_PIRATE_ONLY | {d.CAP_PWM, d.CAP_ADC, d.CAP_FREQUENCY, d.CAP_PULLUP_VOLTAGE},
    "v3": d.BUS_PIRATE_ONLY | {d.CAP_PWM, d.CAP_ADC, d.CAP_FREQUENCY, d.CAP_SELF_TEST,
                               d.CAP_EXTENDED_AUX},
    "unknown": d.BUS_PIRATE_ONLY | {d.CAP_PWM, d.CAP_ADC, d.CAP_FREQUENCY},
}

@pytest.mark.parametrize("variant", sorted(EXPECTED_CAPS))
def test_capabilities_are_unchanged(variant):
    assert d.capabilities_for(variant) == EXPECTED_CAPS[variant]

@pytest.mark.parametrize("variant, firmware, devid, text", [
    ("v3", "v6.1", None, "Bus Pirate v3, firmware v6.1"),
    ("v4", None, None, "Bus Pirate v4"),
    ("bitpirate", "1.8", None, "ESP32 Bit Pirate, firmware 1.8"),
    ("bp6", None, "hw 6.0", "Bus Pirate 6"),
    ("bp6", None, "hw 5.1", "Bus Pirate 5 (untested)"),
    ("unknown", None, None, "unidentified Bus Pirate"),
])
def test_descriptions_are_unchanged(variant, firmware, devid, text):
    assert d.DeviceProfile(variant=variant, firmware=firmware, devid=devid).describe() == text

def test_the_constants_are_also_in_their_own_module():
    from buspirate import capabilities as c
    assert c.CAP_ONEWIRE == d.CAP_ONEWIRE and c.BUS_PIRATE_ONLY == d.BUS_PIRATE_ONLY
```

(Check `DeviceProfile`'s field names for `devid` before running; adjust the constructor call, not the expected text.)

- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_boards.py -v`. Expected: everything passes except `test_the_constants_are_also_in_their_own_module` (ModuleNotFoundError).

- [ ] **Step 3: Move** the `CAP_*` block, `BUS_PIRATE_ONLY` and `_CAPABILITY_HOME` (renamed `CAPABILITY_HOME`) into `buspirate/capabilities.py`, keeping their comments. In `device.py`, `from .capabilities import *` and alias `_CAPABILITY_HOME = CAPABILITY_HOME`. Give `capabilities.py` an `__all__`.

- [ ] **Step 4: Run** `.venv/bin/python -m pytest -q tests`. Expected: all pass (798 + the new ones).

- [ ] **Step 5: Commit** `git add buspirate/capabilities.py buspirate/device.py tests/test_boards.py && git commit -m "Pin board behaviour in tests; capability names get their own module"`

---

### Task 2: The `Board` registry, read by `device.py`

**Files:**
- Create: `buspirate/boards/__init__.py`, `buspirate/boards/v3.py`, `v4.py`, `bp6.py`, `bitpirate.py`
- Modify: `buspirate/device.py` (`capabilities_for`, `DeviceProfile.describe`)
- Test: `tests/test_boards.py`

**Interfaces:**
- Consumes: `buspirate.capabilities` (Task 1).
- Produces, in `buspirate/boards/__init__.py`:
  - `@dataclass(frozen=True) class Board` with fields `variant: str`, `name: str`, `capabilities: FrozenSet[str]`, `simulated_name: str`, `terminal_caption: str`, `guide_page: Optional[str]`, `manual: str`, and (filled in Task 3) `wiring: Dict[str, Any] = field(default_factory=dict)`, `led_rules: Dict[str, Dict[str, str]] = field(default_factory=dict)`, `led_note: str = ""`.
  - `REGISTRY: Dict[str, Board]`, in the order v3, v4, bitpirate, bp6.
  - `DEFAULT_VARIANT = "v3"`.
  - `UNKNOWN_CAPABILITIES: FrozenSet[str]` (the fallback set).
  - `def get(variant: Optional[str]) -> Board`: the registry entry, or the `DEFAULT_VARIANT` board for `None`/unknown.
  - `def capabilities_for(variant: str) -> FrozenSet[str]`: the board's set, or `UNKNOWN_CAPABILITIES`.

Values each board module sets (copied verbatim from where they live today):

| | `name` | `simulated_name` | `terminal_caption` | `guide_page` | `manual` |
|---|---|---|---|---|---|
| v3 | Bus Pirate v3 | simulated Bus Pirate v3 | The Bus Pirate's own terminal. Type a command; '?' lists them. | `None` | `official` |
| v4 | Bus Pirate v4 | simulated Bus Pirate v4 | same as v3 | `bus-pirate-v4` | `official` |
| bitpirate | ESP32 Bit Pirate | simulated ESP32 Bit Pirate | The Bit Pirate's own command line. Type a command; 'help' lists them. | `bitpirate` | `bitpirate-wiki` |
| bp6 | Bus Pirate 6 | simulated Bus Pirate 6 | The Bus Pirate 6's own terminal. Type a command; '?' lists them. If it asks 'VT100 compatible color mode?', answer n. | `bus-pirate-6` | `official` |

Capabilities: the sets in `EXPECTED_CAPS`, with the comments from today's `capabilities_for` moved alongside each.

- [ ] **Step 1: Write the failing tests** in `tests/test_boards.py`:

```python
from buspirate import boards

def test_the_registry_holds_the_four_boards_in_order():
    assert list(boards.REGISTRY) == ["v3", "v4", "bitpirate", "bp6"]
    assert all(b.variant == v for v, b in boards.REGISTRY.items())

def test_an_unknown_variant_gets_the_default_board_and_fallback_capabilities():
    assert boards.get("unknown").variant == "v3"
    assert boards.get(None).variant == "v3"
    assert boards.capabilities_for("unknown") == EXPECTED_CAPS["unknown"]

def test_device_reads_capabilities_from_the_registry(monkeypatch):
    import dataclasses
    fake = dataclasses.replace(boards.REGISTRY["v4"], capabilities=frozenset({"x"}))
    monkeypatch.setitem(boards.REGISTRY, "v4", fake)
    assert d.capabilities_for("v4") == frozenset({"x"})
```

- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_boards.py -v`. Expected: the three new tests fail with ImportError.

- [ ] **Step 3: Create the package** as specified above. `device.capabilities_for` becomes a call to `boards.capabilities_for`. `describe()` keeps its Bus Pirate 5 special case and otherwise takes `boards.REGISTRY[variant].name`, falling back to `"unidentified Bus Pirate"`. Import `boards` inside the two functions if a module-level import is circular (boards import `capabilities`, not `device`, so it should not be).

- [ ] **Step 4: Run** `.venv/bin/python -m pytest -q tests`. Expected: all pass.

- [ ] **Step 5: Commit** `git add buspirate/boards tests/test_boards.py buspirate/device.py && git commit -m "Describe each board once, in buspirate/boards"`

---

### Task 3: Wiring and LEDs move into the boards

**Files:**
- Modify: `buspirate/boards/v3.py`, `v4.py`, `bp6.py`, `bitpirate.py`; `buspirate/web/wiring.py`
- Test: `tests/test_boards.py`

**Interfaces:**
- Consumes: `Board.wiring`, `Board.led_rules`, `Board.led_note` (Task 2).
- Produces: `buspirate/web/wiring.py` keeps exporting `BOARDS: Dict[str, Dict[str, Any]]`, `LED_RULES`, `LED_NOTES`, `DEFAULT_VARIANT`, `BP6_HEADER`, `BP6_GEOMETRY`, `DOCK_HEADER`, `DOCK_GEOMETRY`, built as `{v: b.wiring for v, b in REGISTRY.items()}` and so on. Cable, refcard and note constants (`SEEED_CABLE`, `REFCARD`, `CABLE_CARD`, `CABLE_CAVEAT`, `POWER_NOTE`, `PULLUP_RAIL_NOTE`, `SIGNAL_*`, `colour`, `colour_name`) stay in `wiring.py`: they belong to the Seeed probe cable, not to one board.
- New shared helper: `buspirate/boards/_wiring.py` with `wire(signal: str, target: str, note: str = "", colour: str = "") -> Dict[str, str]`, which the Bit Pirate and BP6 modules use in place of `wiring._wire`.

- [ ] **Step 1: Write the failing test** in `tests/test_boards.py`, snapshotting today's served data first:

```python
import json

def test_wiring_is_served_from_the_boards():
    from buspirate.web import wiring
    for variant, board in boards.REGISTRY.items():
        assert wiring.BOARDS[variant] is board.wiring
        assert wiring.LED_RULES[variant] is board.led_rules
        assert wiring.LED_NOTES[variant] == board.led_note
```

Before editing anything, save a snapshot to compare against:
`.venv/bin/python -c "import json; from buspirate.web import wiring as w; json.dump({'b': w.BOARDS, 'r': w.LED_RULES, 'n': w.LED_NOTES}, open('/tmp/wiring-before.json','w'), sort_keys=True, default=str)"` (use the scratchpad directory, not `/tmp`, if one is set).

- [ ] **Step 2: Run** the test. Expected: FAIL (`board.wiring` is the empty default).

- [ ] **Step 3: Move** `_BOARD_V3`, `_BOARD_V4`, `_BOARD_BITPIRATE` (with the dock constants and `_dock_pins`), `_BOARD_BP6` (with `BP6_HEADER`, `BP6_GEOMETRY`, `_bp6_pins` and its notes), each board's `LED_RULES` entry and its `LED_NOTES` text into that board's module. `_LED_NOTE_COMMON` goes into `boards/_wiring.py`, and the v3 and v4 notes use it. `wiring.py` builds its public names from the registry.

- [ ] **Step 4: Run** the test, then re-dump the same JSON to the scratchpad as `wiring-after.json`, and `diff` the two. Expected: the test passes and the diff is empty.

- [ ] **Step 5: Run** `.venv/bin/python -m pytest -q tests && make ui-test`. Expected: all pass, "all frontend checks passed". Also `.venv/bin/python scripts/draw_bp6_board.py` still imports (it reads `wiring.BP6_HEADER`).

- [ ] **Step 6: Commit** `git add buspirate/boards buspirate/web/wiring.py tests/test_boards.py && git commit -m "Each board's wiring and LEDs live in its own module"`

---

### Task 4: The rest of the app reads the registry

**Files:**
- Modify: `buspirate/web/docs.py` (`MANUALS`, `BOARD_PAGE`), `buspirate/web/session.py` (`SIMULATED_VARIANTS`, `SIMULATED_NAMES`, the terminal-caption `if` chain near line 965), `buspirate/cli.py` (the two `choices=[...]` lists), `buspirate/web/server.py` (`/api/state`), `buspirate/web/static/app.js` (`VARIANT_LABELS`)
- Test: `tests/test_boards.py`, `tests/ui/frontend.mjs`

**Interfaces:**
- Consumes: `boards.REGISTRY`, `boards.get`, `Board.manual`, `Board.guide_page`, `Board.simulated_name`, `Board.terminal_caption`, `Board.name` (Task 2).
- Produces:
  - `docs.MANUALS: Dict[str, str]`, folder to sidebar heading (`{"official": OFFICIAL_GROUP, "bitpirate-wiki": BITPIRATE_GROUP}`). `available(variant)` lists the manual `boards.get(variant).manual` and moves `boards.get(variant).guide_page` up. `BOARD_PAGE` and the `"for"` lambdas are deleted.
  - `/api/state` gains `"variant_labels": {variant: board.name}`; `app.js` builds its drop-down labels from `state.variantLabels` and deletes `VARIANT_LABELS`. Everything else in the payload is unchanged.

- [ ] **Step 1: Write the failing tests:**

```python
def test_the_guide_follows_each_boards_manual_and_page():
    from buspirate.web import docs
    assert boards.get(None).manual == "official"           # nothing connected
    assert boards.REGISTRY["bitpirate"].manual == "bitpirate-wiki"
    assert not hasattr(docs, "BOARD_PAGE")

def test_simulators_and_terminal_captions_come_from_the_boards():
    from buspirate.web import session
    assert session.SIMULATED_VARIANTS == tuple(boards.REGISTRY)
    assert session.SIMULATED_NAMES == {v: b.simulated_name for v, b in boards.REGISTRY.items()}

def test_state_carries_the_board_names(client):   # reuse the dashboard test client fixture
    labels = client.get("/api/state").json()["variant_labels"]
    assert labels == {v: b.name for v, b in boards.REGISTRY.items()}

def test_an_override_outside_the_registry_is_refused(client):
    # Drive the Connection panel's set-variant action with "v9" and assert the
    # existing "pick one of: auto, v3, v4, bitpirate, bp6" error.
```

(Copy the `client` fixture import from `tests/test_dashboard.py`; for the override test, find the Connection panel action that calls `connection.py:65` and post to `/api/run` the same way `test_dashboard.py` does.)

In `tests/ui/frontend.mjs`, add one check that the "Follow the board" drop-down still lists "ESP32 Bit Pirate".

- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_boards.py -v`. Expected: the new tests fail (no `variant_labels`, `BOARD_PAGE` still exists).

- [ ] **Step 3: Make the changes** listed under Files. The existing `tests/test_docs_viewer.py` board tests must pass unchanged; they are the proof that the guide behaves as before.

- [ ] **Step 4: Run** `.venv/bin/python -m pytest -q tests && make ui-test`. Expected: all pass.

- [ ] **Step 5: Check** that no per-variant table is left: `grep -rnE '"(v3|v4|bp6|bitpirate)"\s*:' buspirate --include=*.py --include=*.js | grep -v "buspirate/boards/\|simulator"` prints nothing, apart from driver selection in `session._open_device` (out of scope, see Global Constraints).

- [ ] **Step 6: Commit** `git add -A buspirate tests && git commit -m "Docs, session, CLI and frontend read the board registry"`

---

### Task 5: Verify and open the PR

- [ ] **Step 1: Python 3.8:** `uv run --isolated --python 3.8 --with pytest --with-editable . python -m pytest -q tests`. Expected: no failures. Use `--isolated` (not plain `uv run`, which rebuilds `.venv`).
- [ ] **Step 2: Live check:** restart the dashboard (`.venv/bin/python -m buspirate dashboard --no-browser`), connect the real Bit Pirate, and confirm the dock picture, the I2C wiring callouts, the guide menu (wiki present) and the "Follow the board" list are as before.
- [ ] **Step 3: Commit** this plan and the spec (`docs/superpowers/plans/2026-11-06-board-registry.md`, `docs/superpowers/specs/2026-11-06-board-driven-app-design.md`), push `board-registry`, and open a PR against `bitpirate-guide` titled "One definition per board: buspirate/boards". The body lists what moved where and states "no visible change", with the test counts.
