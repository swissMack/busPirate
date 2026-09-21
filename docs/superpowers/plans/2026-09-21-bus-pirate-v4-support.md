# Bus Pirate v4 Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the dashboard show the right board, the right pinout and the right LED behaviour for a Bus Pirate v4, with a manual override over the auto-detected variant.

**Architecture:** `wiring.py`'s single `BOARD_V3` constant becomes a `BOARDS` registry keyed by variant, and a parallel `LED_RULES` registry captures per-variant LED semantics. The session gains a `display_variant` override that defaults to the detected variant; `/api/state` resolves board, caveat and LED data through it. `app.js` stays protocol-agnostic — it renders whatever board it is served.

**Tech Stack:** Python 3, FastAPI, pytest (`.venv/bin/python -m pytest`), vanilla ES modules, jsdom (`node tests/ui/frontend.mjs` against a running `--demo` server).

**Spec:** `docs/superpowers/specs/2026-09-21-bus-pirate-v4-support-design.md`

## Global Constraints

- The `client` fixture in `tests/test_dashboard.py` is parametrised `["v3", "v4"]`. Every dashboard test runs twice. Never assume `v3`.
- `app.js` knows nothing protocol-specific by design. Variant logic belongs server-side. The only frontend exception is the USB flash, which is driven by a served rule, not a hard-coded variant check.
- Run the frontend suite as: start `.venv/bin/python -m buspirate dashboard --demo --no-browser`, wait 5s, `node tests/ui/frontend.mjs`, then `pkill -f "buspirate dashboard"`. It disconnects the session on startup, so it is safe to re-run.
- Signal names must match the existing keys in `COLOURS` in `wiring.py` so `colour()` keeps working: use `"+3.3V"`, not `"+3v3"`.
- Nothing in this plan is verified against v4 hardware. Every v4 behavioural claim gets a checklist entry in Task 8.
- Do not commit the working tree's pre-existing LED changes as part of these tasks; commit only the files each task names.

---

### Task 1: Board registry

Pure refactor. `BOARD_V3` becomes `BOARDS["v3"]` with its caveat folded in. No behaviour change — this exists so Task 5 has somewhere to put v4.

**Files:**
- Modify: `buspirate/web/wiring.py`
- Modify: `buspirate/web/server.py`
- Test: `tests/test_dashboard.py`

