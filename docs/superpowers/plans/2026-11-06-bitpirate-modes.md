# Bit Pirate Modes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The Bit Pirate's own functions become usable from the left menu: new panels for its modes, and extra actions on I2C and UART, each a click with typed fields, its reply shown in the panel.

**Architecture:** Each Bit Pirate mode is described as data: a `CliMode` with its `CliCommand`s, in `buspirate/boards/bitpirate_modes.py`, held on `Board.modes`. One panel module, `web/panels/cli_modes.py`, turns every board's modes into ordinary `Panel`s, each gated by a capability `cli_mode:<id>` that only that board has. The driver gains one generic mode, `CliModeSession`, entered through `session.ensure_mode("cli:<id>")`. It answers the mode's `config` pin questions with dock-header pins (as I2C, SPI and UART do now), runs a command line, and returns the reply lines, or hands the port to a text stream for commands that run until stopped. The frontend gains a `lines` result renderer and menu group headings.

**Tech Stack:** Python 3.8+, FastAPI, vanilla JS, pytest, jsdom checks.

**Spec:** `docs/superpowers/specs/2026-11-06-board-driven-app-design.md` §3 and "Order of work" step 3. Sources for every command and reply: the imported wiki (`docs/bitpirate-wiki/0*-*.md`, `1*-*.md`) and the firmware source, geo-tp/ESP32-Bit-Pirate tag `v1.8`, `src/Controllers/*Controller.cpp`.

