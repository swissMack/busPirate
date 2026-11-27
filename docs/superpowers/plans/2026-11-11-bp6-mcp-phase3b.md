# BP6 MCP phase 3b — sniffers and infrared — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the `bp6` MCP server listen to an I2C bus, a 2-wire (SLE4442-style) bus and a PS/2 keyboard, and receive, decode and send infrared remote codes, all through the BP6 text terminal.

**Architecture:** A new `Console.listen()` runs a command that streams until a key stops it: it collects output for a fixed time, answers the firmware's one-key menus, sends the stop key, and waits for the prompt. Recipes gain `terminal_flags`, so the engine's `m` line carries the mode's settings and no setup question is asked. Each feature is a small parser in `buspirate/bp6/` or `buspirate/devices/` plus recipes in a new `buspirate/mcp_bp6/recipes/sniff.py` and `recipes/infrared.py`. The simulator prints the firmware's exact strings for each new command.

**Tech Stack:** Python 3.8+ core, `mcp` SDK only in `buspirate/mcp_bp6/server.py`, pytest.

**Spec:** `docs/superpowers/specs/2026-11-10-bp6-mcp-server-design.md` (sections 4.4, 5 and 6, phase 3).
**Terminal facts:** `docs/superpowers/research/2026-11-11-bp6-terminal-commands-3b.md` (cited as §N), with the phase 3a companion `docs/superpowers/research/2026-11-11-bp6-terminal-commands.md` (cited as [C] §N). Both were read from firmware source at commit e2429e0. Every command string, stop key and output format below comes from them.
**Builds on:** phase 3a, `docs/superpowers/plans/2026-11-11-bp6-mcp-phase3a.md` (merged as PR #47): `Console`, `_TripWatch`, terminal recipes, `supply_by="action"`, `hiz` leaving the terminal mode.

**Scope (my calls against the spec's phase 3 list):**
- **In 3b:** the I2C sniffer, the 2WIRE sniffer, the PS/2 keyboard sniffer, IR receive (with NEC and RC5 decoding) and IR send.
- **Not built, with reasons** (each goes in the notes' "not automated" list, Task 6):
  - **The USB sniffer.** Its capture (`s`) blocks the firmware until enough packets arrive. With no traffic the board hangs until a replug, and nothing polls a key (§4). It also leaves the system clock at 120 MHz until a reset, which changes later PWM, UART and logic rates. Scripting it would leave an owner with a wedged board.
  - **`gps`.** The phase 1 `gps` recipe already reads and decodes NMEA over BPIO2. The terminal command adds nothing, and it returns silently without VOUT (§5).
  - **`logic`.** It only records what the BP6 itself drives during later bus-syntax lines. Its only text output is the first 80 samples (§7). Real captures go through the `pulseview` hand-off built in 3a.
  - **`tvbgone`.** It cannot be interrupted and switches off every TV in range (§6).
- **3c** stays as planned: SIM ATR, SLE4442, USB-PD, UART glitch, disk and macros.

## Global Constraints

- Core code stays Python 3.8-clean. Only `buspirate/mcp_bp6/server.py` imports `mcp`.
- The universal `buspirate` server and the desktop app must not change behaviour. Add no attributes to `buspirate/mcp/session.py`. BP6-only state lives in `buspirate/mcp_bp6/state.py`.
- Tests:
  - Python 3.9: `.venv/bin/python -m pytest tests/ -q` (from a worktree: `../../.venv/bin/python`)
  - Python 3.13: `uv run -q --isolated --python 3.13 --with-editable '.[dev,mcp]' python -m pytest tests/ -q`
  - Python 3.8: `uv run -q --isolated --python 3.8 --with-editable '.[dev]' python -m pytest tests/ -q --ignore-glob='*mcp*'`
  - Never use a plain `uv run`. macOS has no `timeout` command.
- **Never send Ctrl-C (`\x03`).** Stop keys are sent as single raw bytes with **no `\r`**: a trailing `\r` counts as another key in the IR and USB menus (§8 item 5).
- **Power rule (unchanged from 3a):**
  - The supply switches on only at a voltage and current the owner said yes to.
  - A recipe whose firmware switches the supply on by itself (the PS/2 sniffer: 5.0 V, 400 mA, plus 5 V pull-ups, §3) is `supply_by="action"`, and its plan names that voltage and current in a warning.
  - Terminal recipe voltages are multiples of 10 mV (`engine.TERMINAL_STEP_MV`).
- **Listening is bounded.** Every listening recipe has a `seconds` option: default 5, at most 60. Output kept in a result is capped: at most 200 transactions, packets or frames, with `truncated: true` when more arrived.
- **Pins the firmware drives must stay unconnected.** Each recipe's notes name them, exactly:
  - I2C and 2WIRE sniffers: IO2 and IO3. IO2 is also 2WIRE's RST.
  - PS/2 sniffer: IO6 and IO7.
  - IR: IO0.
- Tokens, the 5-minute window, `LOCKED` options and the destructive two-yes flow are unchanged. No 3b recipe is destructive. The PS/2 sniffer is `risk="owner-only"`.
- Copy rule: recipe text uses plain words and names the voltage. Every recipe has a docs.buspirate.com `source`.

## Review Focus

1. **The firmware returns to the prompt before the listening time is up.** Examples: `Invalid command: sniff` in the wrong mode, or a `PSU ERROR CODE` line. `listen()` returns at once with the reply. It never sends the stop key at the main prompt, where `x` or `q` would be typed as a command. (Test in Task 1.)
2. **A stop key sent too early is swallowed.** PS/2 discards input until `Sniffing...` (§3). `listen(ready=...)` starts the clock and allows the stop key only after the ready text. If the ready text never comes within 3 s, it raises `TerminalError` naming what was seen. (Test in Task 1.)
3. **A busy bus floods the result.** 10,000 transactions in 60 s must come back as 200 plus `count` and `truncated: true`, not as one huge reply. (Tests in Tasks 2 and 3.)
4. **A transaction cut off by the stop key** (no closing `]`) is kept, with `complete: false`, never dropped or merged with the next one. (Test in Task 2.)
5. **The PS/2 sniffer's own supply.** If the firmware prints `PSU 5v Enabled`, `session.power` records 5000 mV / 400 mA even when parsing fails later. If it prints `PSU ERROR CODE`, the result is an error and `session.power` stays None. (Test in Task 3.)

---

### Task 1: `Console.listen`, mode flags and the simulator's streaming state

**Files:**
- Modify: `buspirate/bp6/console.py`
- Modify: `buspirate/mcp_bp6/recipes/__init__.py` (Recipe field `terminal_flags`)
- Modify: `buspirate/mcp_bp6/engine.py` (pass the flags to `console_power.set_mode`)
- Modify: `buspirate/simulator_bp6.py` (modes `2WIRE`, `PS2`, `INFRARED`; `m` flags; a streaming state)
- Test: `tests/test_bp6_console.py`, `tests/test_mcp_bp6_engine.py`, `tests/test_bp6_simulator.py`

**Interfaces:**
- Produces:
  - `Console.listen(line: str, seconds: float, stop: str, ready: Optional[str] = None, keys: Sequence[Answer] = (), timeout: float = 3.0) -> Reply`
    - Sends `line` + `\r` and collects output.
    - With `ready`, the clock starts once `ready` appears. If it doesn't appear within `timeout`, the method raises `TerminalError("<line> did not start: <last 200 chars>")`, after sending `stop` so the board is not left listening.
    - Each `Answer` in `keys` is answered every time its pattern appears in new output, not once. The reply is sent raw, without `\r`. `Answer.wait_s` is honoured.
    - After `seconds`, it sends `stop` raw, then reads to the main prompt within `timeout`.
    - If the main prompt (ETX) appears first, it returns at once without sending `stop`.
    - It never aborts on a `>`-ending line: menus end in `> ` too.
    - It returns `Reply(text, mode, error)` exactly as `command()` does, including a pending trip error.
  - `Recipe.terminal_flags: str = ""`. This is the rest of the `m` line, such as `"-s 400"`. Only terminal recipes may set it; the existing registration check is extended.
  - `engine._run_terminal` calls `console_power.set_mode(con, want, recipe.terminal_flags)`.
  - Simulator:
    - `TERMINAL_MODES` gains `"2WIRE"`, `"PS2"` and `"INFRARED"`. The `m` handler ignores trailing flags.
    - In INFRARED mode the prompt reads `INFRARED-(RAW)> `, `INFRARED-(NEC)> ` or `INFRARED-(RC5)> `, following the `-p` flag (default raw; §6). `Console.mode` reads `INFRARED`.
    - `_stream(text, banner, stop_keys, end_text, chunks)` is a helper for the later tasks. It prints `banner`, then each chunk of `chunks`, an iterable of strings, one per 20 ms. On a key in `stop_keys` it prints `end_text` and the prompt. Other keys are ignored.
    - `fake.keys_seen` (a list) records every key received while streaming.

- [ ] **Step 1: Write the failing tests.**
  - `test_listen_stops_after_seconds`: a fake serial streams `"Press x to exit\r\n[ [0xA0]+]\r\n"` and returns to `I2C> \x03` only after receiving `b"x"`. `listen("sniff", 0.2, "x")` returns text containing `[0xA0]+`. The bytes written end with `b"x"`, not `b"x\r"`, and never contain `b"\x03"`.
  - `test_listen_returns_early_at_prompt`: the fake answers `sniff` with `"Invalid command: sniff. Type ? for help.\r\nHiZ> \x03"`. `listen` returns within 0.5 s with `mode == "HiZ"`, and no stop key was written.
  - `test_listen_waits_for_ready`: the fake prints `Sniffing...` after 0.3 s and swallows anything received before it. `listen(..., seconds=0.1, stop="q", ready="Sniffing...")` sends `q` only after `Sniffing...`.
  - `test_listen_ready_missing_raises`: no ready text arrives. `TerminalError` matches `did not start`, and `stop` was sent.
  - `test_listen_answers_menu_repeatedly`: the fake prints `"space for next, 'x' to exit > "` twice. `keys=[Answer("space for next", " ", 0)]` sends `b" "` twice and `x` at the end.
  - `test_terminal_flags_on_m_line` (engine): a test recipe with `terminal_mode="i2c"` and `terminal_flags="-s 400"` makes the simulator log the line `m i2c -s 400`.
  - `test_terminal_flags_only_for_terminal`: `Recipe(..., transport="bpio2", terminal_flags="-s 400")` raises `ValueError`.
  - `test_sim_infrared_prompt` (simulator): `m infrared -p raw -r 38k_demod` gives a prompt `INFRARED-(RAW)> `, and `Console.mode == "INFRARED"`. `m infrared -p nec` gives `INFRARED-(NEC)> `.
- [ ] **Step 2: Run them; expect failures** (`AttributeError: listen`, `unexpected keyword terminal_flags`).
- [ ] **Step 3: Implement.** `listen` shares `_drain`, `_write`, `_read`, `_at_main_prompt` and `_reply` with `command`. Do not change `command`.
- [ ] **Step 4: Run the three test files; expect PASS.** Then run the full 3.9 suite.
- [ ] **Step 5: Commit:** `bp6: Console.listen for streaming commands; recipe terminal_flags`

### Task 2: I2C and 2WIRE sniffers

**Files:**
- Create: `buspirate/bp6/sniff.py`
- Create: `buspirate/mcp_bp6/recipes/sniff.py` (import it in `recipes/__init__.py`)
- Modify: `buspirate/simulator_bp6.py` (`sniff` in I2C and 2WIRE modes)
- Test: `tests/test_bp6_sniff.py`, `tests/test_mcp_bp6_recipes_other.py`

**Interfaces:**
- Consumes: `Console.listen`, `Recipe.terminal_flags` (Task 1).
- Produces:
  - `sniff.parse_i2c(text: str) -> List[Dict]`. One dict per transaction line; the default format is in §1. Keys:
    - `address`: 7-bit int, the first byte >> 1;
    - `read`: bool, the first byte's bit 0;
    - `data`: hex string of the bytes after the address, space-separated (`"00 12"`);
    - `acks`: string of `+`/`-`, one per byte, address included;
    - `complete`: False when the line has no closing `]`;
    - `restarts`: the count of extra `[` inside the line.
    `U` lines are skipped and counted by the caller.
  - `sniff.parse_2wire(text: str) -> List[Dict]`. Keys `data` (hex string of all bytes) and `complete` (§2).
  - `sniff.listen_i2c(con, seconds) -> Dict` and `sniff.listen_2wire(con, seconds) -> Dict`. Each runs `con.listen("sniff", seconds, "x")` and returns `{"transactions": [...][:200], "count": n, "truncated": bool, "unknown": n_U, "seconds": seconds}`. `TerminalError` is raised on `reply.error`.
  - Recipes (`i2c-sniff` has `bus="i2c"`, `2wire-sniff` has `bus="pins"`; both `transport="terminal"`, `risk="none"`, `pullups=False`, `default_mv=0`, `min_mv=1800`, `max_mv=5000`, `milliamps=100`, options `{"seconds": 5}`). The check refuses `seconds` that is not a number with 0 < `seconds` ≤ 60.

    | Recipe | Mode, flags | Words | Wiring | Notes |
    |---|---|---|---|---|
    | `i2c-sniff` | `i2c`, `-s 400` | `i2c-sniff`, `sniff`, `sniffer`, `i2c`, `bus`, `traffic`, `monitor`, `spy` | SDA→IO0, SCL→IO1, GND→GND, target VCC→VOUT | "IO2 and IO3 are driven by the sniffer: leave them unconnected"; "listens only: the bus's own pull-ups and supply are used"; "up to about 500 kHz; on a very busy bus some bytes can be lost without warning" |
    | `2wire-sniff` | `2wire`, `-s 400` | `2wire-sniff`, `2wire`, `sle4442`, `smart card`, `sniff`, `sniffer` | same | "IO2 and IO3 are driven by the sniffer: leave them unconnected (IO2 is also 2WIRE's RST)"; "no ACK bits on this bus" |

    `source`: `https://docs.buspirate.com/docs/command-reference/`.
  - Simulator: `fake.sniff_lines` (a list of strings, e.g. `"[ [0xA0]+ [0x00]+ [0x12]-]\r\n"`) is streamed by `sniff` in I2C and 2WIRE through `_stream`, with banner `"I2C Sniffer\r\nPress x to exit\r\n"` or `"2Wire Sniffer\r\nPress x to exit\r\n"`, stop key `x` only, and no end text.

- [ ] **Step 1: Write the failing tests.**
  - `test_parse_i2c_default`: `"[ [0xA0]+ [0x00]+ [0x12]-]\r\n"` → `[{"address": 0x50, "read": False, "data": "00 12", "acks": "++-", "complete": True, "restarts": 0}]`.
  - `test_parse_i2c_restart_and_read`: `"[ [0xA0]+ [0x00]+ [ [0xA1]+ [0x34]-]\r\n"` → one transaction, `restarts == 1`, `address == 0x50`, `read is False`, `data == "00 A1 34"`.
  - `test_parse_i2c_cut_off`: `"[ [0xA0]+ [0x00]+"` (no `]`) → `complete is False`, and it is kept.
  - `test_parse_2wire`: `"[ 0x30 0x00 0xFF]\r\n"` → `[{"data": "30 00 FF", "complete": True}]`.
  - `test_i2c_sniff_recipe_runs`: set `fake.sniff_lines` to 3 transactions. Plan `i2c-sniff` with `{"millivolts": 3300, "seconds": 0.2}`, then run. `result["count"] == 3`; the simulator's mode is `I2C`; the line `m i2c -s 400` was received; `x` was received.
  - `test_sniff_truncates`: 250 lines → `count == 250`, `len(transactions) == 200`, `truncated is True`.
  - `test_sniff_seconds_refused`: `{"seconds": 61}` → `check.ok is False`, with an error naming 60.
  - `test_sniff_notes_name_driven_pins`: both recipes' notes mention `IO2 and IO3`.
- [ ] **Step 2: Run them; expect failures.**
- [ ] **Step 3: Implement.** Parse with one regex per token (`\[0x([0-9A-F]{2})\]([+-])` for the default I2C format, `0x([0-9A-F]{2})` for 2WIRE). Use the default format only; do not pass `-q`, `-r` or `-7`.
- [ ] **Step 4: Run; expect PASS.** Then the full 3.9 suite.
- [ ] **Step 5: Commit:** `bp6-mcp: I2C and 2WIRE sniffer recipes`

### Task 3: PS/2 keyboard sniffer

**Files:**
- Create: `buspirate/bp6/ps2.py`
- Modify: `buspirate/mcp_bp6/recipes/sniff.py`
- Modify: `buspirate/simulator_bp6.py` (`sniff` in PS2 mode)
- Test: `tests/test_bp6_sniff.py`, `tests/test_mcp_bp6_recipes_other.py`

**Interfaces:**
- Consumes: `Console.listen` (Task 1); `power.plan_power`, and the `supply_by="action"` pattern from `recipes/handoff.py`.
- Produces:
  - `ps2.parse(text: str) -> Dict` with:
    - `packets`: one per `"[0x%04X] t:0x%08X %c:0x%02X"` line, as `{"index": int, "ms": int, "from": "keyboard"|"host", "byte": "1C"}`. `D` is `keyboard`, `H` is `host`.
    - `keys`: the entry names that follow a packet line, in order, such as `MAKE_A`.
    - `typed`: the text after the last `key break tracker (limit 0x..): `, or `""`.
    - `dropped`: the sum of the `!! ring buffer full, %u packet(s) dropped !!` counts.
  - `ps2.listen(con, seconds) -> Dict`:
    - runs `con.listen("sniff", seconds, "q", ready="Sniffing...")`;
    - returns `parse()` output with `packets` capped at 200, plus `count`, `truncated`, `seconds` and `supply`;
    - `supply` is `{"millivolts": 5000, "milliamps": 400, "on": True}` when `PSU 5v Enabled` is seen.
    It raises `TerminalError` when `PSU ERROR CODE` is seen, quoting the line.
  - Recipe `ps2-sniff`:
    - Basics: `bus="pins"`, `transport="terminal"`, `terminal_mode="ps2"`, `risk="owner-only"`, `supply_by="action"`, `pullups=False`.
    - Power: `default_mv=min_mv=max_mv=5000`, `milliamps=400`, `target_powered_ok=False`.
    - Options: `{"seconds": 10}`.
    - Words: `ps2`, `ps/2`, `keyboard`, `sniff`, `sniffer`, `keylogger`, `mouse`.
    - Wiring: keyboard DATA → IO4, keyboard CLOCK → IO5, GND → GND.
    - `target_powered_error`: "VOUT reads a voltage: the PS/2 sniffer drives VOUT to 5 V itself, so leave VOUT unconnected (the keyboard keeps its own supply from the computer)".
    - Notes, verbatim:
      - "the sniffer switches the Bus Pirate's supply on at 5.0 V (400 mA) and the pull-ups to 5 V by itself; it stays on until hiz";
      - "leave VOUT, IO6 and IO7 unconnected; IO6 and IO7 are driven by the sniffer";
      - "only for a keyboard you own: everything typed on it is recorded".
  - The action sets `con.session.power = power.plan_power("bp6", 5000, power.SOURCE_OWNER, False, 400)` as soon as `PSU 5v Enabled` is in the reply. It does this before any parsing that could raise.
  - Simulator:
    - `sniff` in PS2 mode prints `"\r\nPSU 5v Enabled\r\n"` and sets `psu_enabled`, `psu_mv=5000`, `psu_ma=400` and `pullups=True`. `fake.ps2_psu_error` set to a code prints `"\r\nPSU ERROR CODE %d\r\n"` and returns to the prompt instead.
    - It prints the banner from §3. It ignores keys for 0.1 s (the drain), then prints `"\r\nPress 'q' to exit\r\n\r\nSniffing...\r\n\r\n"`.
    - It streams `fake.ps2_lines`. Stop keys are `q` and `Q`, and the end text is `"\r\n\r\nexit...\r\n"`.
    - Leaving PS2 mode switches `psu_enabled` and `pullups` off.

- [ ] **Step 1: Write the failing tests.**
  - `test_ps2_parse`: lines `"[0x0000] t:0x00001234 D:0x1C\r\nMAKE_A --> a\r\n-----------\r\n"`, then `"[0x0001] t:0x00001240 D:0xF0\r\n[0x0002] t:0x00001241 D:0x1C\r\nBREAK_A --> a\r\n**********\r\nkey break tracker (limit 0x13F bytes): a\r\n**********\r\n-----------\r\n"`. Expected: `keys == ["MAKE_A", "BREAK_A"]`, `typed == "a"`, `packets[0] == {"index": 0, "ms": 0x1234, "from": "keyboard", "byte": "1C"}`.
  - `test_ps2_dropped`: two overflow lines with 3 and 4 → `dropped == 7`.
  - `test_ps2_sniff_recipe_runs`: plan, then run with `{"seconds": 0.2}`. `result["typed"] == "a"`; `session.power.millivolts == 5000` and `milliamps == 400`; `q` was sent only after `Sniffing...`.
  - `test_ps2_plan_is_owner_only_and_names_5v`: the plan's warnings contain "ask the owner to confirm the device is theirs" and "5.0 V (400 mA)".
  - `test_ps2_refuses_live_vout`: set the simulator's VOUT reading to 3300 mV with the supply off. The plan or run refuses with the `target_powered_error` text.
  - `test_ps2_psu_error`: `fake.ps2_psu_error = 2` → the result has an `error` containing `PSU ERROR CODE 2`, and `session.power is None`.
  - `test_ps2_hiz_turns_supply_off`: after a run, `hiz` → `fake.psu_enabled is False`, `fake.mode == "HiZ"`, `session.power is None`.
- [ ] **Step 2: Run them; expect failures.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run; expect PASS.** Then the full 3.9 suite.
- [ ] **Step 5: Commit:** `bp6-mcp: PS/2 keyboard sniffer (owner-only)`

### Task 4: Infrared codes: aIR parsing, NEC and RC5

**Files:**
- Create: `buspirate/devices/ir.py`
- Test: `tests/test_ir_codes.py`

**Interfaces:**
- Produces (pure Python, no board):
  - `ir.parse_air(text: str) -> List[Dict]`. One dict per `$<khz>:<v>,<v>,...,;` frame (§6) in `text`, as `{"carrier_khz": int, "durations": List[int]}`. Durations are µs, mark first, alternating.
  - `ir.decode(durations: List[int]) -> Optional[Dict]`:
    - **NEC:** leader mark 9000 µs ±20 % and space 4500 ±20 %, then 32 bits. Mark about 560; space about 560 for 0 and 1690 for 1, each ±35 %; LSB first. Returns `{"protocol": "nec", "address": a, "command": c}` when command and its inverse match. When address and inverse don't match, `address` is the 16-bit value and `"extended": True`.
    - **RC5:** Manchester coding, half-bit 889 µs ±35 %, 14 bits. Returns `{"protocol": "rc5", "address": 0-31, "command": 0-63, "toggle": 0|1}`. Field bit 6 of the command comes from the inverted S2.
    - Anything else returns None.
  - `ir.encode_nec(address: int, command: int) -> List[int]` gives durations for one NEC frame: 9000, 4500, then 32 × (560, 560 or 1690), then a final mark of 560. Address and command are 0–255; their inverses are added.
  - `ir.to_air(carrier_khz: int, durations: List[int]) -> str` formats `$<khz>:<d1>,<d2>,...,<dn>,` with **no `;`**, because the terminal treats `;` as a command separator (§6). It raises `ValueError` above 127 mark/space pairs, or when the carrier is outside 20–60 kHz.
  - `ir.encode_nec` is used by tests and the simulator to build received frames. The board sends NEC itself (Task 5), because a NEC frame in aIR text is about 330 characters and the terminal line holds 256 (§9).

- [ ] **Step 1: Write the failing tests.**
  - `test_nec_roundtrip`: `decode(encode_nec(0x04, 0x08)) == {"protocol": "nec", "address": 4, "command": 8}`.
  - `test_nec_tolerates_jitter`: the same frame with every duration scaled by 1.15 decodes the same.
  - `test_nec_bad_inverse_none`: one flipped command bit → `None`.
  - `test_rc5_decode`: hand-built durations for address 5, command 12, toggle 1 → those values.
  - `test_parse_air_two_frames`: `"$38:9000,4500,560,560,;\r\n\r\n$36:889,889,;\r\n"` → 2 frames with carriers 38 and 36.
  - `test_to_air_no_semicolon`: `to_air(38, [9000, 4500, 560]) == "$38:9000,4500,560,"`.
  - `test_to_air_limits`: 255 durations → `ValueError` naming 127; `carrier_khz=70` → `ValueError` naming 20–60.
- [ ] **Step 2: Run them; expect failures.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run; expect PASS** (also under Python 3.8).
- [ ] **Step 5: Commit:** `devices: infrared aIR parsing, NEC and RC5 decoding, NEC encoding`

### Task 5: IR receive and send recipes

**Files:**
- Create: `buspirate/bp6/infrared.py`
- Create: `buspirate/mcp_bp6/recipes/infrared.py` (import it in `recipes/__init__.py`)
- Modify: `buspirate/mcp_bp6/recipes/__init__.py` (`BUSES` gains `"infrared"`)
- Modify: `buspirate/simulator_bp6.py` (`irrx` and `irtx` in INFRARED mode)
- Test: `tests/test_bp6_infrared.py`, `tests/test_mcp_bp6_recipes_other.py`

**Interfaces:**
- Consumes: `Console.listen` (Task 1); `ir.*` (Task 4).
- Produces:
  - `infrared.SENSORS = {"38d": "36-40 kHz demodulator on IO5", "56d": "56 kHz demodulator on IO7", "38b": "38 kHz barrier sensor on IO3"}`.
  - `infrared.receive(con, seconds: float, sensor: str) -> Dict`:
    - runs `con.listen("irrx -s %s" % sensor, seconds, "x", ready="Listening for IR packets", keys=[Answer("space for next", " ", 0)])`;
    - returns `{"frames": [{"carrier_khz", "durations", "air", "decoded"}][:50], "count", "truncated", "sensor", "seconds"}`.
    `air` is the frame's aIR text without `;`, ready to send again. `decoded` is `ir.decode()` or None.
  - `infrared.MAX_LINE = 256`: the terminal's line limit. Longer lines are cut silently (§9).
  - `infrared.send_air(con, air: str) -> Dict`:
    - raises `ValueError` when `len("irtx " + air) > MAX_LINE`, naming the length and the 256 limit, and suggesting `ir-send-nec` or `ir-send-rc5`;
    - otherwise runs `con.command("irtx " + air, timeout=5.0)`;
    - on `done`, returns `{"sent": True, "carrier_khz": k, "pairs": n}`, parsed from `Parsed AIR packet: modulation frequency %dkHz, %d MARK/SPACE pairs`;
    - otherwise raises `TerminalError` with the firmware's error line (§6 lists them).
  - `infrared.send_code(con, value: int) -> Dict` runs `con.command("> 0x%04X" % value, timeout=5.0)` (§9). It returns `{"sent": True, "tx": "0x...."}` from the `TX: 0x([0-9A-F]+)\.16` line, and raises `TerminalError` when that line is missing.
  - `receive` adds `"resendable": len("irtx " + air) <= MAX_LINE` to each frame.
  - Recipes (`bus="infrared"`, `transport="terminal"`, `terminal_mode="infrared"`, `terminal_flags="-p raw -r 38k_demod"`, `default_mv=3300`, `min_mv=2700`, `max_mv=5000`, `milliamps=100`, `pullups=False`):

    | Recipe | Options | Check refuses |
    |---|---|---|
    | `ir-receive` | `{"seconds": 10, "sensor": "38d"}` | `seconds` outside 0–60; `sensor` not in `SENSORS` |
    | `ir-send-nec` (`terminal_flags="-p nec"`) | `{"address": None, "command": None}` | `address` or `command` missing or outside 0–255 |
    | `ir-send-rc5` (`terminal_flags="-p rc5"`) | `{"address": None, "command": None, "toggle": 0}` | `address` outside 0–31, `command` outside 0–63, `toggle` not 0 or 1 |
    | `ir-send-raw` | `{"air": None}` | `air` missing, not matching `^\$\d{2}:(\d{1,5},)+$`, or longer than the line limit |

    - **Words:** `ir-receive`: `ir`, `infrared`, `remote`, `receive`, `learn`, `decode`, `nec`, `rc5`. the three senders: `ir`, `infrared`, `remote`, `send`, `transmit`, `blast`, plus `nec`, `rc5` or `raw`.
    - **Wiring:** IR receiver OUT → IO5 (or IO7 or IO3, by sensor), IR LED driver input → IO4, VCC → VOUT, GND → GND. The IR Toy plank fits all of them.
    - **Notes:**
      - "leave IO0 unconnected: the receiver drives it internally";
      - "point the remote at the receiver from about 10 cm and press the button briefly";
      - for the senders: "the LED on IO4 needs a transistor driver; the IR Toy plank has one".
    - **Sender actions:**
      - NEC sends `send_code(address << 8 | command)`; the firmware adds the inverses.
      - RC5 sends `send_code(toggle << 11 | address << 6 | command)`; the firmware forces S1 and S2.
      - Raw calls `send_air(air)`.
  - Simulator:
    - `irrx -s <s>` prints `"No file specified, packets cannot be saved\r\n"`, then `"RX sensor: <name>\r\n"`, then `"\r\nListening for IR packets (x to exit)...\r\n"`.
    - Then for each item of `fake.ir_frames` (aIR strings without `;`), it prints `"\r\n<air>;\r\n\r\nModulation frequency %dkHz, %d MARK/SPACE pairs\r\n\r\n'r' or 't' to re-transmit, space for next, 'x' to exit > "`. On a space it goes on to the next frame; on `x` it prints `"Exiting...\r\n"` and the prompt.
    - `irtx <air>` records `("raw", air)` in `fake.ir_sent` and prints the success lines from §6.
    - A line `> 0xNNNN` in NEC or RC5 mode records `("nec"|"rc5", value)` and prints `"\r\n\r\nTX: 0x%04X.16 \r\n"` before the prompt. In RC5 the echoed value has `0x3000` OR'd in (§9).
    - A line longer than 256 characters is cut at 256, as the firmware does.

- [ ] **Step 1: Write the failing tests.**
  - `test_ir_receive_decodes_nec`: `fake.ir_frames = [ir.to_air(38, ir.encode_nec(4, 8))]`. Run `ir-receive` with `{"seconds": 0.3}`. `frames[0]["decoded"] == {"protocol": "nec", "address": 4, "command": 8}`; `frames[0]["air"]` starts with `$38:9000,4500,`.
  - `test_ir_receive_two_frames_space_between`: with 2 frames, `count == 2`, and the keys the simulator saw were `" "`, then `"x"`.
  - `test_ir_send_nec`: `ir-send-nec` with `{"address": 4, "command": 8}` → the simulator received the line `> 0x0408`, `fake.ir_sent == [("nec", 0x0408)]`, and `result["tx"] == "0x0408"`. The mode line was `m infrared -p nec`.
  - `test_ir_send_rc5`: `{"address": 5, "command": 12, "toggle": 1}` → the line `> 0x094C`.
  - `test_ir_send_raw_resends_received`: a short received frame (`$38:900,450,560,560,560,`), passed as `ir-send-raw` `{"air": ...}`, is sent unchanged.
  - `test_ir_send_raw_too_long`: a NEC frame's aIR → `check.ok is False`, the error names 256 and suggests `ir-send-nec`, and nothing was written to the terminal.
  - `test_ir_receive_marks_long_frames`: a received NEC frame has `resendable is False`.
  - `test_ir_send_refuses_semicolon`: `air="$38:9000,4500,;"` → `check.ok is False`.
  - `test_ir_sensor_refused`: `sensor="99"` → `check.ok is False`, and the error lists `38d, 56d, 38b`.
  - `test_ir_wiring_follows_sensor`: plan `ir-receive` with `sensor="56d"` → the wiring row for the receiver says IO7.
- [ ] **Step 2: Run them; expect failures.**
- [ ] **Step 3: Implement.** The wiring follows `sensor` through the engine's existing `_wiring` option filter. If that filter cannot express it, add a `wiring_for(options)` callable to `Recipe`, defaulting to None; record that as a ruling.
- [ ] **Step 4: Run; expect PASS.** Then the full 3.9 suite.
- [ ] **Step 5: Commit:** `bp6-mcp: IR receive and send recipes`

### Task 6: Server text, notes, docs and smoke test

**Files:**
- Modify: `buspirate/mcp_bp6/server.py` (INSTRUCTIONS)
- Modify: `buspirate/mcp_bp6/notes/bp6.md`, `docs/mcp.md`
- Test: `tests/test_mcp_bp6_server.py`

- [ ] **Step 1: Write the failing tests.**
  - `test_recipes_list_phase3b`: `recipes()` lists `i2c-sniff`, `2wire-sniff`, `ps2-sniff`, `ir-receive`, `ir-send-nec`, `ir-send-rc5` and `ir-send-raw`, each with a `source` starting `https://docs.buspirate.com/`. `ir-send` itself is not a recipe; `ir-send-nec`, `ir-send-rc5` and `ir-send-raw` are.
  - `test_instructions_mention_listening`: INSTRUCTIONS says, in plain words, that sniffers and IR receive listen for `seconds` (at most 60), and that the PS/2 sniffer needs the owner to confirm the keyboard is theirs. INSTRUCTIONS stays under 2000 characters.
- [ ] **Step 2: Implement.** Then update the notes:
  - Add a **"Not automated"** section: the USB sniffer, `gps`, `logic` and `tvbgone`, each with its one-line reason from the Scope section above.
  - Add these items to **"Unverified on a real board"**:
    - the sniffers' stop keys and their output format;
    - whether a busy I2C bus loses bytes at 400 kHz;
    - that the PS/2 supply goes off when the mode is left;
    - the IR plank's current at 100 mA;
    - that the 256-character line limit cuts lines silently;
    - the `TX:` echo of `> 0x....` in NEC and RC5 modes;
    - the aIR timings of a real remote.
- [ ] **Step 3: Smoke test.** Write a stdio smoke script (scratchpad, not committed) against `buspirate mcp-bp6 --demo`. It runs each 3b recipe (plan, then run), then `hiz`. No step returns an `error`.
- [ ] **Step 4: Run the full suites (3.9, 3.13, 3.8 subset). Commit:** `bp6-mcp: phase 3b notes, docs and instructions`