**Interfaces:**
- Consumes: nothing
- Produces: `BOARDS: Dict[str, Dict[str, Any]]`, keys `"v3"`. Each value has `image`, `width`, `height`, `gutter`, `gutter_left`, `label`, `pins`, `side`, `leds`, `caveat`. `BOARD_V3` and `BOARD_CAVEAT` are gone.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_dashboard.py`:

```python
def test_the_board_registry_is_keyed_by_variant():
    from buspirate.web.wiring import BOARDS

    assert set(BOARDS) == {"v3"}
    board = BOARDS["v3"]
    assert board["label"] == "Bus Pirate v3.6"
    assert len(board["pins"]) == 10
    assert set(board["leds"]) == {"PWR", "USB", "MODE", "VREG"}
    assert "v3.6" in board["caveat"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_dashboard.py -k registry -q`
Expected: FAIL with `ImportError: cannot import name 'BOARDS'`

- [ ] **Step 3: Implement**

In `buspirate/web/wiring.py`, rename `BOARD_V3 = {` to `_BOARD_V3 = {`, move the `BOARD_CAVEAT` text into it as a `"caveat"` key, then add the registry after it:

```python
_BOARD_V3 = {
    "image": "/static/img/board-v3.png",
    # ... existing keys unchanged ...
    "caveat": (
        "This is a Bus Pirate v3.6. The v4 is laid out differently — check "
        "the silkscreen next to your own header before trusting the positions."
    ),
}

#: Board geometry by variant. The dashboard serves one of these, chosen by
#: DeviceSession.effective_variant().
BOARDS: Dict[str, Dict[str, Any]] = {"v3": _BOARD_V3}
```

Add `from typing import Any, Dict` at the top if absent. Delete the standalone `BOARD_CAVEAT`.

In `buspirate/web/server.py`, replace the `BOARD_CAVEAT, BOARD_V3,` import lines with `BOARDS,` (keeping alphabetical order), and change the state dict:

```python
            "board": BOARDS["v3"],
            "board_caveat": BOARDS["v3"]["caveat"],
```

(Task 2 makes this variant-aware. Keeping it literal here keeps this task a no-op refactor.)

- [ ] **Step 4: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS — 281 passed, 1 skipped. The existing `test_the_board_caveat_names_the_variant` must still pass unchanged.

- [ ] **Step 5: Commit**

```bash
git add buspirate/web/wiring.py buspirate/web/server.py tests/test_dashboard.py
git commit -m "refactor: make board geometry a registry keyed by variant"
```

---

### Task 2: Effective variant and the API fields

**Files:**
- Modify: `buspirate/web/session.py`
- Modify: `buspirate/web/server.py`
- Test: `tests/test_dashboard.py`

**Interfaces:**
- Consumes: `BOARDS` from Task 1
- Produces: `DeviceSession.display_variant: Optional[str]`, `DeviceSession.effective_variant() -> str`, `DeviceSession.variant_source() -> str`. `/api/state` gains `variant`, `variant_detected`, `variant_source`, `variants`.

- [ ] **Step 1: Write the failing test**

```python
def test_the_state_reports_the_detected_variant(client):
    connect(client)
    body = client.get("/api/state").json()
    assert body["variant"] == client.variant
    assert body["variant_detected"] == client.variant
    assert body["variant_source"] == "detected"
    assert body["variants"] == ["v3", "v4"]


def test_an_unconnected_dashboard_defaults_to_v3_and_says_so(client):
    body = client.get("/api/state").json()
    assert body["variant"] == "v3"
    assert body["variant_detected"] is None
    assert body["variant_source"] == "default"


def test_the_board_served_follows_the_detected_variant(client):
    connect(client)
    body = client.get("/api/state").json()
    assert body["board"]["label"].endswith(client.variant.replace("v", ""))  \
        or client.variant in body["board"]["label"].lower().replace(" ", "")
```

Replace that last assertion with the exact one once Task 5 lands v4; for now assert only the v3 case:

```python
def test_the_board_served_follows_the_detected_variant(client):
    connect(client)
    body = client.get("/api/state").json()
    if client.variant == "v3":
        assert body["board"]["label"] == "Bus Pirate v3.6"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_dashboard.py -k "variant" -q`
Expected: FAIL with `KeyError: 'variant'`

- [ ] **Step 3: Implement the session methods**

In `buspirate/web/session.py`, add to `__init__` beside `self.last_pins`:

```python
        #: Manual override of the variant the UI presents. None = follow
        #: whatever the banner said.
        self.display_variant: Optional[str] = None
```

Add these methods next to `leds()`:

```python
    def detected_variant(self) -> Optional[str]:
        """What the banner said, or None if nothing is connected."""
        if self.bp is None or not self.bp.is_open:
            return None
        variant = self.bp.profile.variant
        return variant if variant in BOARDS else None

    def effective_variant(self) -> str:
        """The variant the UI should present: override, else detected, else v3."""
        if self.display_variant is not None:
            return self.display_variant
        return self.detected_variant() or DEFAULT_VARIANT

    def variant_source(self) -> str:
        """Why effective_variant() is what it is: override, detected or default."""
        if self.display_variant is not None:
            return "override"
        if self.detected_variant() is not None:
            return "detected"
        return "default"
```

Import at the top of `session.py`: `from .wiring import BOARDS, DEFAULT_VARIANT`.

In `wiring.py`, add after `BOARDS`:

```python
#: What to present when nothing is connected, or the banner was unreadable.
DEFAULT_VARIANT = "v3"
```

- [ ] **Step 4: Implement the API fields**

In `buspirate/web/server.py`, inside the state builder, replace the two literal board lines with:

```python
    variant = session.effective_variant()
    board = BOARDS[variant]
    ...
            "board": board,
            "board_caveat": board["caveat"],
            "variant": variant,
            "variant_detected": session.detected_variant(),
            "variant_source": session.variant_source(),
            "variants": sorted(BOARDS),
```

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS. Note `variants` is `["v3"]` until Task 5 — amend the assertion in Step 1 to `["v3"]` now and back to `["v3", "v4"]` in Task 5.

- [ ] **Step 6: Commit**

```bash
git add buspirate/web/session.py buspirate/web/server.py buspirate/web/wiring.py tests/test_dashboard.py
git commit -m "feat: resolve the served board through an effective variant"
```

---

### Task 3: The switch, and clearing it on disconnect

**Files:**
- Modify: `buspirate/web/panels/connection.py`
- Modify: `buspirate/web/session.py`
- Test: `tests/test_dashboard.py`

**Interfaces:**
- Consumes: `effective_variant()`, `variant_source()` from Task 2
- Produces: a `set_variant` action on the `connection` panel taking one param `variant` of type `str`, accepting `"auto"`, `"v3"`, `"v4"`.

- [ ] **Step 1: Write the failing test**

```python
def test_overriding_the_variant_changes_what_is_served(client):
    connect(client)
    status, body = run(client, "connection", "set_variant", variant="v3")
    assert status == 200, body
    state = client.get("/api/state").json()
    assert state["variant"] == "v3"
    assert state["variant_source"] == "override"
    assert state["variant_detected"] == client.variant


def test_auto_restores_detection(client):
    connect(client)
    run(client, "connection", "set_variant", variant="v3")
    status, body = run(client, "connection", "set_variant", variant="auto")
    assert status == 200, body
    state = client.get("/api/state").json()
    assert state["variant"] == client.variant
    assert state["variant_source"] == "detected"


def test_an_unknown_variant_is_refused_in_a_sentence(client):
    connect(client)
    status, body = run(client, "connection", "set_variant", variant="v9")
    assert status == 400
    assert "v9" in body["error"]
    assert "Traceback" not in body["error"]


def test_disconnecting_clears_the_override(client):
    connect(client)
    run(client, "connection", "set_variant", variant="v3")
    run(client, "connection", "disconnect")
    connect(client)
    state = client.get("/api/state").json()
    assert state["variant_source"] == "detected"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_dashboard.py -k "variant" -q`
Expected: FAIL with `panel 'connection' has no action 'set_variant'` (404)

- [ ] **Step 3: Implement the handler**

In `buspirate/web/panels/connection.py`, add the import `from ..wiring import BOARDS, SEEED_CABLE` (extending the existing wiring import), and the handler:

```python
def _set_variant(ctx, variant):
    if variant == "auto":
        ctx.session.display_variant = None
        return text(
            "Following the connected board again.", tone="good"
        )
    if variant not in BOARDS:
        raise BusPirateError(
            f"{variant!r} is not a board this dashboard knows — "
            f"pick one of: auto, {', '.join(sorted(BOARDS))}"
        )
    ctx.session.display_variant = variant
    return text(f"Showing {BOARDS[variant]['label']}.", tone="good")
```

Import `BusPirateError` at the top: `from ...exceptions import BusPirateError`. Check the existing import style in `session.py` and match it.

Register the action in the `Panel(...)` action list, after `identify`:

```python
        Action(
            name="set_variant",
            label="Show a different board",
            help="The dashboard follows whatever is plugged in. Override this "
            "to read about the other version — the header pinout and the LED "
            "behaviour both differ.",
            params=[
                Param("variant", "str", "Board to show", default="auto"),
            ],
            handler=_set_variant,
        ),
```

- [ ] **Step 4: Clear the override on disconnect**

In `session.py`'s `disconnect_blocking()`, beside the existing `last_pins` reset:

```python
        # An override set while inspecting one board must not follow you onto
        # the next one you plug in.
        self.display_variant = None
```

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add buspirate/web/panels/connection.py buspirate/web/session.py tests/test_dashboard.py
git commit -m "feat: let the board shown be overridden, and clear it on disconnect"
```

---

### Task 4: Per-variant LED rules

**Files:**
- Modify: `buspirate/web/wiring.py`
- Modify: `buspirate/web/session.py`
- Test: `tests/test_dashboard.py`

**Interfaces:**
- Consumes: `effective_variant()` from Task 2
- Produces: `LED_RULES: Dict[str, Dict[str, Dict[str, str]]]` in `wiring.py`, and `LED_NOTES: Dict[str, str]` replacing the single `LED_NOTE`. `session.leds()` becomes variant-aware.

- [ ] **Step 1: Write the failing test**

```python
def test_the_led_rules_cover_every_led_on_every_board(client):
    from buspirate.web.wiring import BOARDS, LED_RULES

    for variant, board in BOARDS.items():
        assert set(LED_RULES[variant]) == set(board["leds"]), variant
        for name, rule in LED_RULES[variant].items():
            assert rule["driver"] in {"hardware", "firmware"}, (variant, name)
            assert rule["means"], (variant, name)


def test_the_v3_usb_led_is_traffic_driven_and_the_v4_one_is_not():
    from buspirate.web.wiring import LED_RULES

    assert LED_RULES["v3"]["USB"]["inference"] == "flash_on_traffic"
    assert LED_RULES["v4"]["USB"]["inference"] == "always_dark"


def test_the_led_note_is_per_variant(client):
    connect(client)
    note = client.get("/api/state").json()["led_note"]
    assert "cannot" in note.lower() or "no command" in note.lower()
```

The second test needs v4 in `LED_RULES`; add the v4 rules in this task even though the v4 *board* arrives in Task 5. The rules are firmware facts, independent of geometry.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_dashboard.py -k "led_rules or usb_led_is_traffic" -q`
Expected: FAIL with `ImportError: cannot import name 'LED_RULES'`

- [ ] **Step 3: Implement the rules**

In `buspirate/web/wiring.py`, replace `LED_NOTE` with:

```python
#: What drives each LED, and how the dashboard should infer its state.
#:
#: ``inference`` is one of:
#:   "powered"          — lit whenever the port is open
#:   "connected"        — lit whenever the port is open (binary mode entered)
#:   "supplies"         — follows the on-board 3.3V/5V regulators
#:   "flash_on_traffic" — a pulse the client drives from the traffic feed
#:   "always_dark"      — never reported lit
LED_RULES: Dict[str, Dict[str, Dict[str, str]]] = {
    "v3": {
        "PWR": {
            "driver": "hardware",
            "inference": "powered",
            "means": "USB power is reaching the board",
        },
        "USB": {
            "driver": "hardware",
            "inference": "flash_on_traffic",
            "means": "data arriving from the host — the FT232RL's RXLED#",
        },
        "MODE": {
            "driver": "firmware",
            "inference": "connected",
            "means": "binary mode is active — the firmware clears it on an overrun",
        },
        "VREG": {
            "driver": "hardware",
            "inference": "supplies",
            "means": "the on-board 3.3V and 5V supplies are on",
        },
    },
    "v4": {
        "PWR": {
            "driver": "hardware",
            "inference": "powered",
            "means": "USB power is reaching the board",
        },
        "USB": {
            "driver": "firmware",
            "inference": "always_dark",
            "means": "lit only while enumerating — dark once configured, "
            "which is the healthy state",
        },
        "MODE": {
            "driver": "firmware",
            "inference": "connected",
            "means": "binary mode is active — the firmware clears it on an overrun",
        },
        "VREG": {
            "driver": "hardware",
            "inference": "supplies",
            "means": "the on-board 3.3V and 5V supplies are on",
        },
    },
}

_LED_NOTE_COMMON = (
    "There is no command that reads the LEDs back, so these are inferred from "
    "what the dashboard believes it has asked the board to do, not measured. "
    "The firmware can change them on its own — an overrun turns MODE off — so "
    "trust the board over this picture."
)

LED_NOTES: Dict[str, str] = {
    "v3": _LED_NOTE_COMMON
    + " On a v3 only MODE is software-driven; USB is the FT232RL's receive "
    "indicator and flickers on traffic.",
    "v4": _LED_NOTE_COMMON
    + " On a v4 both MODE and USB are software-driven, and USB goes dark once "
    "the board has enumerated — dark is the healthy state, not a fault.",
}
```

- [ ] **Step 4: Make `leds()` consult them**

Replace the body of `DeviceSession.leds()`:

```python
    def leds(self) -> Dict[str, bool]:
        """What the indicator LEDs should be showing, for the shown variant.

        Inferred, never read: no command reports LED state. See LED_NOTES.
        """
        live = self.bp is not None and self.bp.is_open
        rules = LED_RULES[self.effective_variant()]
        state = {}
        for name, rule in rules.items():
            how = rule["inference"]
            if how == "supplies":
                state[name] = live and self._supplies_on()
            elif how in {"powered", "connected"}:
                state[name] = live
            else:  # flash_on_traffic, always_dark
                state[name] = False
        return state
```

Import `LED_RULES` in `session.py`.

- [ ] **Step 5: Serve the per-variant note**

In `server.py`, replace `"led_note": LED_NOTE,` with `"led_note": LED_NOTES[variant],` and fix the import to `LED_NOTES`.

- [ ] **Step 6: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS. The existing `test_the_usb_led_is_never_steadily_lit` and `test_connecting_lights_power_and_mode_but_not_vreg` must still pass on both variants.

- [ ] **Step 7: Commit**

```bash
git add buspirate/web/wiring.py buspirate/web/session.py buspirate/web/server.py tests/test_dashboard.py
git commit -m "feat: drive the LED model from per-variant rules"
```

---

### Task 5: The v4 board entry

**Unblocked 2026-09-21:** the photograph is committed at
`buspirate/web/static/img/board-v4.jpg`, 700x525 — the same dimensions as
`board-v3.png`, so the measurement method transfers directly. It is a `.jpg`,
not a `.png`; the served path must match.

**Files:**
- Already present: `buspirate/web/static/img/board-v4.jpg` (supplied by the repo owner)
- Modify: `buspirate/web/wiring.py`
- Test: `tests/test_dashboard.py`

**Interfaces:**
- Consumes: `BOARDS` from Task 1
- Produces: `BOARDS["v4"]`, twelve pins, four LEDs.

- [ ] **Step 1: Confirm the image is present and 700×525**

```bash
sips -g pixelWidth -g pixelHeight buspirate/web/static/img/board-v4.jpg
```
Expected: `pixelWidth: 700`, `pixelHeight: 525`. If it differs, use the real numbers for `width`/`height` and scale the measurements accordingly.

- [ ] **Step 2: Measure the LED coordinates**

Crop the top strip and enlarge it 3×, then read the LED centres off the enlarged image:

```bash
S=/tmp/bpmeasure && mkdir -p $S
sips -c 160 700 --cropOffset 60 0 buspirate/web/static/img/board-v4.jpg --out $S/leds.png
sips -z 480 2100 $S/leds.png --out $S/leds_big.png
```

Open `$S/leds_big.png`. For an LED whose centre reads at `(xb, yb)` in the enlarged crop, the coordinate for the dict is:

```
x = xb / 3
y = 60 + yb / 3        # 60 is the --cropOffset row
```

Cross-check against the silkscreen: PWR, USB, MODE and VREG sit left to right, each directly above its own label. Verify with a tight crop before trusting the numbers:

```bash
sips -c 30 360 --cropOffset 84 180 buspirate/web/static/img/board-v4.jpg --out $S/v.png
sips -z 240 2880 $S/v.png --out $S/v_big.png
```

- [ ] **Step 3: Measure the twelve header pins**

Same method, cropping the region around the `IO` header on the right of the board. The header is a 2×6: six evenly spaced rows, two columns. Measure the top-left and bottom-left pad centres, then interpolate the four rows between them rather than measuring each — even spacing is guaranteed by the 0.1" pitch.

- [ ] **Step 4: Add the registry entry**

In `wiring.py`, beside `_BOARD_V3`:

```python
_BOARD_V4 = {
    "image": "/static/img/board-v4.jpg",
    "width": 700,
    "height": 525,
    "gutter": 290,
    "gutter_left": 290,
    "label": "Bus Pirate v4.0",
    # Twelve pins: the v4 header is a 2x6, not the v3's 2x5, and it carries
    # three AUX lines. Confirmed against hardware/v4/BusPirate-v4.brd.png and
    # the firmware's own pin list in procMenu.c.
    "pins": {
        "GND": [MEASURED, MEASURED],
        "+5V": [MEASURED, MEASURED],
        "+3.3V": [MEASURED, MEASURED],
        "VPU": [MEASURED, MEASURED],
        "ADC": [MEASURED, MEASURED],
        "AUX2": [MEASURED, MEASURED],
        "AUX1": [MEASURED, MEASURED],
        "AUX": [MEASURED, MEASURED],
        "CS": [MEASURED, MEASURED],
        "MISO": [MEASURED, MEASURED],
        "CLK": [MEASURED, MEASURED],
        "MOSI": [MEASURED, MEASURED],
    },
    "leds": {
        "PWR": [MEASURED, MEASURED],
        "USB": [MEASURED, MEASURED],
        "MODE": [MEASURED, MEASURED],
        "VREG": [MEASURED, MEASURED],
    },
    "side": {
        "GND": "left", "+3.3V": "left", "ADC": "left",
        "AUX1": "left", "CS": "left", "CLK": "left",
        "+5V": "right", "VPU": "right", "AUX2": "right",
        "AUX": "right", "MISO": "right", "MOSI": "right",
    },
    "caveat": (
        "This is a Bus Pirate v4.0. Its header is a 2x6 with three AUX lines, "
        "not the v3's 2x5 — check the silkscreen next to your own header "
        "before trusting the positions."
    ),
}

BOARDS: Dict[str, Dict[str, Any]] = {"v3": _BOARD_V3, "v4": _BOARD_V4}
```

Replace every `MEASURED` with the number from Steps 2 and 3. **A remaining `MEASURED` is a bug, not a placeholder to ship.**

- [ ] **Step 5: Write the test**

```python
def test_the_v4_header_is_a_two_by_six_with_three_aux_lines():
    from buspirate.web.wiring import BOARDS

    pins = BOARDS["v4"]["pins"]
    assert len(pins) == 12
    assert {"AUX", "AUX1", "AUX2"} <= set(pins)
    rows = {}
    for signal, (x, y) in pins.items():
        rows.setdefault(y, []).append(signal)
    assert len(rows) == 6
    assert all(len(v) == 2 for v in rows.values())


def test_every_board_pin_sits_inside_its_image():
    from buspirate.web.wiring import BOARDS

    for variant, board in BOARDS.items():
        for signal, (x, y) in {**board["pins"], **board["leds"]}.items():
            assert 0 < x < board["width"], (variant, signal)
            assert 0 < y < board["height"], (variant, signal)


def test_the_v4_photo_is_served(client):
    response = client.get("/static/img/board-v4.jpg")
    assert response.status_code == 200
    assert response.content[:3] == b"\xff\xd8\xff"  # JPEG magic
```

Also update Task 2's `variants` assertion back to `["v3", "v4"]`, and add:

```python
def test_a_v4_is_served_the_v4_board(client):
    connect(client)
    label = client.get("/api/state").json()["board"]["label"]
    assert label == ("Bus Pirate v4.0" if client.variant == "v4" else "Bus Pirate v3.6")
```

- [ ] **Step 6: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add buspirate/web/wiring.py buspirate/web/static/img/board-v4.jpg tests/test_dashboard.py
git commit -m "feat: add the Bus Pirate v4 board geometry"
```

---

### Task 6: The frontend switch

**Files:**
- Modify: `buspirate/web/static/index.html`
- Modify: `buspirate/web/static/app.js`
- Modify: `buspirate/web/static/app.css`
- Test: `tests/ui/frontend.mjs`

**Interfaces:**
- Consumes: `variant`, `variant_detected`, `variant_source`, `variants` from Task 2; `led_rules` must also now be served — add `"led_rules": LED_RULES[variant],` to the state dict in `server.py` as part of this task.
- Produces: `#variant` select and `#variant-warning` badge in the DOM.

- [ ] **Step 1: Write the failing test**

In `tests/ui/frontend.mjs`, after the LED strip checks:

```js
// --- the variant switch
check("variant selector offers both boards",
  $("variant") && [...$("variant").options].map((o) => o.value).join(",") === "auto,v3,v4",
  $("variant") ? [...$("variant").options].map((o) => o.value).join(",") : "no #variant");
check("no mismatch warning while following detection", $("variant-warning").hidden);
```

And after the board diagram checks:

```js
$("variant").value = "v4";
$("variant").dispatchEvent(new window.Event("change"));
await settle(600);
check("switching to v4 redraws the diagram with the v4 board",
  $("panel").querySelector(".card-img--board image").getAttribute("href") === "/static/img/board-v4.jpg",
  $("panel").querySelector(".card-img--board image").getAttribute("href"));
check("the v4 header shows twelve pins",
  $("panel").querySelectorAll(".card-img--board circle").length === 12,
  `${$("panel").querySelectorAll(".card-img--board circle").length}`);
check("overriding onto the wrong board warns", !$("variant-warning").hidden);
$("variant").value = "auto";
$("variant").dispatchEvent(new window.Event("change"));
await settle(600);
check("returning to auto clears the warning", $("variant-warning").hidden);
```

- [ ] **Step 2: Run it to verify it fails**

```bash
pkill -f "buspirate dashboard"; sleep 1
nohup .venv/bin/python -m buspirate dashboard --demo --no-browser >/tmp/bpsrv.log 2>&1 &
sleep 5; node tests/ui/frontend.mjs; pkill -f "buspirate dashboard"
```
Expected: FAIL — "no #variant"

- [ ] **Step 3: Add the markup**

In `index.html`, inside `.statusblock` after the `#leds` div:

```html
    <div class="variantpick">
      <select id="variant" aria-label="Which board to show">
        <option value="auto">Follow the board</option>
      </select>
      <span id="variant-warning" class="variant-warning" hidden></span>
    </div>
```

- [ ] **Step 4: Render and wire it**

In `app.js`, extend the state object with `variant: "v3", variantDetected: null, variantSource: "default", variants: [], ledRules: {}`, populate them in `loadState()` from `data.variant`, `data.variant_detected`, `data.variant_source`, `data.variants`, `data.led_rules`, and add:

```js
const VARIANT_LABELS = { v3: "Bus Pirate v3", v4: "Bus Pirate v4" };

function renderVariant() {
  const select = $("variant");
  if (!select) return;
  const wanted = ["auto", ...state.variants];
  if ([...select.options].map((o) => o.value).join() !== wanted.join()) {
    select.replaceChildren(
      el("option", { value: "auto" }, "Follow the board"),
      ...state.variants.map((v) => el("option", { value: v }, VARIANT_LABELS[v] || v))
    );
  }
  select.value = state.variantSource === "override" ? state.variant : "auto";

  // Only a genuine disagreement is worth a warning: an override that matches
  // what is plugged in is harmless.
  const warning = $("variant-warning");
  const wrong =
    state.variantSource === "override" &&
    state.variantDetected &&
    state.variantDetected !== state.variant;
  warning.hidden = !wrong;
  warning.textContent = wrong
    ? `showing ${state.variant} — a ${state.variantDetected} is connected`
    : "";
}
```

Call `renderVariant()` from `renderStatus()`. Wire the change handler once, next to the other one-time setup at the bottom of the file:

```js
$("variant").addEventListener("change", async (event) => {
  await api("/api/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      panel: "connection",
      action: "set_variant",
      params: { variant: event.target.value },
    }),
  });
  await loadState();
});
```

`loadState()` calls `render()`, which re-renders the panel — so the board diagram picks up the new geometry without extra work.

- [ ] **Step 5: Make the USB flash conditional**

In `flashUsbLed()`, return early when the served rules say USB is not traffic-driven:

```js
function flashUsbLed() {
  const rule = (state.ledRules.USB || {}).inference;
  if (rule !== "flash_on_traffic") return;
  const marks = [...document.querySelectorAll('[data-led="USB"]')];
  // ... rest unchanged ...
}
```

Also drive the LED tooltips from `state.ledRules[name].means` rather than the hard-coded `LED_MEANS` map, and delete `LED_MEANS`.

- [ ] **Step 6: Style it**

In `app.css`, beside the `.leds` rules:

```css
.variantpick { display: flex; align-items: center; gap: 6px; }
.variantpick select {
  font-family: var(--mono); font-size: 11px;
  background: var(--bg-sunken); color: var(--text);
  border: 1px solid var(--line); border-radius: 3px; padding: 1px 3px;
}
.variant-warning {
  font-family: var(--mono); font-size: 10px;
  color: var(--warn); border: 1px solid var(--warn);
  border-radius: 2px; padding: 0 4px;
}
```

- [ ] **Step 7: Run both suites**

```bash
.venv/bin/python -m pytest tests/ -q
pkill -f "buspirate dashboard"; sleep 1
nohup .venv/bin/python -m buspirate dashboard --demo --no-browser >/tmp/bpsrv.log 2>&1 &
sleep 5; node tests/ui/frontend.mjs; pkill -f "buspirate dashboard"
```
Expected: both PASS

- [ ] **Step 8: Commit**

```bash
git add buspirate/web/static/ buspirate/web/server.py tests/ui/frontend.mjs
git commit -m "feat: add the board switch and warn when it disagrees with the hardware"
```

---

### Task 7: Surface the v4 AUX/CS command, and label AUX1/AUX2 honestly

`buspirate/i2c.py:251-256` implements `I2C.extended_aux()`, gated on
`CAP_EXTENDED_AUX` and backed by a real binary command (`Firmware/I2C.c:935`,
I2C subcommand `0b1001`). No panel exposes it. Meanwhile AUX1 and AUX2, the
extra v4 header pins, genuinely are unreachable over binary and must say so.

**Do NOT remove `CAP_EXTENDED_AUX`** — `i2c.py:254` and `tests/test_device.py:35`
both depend on it, and it is correctly named for what it gates.

**Files:**
- Modify: `buspirate/web/panels/i2c.py`
- Modify: `buspirate/web/wiring.py`
- Test: `tests/test_dashboard.py`

**Interfaces:**
- Consumes: `BOARDS["v4"]` from Task 5; `device_module.CAP_EXTENDED_AUX`
- Produces: an `extended_aux` action on the `i2c` panel. `SIGNAL_NOTES` gains `AUX1`, `AUX2`.

- [ ] **Step 1: Write the failing test**

```python
def test_the_aux_control_is_offered_on_v4_only(client):
    body = connect(client)
    panels = {p["id"]: p for p in body["panels"]}
    actions = {a["name"] for a in panels["i2c"]["actions"]}
    if client.variant == "v4":
        assert "extended_aux" in actions
    else:
        assert "extended_aux" not in actions


def test_driving_aux_high_on_a_v4_reports_what_it_did(client):
    if client.variant != "v4":
        pytest.skip("extended AUX is a v4 command")
    connect(client)
    status, body = run(client, "i2c", "extended_aux", pin="aux", level="high")
    assert status == 200, body
    assert "AUX" in body["result"]["text"]


def test_the_v4_aux_pins_say_they_are_terminal_only():
    from buspirate.web.wiring import SIGNAL_NOTES

    for signal in ("AUX1", "AUX2"):
        assert "terminal" in SIGNAL_NOTES[signal].lower(), signal
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_dashboard.py -k "aux" -q`
Expected: FAIL — `extended_aux` not in actions

- [ ] **Step 3: Implement the handler**

In `buspirate/web/panels/i2c.py`, read how the existing `pullup_voltage` action
is written (it is the other `CAP_`-gated action in this file) and follow it.
Add:

```python
_AUX_PINS = [{"value": "aux", "label": "AUX"}, {"value": "cs", "label": "CS"}]
_AUX_LEVELS = [
    {"value": "low", "label": "Drive low"},
    {"value": "high", "label": "Drive high"},
    {"value": "hiz", "label": "Release (HiZ)"},
    {"value": "read", "label": "Read"},
]

# Sub-command bytes from Firmware/I2C.c:935.
_AUX_SELECT = {"aux": 0x10, "cs": 0x20}
_AUX_ACTION = {"low": 0x00, "high": 0x01, "hiz": 0x02, "read": 0x03}


def _extended_aux(ctx, pin, level):
    ctx.mode.extended_aux(_AUX_SELECT[pin])
    ctx.mode.extended_aux(_AUX_ACTION[level])
    name = pin.upper()
    if level == "read":
        return text(f"{name} read back.")
    return text(f"{name} set {level}.", tone="good")
```

Register it in the i2c panel's action list:

```python
        Action(
            name="extended_aux",
            label="Drive AUX or CS",
            help="Bus Pirate v4 only. Drives the AUX or CS pin directly while "
            "in I2C mode. AUX1 and AUX2 on the v4 header are not reachable "
            "this way — they are terminal-mode only.",
            requires=device_module.CAP_EXTENDED_AUX,
            params=[
                Param("pin", "enum", "Pin", default="aux", choices=_AUX_PINS),
                Param("level", "enum", "Do what", default="high", choices=_AUX_LEVELS),
            ],
            handler=_extended_aux,
        ),
```

Confirm `device_module` and `text` are already imported in this file; add them if not.

- [ ] **Step 4: Add the signal notes**

In `wiring.py`, add to `SIGNAL_NOTES`:

```python
    "AUX1": "Second auxiliary pin, v4 only. Terminal mode only — the binary "
            "protocol has no command for it, so the dashboard cannot drive it.",
    "AUX2": "Third auxiliary pin, v4 only. Terminal mode only — the binary "
            "protocol has no command for it, so the dashboard cannot drive it.",
```

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS. `tests/test_device.py:35` (`profile.has(CAP_EXTENDED_AUX)`) must still pass — the capability stays.

- [ ] **Step 6: Commit**

```bash
git add buspirate/web/panels/i2c.py buspirate/web/wiring.py tests/test_dashboard.py
git commit -m "feat: expose the v4 AUX/CS command and label AUX1/AUX2 terminal-only"
```

---

### Task 8: Documentation and the verification checklist

**Files:**
- Modify: `docs/bus-pirate-v4.md`
- Modify: `docs/pins-and-power.md`
- Modify: `docs/user-guide.md`
- Modify: `docs/troubleshooting.md`
- Modify: `buspirate/web/static/img/CREDITS.md`
- Test: `tests/test_dashboard.py`

- [ ] **Step 1: Write the failing test**

```python
def test_the_v4_guide_page_documents_the_header_and_the_leds(client):
    page = client.get("/api/docs/bus-pirate-v4").json()["markdown"]
    assert "AUX2" in page
    assert "2x6" in page or "2×6" in page
    assert "VREG" in page
```

Check the docs endpoint's real shape in `buspirate/web/docs.py` first and match it; adjust the path and key if they differ.

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/ -k v4_guide -q`
Expected: FAIL — `AUX2` not in the page

- [ ] **Step 3: Write the v4 page**

In `docs/bus-pirate-v4.md`, add a header section with the 2×6 table from the spec, and an LED table giving the v4 column from the spec's LED table — in particular that USB is firmware-driven and **dark once enumerated**, and that there is no FT232RL. State that AUX1/AUX2 are terminal-mode only.

- [ ] **Step 4: Make the LED docs per-variant**

In `docs/pins-and-power.md`, restructure `## The four LEDs` so the table has a v3 column and a v4 column rather than being v3 with a v4 footnote. Keep the existing `### MODE does not mean "in a protocol"` subsection — it is true of both.

- [ ] **Step 5: Add the v4 header diagram**

In `docs/user-guide.md`'s `## The board's header`, add a second ASCII diagram for the v4's 2×6 beside the existing v3 2×5, and say which is which.

- [ ] **Step 6: Extend the verification checklist**

Append to the `## Not yet verified against hardware` list at the end of `docs/troubleshooting.md`:

```markdown
- [ ] v4: MODE lit from the moment the dashboard connects, not from entering
      a protocol
- [ ] v4: the USB LED **dark** once enumerated — the inverse of a v3, and the
      claim most likely to be wrong
- [ ] v4: the 2x6 header order against your own silkscreen
- [ ] v4: the measured LED and pin coordinates land on the real parts
- [ ] v4: AUX2 really is inert over the binary protocol — nothing in the Pins
      panel should move it
- [ ] v3: the LED model — MODE lit from connect, USB flickering on traffic,
      VREG following the supplies
```

- [ ] **Step 7: Record the photo's provenance**

In `buspirate/web/static/img/CREDITS.md`, add a `board-v4.jpg` entry mirroring the existing `board-v3.png` one: supplied by the repository owner, licence not established, same pre-public action. Note that its pin and LED coordinates were measured from this exact file and must be re-measured if it is replaced.

- [ ] **Step 8: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add docs/ buspirate/web/static/img/CREDITS.md tests/test_dashboard.py
git commit -m "docs: document the v4 header, LEDs and what is still unverified"
```

---

## Self-review notes

- **Spec coverage:** section 1 → Task 1 + 5; section 2 → Tasks 2, 3, 4; section 3 → Tasks 2, 6; section 4 → Task 6; section 5 → Task 7; section 6 → Task 8; section 7 → tests inside each task. Verification list → Task 8 Step 6.
- **Known ordering constraint:** Task 5 needed the photo, which arrived 2026-09-21. No task is now blocked on an external input. Task 6 needs Task 5, because its jsdom checks assert the v4 image path and twelve pins.
- **Type consistency:** `effective_variant()`, `detected_variant()`, `variant_source()` and `display_variant` are named identically everywhere. `BOARDS`, `LED_RULES`, `LED_NOTES` and `DEFAULT_VARIANT` all live in `wiring.py`.
