# Bus Pirate MCP Server — Stage 1 (Core) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local stdio MCP server (`buspirate mcp`). It detects the connected board, offers only the tools that board supports, and asks before powering a target. It gives wiring as pin → colour → target pin, runs I2C/SPI/UART/1-Wire/pin jobs with the right settings for the board, and serves distilled knowledge notes.

**Architecture:** A thin front end over the existing driver, beside the dashboard. The board logic is pure Python and runs on Python 3.8: wiring, the power rules, confirmation tokens, the board session and the knowledge lookup. Tests run it against the existing simulators. Only `server.py` imports the MCP SDK (`mcp>=2.3,<3`, Python ≥3.10). It registers tools per board with `MCPServer.add_tool` / `remove_tool`, and sends `ctx.notify_tools_changed()` when the board changes.

**Tech Stack:** Python, `mcp` 2.3 (`from mcp.server.mcpserver import MCPServer, Context`), pyserial, pytest, the repo's simulators (`buspirate/simulator*.py`).

**Spec:** `docs/superpowers/specs/2026-11-09-buspirate-mcp-design.md`. This plan is **stage 1 only**. Stages 2–6 each get their own plan after this one ships: ESP, AVR, SPI flash, the remaining modes plus the terminal hatch, low-voltage PIC, and knowledge layer 2.

## Global Constraints

