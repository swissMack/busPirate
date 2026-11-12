# BP6 MCP phase 3c Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Terminal recipes for a smart card's answer to reset (read-only), the USB-PD plank (status, request with its own yes, reset) and the BP6's own disk (list, show, hex, delete with its own yes).

**Architecture:** Each feature gets a parser/driver module in `buspirate/bp6/` (pure functions over a `Console`), a recipe module in `buspirate/mcp_bp6/recipes/`, and simulator support in `buspirate/simulator_bp6.py`. Task 1 lets a terminal recipe be destructive: the change runs in the terminal on `recipe_commit`, after the same identity check the BPIO2 recipes use.

**Tech Stack:** Python ≥3.8, pytest, the existing `Console` (`buspirate/bp6/console.py`), recipe engine (`buspirate/mcp_bp6/engine.py`) and `FakeBp6` simulator.

**Spec:** `docs/superpowers/specs/2026-11-10-bp6-mcp-server-design.md` (§4.4, §5, §6 item 3). Research: `docs/superpowers/research/2026-11-12-bp6-terminal-commands-3c.md` plus the firmware facts quoted below (firmware commit e2429e0c, files under `src/`).

## Global Constraints

- Python 3.8 compatible: `from __future__ import annotations`, `typing` generics, no `match`, no `X | Y` at runtime.
- Never send Ctrl-C to the terminal. A terminal line is at most 256 characters.
- Terminal recipe voltages are multiples of 10 mV.
- `buspirate/mcp_bp6/notes/bp6.md` lines are at most 100 characters.
- Agreed scope (owner, 2026-11-12): card answer read-only; USB-PD status, request and reset; disk list/show/hex and delete. **Not automated** (write down, do not build): macros, scripts, `button`, `pause -b`, `bridge`, `fusb302 scan`, `format`, `edit`, `hexedit`, UART `glitch`, `sle4442`.
- Spec §5: "USB-PD plank: reading the source's offers is fine; requesting a voltage above 5 V needs its own yes naming the voltage (up to 28 V)." Ruling: **every** request goes through `recipe_commit`, so the yes always names voltage and current.
- Test commands (from the worktree): 3.9 `../../.venv/bin/python -m pytest tests/ -q -p no:cacheprovider`; 3.13 `uv run -q --isolated --python 3.13 --with-editable '.[dev,mcp]' python -m pytest tests/ -q`; 3.8 `uv run -q --isolated --python 3.8 --with-editable '.[dev]' python -m pytest tests/ -q --ignore-glob='*mcp*'`.

## Review Focus

1. A FatFs error printed with no line ending, right before the prompt (`Error: no file` then the prompt on the same line): the reply must end at once and carry the error, not time out. Test in Task 1.
2. A commit token redeemed after the board left the recipe's terminal mode (another recipe ran): refuse with "plan again", send no change. Test in Task 1.
3. The USB-PD source changed between prepare and commit (different PDO list): refuse, request nothing. Test in Task 3.
4. A disk path with a space, a `;`, more than 31 characters or a non-8.3 name: refused before anything is sent. Test in Task 4.
5. No card inserted (no bytes after reset): a clear "no answer" result, async print switched off again (`]` sent). Test in Task 2.

---

### Task 1: Terminal destructive recipes and console groundwork

**Files:**
- Modify: `buspirate/mcp_bp6/recipes/__init__.py` (drop the "terminal recipe may not change a chip" rule; update the docstring)
- Modify: `buspirate/mcp_bp6/engine.py` (`plan_recipe` note, `commit_recipe`)
- Modify: `buspirate/bp6/console.py` (`collect`, inline-prompt end in `command`)
- Test: `tests/test_mcp_bp6_engine.py`, `tests/test_bp6_console.py`

**Interfaces:**
- Produces: `Console.collect(seconds: float) -> str` — reads for `seconds`, sends nothing, returns the cleaned text (ANSI and ETX stripped). A main prompt in it does not end it early.
- Produces: a terminal recipe may have `risk="destructive"`; `recipe_commit` runs its `commit(con, options, prepared)` with the `Console` (wrapped in `_TripWatch`).
- Produces: `engine.CHANGE_NOTE = "this recipe makes a change: after the power yes it shows exactly what will change and stops; the change needs its own yes"` — used in place of `PREPARE_NOTE` when the recipe's `options` has no `"backup"` key.

