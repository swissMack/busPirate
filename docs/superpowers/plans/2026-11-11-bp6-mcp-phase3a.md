# BP6 MCP phase 3a — the terminal path — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the `bp6` MCP server drive the Bus Pirate 6's text terminal for what BPIO2 cannot do: PWM, frequency measurement, the self-test, blueTag JTAG/SWD pin finding, and handing the port to flashrom, avrdude or PulseView.

**Architecture:** A `Console` (new `buspirate/bp6/console.py`) sends one terminal line at a time, answers only the sub-prompts it was told to expect, and returns cleaned text. `Bp6.console()` opens it inside the session lock and re-syncs BPIO2 afterwards. Recipes gain `transport="terminal"`: the engine switches the terminal mode first, then applies the planned supply with `W`, because a terminal mode change switches the supply off. The simulator's terminal grows a command interpreter that prints the firmware's exact strings.

**Tech Stack:** Python 3.8+ core, `mcp` SDK only in `buspirate/mcp_bp6/server.py`, pytest.

**Spec:** `docs/superpowers/specs/2026-11-10-bp6-mcp-server-design.md` (sections 4.3, 4.4, 5 and 6, phase 3).
**Terminal facts:** `docs/superpowers/research/2026-11-11-bp6-terminal-commands.md`, read from firmware source at commit e2429e0 (2026-11-01). Every command string, prompt and output format in this plan comes from it. Section numbers below (§N) refer to it.