- Core package stays Python **3.8**-clean: `buspirate/mcp/*.py` except `server.py`, which runs on Python ≥3.10. CI runs Python 3.8 and 3.13.
- The MCP SDK is an optional extra only: `mcp = ["mcp>=2.3,<3; python_version >= '3.10'"]`. Core `dependencies` are unchanged.
- **Power is never switched on without a redeemed confirmation token**, and the token records where the voltage came from: `"owner"`, or `"measured"` and then confirmed by the owner.
- Destructive or power tools work in two steps: `*_plan` returns the plan and a token, and `*_apply(token)` executes it. Tokens are single-use and expire after **300 s**.
- Supply rules:
  - **v3/v4:** 3300 or 5000 mV only, picked by wire. Any other level is refused.
  - **BP6/BP5:** 800–5000 mV, current limit 1–500 mA, default limit **100 mA** for the MCP server (stricter than the board's 300). Above 3600 mV or a limit of 0 (none) is flagged `needs_extra_confirmation`.
  - **Bit Pirate:** the dock switch is 1800, 3300 or 5000 mV, set by the owner. Software cannot set it.
- Wire colours:
  - **v3/v4:** Seeed, via `buspirate.web.wiring.colour_name`.
  - **BP6 and Bit Pirate dock:** VOUT/VIO red, IO0 orange, IO1 yellow, IO2 green, IO3 blue, IO4 purple, IO5 brown, IO6 grey, IO7 white, GND black.
  - Every wiring step carries both the pin label and the colour.
- Results are given in real units: use `buspirate.devices` decoders, and include hex only next to a meaning.
- Every opened board is closed through `close()` (drain + HiZ / terminal reset), including on errors and on server exit.
- The repo's current branch is `webui-start`. Work on a new branch `mcp-server` cut from it.

## Review Focus

1. **Board unplugged mid-call** (`PortGoneError` / `OSError`): the tool returns "board disconnected", the session drops to the connect-only tool set, and nothing hangs. Covered by a test in Task 6 and Task 9.
2. **Power token replayed, expired, or used for a different action**: refused, and nothing switches on. Covered in Task 5 and Task 8.
3. **Owner gives a level the board cannot make** (1.8 V on a v3/v4; 6 V anywhere): refused, with the alternative named. Covered in Task 4.
4. **Two boards attached at once**: `connect()` with no port lists both and connects to neither. Covered in Task 6.
5. **A bus tool run before power was approved**: it runs with power **off** and says so in its result. It never powers the target implicitly. Covered in Task 9.

---

### Task 1: Spike — does Claude Code refresh tools on `list_changed`?

Throwaway. Nothing from it is committed.

**Files:** `/private/tmp/.../scratchpad/spike_mcp.py` only.

- [ ] **Step 1:** Write a 20-line `MCPServer("spike")` with a tool `connect(ctx: Context) -> str`. It calls `server.add_tool(hello)`, then `await ctx.notify_tools_changed()`, and returns `"ok"`. Run it with `uv run --isolated --no-project --python 3.12 --with 'mcp==2.3.0' python spike_mcp.py` (stdio).
- [ ] **Step 2:** Register it with `claude mcp add spike -- uv run --isolated --no-project --python 3.12 --with mcp==2.3.0 python <abs path>`. Start a new Claude Code session, call `connect`, then check whether `hello` is callable in the same session.
- [ ] **Step 3:** Record the result in one line in the plan's Task 8 notes.
  - **Refreshes:** Task 8 uses `notify_tools_changed`.
  - **Does not:** Task 8 still auto-connects at startup (below), and the tool result of `connect` / `disconnect` adds: "Run `/mcp` → reconnect `buspirate` to see the new tools."
- [ ] **Step 4:** `claude mcp remove spike`.

---

### Task 2: Shared simulated-board opener

**Files:**
- Modify: `buspirate/connect.py`: add `open_simulated`
- Modify: `buspirate/web/session.py:388-423`: `_open_device` calls `open_simulated`
- Test: `tests/test_connect.py`

**Interfaces:**
- Produces: `open_simulated(variant: str, on_traffic=None)`, which returns an opened `BusPirate`, `BusPirate6` or `BitPirate`. The variant is one of `"v3"`, `"v4"`, `"bp6"`, `"bitpirate"`. Any other value raises `ValueError`. Its bodies are the three branches that live in `web/session.py:_open_device` today, with the same timeouts.

- [ ] **Step 1: Failing test**
```python
@pytest.mark.parametrize("variant,expected", [("v3", "Bus Pirate v3"), ("v4", "Bus Pirate v4"),
                                              ("bp6", "Bus Pirate 6"), ("bitpirate", "ESP32 Bit Pirate")])
def test_open_simulated_identifies(variant, expected):
    bp = open_simulated(variant)
    try:
        assert bp.profile.describe().startswith(expected)
    finally:
        bp.close()

def test_open_simulated_rejects_unknown():
    with pytest.raises(ValueError):
        open_simulated("v9")
```
- [ ] **Step 2:** `.venv/bin/python -m pytest tests/test_connect.py -q`. Expected: FAIL (ImportError).
- [ ] **Step 3:** Move the simulated branches into `open_simulated`. `_open_device` keeps `simulated_variant(port)` and calls `open_simulated(variant, on_traffic=self._on_traffic)`.
- [ ] **Step 4:** `.venv/bin/python -m pytest tests/ -q`. Expected: all pass, including the existing dashboard tests.
- [ ] **Step 5:** `git switch -c mcp-server`, then commit: `connect: open_simulated, shared by the dashboard and the coming MCP server`.

---

### Task 3: Wiring steps with colours

**Files:**
- Modify: `buspirate/boards/bp6.py`: add `BP6_CABLE: Dict[str, str]` (pin label → colour name), from the Global Constraints colour list.
- Create: `buspirate/mcp/__init__.py` (docstring only), `buspirate/mcp/wiring.py`
- Test: `tests/test_mcp_wiring.py`

**Interfaces:**
- Consumes: `boards.get(variant).wiring["panels"][job]["wiring"]` (rows as dicts `signal/colour/target/note`) for bp6 and bitpirate. `buspirate.web.panels.<job>.PANEL.wiring` (`List[Wire]`) is the default for v3/v4. `buspirate.web.wiring.colour_name(signal)`. `boards.bitpirate.DOCK_HEADER` (index i ↔ BP6 `BP6_HEADER[i]`).
- Produces:
  - `JOBS = ("i2c", "spi", "uart", "onewire", "rawwire", "pins")`
  - `@dataclass(frozen=True) class WiringStep: pin: str; colour: str; target: str; note: str` with `to_dict() -> dict`
  - `wiring_steps(variant: str, job: str) -> List[WiringStep]`. Raises `KeyError` for a job the board has no wiring for.
  - `cable_colour(variant: str, pin: str) -> str`. On the Bit Pirate, `pin` is a dock label (`"IO15"`, `"VIO"`, `"GND"`), coloured by its position in `DOCK_HEADER`, mapped onto the BP6 colour of the same position.

- [ ] **Step 1: Failing tests**
```python
def test_v3_i2c_uses_seeed_colours():
    steps = {s.pin: s for s in wiring_steps("v3", "i2c")}
    assert steps["CLK"].colour == "purple" and steps["CLK"].target == "SCL"
    assert steps["MOSI"].colour == "grey" and steps["GND"].colour == "brown"

def test_bp6_spi_uses_shrink_colours():
    steps = {s.pin: s for s in wiring_steps("bp6", "spi")}
    assert steps["IO4"].colour == "purple" and "MISO" in steps["IO4"].target
    assert steps["IO6"].colour == "grey" and steps["GND"].colour == "black"
    assert steps["VOUT"].colour == "red"

def test_bitpirate_dock_follows_bp6_positions():
    steps = {s.pin: s for s in wiring_steps("bitpirate", "i2c")}
    assert steps["IO15"].colour == "orange"   # dock position 1 == BP6 IO0
    assert steps["IO16"].colour == "yellow"

def test_every_step_has_pin_and_colour():
    for variant in ("v3", "v4", "bp6", "bitpirate"):
        for step in wiring_steps(variant, "i2c"):
            assert step.pin and step.colour, (variant, step)

def test_unknown_job_raises():
    with pytest.raises(KeyError):
        wiring_steps("bitpirate", "rawwire")
```
- [ ] **Step 2:** `.venv/bin/python -m pytest tests/test_mcp_wiring.py -q`. Expected: FAIL (ImportError).
- [ ] **Step 3:** Implement. A board override wins over the panel default, the same way `web/server.py:95-108` merges them. **The panel default (v3/v4 Seeed rows) is used only for boards whose `wiring` does not have `"cable": False`.** The BP6 and the Bit Pirate have `"cable": False`, so a job they have no override for raises `KeyError` rather than returning v3 pins. Steps with an empty colour after lookup fall back to the pin label repeated (no blank colours). The BP6 `BP6_CABLE` keys are exactly `BP6_HEADER`.
- [ ] **Step 4:** Run the tests. Expected: PASS. Also run `uv run --isolated --python 3.8 --with-editable '.[dev]' python -m pytest tests/test_mcp_wiring.py -q`. Expected: PASS.
- [ ] **Step 5:** Commit: `mcp: wiring steps with each board's own cable colours`.

---

### Task 4: Power rules

**Files:**
- Create: `buspirate/mcp/power.py`
- Test: `tests/test_mcp_power.py`

**Interfaces:**
- Produces:
  - `VoltageSource = Literal` values `"owner"` / `"measured"`, as plain str constants `SOURCE_OWNER`, `SOURCE_MEASURED` (Python 3.8: no `Literal` import needed).
  - `@dataclass(frozen=True) class PowerPlan` with fields:
    - `variant: str; millivolts: int; milliamps: Optional[int]; pullups: bool; source: str`
    - `instructions: List[str]` (what the owner must do by hand: which wire, or which dock switch position)
    - `needs_extra_confirmation: bool`
    - `to_dict() -> dict`
  - `class PowerRefused(ValueError)`. Its message always names an alternative.
  - `plan_power(variant: str, millivolts: int, source: str, pullups: bool = True, milliamps: Optional[int] = None) -> PowerPlan`
  - `@dataclass(frozen=True) class Measurement: pins_mv: Dict[str, int]; note: str` with `to_dict()`
  - `measure(bp) -> Measurement`
    - **BP6:** `bp.status().adc_mv` zipped with `status().pin_labels`.
    - **v3/v4:** `{"ADC": round(bp.read_voltage() * 1000)}`, with the note "probe the target's rail with the ADC wire (yellow)".
    - **Bit Pirate:** `{}`, with the note "cannot measure; read the part number or use a meter".
  - `suggest_level(m: Measurement) -> Optional[int]`: the nearest of 1800/3300/5000 to the highest pin reading at or above 1000 mV. `None` when everything is below 1000 mV (unpowered target).

- [ ] **Step 1: Failing tests**
```python
def test_v3_refuses_1v8_and_names_alternative():
    with pytest.raises(PowerRefused, match="Bus Pirate 6|own supply"):
        plan_power("v3", 1800, SOURCE_OWNER)

def test_v4_3v3_tells_which_wire():
    plan = plan_power("v4", 3300, SOURCE_OWNER)
    assert any("red" in line and "+3.3V" in line for line in plan.instructions)
    assert any("not" in line.lower() and "+5V" in line for line in plan.instructions)

def test_bp6_default_limit_and_extra_confirmation():
    assert plan_power("bp6", 3300, SOURCE_OWNER).milliamps == 100
    assert plan_power("bp6", 5000, SOURCE_OWNER).needs_extra_confirmation
    assert plan_power("bp6", 3300, SOURCE_OWNER, milliamps=0).needs_extra_confirmation

@pytest.mark.parametrize("mv", [700, 5100, 6000])
def test_bp6_out_of_range_refused(mv):
    with pytest.raises(PowerRefused):
        plan_power("bp6", mv, SOURCE_OWNER)

def test_bitpirate_names_dock_switch():
    plan = plan_power("bitpirate", 3300, SOURCE_OWNER)
    assert any("3V3" in line and "switch" in line for line in plan.instructions)

def test_bad_source_refused():
    with pytest.raises(ValueError):
        plan_power("bp6", 3300, "guessed")

def test_measure_bp6_and_suggest():
    bp = open_simulated("bp6")
    try:
        m = measure(bp)
        assert m.pins_mv and all(isinstance(v, int) for v in m.pins_mv.values())
        assert suggest_level(m) == 3300          # the simulator reports 3300 mV on every IO
    finally:
        bp.close()

def test_suggest_none_when_unpowered():
    assert suggest_level(Measurement({"IO0": 12, "IO1": 0}, "")) is None
```
- [ ] **Step 2:** Run. Expected: FAIL (ImportError).
- [ ] **Step 3:** Implement against the Global Constraints values. The v3/v4 instructions use `colour_name("+3.3V")` / `colour_name("+5V")`. The v4's VPU line, when `pullups=True`, says the v4 can feed VPU in software (`set_pullup_voltage`). The v3 line says "wire VPU (green) to the target's VCC".
- [ ] **Step 4:** Run the tests, plus the 3.8 run as in Task 3. Expected: PASS.
- [ ] **Step 5:** Commit: `mcp: power rules — ask, never guess, per board`.

---

### Task 5: One-time confirmation tokens

**Files:**
- Create: `buspirate/mcp/confirm.py`
- Test: `tests/test_mcp_confirm.py`

**Interfaces:**
- Produces:
  - `class ConfirmError(ValueError)`
  - `class ConfirmStore` with:
    - `__init__(ttl: float = 300.0, clock=time.monotonic)`
    - `issue(action: str, payload: Any) -> str` (token: `secrets.token_hex(8)`)
    - `redeem(token: str, action: str) -> Any`. Raises `ConfirmError` for an unknown, expired, already-used or wrong-action token. The token is consumed even when the action is wrong.

- [ ] **Step 1: Failing tests**
```python
def test_redeem_once():
    s = ConfirmStore(); t = s.issue("power", {"mv": 3300})
    assert s.redeem(t, "power") == {"mv": 3300}
    with pytest.raises(ConfirmError): s.redeem(t, "power")

def test_wrong_action_consumes():
    s = ConfirmStore(); t = s.issue("power", 1)
    with pytest.raises(ConfirmError): s.redeem(t, "erase")
    with pytest.raises(ConfirmError): s.redeem(t, "power")

def test_expiry():
    now = [0.0]; s = ConfirmStore(ttl=300, clock=lambda: now[0]); t = s.issue("power", 1)
    now[0] = 301
    with pytest.raises(ConfirmError, match="expired"): s.redeem(t, "power")
```
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Commit: `mcp: single-use confirmation tokens`.

---

### Task 6: Board session

**Files:**
- Create: `buspirate/mcp/session.py`
- Test: `tests/test_mcp_session.py`

**Interfaces:**
- Consumes: `ports.discover()`, `ports.resolve`, `ports.usb_id_for`, `connect.open_device`, `connect.open_simulated` (Task 2), `boards.get(variant)`, `power.PowerPlan` (Task 4).
- Produces: `class NotConnected(RuntimeError)`, `class BoardGone(RuntimeError)`, and `class BoardSession` with:
  - `__init__(opener: Optional[Callable[[str], Any]] = None, discover=ports.discover, simulated: Optional[str] = None)`. When `simulated` is set (a variant), `candidates()` returns `["simulated-<variant>"]` and opening uses `open_simulated`.
  - `candidates() -> List[str]`: likely Bus Pirate ports (`PortCandidate.likely_bus_pirate()`).
  - `connect(port: Optional[str] = None) -> dict`:
    - With `port=None` and exactly one candidate, it opens that one.
    - With zero candidates it raises `NotConnected("no board found…")`.
    - With two or more it returns `{"connected": False, "choose_from": [...]}` and opens nothing.
    - On success it returns `{"connected": True, "port", "board": profile.describe(), "variant", "capabilities": sorted}`.
  - `disconnect() -> None`: closes the board, forgets `power`, and is idempotent.
  - `board`: the open device, or `None`.
  - `variant -> Optional[str]`
  - `capabilities -> FrozenSet[str]`: the profile's capabilities, empty when disconnected.
  - `power: Optional[PowerPlan]`: the approved plan, if any.
  - `run(fn: Callable[[Any], T]) -> T`. It holds a `threading.Lock` and raises `NotConnected` when there is no board. `PortGoneError` or `OSError` makes it close quietly, set `board=None`, and raise `BoardGone("board disconnected")`.
  - `peripherals() -> Dict[str, bool]`: `{"power": self.power is not None, "pullups": bool(self.power and self.power.pullups)}`. Bus tools pass these to `mode.configure_peripherals(**...)`.

- [ ] **Step 1: Failing tests**
```python
def test_connect_single_simulated():
    s = BoardSession(simulated="bp6")
    info = s.connect()
    assert info["connected"] and info["variant"] == "bp6"
    assert "psu_programmable" in info["capabilities"]
    s.disconnect(); s.disconnect()          # idempotent
    assert s.board is None and s.capabilities == frozenset()

def test_two_boards_asks():
    s = BoardSession(discover=lambda include_unlikely=False: [_cand("/dev/a"), _cand("/dev/b")])
    assert s.connect() == {"connected": False, "choose_from": ["/dev/a", "/dev/b"]}
    assert s.board is None

def test_no_board():
    with pytest.raises(NotConnected):
        BoardSession(discover=lambda include_unlikely=False: []).connect()

def test_port_gone_drops_board():
    s = BoardSession(simulated="v3"); s.connect()
    def boom(bp): raise PortGoneError("gone")
    with pytest.raises(BoardGone):
        s.run(boom)
    assert s.board is None

def test_peripherals_off_until_power_approved():
    s = BoardSession(simulated="v3"); s.connect()
    assert s.peripherals() == {"power": False, "pullups": False}
    s.disconnect()
```
  (`_cand(port)` is a test helper: a stub with `.device = port` and `likely_bus_pirate() -> True`.)
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement. Real ports open with `open_device(resolve(port), usb_id=usb_id_for(port))`. A `Resource busy` `OSError` on open becomes `NotConnected("<port> is held by another program — close the dashboard or terminal using it")`.
- [ ] **Step 4:** Run, plus the 3.8 run. Expected: PASS.
- [ ] **Step 5:** Commit: `mcp: board session — one board, opened on request, dropped when unplugged`.

---

### Task 7: Knowledge notes and lookup (layer 1)

**Files:**
- Create: `buspirate/mcp/knowledge.py`, and `buspirate/mcp/notes/*.md` (one per topic, listed below)
- Modify: `pyproject.toml`: packages gain `buspirate.mcp`; package-data `"buspirate.mcp" = ["notes/*.md"]`
- Test: `tests/test_mcp_knowledge.py`

**Notes to write.** Each one is under 150 lines, built from the spec's research and the repo docs, and ends with a `Sources:` list of URLs or repo paths:
- `boards.md`: the spec's constraints table, plus the hardware traps from `docs/troubleshooting.md` and `docs/bus-pirate-6.md`.
- `power.md`: how to choose a target voltage, 5 V tolerance per board, the 150 mA limit of the v3/v4, and "unknown → measure".
- `wiring.md`: the colour schemes, crossing TX/RX, WP/HOLD high, VPU, and shared GND.
- `i2c.md`, `spi.md`, `uart.md`, `onewire.md`: condensed from `docs/<bus>.md` and the symptom table.
- `esp.md`: strapping pins per chip, `--before no-reset`, fixed 115200, and esptool errors with their causes. Written now so knowledge is ready before stage 2.
- `avr.md`: avrdude `-c buspirate` / `buspirate_bb` options, wiring, firmware notes, and the BP6 binmode 5 replug.
- `pic.md`: low-voltage parts only, PiratePICprog, wiring, and that the v3/v4 is the only route.
- `errors.md`: every error message seen in the research, mapped to its cause and fix.

**Interfaces:**
- Produces:
  - `topics() -> List[Dict[str, str]]`: `[{"topic", "title"}]` (the title is the note's first `# ` line).
  - `read(topic: str) -> str`. Raises `KeyError` with the list of valid topics.
  - `search(query: str, limit: int = 8) -> List[Dict[str, str]]`: `[{"source", "heading", "excerpt"}]`. It searches the notes **and** the bundled `docs/*.md`, `docs/official/**/*.md` and `docs/bitpirate-wiki/*.md`. A section scores higher the more query words it contains, and notes rank first on equal scores. `docs/` is located relative to the package. When it is absent (an installed wheel), only the notes are searched.

- [ ] **Step 1: Failing tests**
```python
def test_topics_listed():
    names = {t["topic"] for t in topics()}
    assert {"boards", "power", "wiring", "i2c", "spi", "uart", "onewire", "esp", "avr", "pic", "errors"} <= names

def test_every_note_cites_sources():
    for t in topics():
        assert "Sources:" in read(t["topic"]), t

def test_search_finds_strapping_pin():
    hits = search("ESP32-C3 GPIO9 download mode")
    assert hits and hits[0]["source"] == "notes/esp.md"

def test_search_reaches_bundled_manual():
    assert any(h["source"].startswith("docs/official/") for h in search("binmode legacy flashrom"))

def test_unknown_topic():
    with pytest.raises(KeyError, match="boards"):
        read("nope")
```
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Write the notes, then implement `knowledge.py` (split the text on `## ` headings).
- [ ] **Step 4:** Run, plus the 3.8 run. Expected: PASS.
- [ ] **Step 5:** Commit: `mcp: distilled knowledge notes and search over the bundled manuals`.

---

### Task 8: MCP server — lifecycle, gating, power, wiring, knowledge

**Files:**
- Create: `buspirate/mcp/server.py` (the only module importing `mcp`)
- Test: `tests/test_mcp_server.py`, starting with `pytest.importorskip("mcp")`

**Interfaces:**
- Consumes: Tasks 3–7.
- Produces:
  - `build_server(session: BoardSession) -> MCPServer`. Its `instructions` string tells Claude:
    - read `boards` first;
    - always call `wiring` and give the owner every step before any bus tool;
    - before `power_plan`, ask the owner whether they know the target voltage, and if not, call `measure_voltages` and then suggest a level;
    - never call `power_apply` until the owner has said yes to the plan shown;
    - when `needs_extra_confirmation` is true, ask a second time, naming the voltage and limit.
  - `ALWAYS = ("find_boards", "connect", "knowledge_topics", "knowledge_read", "knowledge_search")`
  - `BOARD_TOOLS: Dict[str, Tuple[FrozenSet[str], ...]]` maps each tool name to alternative capability sets. The tool is listed when **any** set is a subset of the board's capabilities, and `(frozenset(),)` means any connected board. `measure_voltages` is `(frozenset({"adc"}), frozenset({"psu_current_readout"}))`, so it is absent on the Bit Pirate. Task 8 adds `disconnect`, `board_status`, `wiring`, `measure_voltages`, `power_plan`, `power_apply`, `power_off`, `hiz`. Task 9 adds the bus tools.
  - `apply_gating(server, session) -> List[str]`: adds or removes tools so that the listed tools are `ALWAYS` plus every `BOARD_TOOLS` entry with a satisfied alternative. Board tools are listed only while connected. Returns the names now listed.
  - Tools, each returning a JSON-able dict:
    - `find_boards()`: returns `{"ports": candidates}`.
    - `connect(port: Optional[str] = None)`: calls `session.connect`, then `apply_gating`, then `await ctx.notify_tools_changed()`.
    - `disconnect()`: same lifecycle in reverse.
    - `board_status()`: board, variant, capabilities, approved power, and the BP6 `status()` fields when on a BP6.
    - `wiring(job: str)`: `{"job", "steps": [WiringStep.to_dict()], "notes"}`. The notes come from the board's panel notes.
    - `measure_voltages()`: `Measurement.to_dict()` plus `"suggested_mv"`.
    - `power_plan(millivolts: int, voltage_source: str, pullups: bool = True, milliamps: Optional[int] = None)`: returns `PowerPlan.to_dict()` plus `"token"`, or `{"refused": str(e)}` on `PowerRefused`.
    - `power_apply(token: str)`: redeems the token, then:
      - **BP6:** `bp.set_power(True, mv, ma)` and `set_pullups(pullups)`; the result includes the measured `psu_mv` and `psu_ma`.
      - **v3/v4:** `bp.set_pins(power=True, pullups=pullups)`.
      - **Bit Pirate:** records the approval only.

      In every case it stores `session.power = plan`.
    - `power_off()`: BP6 `set_power(False)`, v3/v4 `set_pins()`. Sets `session.power = None`.
    - `hiz()`: `bp.hiz()` where it exists, else `power_off()`.
    - `knowledge_topics()`, `knowledge_read(topic)`, `knowledge_search(query)`.
  - `run_stdio(simulated: Optional[str] = None) -> None`: builds the session. It **auto-connects at startup when exactly one candidate exists**, so the first tool list is already gated. It then runs `server.run("stdio")` and disconnects in a `finally`.
  - Every tool catches `BoardGone`: it calls `apply_gating`, notifies, and returns `{"error": "board disconnected — plug it back in and call connect"}`. `NotConnected` returns `{"error": str(e)}`.

- [ ] **Step 1: Failing tests** (use `asyncio.run(server.call_tool(name, args))`, `asyncio.run(server.list_tools())`, and read `result.content[0].text` as JSON)
```python
def test_disconnected_lists_only_always():
    server = build_server(BoardSession(simulated="v3"))
    assert names(server) == set(ALWAYS)

@pytest.mark.parametrize("variant", ["v3", "v4", "bp6", "bitpirate"])
def test_connect_lists_board_tools(variant):
    server = build_server(BoardSession(simulated=variant)); call(server, "connect")
    assert {"disconnect", "board_status", "wiring", "power_plan", "power_apply", "hiz"} <= names(server)
    assert ("measure_voltages" in names(server)) == (variant != "bitpirate")

def test_power_plan_then_apply_bp6():
    session = BoardSession(simulated="bp6"); server = build_server(session); call(server, "connect")
    plan = call(server, "power_plan", {"millivolts": 3300, "voltage_source": "owner"})
    assert plan["milliamps"] == 100 and plan["token"]
    applied = call(server, "power_apply", {"token": plan["token"]})
    assert applied["psu_enabled"] is True
    assert "error" in call(server, "power_apply", {"token": plan["token"]})      # replay refused

def test_power_apply_rejects_garbage_token():
    server = build_server(BoardSession(simulated="v4")); call(server, "connect")
    assert "error" in call(server, "power_apply", {"token": "deadbeef"})

def test_refused_level_reported_not_raised():
    server = build_server(BoardSession(simulated="v3")); call(server, "connect")
    assert "refused" in call(server, "power_plan", {"millivolts": 1800, "voltage_source": "owner"})

def test_disconnect_returns_to_always():
    server = build_server(BoardSession(simulated="v3")); call(server, "connect"); call(server, "disconnect")
    assert names(server) == set(ALWAYS)
```
- [ ] **Step 2:** `uv run --isolated --python 3.13 --with-editable '.[dev,mcp]' python -m pytest tests/test_mcp_server.py -q`. Expected: FAIL (ImportError).
- [ ] **Step 3:** Implement. Register each tool function with `server.add_tool(fn, name=…, description=…)`. Descriptions say *when* to use the tool, and the power ones repeat the ask-first rule.
- [ ] **Step 4:** Run the same command. Expected: PASS. Also run `.venv/bin/python -m pytest tests/ -q` (Python 3.9, no mcp). Expected: the server tests are **skipped** and nothing else fails.
- [ ] **Step 5:** Commit: `mcp: server with board-gated tools, two-step power, wiring and knowledge`.

---

### Task 9: Bus tools — I2C, SPI, UART, 1-Wire, pins

**Files:**
- Create: `buspirate/mcp/jobs.py` (pure, Python 3.8: the work each tool does, taking `session`)
- Modify: `buspirate/mcp/server.py`: register the tools and add them to `BOARD_TOOLS`
- Test: `tests/test_mcp_jobs.py` (Python 3.8, against the simulators), and `tests/test_mcp_server.py` (gating)

**Interfaces:**
- Consumes: `session.run`, `session.peripherals()`, `buspirate.devices` (`i2c_label`, `read_i2c`, `explain_i2c_register`, `read_onewire`, `onewire_label`, `spi_sensor`, `spi_sensors`), `SPIFlash.jedec_id/capacity`, `bp.profile.i2c_speeds` / `spi_speeds`.
- Produces: functions in `jobs.py`. Each opens its mode with `with bp.<mode>() as m: m.configure_peripherals(**session.peripherals())`, and each result carries `"power": session.peripherals()["power"]` plus, when power is off, the line `"note": "target not powered by the Bus Pirate — it needs its own supply, or approve power first"`.

| Function → tool | Needs capability | Returns |
|---|---|---|
| `i2c_scan(session, speed_khz=100)` | — | `{"devices": [{"address": "0x76", "address_8bit": "0xEC/0xED", "label", "reading": {...} or None}]}`. The speed is the highest available ≤ requested, from `profile.i2c_speeds`. The reading comes from `read_i2c`. |
| `i2c_read(session, address, register, count=1)` | — | `{"hex", "meaning"}` via `explain_i2c_register` |
| `i2c_sensor(session, address)` | — | the decoded `Reading` as `{"device", "values": meaning}`, or `{"error": "no decoder for 0x.."}` |
| `spi_identify(session, mode=0, speed_khz=1000)` | — | `{"jedec": "ef 40 18", "manufacturer_device" (from SPIFlash), "capacity_bytes", "warning"}`. The warning is set when the ID is all `ff` or all `00`: "MISO not connected or WP/HOLD not tied high — the chip is not blank". |
| `spi_transfer(session, write_hex, read_count, mode=0, speed_khz=1000)` | `spi_modes` when `mode != 0` | `{"read_hex"}` |
| `spi_sensor_read(session, name)` | — | decoded reading; the error lists `spi_sensors()` names |
| `uart_send(session, text, baud=115200)` / `uart_listen(session, seconds=2.0, baud=115200)` | — | `{"sent"}` / `{"text", "hex"}` |
| `onewire_scan(session)` | `onewire` | `{"devices": [{"rom", "label", "reading"}]}` |
| `pins_read_voltage(session)` | `adc` | `{"ADC_mv"}` |
| `pwm(session, frequency_hz, duty)` / `pwm_off(session)` | `pwm` | `{"frequency_hz", "duty"}` |
| `frequency(session)` | `frequency_count` | `{"hz"}` |

Board-specific settings are chosen inside these functions: speed indices from the profile; the Bit Pirate dock pins come from its driver, so nothing extra is needed. Validate `address` (0x08–0x77), and refuse 8-bit-looking input above 0x77 with: "that looks like an 8-bit address — use 0x{addr>>1:02X}".

- [ ] **Step 1: Failing tests** (parametrised over `open_simulated` variants where the job exists)
```python
@pytest.mark.parametrize("variant", ["v3", "v4", "bp6", "bitpirate"])
def test_i2c_scan_labels_devices(variant):
    s = connected(variant)
    result = i2c_scan(s)
    assert result["devices"] and all(d["label"] for d in result["devices"])
    assert result["power"] is False and "note" in result

def test_eight_bit_address_refused():
    with pytest.raises(ValueError, match="0x50"):
        i2c_read(connected("v3"), 0xA0, 0, 1)

def test_spi_identify_bp6_has_capacity():
    assert spi_identify(connected("bp6"))["capacity_bytes"] == 16777216

def test_spi_identify_warns_on_ff(monkeypatch):
    ...  # simulator returning ff ff ff → result["warning"] mentions "not blank"

def test_power_reasserted_after_apply():
    s = connected("v3"); s.power = plan_power("v3", 3300, SOURCE_OWNER)
    assert i2c_scan(s)["power"] is True

def test_unplug_mid_scan_raises_boardgone():
    ...  # make the fake serial raise OSError on read → BoardGone, s.board is None
```
  And in `test_mcp_server.py`: `onewire_scan` is listed on v3/v4/bp6 but not on bitpirate; `pwm` is listed on v3/v4 only; `spi_transfer` with `mode=2` on bitpirate returns an error.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement `jobs.py`, then register thin async wrappers in `server.py` that call `session.run(lambda bp: jobs.x(session, …))` via `anyio.to_thread.run_sync`, so serial I/O never blocks the event loop.
- [ ] **Step 4:** Run the Python 3.8 run for `test_mcp_jobs.py`, and the 3.13 `.[dev,mcp]` run for everything. Expected: PASS.
- [ ] **Step 5:** Commit: `mcp: I2C, SPI, UART, 1-Wire and pin tools, settings chosen per board`.

---

### Task 10: CLI, packaging, CI, docs

**Files:**
- Modify: `buspirate/cli.py`: subcommand `mcp [--demo] [--variant v3|v4|bitpirate|bp6]`
- Modify: `pyproject.toml`: extra `mcp`, the `buspirate.mcp` package (done in Task 7); keep `requires-python = ">=3.8"`
- Modify: `Makefile`: target `mcp-demo` (`uv run --isolated --python 3.13 --with-editable '.[mcp]' python -m buspirate mcp --demo --variant $(VARIANT)`)
- Modify: `.github/workflows/tests.yml`: the 3.13 job installs `'.[dev,mcp]'`
- Create: `docs/mcp.md`: setup (`claude mcp add buspirate -- <venv python> -m buspirate mcp`), what each tool does, the power flow, and the stage roadmap
- Modify: `README.md` documentation table (a row for MCP server); `docs/troubleshooting.md` (a hardware checklist "MCP server, stage 1" covering connect, the gated tool list, power plan/apply on the BP6, a v4 3.3 V wire instruction, an I2C scan with labels, unplug mid-scan)
- Modify: `~/.claude/skills/buspirate/SKILL.md`: one line under Overview, "If the `buspirate` MCP tools are available, use them instead of scripting the driver"
- Test: `tests/test_mcp_cli.py`, `tests/test_packaging.py`

**Interfaces:**
- `cmd_mcp(args) -> int`: imports `buspirate.mcp.server` lazily. On `ImportError`, or Python < 3.10, it prints `the MCP server needs Python 3.10+ and: pip install 'buspirate[mcp]'` to stderr and returns 2.

- [ ] **Step 1: Failing tests**
```python
def test_mcp_subcommand_parses():
    args = build_parser().parse_args(["mcp", "--demo", "--variant", "bp6"])
    assert args.demo and args.variant == "bp6"

def test_mcp_without_sdk_explains(monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "buspirate.mcp.server", None)
    assert main(["mcp", "--demo"]) == 2
    assert "buspirate[mcp]" in capsys.readouterr().err

def test_notes_ship_in_package():   # in test_packaging.py
    ...  # the built wheel contains buspirate/mcp/notes/esp.md
```
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement, then write the docs.
- [ ] **Step 4:**
  - Run `.venv/bin/python -m pytest tests/ -q` (3.9) and the 3.8 and 3.13 runs. Expected: all pass, with the server tests skipped only where `mcp` is missing.
  - Then `make mcp-demo VARIANT=bp6` with `claude mcp add buspirate-demo -- …`. Call `connect`, `wiring i2c`, `power_plan 3300 owner`, `power_apply`, and `i2c_scan`. Expected: a BMP280 at 0x76 with readings in °C/hPa, and power reported true.
- [ ] **Step 5:** Commit: `mcp: buspirate mcp command, docs, CI with the mcp extra`.

---

## Self-review notes

- **Spec coverage, stage 1:**
  - board-driven gating: Task 8
  - intent → settings: Task 9
  - power ask/measure/suggest: Tasks 4 and 8
  - wiring with colours: Task 3
  - knowledge layer 1, plus search over the already-bundled manuals: Task 7
  - real units: Task 9
  - clean close / BP6 traps: Tasks 6 and 8, through the driver's `close()`
  - optional extra / Python 3.8: Tasks 8 and 10
  - lifecycle and the multiple-boards rule: Tasks 6 and 8
- **Deferred to later plans, by design:**
  - stage 2: ESP flashing
  - stage 3: AVR
  - stage 4: SPI flash write
  - stage 5: sniffers, SUMP, JTAG, raw wire, LCD, Bit Pirate extra modes, terminal escape hatch
  - stage 6: low-voltage PIC
  - knowledge layer 2: importing the Dangerous Prototypes and Espressif pages