- [ ] **Step 1: Write the failing tests**

In `tests/test_mcp_bp6_engine.py` replace `test_terminal_destructive_refused` with tests over a registered test recipe (`transport="terminal"`, `terminal_mode="dio"`, `risk="destructive"`, `check` returning `{"ok": True, "identity": opts.get("ident", "X")}`, `action` returning `{"chip": "c", "operation": "op", "start": 0, "length": 1, "summary": "s", "backup": None}`, `commit` recording that it ran and returning `{"done": True}`):
- `test_terminal_destructive_allowed`: constructing it raises nothing.
- `test_terminal_destructive_commit_runs_in_terminal`: plan → run returns `commit.token`; `commit_recipe` returns `committed is True` and the commit callable received an object with a `command` method.
- `test_terminal_commit_refused_after_mode_change` (Review Focus 2): after the run, switch the simulator to another mode (send `m i2c -s 400` through a console); `commit_recipe` returns an `error` starting `"plan again"` and the commit callable never ran.
- `test_terminal_commit_refused_on_identity_change`: the check's identity differs at commit → `"plan again"`, no commit.
- `test_change_note_without_backup_option`: the plan's `warnings` contain `CHANGE_NOTE`, not `PREPARE_NOTE`.

In `tests/test_bp6_console.py`:
- `test_collect_returns_text_after_prompt`: the fake port yields `"0x3b 0x9f "` after 0.05 s; `con.collect(0.3) == "0x3b 0x9f "` (strip-insensitive compare).
- `test_command_ends_at_inline_prompt_with_error` (Review Focus 1): the reply to `cat x` is `"cat x\r\n\x1b[...mError:\x1b[...m no file\x1b[0m" + "HiZ> \x03"`; `command` returns within 1 s, `reply.mode == "HiZ"`, `"Error: no file" in reply.text` and `reply.error` is that line.

- [ ] **Step 2: Run them, expect failures** (`pytest tests/test_mcp_bp6_engine.py tests/test_bp6_console.py -q`).

