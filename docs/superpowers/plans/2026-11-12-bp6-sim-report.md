# BP6 SIM report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One recipe, `sim-report`, that reads a SIM card read-only and returns a business-level report: who issued it, which operator and country, the subscriber and card identities, and what the operator has enabled, in plain words, with no SIM knowledge needed from the owner.

**Architecture:** A T=0 command layer over the HDUART terminal in listen mode (`buspirate/bp6/sim.py`) that can only send an allow-list of read-only commands; decoders that turn each SIM file into named fields (`buspirate/devices/sim.py`, with bundled country/operator tables); one recipe (`buspirate/mcp_bp6/recipes/sim.py`) that runs everything and assembles the report. A PIN, if the owner gives one, goes through the existing two-yes commit flow and is tried exactly once.

**Tech Stack:** Python ≥3.8, pytest, `Console` (`buspirate/bp6/console.py`), the recipe engine with terminal commits (phase 3c Task 1), `FakeBp6` simulator.

**Builds on:** phase 3c (branch `bp6-phase3c`): `smartcard-atr`, `bp6/smartcard.py` (`read_atr`, clock on IO1, `BAUD`), `devices/smartcard.py` (`parse_atr`), terminal destructive recipes. Start this branch from main after 3c is merged.

## Design (owner decisions 2026-11-12, then Claude's calls)

Owner:
- **The report is for business use.** No SIM knowledge needed: one recipe, no file names or codes to choose. The top of the result is a plain summary (operator, country, brand, identities, capabilities); the raw values sit underneath.
- **Operator and network information only.** No contacts, SMS, own phone number (MSISDN) or call records are read.
- **Part of the SIM card plank.** The SIM report belongs to the IC card and SIM adapter plank: asking for the plank (or "SIM") offers it, and its wiring step is "plug the plank in, switches on VCC:VOUT and GND:GND, card in a socket" rather than five wires.
- **PIN support:** if the SIM PIN is on, PIN-protected files are listed as locked unless the owner gives the PIN; then the plan shows the attempts left, the PIN needs its own yes, and it is tried exactly once, never retried.

Claude's calls:
- Read-only by construction: the command layer refuses any instruction outside SELECT (`A4`), READ BINARY (`B0`), READ RECORD (`B2`), GET RESPONSE (`C0`), STATUS (`F2`), and VERIFY (`20`) — VERIFY only through `verify_pin_once`, and its no-data form (attempts left) only through `pin_status`.
- Listen mode for both directions: the firmware claims IO0 only while it sends a byte and releases it at once (`pirate/hwuart_pio.c`, `hwuart_pio_write` with `cfg->listen`), as a SIM expects. No speed change (no PPS): 9600 baud throughout.
- GSM commands (class `A0`, DF `7F20`) first, which almost every SIM still answers; if the card refuses them, the UICC/USIM route (class `00`, the USIM application from `EF_DIR`).
- The PIN is refused when only one attempt is left (a wrong PIN would block the SIM until its PUK). It never appears in a result, a log or an error.
- The secret key (Ki) and authentication keys cannot be read from any SIM; the report says so instead of leaving a gap.
- Operator names: MCC → country from the ITU E.212 list; MCC+MNC → operator from a bundled table whose licence allows redistribution (Task 2 picks it and records the source). The SIM's own provider name (SPN) is shown beside it.

## Global Constraints

- Python 3.8 compatible; never send Ctrl-C; terminal lines ≤256 characters; terminal voltages in 10 mV steps.
- No instruction outside the allow-list is ever sent; no UPDATE, no write of any kind, no PIN change, no PUK, no authentication (`88`).
- A PIN attempt only on `recipe_commit` after its own yes, once; never automatically retried; refused at 1 attempt left.
- Not read: `EF_ADN`, `EF_SMS`, `EF_MSISDN`, `EF_FDN`, `EF_SDN`, call or message logs.
- Every value in the report has a plain-English label; codes are kept only in the `raw` section.

## Review Focus

1. A card that answers GSM `A0` commands with `6E 00` (class not supported): the USIM route takes over, the report is the same shape. Test in Task 1/4.
2. A file that does not exist on this card (`6A 82` / `94 04`): the field shows "not on this card", the report continues. Test in Task 3.
3. A wrong PIN: the result says how many attempts are left now, nothing is retried, and the protected fields stay "locked". Test in Task 4.
4. A card pulled mid-read (no bytes): a clear error, clock and async print off. Test in Task 1.
5. A 2-digit vs 3-digit MNC (from `EF_AD`): the operator lookup uses the right split. Test in Task 2.

---