**Scope (my call; the spec's phase 3 is about 15 features):**
- **Here, 3a:** the terminal path, PWM, frequency, self-test, blueTag, and the Legacy (flashrom/avrdude) and SUMP (PulseView) hand-offs.
- **3b:** the I2C, 2WIRE, PS/2 and USB sniffers, `gps`, IR, and the `logic` command.
- **3c:** SIM ATR, SLE4442, USB-PD, UART glitch, disk and macros.

## Global Constraints

- Core code stays Python 3.8-clean. Only `buspirate/mcp_bp6/server.py` imports `mcp`.
- The universal `buspirate` server and the desktop app must not change behaviour. `buspirate/mcp/session.py` is shared, so add no attributes to it. BP6-only state lives in `buspirate/mcp_bp6/state.py` (Task 2).
- Tests:
  - Python 3.9: `.venv/bin/python -m pytest tests/ -q`
  - Python 3.13: `uv run -q --isolated --python 3.13 --with-editable '.[dev,mcp]' python -m pytest tests/ -q`
  - Python 3.8: `uv run -q --isolated --python 3.8 --with-editable '.[dev]' python -m pytest tests/ -q --ignore-glob='*mcp*'`
  - Never use a plain `uv run`. macOS has no `timeout` command.
- **Never send Ctrl-C (`\x03`) to the terminal.** At the colour question it wedges the board until a replug (`bp6/terminal.py`). To leave a sub-prompt, send `x\r`.
- **Power rule:**
  - The supply may switch on only at a voltage and current the owner said yes to.
  - Terminal `W` is sent only with the planned `millivolts`/`milliamps`, or the session's confirmed `session.power` values, and only after range checks (800–5000 mV, 0–500 mA). This avoids the `W 9` fall-into-prompt trap (§7).
  - A recipe whose firmware path switches the supply on by itself (self-test, SUMP) must say so in its plan's warnings, with the voltage.
- Tokens, the 5-minute window, `LOCKED` options and the destructive two-yes flow are unchanged. Phase 3a adds no destructive recipe. A recipe with `transport="terminal"` and `risk="destructive"` is refused at registration.
- Copy rule: tool descriptions and recipe text use plain words and name the voltage. Every recipe has a docs.buspirate.com `source`.

## Review Focus

1. **An unexpected sub-prompt.** Examples: `Use previous settings?` from a saved mode file, or a re-asked frequency. `Console` sends `x\r`, then raises `TerminalError` naming the question. It never waits out the full timeout and never guesses an answer. (Test in Task 1.)
2. **The supply trips during a terminal command.** The firmware prints `Error: Current over limit, power supply disabled` or `Potential short circuit` at any time. `Reply.error` carries it, and the engine clears `session.power`. (Test in Task 2.)
3. **The board is unplugged mid-console, or while lent.** The serial error surfaces as `BoardGone` through `session.run`. It never hangs, and the lent state is dropped on reconnect. (Tests in Tasks 1 and 6.)
4. **A re-run after a BPIO2 bus tool changed the mode.** `recipe_run(token=None)` on a terminal recipe whose mode is no longer current says "plan again". It never sends `m` or `W`. (Test in Task 2.)
5. **The server exits while the board is lent.** Legacy gets `q` then `y`, so the board resets and its supply goes off. SUMP gets `binmode 2`, then `n`, then HiZ. (Test in Task 6.)

---

### Task 1: The console and the simulated terminal

**Files:**
- Create: `buspirate/bp6/console.py`
- Modify: `buspirate/bp6/device.py` (add `console()`)
- Modify: `buspirate/simulator_bp6.py` (terminal interpreter)
- Test: `tests/test_bp6_console.py`

**Interfaces:**
- Produces:
  - `class TerminalError(BusPirateError)`
  - `@dataclass(frozen=True) class Answer: pattern: str; reply: str; wait_s: float = 0.0`. When `pattern` appears in the output and no main prompt follows within `wait_s`, `Console` sends `reply + "\r"` (a `reply` of `" "` is sent bare, without `\r`). Each `Answer` is used at most once.
  - `@dataclass(frozen=True) class Reply: text: str; mode: str; error: Optional[str]`. `text` is the cleaned output between the echo and the next main prompt. `mode` is the prompt's mode name (`HiZ`, `DIO`, `JTAG`…). `error` is the first error line, or None.
  - `class Console`:
    - `__init__(self, serial, notify, timeout: float = 3.0)`
    - `.mode: str`, the mode from the last prompt seen
    - `command(self, line: str, timeout: float = 3.0, answers: Sequence[Answer] = ()) -> Reply`
  - `clean(raw: str) -> str`
  - `Bp6.console(self) -> ContextManager[Console]`

- [ ] **Step 1: Write the failing tests** in `tests/test_bp6_console.py`. Use `FakeBp6` and its `factory`, like `tests/test_bp6_driver.py`.
  - `test_clean_strips_escapes`: `clean("\x1b[38;2;1;2;3mHiZ\x1b[0m> \x03\x07\r\n\x1b[0K\r\x1b[5C")` returns `"HiZ> \n"`.
  - `test_command_returns_text_and_mode`: after `con.command("m dio")`, `reply.mode == "DIO"`, `"Mode: DIO" in reply.text` and `reply.error is None`.
  - `test_error_line_is_reported`: in HiZ, `con.command("W 3.3 100")` gives `reply.error == "Command has no effect in HiZ mode, press 'm' to choose a mode"`.
  - `test_invalid_command_is_an_error`: `con.command("frobnicate").error.startswith("Invalid command: frobnicate")`.
  - `test_unexpected_subprompt_aborts`: arrange the simulator so `m i2c` asks `Use previous settings?` (set `FakeBp6.saved_modes = {"i2c"}`). `con.command("m i2c")` raises `TerminalError` whose message contains `Use previous settings?`. The simulator received `x\r` and is back at `HiZ> `. Wall time is under 1 s.
  - `test_answers_are_used_once`: `G 0` in DIO mode with answers for the frequency and the duty works. If the simulator re-asks the frequency (invalid value), the second ask raises `TerminalError`.
  - `test_never_sends_ctrl_c`: across every test in this file, `b"\x03"` is never in the simulator's received bytes. Use a fixture that asserts this at teardown.
  - `test_console_resyncs_bpio2`: after `with bp.console(): ...`, `bp.status()` works and the simulator saw the terminal port closed.
  - `test_unplug_mid_command`: the simulator's terminal port raises `SerialException` on read, so `command` raises `BusPirateError` (`BoardGone` when run under `session.run`).

- [ ] **Step 2: Run them.** `.venv/bin/python -m pytest tests/test_bp6_console.py -q` fails, because there is no module yet.

- [ ] **Step 3: Implement `console.py`.**
  - **Reading:** read until a main prompt. A main prompt is a line matching `^([A-Z0-9]+)(-\([^)]*\))?> $` after `clean`. ETX `\x03` is the firmware's end-of-prompt byte (§0), so finding it means "check now". The simulator before this task sent no ETX, so match on the prompt regex too.
  - **Sub-prompts:** a sub-prompt is cleaned text ending in `>` (optionally followed by a space) whose last 200 characters contain `x to exit` or `y/n`. Also match the special Answer patterns that never end in `>`, such as the self-test's `PUSH BUTTON (SPACE TO SKIP):`. For an unexpected sub-prompt, send `x\r`, read to the main prompt, and raise.
  - **Echo:** the first line of output is the echo; drop it.
  - **Errors:** `error` is the first cleaned line matching `^(Error: .*|Invalid command: .*|Command has no effect in HiZ mode.*|.* out of range: .*|.*is not available.*|.*is invalid!.*|.*has no frequency measurement hardware!.*|.*is unavailable because.*|.*is in use by.*)$`.
  - **Timeouts:** a timeout raises `TerminalError("the terminal did not answer <line>")`.

- [ ] **Step 4: Implement `Bp6.console()`.**
  1. Refuse to nest.
  2. Open `self.terminal_port` with `self._make_serial`, run `term.wake` (raise `TerminalError` if False), then build the `Console`.
  3. On exit, close the port, set `self._mode = None`, then call `self._status(self.first_reply_timeout)`. This is the same late-first-reply wait as `stop_stream`.

- [ ] **Step 5: Turn the simulator's terminal into an interpreter.**
  - Keep the existing colour question and binmode lines unchanged. Prompts are now `"<MODE>> \x03"`. The echo carries `"\x1b[0K"` noise.
  - Commands, with the exact strings from §0, §6 and §7:
    - `m hiz|dio|jtag|i2c` (i2c without `-s` asks `Use previous settings?` when in `saved_modes`). A mode change switches the simulated supply and pull-ups off.
    - `W <v> <ma>`: the success lines from §7. This also sets the BPIO2-visible `psu_enabled`/`psu_set_mv`/`psu_set_ma`/`psu_mv`.
    - `w`, `P`, `p`. In HiZ, `W`/`w`/`P`/`p`/`G`/`g` print the HiZ refusal.
    - Unknown commands print `Invalid command: <x>. Type ? for help.`.
    - The `trip_next_w` flag makes the next `W` print `\x07\r\nError: Current over limit, power supply disabled\r\n`.
  - Add a method `lines_received() -> List[bytes]` for assertions.

- [ ] **Step 6: Run the tests.** `tests/test_bp6_console.py`, `tests/test_bp6_simulator.py` and `tests/test_bp6_driver.py` pass. The old terminal tests still pass.

- [ ] **Step 7: Commit:** `bp6: a terminal console that answers only expected prompts`

### Task 2: Terminal recipes in the engine

**Files:**
- Modify: `buspirate/mcp_bp6/recipes/__init__.py`, `buspirate/mcp_bp6/engine.py`
- Create: `buspirate/mcp_bp6/state.py`, `buspirate/mcp_bp6/console_power.py`
- Modify: `buspirate/mcp_bp6/server.py` (`hiz` only)
- Test: `tests/test_mcp_bp6_engine.py`

**Interfaces:**
- Consumes: `Console`, `Answer`, `Reply`, `TerminalError` and `Bp6.console()` (Task 1).
- Produces:
  - New `Recipe` fields, all with defaults:
    - `transport: str = "bpio2"` (`"bpio2"` or `"terminal"`)
    - `terminal_mode: Optional[str] = None`, the `m` argument, such as `"dio"` or `"jtag"`; None means stay in HiZ
    - `precheck: Optional[Callable[[Any, Dict[str, Any]], Dict[str, Any]]] = None`, which runs over BPIO2 before the console opens
    - `supply_by: str = "engine"` (`"engine"`, or `"action"` when the firmware's own prompt sets the supply, as in Task 6)
    - `target_powered_ok: bool = True`
  - `BUSES` gains `"jtag"` and `"board"`.
  - For terminal recipes, `check` and `action` receive the `Console` in place of the board.
  - In `buspirate/mcp_bp6/console_power.py`:
    - `set_mode(con, name: str, flags: str = "") -> Reply`, which raises `TerminalError` unless `reply.mode == name.upper()`
    - `power_on(con, mv: int, ma: int) -> Dict[str, Any]`, which returns `{"vreg_mv", "vout_mv", "current_ma"}` parsed from `Vreg output: %d.%dV, Vref/Vout pin: %d.%dV, Current: %d.%dmA`, and raises `TerminalError` on `reply.error` or when `Power supply:  Enabled` is missing
    - `pullups(con, on: bool) -> Reply`
  - `state.py`:
    - `@dataclass class Bp6State: lent: Optional[Dict[str, Any]] = None; pwm_pins: Set[int] = field(default_factory=set); terminal_mode: Optional[str] = None`
    - `def of(session) -> Bp6State`, kept in a `weakref.WeakKeyDictionary`

- [ ] **Step 1: Write the failing tests.** Add a test recipe, registered in a fixture and removed after: `transport="terminal"`, `terminal_mode="dio"`, `default_mv=3300`.
  - `test_terminal_recipe_powers_after_mode`: `recipe_run` sends exactly `m dio`, then `W 3.30 <ma>`, then (if `pullups`) `P`, in that order, before check and action. `session.power` equals the plan afterwards.
  - `test_terminal_recipe_target_powered_sends_no_W`: the target measures 3300 mV at plan and run. No `W` line is sent; `P` is sent if `pullups`.
  - `test_target_powered_refused_when_not_ok`: with `target_powered_ok=False` and the target at 3300 mV, `recipe_plan` returns an error that names the measured voltage.
  - `test_trip_during_W_clears_power`: set `trip_next_w`. The result has `error` containing `Current over limit` and `session.power is None`. The action did not run.
  - `test_rerun_wrong_mode_refused`: run once, then a BPIO2 `i2c_scan`, then `recipe_run(token=None)`. The error contains `plan again`, and no `m` or `W` line was sent on the re-run.
  - `test_rerun_same_mode_sends_no_m_or_W`: the re-run sends only the action's own lines.
  - `test_terminal_destructive_refused`: registering a terminal recipe with `risk="destructive"` raises `ValueError`.
  - `test_precheck_runs_over_bpio2_first`: a failing precheck stops the run before the console opens. The terminal port is never opened.
  - `test_hiz_returns_terminal_to_hiz`: after a terminal recipe, the `hiz` tool sends `g <pin>` for each pin in `state.of(session).pwm_pins`, then `m hiz`, then does the BPIO2 hiz. It clears `pwm_pins` and `terminal_mode`.

- [ ] **Step 2: Run them, and check that they fail.**

- [ ] **Step 3: Implement the terminal branch of `_run_planned` and `_rerun`.**
  - **The BPIO2 part stays the same:** target measurement and `_power_error` for re-runs. The plan logic is shared. Plan-time refusal honours `target_powered_ok`.
  - **Then inside `bp.console()`:**
    1. **First run:** call `set_mode` when `terminal_mode` is set, otherwise `m hiz`.
    2. **Power,** only when the supply is the BP6 and `supply_by == "engine"`: run `power_on(con, plan.millivolts, plan.milliamps)`, check that `vout_mv` is within ±10 % of the plan, then set `session.power = plan`.
    3. **Pull-ups:** send `P` if `recipe.pullups`.
    4. Then the check and the action.
  - **Re-run:** if `con.mode != terminal_mode.upper()`, return the error `"plan again: the board is in <mode> mode now"`.
  - **Errors:** catch `TerminalError` into `{"error": ...}`. Clear `session.power` when the text contains `power supply disabled`.
  - **State:** record `state.of(session).terminal_mode`.

- [ ] **Step 4: Extend the `hiz` tool in `server.py` as tested.** If no terminal mode was recorded, `hiz` is unchanged and opens no console.

- [ ] **Step 5: Run the engine, recipe and server tests.** All pass.

- [ ] **Step 6: Commit:** `bp6-mcp: terminal recipes switch mode, then apply the planned supply`

### Task 3: PWM and frequency

**Files:**
- Create: `buspirate/bp6/signals.py`, `buspirate/mcp_bp6/recipes/signals.py` (import it in `recipes/__init__.py`)
- Modify: `buspirate/mcp_bp6/server.py` (tools `pwm`, `pwm_off`, `frequency`; add them to `TOOL_NAMES`)
- Modify: `buspirate/simulator_bp6.py` (the `G`, `g`, `f` commands)
- Test: `tests/test_bp6_signals.py`, `tests/test_mcp_bp6_recipes_other.py`, `tests/test_mcp_bp6_server.py`

**Interfaces:**
- Consumes: `Console`, `Answer` (Task 1); `set_mode`, `power_on`, `pullups`, `state.of` (Task 2).
- Produces, in `bp6/signals.py`:
  - `pwm_start(con, pin: int, hz: float, duty: float) -> Dict[str, Any]`, returning `{"pin", "actual_hz", "actual_duty_percent"}`
  - `pwm_stop(con, pin: int) -> Dict[str, Any]`
  - `measure_frequency(con, pin: int) -> Dict[str, Any]`, returning `{"pin", "hz", "duty_percent"}`
  - `PWM_MIN_HZ = 8`, `PWM_MAX_HZ = 62_500_000`, `FREQ_PINS = (1, 3, 5, 7)`
- Recipes: `pwm-signal` and `frequency-measure`. Both: `bus="pins"`, `transport="terminal"`, `terminal_mode="dio"`, `default_mv=3300`, `min_mv=1200`, `max_mv=5000`, `milliamps=100`, no pull-ups.

- [ ] **Step 1: Write the failing tests.**
  - `test_pwm_start_sends_three_lines`: the console sends `G 2`, then `1000hz`, then `50%`. `actual_hz == 1000`; `actual_duty_percent` is within 0.5 of 50.
  - `test_pwm_pair_partner_refused`: with `pwm_pins={2}`, `pwm-signal` on pin 3 returns, without sending anything, an error saying IO2 and IO3 share one PWM.
  - `test_pwm_range`: hz 5 and hz 70e6 are refused locally with the range named; duty 0 and duty 101 are refused.
  - `test_frequency_even_pin_refused`: pin 2 is refused locally with "only IO1, IO3, IO5 and IO7".
  - `test_frequency_parses`: the simulator prints `Frequency IO1: 1.00kHz 1.00ms (1000Hz), Duty cycle: 50.0%`, giving `{"pin": 1, "hz": 1000, "duty_percent": 50.0}`.
  - `test_never_bare_f`: no sent line equals `f` or `F` without a pin. `F` is never sent at all; it never ends by itself (§3).
  - `test_pwm_tool_needs_power_or_target`: with no `session.power` and no target voltage, the `pwm` tool returns the error `"plan power first (power_plan, then power_apply) or power the target"`.
  - `test_pwm_tool_reasserts_confirmed_power`: with `session.power` at 3300 mV / 100 mA, the tool sends `m dio`, then `W 3.30 100`, then `G …`. If the console is already in DIO it sends only `G …`.
  - `test_pwm_off_tool`: sends `g 2` and removes 2 from `pwm_pins`.

- [ ] **Step 2: Run them, and check that they fail.**

- [ ] **Step 3: Implement `signals.py`.** Use the exact output formats in §2 and §3:
  - success: `Generate frequency: Enabled on IO%d`
  - the `Actual frequency:` and `Actual duty cycle: %.0fns` lines
  - the `f <pin>` line

  `actual_duty_percent = duty_ns / period_ns * 100`, where the period comes from `Actual period: %.0fns`. Answers: `Answer("Period or frequency", f"{hz:g}hz")` and `Answer("Duty cycle (%)", f"{duty:g}%")`.

- [ ] **Step 4: Implement the recipes and the three tools.**
  - The tools run inside `session.run` → `bp.console()`.
  - **Power rule** (my call; a tool has no plan of its own): the tool needs either the confirmed `session.power`, re-applied after `m dio`, or a measured target voltage.
  - Recipe options: `pin` (default 0) and `hz` (default 1000) for `pwm-signal`, plus `duty` (default 50); `pin` (default 1) for `frequency-measure`.
  - `pwm-signal` adds its pin to `pwm_pins`. Its notes say the signal keeps running until `pwm_off` or `hiz`.

- [ ] **Step 5: Extend the simulator** with `G`/`g`/`f` and the §2 and §3 strings. Quantise the actual frequency the way `pwm_freq_find` does, or return the request exactly; either is fine for these tests.

- [ ] **Step 6: Run all tests. Commit:** `bp6-mcp: PWM and frequency over the terminal`

### Task 4: Self-test

**Files:**
- Create: `buspirate/mcp_bp6/recipes/board.py` (registered)
- Modify: `buspirate/simulator_bp6.py` (`~`)
- Test: `tests/test_mcp_bp6_recipes_other.py`

**Interfaces:**
- Consumes: Task 2's `precheck`, `transport`, `terminal_mode=None`, `Answer(wait_s)`.
- Produces: recipe `self-test`.
  - Fields: `bus="board"`, `max_mv=0`, `min_mv=0`, `default_mv=0`, `transport="terminal"`, `wiring=()`.
  - Option: `button_s` (default 20, from 0 to 60).
  - Result: `{"passed": bool, "errors": [str], "button": "pressed" | "skipped", "verdict": str}`.

- [ ] **Step 1: Write the failing tests.**
  - `test_selftest_precheck_refuses_connected_pins`: any IO pin or VOUT reading above 300 mV over BPIO2 stops the run with "disconnect everything from the Bus Pirate's pins first". `~` is not sent.
  - `test_selftest_plan_names_its_own_supply`: the plan's warnings contain `"the self-test switches the Bus Pirate's own supply on at 3.3 V"` and `"press the board's button"`.
  - `test_selftest_pass`: the simulator presses the button. The result is `passed True`, `button "pressed"`, `errors []`.
  - `test_selftest_button_skipped`: with `button_s=0`, the console sends `" "` at `PUSH BUTTON (SPACE TO SKIP):`. The simulator then ends `ERRORS: 1` / `FAIL! :(`. The result is `passed False`, `button "skipped"`, and the verdict is `"every block passed; the button test was skipped"`.
  - `test_selftest_never_formats`: the simulator asks `Format the Bus Pirate NAND flash?`, and the console answers `n`.
  - `test_selftest_reports_error_lines`: the simulator prints `BIO3 FLOAT: 1/0.92V ERROR!`. The line appears in `errors`, and the verdict names it.

- [ ] **Step 2: Run them, and check that they fail.**

- [ ] **Step 3: Implement the recipe.**
  - Send `~` with timeout 60 + `button_s`.
  - Answers: `Answer("Format the Bus Pirate NAND flash", "n")` and `Answer("PUSH BUTTON (SPACE TO SKIP):", " ", wait_s=button_s)`.
  - Parse: `PASS :)` / `ERRORS: %d` / `FAIL! :(`; every line containing `ERROR`; `SKIPPED`.
  - The verdict is plain words.
  - Set `session.power = None` afterwards; the firmware switches the supply off at the end (§4).

- [ ] **Step 4: Extend the simulator** with the §4 lines, in order.

- [ ] **Step 5: Run all tests. Commit:** `bp6-mcp: self-test recipe`

### Task 5: blueTag

**Files:**
- Create: `buspirate/bp6/bluetag.py`
- Create: `buspirate/mcp_bp6/recipes/jtag.py` (registered)
- Modify: `buspirate/simulator_bp6.py` (`bluetag` in JTAG mode only)
- Test: `tests/test_bp6_bluetag.py`, `tests/test_mcp_bp6_recipes_other.py`

**Interfaces:**
- Produces:
  - In `bp6/bluetag.py`:
    - `scan(con, protocol: str, channels: int, pulsing: bool = True) -> Dict[str, Any]`, returning `{"found": bool, "pinout": {name: "IOn" | None}, "devices": [{"idcode", "manufacturer", "part", "version"}], "channels"}`
    - `scan_seconds(protocol, channels) -> float`
  - Recipes `jtag-pinout` and `swd-pinout`:
    - Fields: `bus="jtag"`, `transport="terminal"`, `terminal_mode="jtag"`, `default_mv=3300`, `min_mv=1200`, `max_mv=5000`, `milliamps=100`, no pull-ups.
    - Options: `channels` (JTAG 4–8, default 6; SWD 2–8, default 4) and `pulsing` (default True).
    - Wiring: one row per channel, `IO0`…`IO(n-1)`, plus GND, plus VOUT ↔ the target's VREF.

- [ ] **Step 1: Write the failing tests.**
  - `test_jtag_hit_parses`: from the simulator's §5 lines `[  Pinout  ]  TDI=IO0 TDO=IO3 TCK=IO4 TMS=IO2 TRST=N/A` and `[ Device 0 ]  0x59602093 (mfg: 'Xilinx', part: 0x9602, ver: 0x5)`, `pinout == {"TDI": "IO0", "TDO": "IO3", "TCK": "IO4", "TMS": "IO2", "TRST": None}` and `devices[0]["idcode"] == "0x59602093"`.
  - `test_swd_hit_parses`: `SWDIO=IO5 SWCLK=IO6`, ARM `0x0BC12477`.
  - `test_nothing_found`: `No JTAG devices found. Please try again.` gives `found False` and the hint "check VREF and GND, and that each IO wire is on a separate pad".
  - `test_channel_range`: JTAG 3 and 9, and SWD 1, are refused locally.
  - `test_pulsing_flag`: `pulsing=False` sends `bluetag jtag -c 6 -d`; SWD never gets `-d`.
  - `test_timeout_scales`: `scan_seconds("jtag", 8) > scan_seconds("jtag", 6) >= 30`. The console call uses it.
  - `test_plan_warns_disturbs_target`: the warnings contain "blueTag pulses the pins and can disturb a running target".

- [ ] **Step 2: Run them, and check that they fail.**

- [ ] **Step 3: Implement.** The progress bar is `\r`-redrawn and needs no parsing. Timeout: `10 + permutations * 0.06` s. JTAG has n(n-1)(n-2)(n-3) permutations; SWD has n(n-1).

- [ ] **Step 4: Extend the simulator.** Add a configurable hit or miss. Outside JTAG mode, `bluetag` gives the invalid-command line.

- [ ] **Step 5: Run all tests. Commit:** `bp6-mcp: blueTag JTAG and SWD pin finder`

### Task 6: Hand-offs to flashrom, avrdude and PulseView

**Files:**
- Create: `buspirate/mcp_bp6/recipes/handoff.py` (registered)
- Create: `buspirate/mcp_bp6/handoff.py` (lend and reclaim)
- Modify: `buspirate/bp6/device.py`: `release_binary()` closes the BPIO2 serial without HiZ or any request; `reattach_binary()` reopens it and reads the status.
- Modify: `buspirate/mcp_bp6/server.py`: `guard` handles lent boards; `connect` and `hiz` reclaim; `run_stdio` reclaims on exit.
- Modify: `buspirate/simulator_bp6.py`: `binmode 1` and `binmode 5`, with the Legacy prompts, `q`/`y`, and the reset.
- Test: `tests/test_mcp_bp6_handoff.py`

**Interfaces:**
- Consumes: Tasks 1 and 2, `state.of(session).lent`.
- Produces:
  - Recipes `flashrom` and `avrdude`:
    - Shared fields: `transport="terminal"`, `terminal_mode=None`, `supply_by="action"`, `target_powered_ok=False`, `default_mv=3300`, `milliamps=100`.
    - `flashrom`: `bus="spi"`, `min_mv=1650`, `max_mv=3600`, the SPI flash wiring from `recipes/spi.py`.
    - `avrdude`: `bus="spi"`, `min_mv=1800`, `max_mv=5000`, the SPI wiring with RESET on CS.
  - Recipe `pulseview`: `bus="pins"`, `min_mv=default_mv=max_mv=3300`, `milliamps=100`, `target_powered_ok=False`, `supply_by="action"`.
  - In `mcp_bp6/handoff.py`: `lend(session, bp, to: str) -> Dict` and `reclaim(session) -> Dict`.
  - While the board is lent, every board tool except `connect`, `hiz`, `board_status`, `recipes` and `bp6_notes` returns: `"the board is lent to <to>; call connect (or hiz) to take it back — <how>"`.

- [ ] **Step 1: Write the failing tests.**
  - `test_flashrom_answers_legacy_prompts`: the console sends `binmode 5`, then answers:
    - OUTPUT HOLD/WP: `y`
    - HOLD HIGH: `y`
    - WP HIGH: `y`
    - clock: `n`
    - volts: `3.30`
    - current: `100`

    It waits for `Done! Just execute flashrom or avrdude`. The BPIO2 serial is closed afterwards, with no HiZ request sent. The result has `command == "flashrom -p buspirate_spi:dev=<binary port>,serialspeed=115200,spispeed=1M -r backup.bin"` and `how_to_return`.
  - `test_avrdude_pins_are_inputs`: answers `n` to OUTPUT HOLD/WP. The command is `avrdude -c buspirate -P <binary port> -p <part>`, with the `part` option (default `m328p`).
  - `test_handoff_refuses_target_powered`: the target measures 3300 mV, so the plan errors with "Legacy mode always switches the Bus Pirate's supply on; switch the target's own supply off first".
  - `test_pulseview_sump_and_warning`: the console sends `binmode 1`, then `n` at `Save setting?`. The plan warns `"the Bus Pirate switches its own 3.3 V supply on (100 mA) when PulseView opens the port"`. The result names the driver "Openbench Logic Sniffer & SUMP compatible" and the serial port.
  - `test_lent_board_refuses_tools`: after a hand-off, `i2c_scan` returns the lent error.
  - `test_connect_reclaims_legacy`: `connect` opens the terminal and sends `q`, then `y` at `Exit legacy binary mode`. The simulator resets: the ports vanish, then return. The server reconnects and BPIO2 answers. `lent` is None.
  - `test_reclaim_sump`: sends `binmode 2`, then `n`, then reopens BPIO2. `lent` is None.
  - `test_exit_reclaims`: `run_stdio`'s cleanup path calls `reclaim` before `disconnect`. Test the helper the cleanup calls; don't run stdio. Afterwards the simulator's supply is off.
  - `test_unplugged_while_lent`: when the terminal port can't be opened at reclaim, `connect` drops `lent` and does a fresh connect if a board is found, otherwise it returns the board-gone error.

- [ ] **Step 2: Run them, and check that they fail.**

- [ ] **Step 3: Implement.**
  - The Legacy prompts are in §8. Answer patterns: `Set OUTPUT HOLD(IO2) & WP(IO3) pins?`, `Set HOLD HIGH?`, `Set WP HIGH?`, `Clock on IO0`, `Volts (0.80V-5.00V)`, `Maximum current (0mA-500mA)`.
  - After `Power supply set to %2.2fV, %3.0fmA`, set `session.power` to the plan.
  - The menu numbers (1 SUMP, 2 BPIO2, 5 Legacy) are checked against the printed `binmode` menu before use. If they differ, raise `TerminalError` naming the menu.
  - Reclaim after Legacy waits up to 10 s for the board's ports to return, using `session.candidates()`, then runs the normal `connect`.

- [ ] **Step 4: Extend the simulator,** including a reset that drops and restores both ports.

- [ ] **Step 5: Run all tests. Commit:** `bp6-mcp: hand the port to flashrom, avrdude or PulseView, and take it back`

### Task 7: Server text, notes, docs and smoke test

**Files:**
- Modify: `buspirate/mcp_bp6/server.py` (INSTRUCTIONS, tool descriptions)
- Modify: `buspirate/mcp_bp6/notes/bp6.md`, `docs/mcp.md`
- Test: `tests/test_mcp_bp6_server.py`

- [ ] **Step 1: Write the failing tests.**
  - `test_tool_names_phase3a`: `TOOL_NAMES` ends with `"pwm", "pwm_off", "frequency"`. The full list is registered.
  - `test_instructions_mention_terminal_rules`: INSTRUCTIONS contains, in plain words:
    - a hand-off lends the board until `connect`;
    - the self-test needs nothing on the pins;
    - blueTag scans can take a minute.
    - INSTRUCTIONS stays under 1800 characters.
  - `test_recipes_list_new`: `recipes()` lists `pwm-signal`, `frequency-measure`, `self-test`, `jtag-pinout`, `swd-pinout`, `flashrom`, `avrdude` and `pulseview`, each with a `source` starting `https://docs.buspirate.com/`.

- [ ] **Step 2: Implement, then add these items to the notes' "Unverified on a real board" list:**
  - the terminal ETX marker and echo escapes;
  - whether PWM keeps running after a BPIO2 bus tool changes the mode;
  - blueTag scan time, and the MCP client's tool timeout;
  - the Legacy SPI pin map for avrdude;
  - the PulseView driver settings;
  - which binmode the owner's unit has saved;
  - the self-test button timing.

- [ ] **Step 3: Smoke test.** Write a stdio smoke script (scratchpad, not committed) against `buspirate mcp-bp6 --demo`. It runs:
  1. `pwm-signal` plan, then run;
  2. `frequency` on IO1;
  3. `self-test` with `button_s=0`;
  4. `jtag-pinout`;
  5. a `flashrom` hand-off, then `connect`, which reclaims;
  6. `hiz`.

  Each step returns no `error`.

- [ ] **Step 4: Run the full suites (3.9, 3.13, 3.8 subset). Commit:** `bp6-mcp: phase 3a tools, notes and docs`