- [ ] **Step 3: Implement**
- `commit_recipe`: for `recipe.transport == "terminal"`, after `_power_error`, open `with bp.console() as raw: con = _TripWatch(raw, session)`; read the mode with `con.command("")` (as `_run_terminal`'s re-run does) and refuse unless it equals `recipe.terminal_mode or "hiz"` (case-insensitive); then the same check/identity/commit steps with `con`; map `TerminalError` to `{"error": ...}` and a trip to `session.power = None` as `_run_terminal` does. BPIO2 recipes keep today's path unchanged.
- `Console.command`: when no `\n<prompt>\x03` has arrived but `_INLINE_ETX_PROMPT` matches the tail, end there, keeping the text before the prompt as the reply's last body line (reuse the `_split(..., start)` idea).

- [ ] **Step 4: Run the full 3.9 suite**, expect all pass.
- [ ] **Step 5: Commit** `bp6-mcp: terminal recipes may make a change on its own yes; console collect and inline-prompt errors`

---

### Task 2: Smart card answer to reset (read-only)

**Files:**
- Create: `buspirate/devices/smartcard.py`, `buspirate/bp6/smartcard.py`, `buspirate/mcp_bp6/recipes/smartcard.py`
- Modify: `buspirate/mcp_bp6/recipes/__init__.py` (import), `buspirate/simulator_bp6.py` (HDUART mode)
- Test: `tests/test_bp6_smartcard.py`, `tests/test_mcp_bp6_recipes_3c.py`

**Firmware facts:** `m hduart -b <baud> -d 8 -p even -s 2 -l listen` sets every option with no prompt (`mode/hwhduart.c`, `-l listen` leaves the IO0 buffer as input). IO0 = RXTX, IO2 = RST. In HDUART bus syntax `}` = RST low (prints `RST LOW`), `{` = RST released high (`RST HIGH`), `[` = print received bytes as they arrive (`UART OPEN (ASYNC READ)`), `]` = stop (`UART CLOSE`). Received bytes print as `0x%02x ` at the prompt. `r` gives up too fast for an ATR: do not use it. Clock on IO1 with `signals.pwm_start` (phase 3a). ISO 7816: baud = clock / 372.

**Interfaces:**
- Produces: `devices.smartcard.parse_atr(data: bytes) -> Dict[str, Any]` with keys `convention` ("direct" for TS 0x3B, "inverse" for 0x3F, else error), `protocols` (sorted list of ints, T=0 when no TD1), `historical` (hex string), `historical_text` (printable ASCII or ""), `ta1` (int or None), `tck_ok` (bool or None when no TCK expected), `complete` (bool: all announced bytes present). Raises `ValueError` on empty data or a bad TS.
- Produces: `bp6.smartcard.read_atr(con, clock_hz: int, wait_s: float) -> Dict[str, Any]`: `pwm_start(con, 1, clock_hz, 50)`, `}` , `[`, `{`, then `con.collect(wait_s)` (+ text after the `{` prompt), then `]`; returns `{"bytes": "3B 9F ...", "atr": parse_atr(...) or None, "clock_hz": actual}`; with no bytes returns `{"bytes": "", "atr": None, "error": "no answer from the card: check that it is inserted and the wiring"}` (Review Focus 5). Always sends `]` and `g 1` at the end, even on error (`try/finally`).

- [ ] **Step 1: Write the failing tests**
- `parse_atr(bytes.fromhex("3B9F96801FC78031E073FE211B6407689A00820190"))` (a SIM): convention "direct", `0 in protocols`, `complete` True. `parse_atr(bytes.fromhex("3B00"))`: `protocols == [0]`, `historical == ""`. `parse_atr(b"\x12")` raises `ValueError`. A T=1 ATR with a wrong TCK gives `tck_ok is False`.
- `read_atr` against the simulator with `sim.card_atr = bytes.fromhex("3B00")`: `bytes == "3B 00"`; the terminal received `G 1`, `}`, `[`, `{`, `]`, `g 1` in that order.
- No card (`sim.card_atr = b""`): the `error` above, and `]` was still sent.
- Recipe `smartcard-atr` through plan → run on the simulator: result has `atr.convention == "direct"`.

- [ ] **Step 2: Run, expect failures.**
- [ ] **Step 3: Implement.** Recipe: `name="smartcard-atr"`, title "Smart card (SIM or bank card): read its answer to reset", words `("sim", "smartcard", "smart", "card", "atr", "iso7816", "bank", "chip card")`, `bus="uart"`, `transport="terminal"`, `terminal_mode="hduart"`, `terminal_flags="-b 9600 -d 8 -p even -s 2 -l listen"`, `default_mv=3000`, `min_mv=1800`, `max_mv=5000`, `milliamps=100`, `pullups=True`, `target_powered_ok=False`, options `{"clock_hz": 3_571_200, "wait_s": 1.0}`, wiring `(("C7 I/O", "IO0"), ("C3 CLK", "IO1"), ("C2 RST", "IO2"), ("C1 VCC", "VOUT"), ("C5 GND", "GND"))`, source `https://docs.buspirate.com/docs/devices/sim-bank-ic-cards/`. The check refuses unless `clock_hz` is 1–5 MHz and `round(clock_hz/372)` is within 2 % of 9600 (the baud is fixed by `terminal_flags`). Notes: "cards are 5 V (class A), 3 V (B) or 1.8 V (C): use the card's class; 3 V suits most SIMs", "read-only: this never sends a command or a PIN to the card". The action calls `read_atr` and records IO1 in `state.of(con.session).pwm_pins` only while running (it stops the clock itself). Simulator: add `"HDUART"` to `TERMINAL_MODES`; in HDUART, `}`/`{`/`[`/`]` answer with the strings above; after `{` while printing is on, say `card_atr` as `0x%02x ` text after the prompt.
- [ ] **Step 4: Full 3.9 suite passes.**
- [ ] **Step 5: Commit** `bp6-mcp: smart card answer to reset (read-only)`

---

### Task 3: USB-PD plank

**Files:**
- Create: `buspirate/bp6/usbpd.py`, `buspirate/mcp_bp6/recipes/usbpd.py`
- Modify: `buspirate/mcp_bp6/recipes/__init__.py`, `buspirate/simulator_bp6.py` (`usbpd` in I2C mode)
- Test: `tests/test_bp6_usbpd.py`, `tests/test_mcp_bp6_recipes_3c.py`

**Firmware facts** (`commands/i2c/usbpd.c`, AP33772S at I2C 0x52, an I2C-mode command): `usbpd status|request|reset`, flags `-p <index>`, `-v <mV>` (PPS/AVS only), `-i <mA>`. Status prints `Source      : PD source connected` (or `Legacy source connected` / `No source detected`), `CC line     : …`, `Data role   : …`, `De-rating   : …`, `VBUS voltage: %d mV`, `VBUS current: %d mA`, `Requested V : %d mV`, `Requested I : %d mA`, `Temperature : %d C`, blank, `Available PDO entries: %d`, then per PDO `PDO %d (SPR|EPR Fixed): %d mV, %d-%d mA[, NNN% peak]` or `PDO %d (SPR|EPR PPS|AVS): <min desc> to %d mV, %d-%d mA` (min desc such as `>=3300 mV`, `>3300 mV and <=5000 mV`, `>=15000 mV`, `>15000 mV and <=20000 mV`, `reserved`). Request prints `Requesting PDO %d, %dmV @ %dmA`, then `PD request accepted|rejected|failed|pending|unknown (PD_MSGRLT=0x%02X)`, optionally `Negotiated voltage: %d mV`, then the measurements. Failures: `Failed to refresh PDO list`, `Failed to request PDO %d`, `Invalid PDO index specified: %d`, `Requested voltage … out of range …`, `Requested current … out of range …`. Reset prints `PD hard reset sent successfully` or `Failed to send PD hard reset`. None of these set the error flag. A fixed PDO is always requested at its own voltage.

**Interfaces:**
- Produces: `bp6.usbpd.parse_status(text: str) -> Dict[str, Any]`: `source`, `vbus_mv`, `vbus_ma`, `requested_mv`, `requested_ma`, `temperature_c` (each None when absent), `pdos`: list of `{"index", "domain", "type", "min_mv", "max_mv", "min_ma", "max_ma"}` (fixed: `min_mv == max_mv`; PPS/AVS `min_mv` from the description: `>=3300`→3300, `>3300 … <=5000`→5000, `>=15000`→15000, `>15000 … <=20000`→20000, `reserved`→`max_mv`).
- Produces: `status(con) -> Dict`, `request(con, pdo: int, mv: Optional[int], ma: Optional[int]) -> Dict` (`accepted: bool`, `result` word, `vbus_mv`, `negotiated_mv`), `reset(con) -> Dict` (`sent: bool`). Each raises `TerminalError` on a `Failed …` line.

- [ ] **Step 1: Write the failing tests**
- `parse_status` over a captured block with three PDOs (Fixed 5000 mV 0-3000 mA; Fixed 9000 mV 0-3000 mA; PPS `>=3300 mV to 21000 mV, 0-3000 mA`) returns those values; `source == "PD source connected"`.
- Recipes on the simulator (`sim.usbpd_pdos` set to those three):
  - `usbpd-status` run: `result["pdos"]` has 3 entries.
  - `usbpd-request` with `{"pdo": 2}`: run stops with `commit.summary` containing `"9000 mV"` and `"3000 mA"`; `recipe_commit` → `committed True`, `result.vbus_mv == 9000`; the simulator saw `usbpd request -p 2 -i 3000`.
  - `{"pdo": 3, "pd_mv": 12000}` → line `usbpd request -p 3 -v 12000 -i 3000`. `{"pdo": 3}` (no `pd_mv`) and `{"pdo": 3, "pd_mv": 22000}` → the check fails, no token. `{"pdo": 9}` → the check fails naming the 3 offers.
  - Review Focus 3: prepare with the three PDOs, then change `sim.usbpd_pdos`; `recipe_commit` → `"plan again"`, the simulator saw no `request`.
  - The source rejects (`sim.usbpd_result = "rejected"`) → `committed False`.
  - `usbpd-reset` run → `sent True`.
- [ ] **Step 2: Run, expect failures.**
- [ ] **Step 3: Implement.** Shared recipe fields: `bus="i2c"`, `transport="terminal"`, `terminal_mode="i2c"`, `terminal_flags="-s 400"`, `default_mv=3300`, `min_mv=3000`, `max_mv=3600`, `milliamps=100`, `pullups=True`, wiring `I2C_WIRING` imported from `recipes/i2c.py`, source `https://docs.buspirate.com/docs/overview/usbpd-adapter/`. Check for all three: `usbpd status`; fails with a hint about the plank and the USB-C source when `source` is "No source detected" or there are no PDOs; `identity` = the PDO lines joined with `|`. `usbpd-request` (`risk="destructive"`, options `{"pdo": None, "pd_mv": None, "pd_ma": None}`): the check also validates the options against the PDO list (PPS/AVS need `pd_mv` within `min_mv..max_mv`; `pd_ma` within `min_ma..max_ma`, default `max_ma`); the action returns `chip="USB-PD source"`, `operation="request"`, `start=pdo`, `length=0`, `backup=None`, `summary="Ask the USB-PD source for <mv> mV at up to <ma> mA (PDO <n>, <domain> <type>). The plank's output pins carry this voltage until usbpd-reset or the source is unplugged; hiz does not change it."`; commit calls `request` and returns `verified = accepted and abs(vbus_mv - mv) <= max(500, mv // 20)`. Notes on all three: "the plank's output can reach 28 V; hiz and the Bus Pirate's supply do not switch it off". Simulator: in I2C mode answer `usbpd status|request|reset` in the formats above from `usbpd_pdos`, `usbpd_result` and the last request.
- [ ] **Step 4: Full 3.9 suite passes.**
- [ ] **Step 5: Commit** `bp6-mcp: USB-PD plank status, request (own yes) and reset`

---

### Task 4: The Bus Pirate's disk

**Files:**
- Create: `buspirate/bp6/disk.py`, `buspirate/mcp_bp6/recipes/disk.py`
- Modify: `buspirate/mcp_bp6/recipes/__init__.py`, `buspirate/simulator_bp6.py` (`ls`, `cat`, `hex`, `rm` in every mode)
- Test: `tests/test_bp6_disk.py`, `tests/test_mcp_bp6_recipes_3c.py`

**Firmware facts** (`commands/global/disk.c`, `hex.c`, `pirate/storage.c`): FAT short names only, names printed lower case, paths up to 31 characters. `ls -l [dir]` prints directories first as `       -  YYYY-MM-DD HH:MM  name/`, then files as `%8u  YYYY-MM-DD HH:MM  name`, then `N dirs, M files`; a missing directory prints nothing and sets the error flag. `cat <file>` prints the text line by line (a `%` in the file is mangled: it is printed with `printf(file)`). `hex <file> -s <start> -b <bytes> -c` prints rows `%08X  ` + up to 16 `%02x ` + ` |ascii|`. `rm <file>` deletes with no prompt. File errors print `Error: <reason>` with no line ending (e.g. `no file`, `no path`, `denied`).

**Interfaces:**
- Produces: `bp6.disk.check_path(path: str, directory: bool = False) -> str` (normalised; raises `ValueError` for empty, >31 characters, characters outside `A-Za-z0-9_-~./`, a component that is not 8.3, `..`, or for a file a trailing `/`) — Review Focus 4.
- Produces: `listing(con, path: str = "/") -> Dict` → `{"path", "dirs": [names], "files": [{"name", "size", "date"}]}`; `show(con, path, max_chars: int = 16384) -> Dict` → `{"text", "truncated"}`; `hexdump(con, path, start: int = 0, length: int = 256) -> Dict` → `{"start", "data_hex", "length"}` (length 1–4096); `delete(con, path) -> Dict` → `{"deleted": True}`. Each raises `TerminalError` with the firmware's `Error: …` text.

- [ ] **Step 1: Write the failing tests**
- `check_path`: `"BPCONFIG.BP"` and `"/dumps/flash.bin"` pass; `"a b.txt"`, `"x;rm y"`, `"longfilename.txt"`, `"a/../b"`, `"/" + "a" * 31` raise.
- On the simulator with `sim.disk = {"bpconfig.bp": b'{"a":1}\n', "dumps/flash.bin": bytes(range(40))}`: `listing(con, "/")` gives `dirs == ["dumps"]`, one file of 8 bytes; `hexdump(con, "dumps/flash.bin", 16, 16)["data_hex"] == bytes(range(16, 32)).hex()`; `show` returns the JSON text; `show` of a missing file raises `TerminalError` containing `no file` (relies on Task 1's inline prompt).
- Recipes: `disk-list`, `disk-show`, `disk-hex` run with no supply (`max_mv=0`); `disk-delete` with `{"path": "bpconfig.bp"}` stops with `commit.summary` naming the file and its size; `recipe_commit` deletes it (`"bpconfig.bp" not in sim.disk`). Deleting a directory or a missing file fails at the check, with no token.
- [ ] **Step 2: Run, expect failures.**
- [ ] **Step 3: Implement.** Recipes: `bus="board"`, `transport="terminal"`, `terminal_mode=None`, `min_mv=max_mv=default_mv=0`, `milliamps=0`, `pullups=False`, `wiring=()`, source `https://docs.buspirate.com/docs/command-reference/`. Options: list `{"path": "/"}`; show `{"path": None, "max_chars": 16384}`; hex `{"path": None, "start": 0, "length": 256}`; delete `{"path": None}` with `risk="destructive"`. The delete check lists the parent directory and requires the name to be a file there; `identity = "<path>:<size>:<date>"`. The action returns `chip="Bus Pirate disk"`, `operation="delete"`, `start=0`, `length=size`, `backup=None`, `summary="Delete <path> (<size> bytes) from the Bus Pirate's disk. It cannot be undone; copy it from the Bus Pirate's USB drive first if it is needed."`. Notes: "the computer sees the disk read-only while the terminal is in use", and on show "use disk-hex for binary files". Words for each so `recipes("disk")`, `recipes("files")` and `recipes("delete file")` find them.
- [ ] **Step 4: Full 3.9 suite passes.**
- [ ] **Step 5: Commit** `bp6-mcp: the Bus Pirate's disk: list, show, hex and delete (own yes)`

---

### Task 5: Instructions, notes, docs and the final check

**Files:**
- Modify: `buspirate/mcp_bp6/server.py` (`INSTRUCTIONS`), `buspirate/mcp_bp6/notes/bp6.md`, `docs/mcp.md`
- Test: existing server/notes tests (`tests/test_mcp_bp6_server.py`)

- [ ] **Step 1:** Add to `INSTRUCTIONS`: "- A USB-PD request and a disk delete stop and return `commit`; read its `summary` (it names the voltage or the file) and call `recipe_commit` only after a second yes." and "- The USB-PD plank's output stays at the requested voltage after `hiz`; run `usbpd-reset` to bring it back to 5 V."
- [ ] **Step 2:** `notes/bp6.md`: under "Not automated", add one line each with its reason: macros/scripts (any byte received aborts a run; pauses end only on the button), `bridge` (ends only on the button), `fusb302 scan` (interactive), `format`/`edit`/`hexedit`, UART `glitch` and `sle4442` (left out of 3c, source not reviewed). Under "Unverified on a real board", add: HDUART listen mode receives the card's ATR; the PWM clock on IO1 runs alongside HDUART on IO0; RST on IO2 idles low after `}`; whether the USB-PD plank needs VOUT from the Bus Pirate or feeds it; each firmware disk write ejects and re-mounts the USB drive (possible hang). Keep every line ≤100 characters.
- [ ] **Step 3:** `docs/mcp.md`: list the eight new recipes in the BP6 recipe table, with the two-yes note for `usbpd-request` and `disk-delete`.
- [ ] **Step 4:** Run all three suites (3.9, 3.13, 3.8 commands above); then a stdio smoke test against `buspirate mcp-bp6 --demo`: `recipes("usb-pd")`, `recipes("disk")`, `recipes("sim")` each find their recipes, and `recipe_plan("disk-list")` returns a plan with no supply.
- [ ] **Step 5: Commit** `bp6-mcp: phase 3c instructions, notes and docs`