**Branch:** `bitpirate-modes`, cut from `one-way-around` (PR #29).

## Global Constraints

- **The first batch is exactly these.**
  - New panels: **1-Wire**, **DIO** and **JTAG** (group "Buses"); **Wi-Fi** and **Bluetooth** (group "Wireless").
  - Extra actions on the existing panels: **I2C** gains Identify, Discovery, Dump, Recover the bus and Sniff (stream); **UART** gains Find the baud rate (`autobaud`).
  - Out of this batch: the add-on module modes (Infrared, Sub-GHz, RFID, RF24, LoRa, CAN, Ethernet, FM, Cell, I2S, LED) are step 4. The interactive shells and adapter modes (`eeprom`, `smartcard`, `wizard`, `openocd`, USB adapters, Pirate Assistant, the HDUART bridge) stay in the Terminal.
- **Never leave a prompt open.** Every command is sent with all its arguments filled in, so the firmware never stops to ask. Any question it asks anyway is answered with its default by `CliTransport.command`, as today.
- **Pins go on the dock header.** Each mode's `config` pin answers use header GPIOs only (15, 16, 17, 18, 10, 11, 12, 13), following the Bus Pirate 6 layout: 1-Wire `Data GPIO` = 15. DIO's pin fields are enums of those eight, labelled `IO15`…`IO13`. JTAG scans header pins only.
- **Only the Bit Pirate sees any of this.** The v3, v4 and Bus Pirate 6 menus and actions are unchanged: their capability sets get none of the `cli_mode:*` or `cli_extras` capabilities.
- **Destructive or noisy commands are excluded:** `jam`, `flood`, `glitch`, `spam`, `deauth`, `spoof`, `bruteforce`, `repeater`, Wi-Fi `ap`. They stay in the Terminal.
- Python 3.8 compatible. Check with `uv run --isolated --python 3.8 --with pytest --with-editable '.[dev]' python -m pytest -q tests`.
- Follow the memory rules on this repo: the simplest UI (one-click actions), and one-stop-shop results (show what the board said, plainly; a temperature reading shows °C as the board prints it).

## Review Focus

1. **A command the firmware rejects** (`Unknown command`, wrong mode) shows the board's own words as an error in the panel, not a stack trace or a silent "Done". Test in Task 2.
2. **Leaving a streaming command** (Sniff, 1-Wire sniff) by switching panel, pressing HiZ or disconnecting stops it, and the next command works. Test in Task 2.
3. **Switching from a CLI mode panel to I2C/SPI/UART and back** re-enters the right firmware mode with the right pins each time. Test in Task 2.
4. **A field left empty or out of range** (DIO PWM duty 150 %, an I2C address 0x90) is refused before anything is sent. Test in Task 3.
5. **The menu on a Bit Pirate with no Wi-Fi in reach** (Wi-Fi scan finds nothing) shows "No networks found" as the board says, not an empty box. Test in Task 4.

---

### Task 1: Modes as data on the board

**Files:**
- Create: `buspirate/boards/_modes.py`, `buspirate/boards/bitpirate_modes.py`
- Modify: `buspirate/boards/_board.py` (`modes` field), `buspirate/boards/bitpirate.py` (capabilities, modes), `buspirate/capabilities.py` (`CAP_CLI_EXTRAS = "cli_extras"`)
- Test: `tests/test_bitpirate_modes.py` (new)

**Interfaces:**
- Produces, in `buspirate/boards/_modes.py` (frozen dataclasses, Python 3.8 typing):
  - `CliParam(name: str, type: str, label: str, default: Any = None, choices: Optional[List[Dict[str, Any]]] = None, minimum: Optional[int] = None, maximum: Optional[int] = None, help: str = "")`, where `type` is one of the registry's `PARAM_TYPES`;
  - `CliCommand(name: str, label: str, line: str, params: Tuple[CliParam, ...] = (), streams: bool = False, timeout: float = 5.0, help: str = "")`. `line` is a `str.format` template over the param names, e.g. `"pwm {pin} {freq} {duty}"`;
  - `CliMode(id: str, title: str, cli_name: str, group: str, blurb: str, doc: str, commands: Tuple[CliCommand, ...], pins: Dict[str, str] = {}, needs: str = "")`. `cli_name` is what follows `m`; `group` is "Buses" or "Wireless"; `pins` holds the `config` answers; `needs` is a line on extra hardware (empty for this batch);
  - `def cli_mode_capability(mode_id: str) -> str` returning `f"cli_mode:{mode_id}"`.
- `Board.modes: Tuple[CliMode, ...] = ()`. The Bit Pirate's `capabilities` become `{CAP_CLI_EXTRAS} | {cli_mode_capability(m.id) for m in MODES}`.
- `bitpirate_modes.MODES`, in menu order, with ids `onewire_cli`, `dio`, `jtag`, `wifi`, `bluetooth` (`onewire_cli` so it never clashes with the Bus Pirate's `onewire` panel). Commands, from the wiki tables and checked against the firmware source:
  - **1-Wire** (`1wire`, pins `{"Data GPIO": "15"}`): Find devices `scan`; Ping `ping`; Read the ROM `read`; Read DS18B20 temperature `temp`; Sniff `sniff` (streams).
  - **DIO** (`dio`): Read a pin `read {pin}`; Set a pin `set {pin} {level}` (level enum H, L, I, O); Pull-up `pullup {pin}`; Pull-down `pulldown {pin}`; PWM `pwm {pin} {freq} {duty}` (freq 1–40000000, duty 0–100); Measure frequency `measure {pin} {ms}`; Pulse `pulse {pin} {us}`; Servo `servo {pin} {angle}` (0–180); Reset a pin `reset {pin}`.
  - **JTAG** (`jtag`): Find JTAG/SWD pins `scan`. Before writing it, check in `JtagController.cpp` which pins `scan` probes and how it asks for them. If it prompts, the command's `line` carries the header pins; if it cannot be limited to the header, leave JTAG out and record a ledger ruling.
  - **Wi-Fi** (`wifi`): Scan for networks `scan`; Status `status`; Connect `connect {ssid} {password}`; Disconnect `disconnect`; Ping a host `ping {host}`.
  - **Bluetooth** (`bluetooth`): Scan for devices `scan` (timeout 15 s); Status `status`.
  - **Extra actions** for the existing panels, listed as `EXTRA_ACTIONS: Dict[str, Tuple[CliCommand, ...]]`, keyed by panel id:
    - `i2c`: Identify `identify {address}`; Discovery `discovery`; Dump `dump {address} {length}`; Recover the bus `recover`; Sniff `sniff` (streams);
    - `uart`: Find the baud rate `autobaud` (timeout 20 s).

  Each mode's `doc` is its wiki page (`bitpirate-wiki/02-1wire`, `09-dio`, `15-jtag`, `14-wifi`, `13-bluetooth`).

- [ ] **Step 1: Failing tests** in `tests/test_bitpirate_modes.py`:

```python
def test_every_command_line_uses_only_its_own_params():
    for mode in MODES:
        for cmd in mode.commands:
            names = {n for _, n, _, _ in string.Formatter().parse(cmd.line) if n}
            assert names == {p.name for p in cmd.params}, (mode.id, cmd.name)

def test_mode_ids_are_unique_and_clash_with_no_panel():
    from buspirate.web.registry import load_panels
    taken = {p.id for p in load_panels()}
    ids = [m.id for m in MODES]
    assert len(ids) == len(set(ids)) and not (set(ids) & taken)

def test_every_mode_doc_exists(): ...            # docs.read(mode.doc) is not None
def test_only_the_bit_pirate_has_mode_capabilities(): ...
def test_no_excluded_command_is_offered():
    banned = {"jam", "flood", "glitch", "spam", "deauth", "spoof", "bruteforce", "repeater", "ap",
              "eeprom", "smartcard", "wizard", "openocd"}
    # no command line's first word is in banned, across MODES and EXTRA_ACTIONS
def test_dock_pins_only():
    # every pins value, and every DIO pin choice, is in {"15","16","17","18","10","11","12","13"}
```

- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_bitpirate_modes.py -q`. Expected: ImportError.
- [ ] **Step 3: Write** `_modes.py`, `bitpirate_modes.py` and the `Board`/capability changes.
- [ ] **Step 4: Run** the new tests and the full suite. Expected: all pass.
- [ ] **Step 5: Commit** "Describe the Bit Pirate's modes as data".

---

### Task 2: A generic CLI mode in the driver and the session

**Files:**
- Modify: `buspirate/bitpirate/modes.py` (`_CliMode.run`, `_CliMode.start_stream`, new `CliModeSession`), `buspirate/bitpirate/device.py` (`cli_mode(spec)`), `buspirate/web/session.py` (`ensure_mode` for `"cli:<id>"`), `buspirate/simulator_bitpirate.py`
- Test: `tests/test_bitpirate_modes.py`, `tests/test_bitpirate_driver.py`

**Interfaces:**
- `_CliMode.run(line: str, timeout: float = 5.0) -> List[str]`: one command, returning the reply lines with the echo and the prompt removed. Raises `ModeError` with the board's own line on `Unknown command`, `Cannot execute`, or a prompt showing another mode (`_check` already does this).
- `_CliMode.start_stream(line: str) -> None`: sends the line and hands the port to a text stream via `bp.start_text_stream`. If `start_text_stream` needs a header, add `header: Optional[str] = None`, where `None` means stream from the first byte after the echoed line.
- `class CliModeSession(_CliMode)`, built from a `CliMode`: `name = spec.cli_name.upper()` (the prompt), `pins = spec.pins`.
- `BitPirate.cli_mode(spec: CliMode) -> CliModeSession`, entered through the same path as `i2c()` (`_enter_mode`, which answers the pin questions and caches them).
- `DeviceSession.ensure_mode("cli:<id>")` finds the spec in `boards.get(variant).modes` and calls `bp.cli_mode(spec)`. Other mode names behave as today.
- The simulator learns the `1WIRE`, `DIO`, `JTAG`, `WIFI` and `BLUETOOTH` modes and every command in `MODES` and `EXTRA_ACTIONS`. Its replies are copied from the firmware's own strings in the matching `Controllers/*Controller.cpp`, with a comment citing the file. It answers anything else in those modes with `Unknown command`.

- [ ] **Step 1: Failing tests:**
  - `test_running_a_command_returns_its_reply_lines`: on the simulator, `bp.cli_mode(onewire).run("scan")` has a line containing a ROM code;
  - `test_entering_a_mode_puts_its_pins_on_the_dock`: the simulator's `settings["1WIRE"]["Data GPIO"] == "15"`;
  - `test_an_unknown_command_raises_with_the_boards_words`: `ModeError`, and the message contains "Unknown command";
  - `test_switching_between_cli_and_bus_modes_reenters_each` (Review Focus 3): cli 1-Wire, then `ensure_mode("i2c")`, then cli 1-Wire again, and the simulator's mode follows each time;
  - `test_a_streaming_command_stops_on_hiz_and_the_next_command_works` (Review Focus 2).
- [ ] **Step 2: Run** them. Expected: FAIL (`cli_mode` missing).
- [ ] **Step 3: Implement** as specified.
- [ ] **Step 4: Run** the new tests and the full suite. Expected: all pass.
- [ ] **Step 5: Commit** "A generic Bit Pirate mode: enter, run a command, stream".

---

### Task 3: Panels from the modes, and the extra actions

**Files:**
- Create: `buspirate/web/panels/cli_modes.py`
- Modify: `buspirate/web/registry.py` (`load_panels` also collects a module-level `PANELS` list; `Panel.group: str = ""` in `to_json`; a `lines(lines: List[str], *, caption: str = "") -> dict` result helper, render `"lines"`), `buspirate/web/panels/i2c.py`, `buspirate/web/panels/uart.py` (append the `EXTRA_ACTIONS` as `Action`s with `requires=CAP_CLI_EXTRAS`)
- Test: `tests/test_bitpirate_modes.py`

**Interfaces:**
- `cli_modes.PANELS`: one `Panel` per `CliMode` across `boards.REGISTRY`, with `id = mode.id`, `mode = f"cli:{mode.id}"`, `doc = mode.doc`, `requires = cli_mode_capability(mode.id)`, `group = mode.group`, `order` after UART, `notes = [mode.needs]` when set, and `wiring` listing the header pins in `mode.pins` plus GND and VIO. Each `CliCommand` becomes an `Action`: its params become `Param`s, `line.format(**params)` is the command, and the result is `lines(...)`, or `live(..., decoder="console")` for streams.
- One shared action builder, `action_for(cmd: CliCommand) -> Action`, is used by both `cli_modes.py` and the I2C and UART extras, so the two can never differ.

- [ ] **Step 1: Failing tests:**
  - `test_a_bit_pirate_sees_its_mode_panels` (`client_bitpirate`, from `tests/test_boards.py`): the panel ids include `onewire_cli`, `dio`, `jtag`, `wifi` and `bluetooth`, each with its `group`;
  - `test_a_bus_pirate_sees_none_of_them` (simulated v3): none of those ids, and the I2C panel has no `identify` action;
  - `test_running_a_mode_action_returns_lines` (`/api/run` onewire_cli/temp → `render == "lines"`, a line with `°C` or `C`, as the firmware prints it);
  - `test_out_of_range_input_is_refused_before_sending` (Review Focus 4): DIO `pwm` with `duty=150` → 400, and the simulator received no `pwm` line;
  - `test_the_i2c_panel_gains_identify_on_a_bit_pirate`.
- [ ] **Step 2: Run** them. Expected: FAIL.
- [ ] **Step 3: Implement.** `load_panels` keeps today's sort (`order`, then `title`).
- [ ] **Step 4: Run** the full suite. Expected: all pass.
- [ ] **Step 5: Commit** "The Bit Pirate's modes become panels; I2C and UART gain its extra actions".

---

### Task 4: Grouped menu and plain-text replies in the frontend

**Files:**
- Modify: `buspirate/web/static/app.js` (`renderNav`: a `.nav__heading` before the first panel of each non-empty `group`; `renderResult`: `lines` renders `pre.console`), `buspirate/web/static/app.css`
- Test: `tests/ui/frontend.mjs`

- [ ] **Step 1: Failing UI checks.** With `simulated-bitpirate` connected:
  - the menu shows the headings "Buses" and "Wireless", with 1-Wire, DIO and JTAG under "Buses" and Wi-Fi and Bluetooth under "Wireless";
  - running 1-Wire → Read DS18B20 temperature shows a `pre.console` holding the board's line;
  - Wi-Fi → Scan with the simulator in "no networks" shows the board's "No networks found" text (Review Focus 5; give the simulator a flag for it);
  - on a simulated v3, no `.nav__heading` appears.
- [ ] **Step 2: Run** `make ui-test`. Expected: those checks FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `make ui-test`, the full suite and the Python 3.8 command. Expected: all pass.
- [ ] **Step 5: Commit** "Menu groups and plain-text replies".

---

### Task 5: The docs, then the real board

- [ ] In `docs/bitpirate.md`, delete the mode table added in PR #27 (spec §2: the menu and the wiki carry it now). Add a short "In the menu" list of the new panels and actions, and a line saying everything else is in the Terminal.
- [ ] Add a "Bit Pirate modes" checklist to `docs/troubleshooting.md` (`- [ ]` per command), and run it on the user's real board with them. 1-Wire and DIO need a part on the header; Wi-Fi and Bluetooth need nothing. Fix the simulator wherever the real output differs, as `bitpirate-support` memory asks.
- [ ] Commit, push `bitpirate-modes`, and open a PR against `one-way-around` titled "Use the Bit Pirate's own modes from the menu".