### Task 1: T=0 command layer (read-only allow-list) and the simulated SIM

**Files:** Create `buspirate/bp6/sim.py`, `tests/test_bp6_sim.py`; modify `buspirate/simulator_bp6.py` (a `FakeSim` behind HDUART in listen mode).

**Interfaces:**
- Produces: `class SimLink` opened with `SimLink.open(con, clock_hz)` (clock on IO1, reset, ATR via `bp6.smartcard`, async print on) and `close()` (async print off, clock off; always, in `finally`); `link.command(cla, ins, p1, p2, data=b"", le=None) -> Tuple[bytes, int]` (response data, status word) handling T=0 procedure bytes: INS / ~INS acknowledgements, `60` (wait), `61xx`/`9Fxx` (GET RESPONSE), `6Cxx` (repeat with Le); `link.select(fid: int)`, `link.read_binary(length)`, `link.read_record(n, length)`; `pin_status() -> Dict` and `verify_pin_once(pin: str) -> Dict`.
- `command` raises `ValueError` for any INS outside `{0xA4, 0xB0, 0xB2, 0xC0, 0xF2}`; `0x20` is reachable only through the two PIN functions.

- [ ] **Step 1 (research, write it into the plan's research doc before code):** from the firmware source (commit e2429e0c): how a bus-syntax write (`0xA0 0xA4 …`) is echoed in the terminal in HDUART mode, and how that echo is told apart from received bytes (`0x%02x ` printed by `hwhduart_periodic`); whether a write while async print is on interleaves the two. Decide the send format (one line per command header, one per data block) and record it.
- [ ] **Step 2: failing tests:** SELECT `3F00` then `2FE2` then READ BINARY 10 against `FakeSim` returns the ICCID bytes and `0x9000`; `61 xx` and `9F xx` trigger GET RESPONSE; `6C xx` repeats with the new Le; INS `0xD6` (UPDATE BINARY) raises `ValueError` before anything is sent (the simulator saw no line); a card that stops answering raises `TerminalError` and the simulator saw `]` and `g 1`.
- [ ] **Step 3: implement**, **Step 4: full 3.9 suite**, **Step 5: commit** `bp6: read-only T=0 command layer for SIM cards`.

### Task 2: Decoders and the operator tables

**Files:** Create `buspirate/devices/sim.py`, `buspirate/devices/data/mcc_mnc.csv` (+ its source and licence in a header line), `tests/test_devices_sim.py`.

**Interfaces:** `decode_iccid(b) -> {"iccid", "luhn_ok", "industry", "country", "issuer_id"}`; `decode_imsi(b, mnc_digits) -> {"imsi", "mcc", "mnc", "msin"}`; `mnc_digits(ef_ad: bytes) -> int` (2 or 3; 2 when absent); `decode_spn(b) -> {"name", "show_on_phone"}`; `decode_plmn_list(b, with_act: bool) -> List[{"mcc", "mnc", "operator", "country", "technologies": [...]}]`; `decode_service_table(b, kind: "sst"|"ust") -> List[{"number", "name", "enabled"}]` (names from 3GPP TS 51.011 §10.3.7 and TS 31.102 §4.2.8); `decode_loci(b)`, `decode_psloci(b)`, `decode_epsloci(b)` (last network, area code, technology); `decode_acc(b) -> List[int]`; `decode_dir(records) -> List[{"aid", "application"}]` (USIM, ISIM, …); `operator(mcc, mnc) -> Optional[str]`; `country(mcc) -> Optional[str]`.

- [ ] **Step 1: failing tests** with byte vectors from the 3GPP specs: ICCID `98 94 …` (swapped BCD) with a valid Luhn digit; IMSI with a 3-digit MNC (`EF_AD` byte 4 = 3) and a 2-digit one (Review Focus 5); a PLMN `62 F2 10` = MCC 262 MNC 01; UST bit 1 = "local phone book"; an empty PLMN `FF FF FF` is skipped; `operator("228", "01")` is a name (from the table), `country("228") == "Switzerland"`.
- [ ] **Step 2: pick the operator table**: a source whose licence permits bundling (record URL and licence in the CSV header); the country list from ITU E.212. If no acceptable operator source exists, ship countries only and show the SIM's SPN plus the codes — record the ruling.
- [ ] **Steps 3–5:** implement, full suite, commit `devices: SIM file decoders with operator and country names`.

### Task 3: The report

**Files:** Create `buspirate/mcp_bp6/recipes/sim.py`; modify `recipes/__init__.py`; tests in `tests/test_mcp_bp6_recipes_sim.py`.

**Interfaces:** `build_report(link) -> Dict` reads, in order: `EF_ICCID 2FE2`, `EF_DIR 2F00`, `EF_PL 2F05` (no PIN); then under DF GSM `7F20` or the USIM application: `EF_SPN 6F46`, `EF_AD 6FAD`, `EF_IMSI 6F07`, `EF_SST/UST 6F38`, `EF_HPPLMN 6F31`, `EF_PLMNwACT 6F60`, `EF_OPLMNwACT 6F61`, `EF_HPLMNwACT 6F62`, `EF_EHPLMN 6FD9`, `EF_FPLMN 6F7B`, `EF_LOCI 6F7E`, `EF_PSLOCI 6F73`, `EF_EPSLOCI 6FE3`, `EF_ACC 6F78`. Result shape:
`{"summary": {"operator", "country", "brand_on_phones", "iccid", "imsi", "card_type" ("SIM"|"USIM"), "pin": "off"|"on, N attempts left"|"blocked", "home_network", "capabilities": [plain phrases such as "4G (LTE)", "5G", "voice over LTE", "SMS over IP", …], "preferred_roaming": [operator (country)], "blocked_networks": [...], "last_network": "...", "not_readable": ["secret key (Ki) and authentication keys — no SIM allows reading them", …locked fields]}, "raw": {file: hex}}`.

- [ ] **Step 1: failing tests** on `FakeSim` profiles: GSM SIM with PIN off (full summary); USIM that refuses class `A0` (Review Focus 1, same summary keys); PIN on (protected fields listed under `not_readable` as "locked by the SIM PIN", ICCID/SPN still shown); a missing `EF_EHPLMN` (Review Focus 2: "not on this card"); no `EF_ADN/SMS/MSISDN` select ever sent.
- [ ] **Steps 2–5:** run, implement, full suite, commit `bp6-mcp: sim-report: a business summary of a SIM card`.

### Task 4: The PIN, once, on its own yes

**Files:** modify `recipes/sim.py`, the tests.

- `sim-report` options `{"pin": None}`. With no PIN it runs straight through (risk `none`: it only reads). With a PIN it is `risk="destructive"` in the engine's sense: the action reads the PIN status and stops with `summary="Try the SIM PIN once. The SIM has N attempts left; a wrong PIN leaves N-1, and at 0 the SIM is blocked until its PUK is entered."`, identity = ICCID + attempts left; the commit calls `verify_pin_once`, then `build_report`. Refuse in the check when attempts left ≤1 or the PIN is not 4–8 digits. Implementation detail for the implementer: since one recipe cannot be both, register two recipes sharing the code: `sim-report` (no PIN option) and `sim-report-pin` (destructive, `pin` required).
- [ ] **Tests:** right PIN → full report, `pin: "on, verified"`; wrong PIN → `committed False`, result says attempts left now (Review Focus 3), simulator saw exactly one VERIFY; attempts left 1 → refused at the check, no VERIFY sent; the PIN string appears in no result, error or plan.
- [ ] **Commit** `bp6-mcp: sim-report-pin: one PIN attempt on its own yes`.

### Task 5: The SIM card plank, instructions, notes, docs

- `Recipe` gains `plank: Optional[str] = None` and a `PLANKS` table in `recipes/__init__.py`: `"sim-iccard": {"name": "IC card and SIM adapter plank", "setup": ("plug the plank into the Bus Pirate's main header", "set the switches to VCC:VOUT and GND:GND", "put the card in the mini, micro or nano SIM socket (or a smart card in the socket on the back)"), "source": "https://docs.buspirate.com/docs/overview/sim-iccard-adapter/"}`. `smartcard-atr`, `sim-report` and `sim-report-pin` set `plank="sim-iccard"`. `recipe_plan` shows the plank's setup steps in place of the per-wire wiring when `plank` is set; `recipes("sim plank")`, `recipes("plank")` and `recipes("sim")` list the three, `sim-report` first. Tests: the plan's wiring for each is the three setup steps; `find_recipes("plank")` returns exactly the plank's recipes.

- INSTRUCTIONS: "For a SIM card run `sim-report`: it reads only, and its `summary` is what to show the owner. Run `sim-report-pin` only if the owner offers the PIN; read the attempts left to them and ask before the commit."
- `notes/bp6.md`: the allow-list, the never-read files, the 1-attempt refusal; Unverified: the T=0 timing through the terminal on a real card, the USIM fallback.
- `docs/mcp.md`: the two recipes.
- Run all three suites and a `--demo` smoke; then, with the owner's yes, run `sim-report` on the owner's SIM (PIN not given) and record what came back (no personal values in the notes).
