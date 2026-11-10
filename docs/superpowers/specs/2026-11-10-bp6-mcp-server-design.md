# Bus Pirate 6 MCP server — design

Date: 2026-11-10. Status: draft for the owner's approval.
Research behind it: `docs/superpowers/research/2026-11-10-bp6-use-cases.md` (74 BP6 capabilities and
use cases from docs.buspirate.com, with coverage and effort). Builds on the stage 1 server
(`docs/superpowers/specs/2026-11-09-buspirate-mcp-design.md`, `buspirate/mcp/`).

## 1. Why

The universal server works (verified on a real BP6 on 2026-11-10: power, I2C scan, `lcd_write` on a
16x2 LCD), but using it felt "exactly the same as before". Getting a known LCD to show text took about
eight tool calls and three questions, and almost all of it is the same every time: read the board notes,
find and connect, wiring, ask the voltage, plan power, a second confirmation because 5 V is above 3.6 V,
apply, scan, write.

The owner wants:

- **A server for the Bus Pirate 6 only.** It narrows the field: no board detection, no v3/v4/Bit Pirate
  notes or branches, fewer tools and less text for Claude to read. A combined v3/v4 server and a Bit
  Pirate server follow later, as separate projects.
- **Recipes.** "Get this LCD working" should need one yes: everything (bus, address, voltage, current
  limit, pull-ups, wiring, the job itself) is pre-configured, and only power-on waits for the owner.
- **The full capability of the BP6**, as documented on docs.buspirate.com (the Dangerous Prototypes
  wiki blocks automated reads; docs.buspirate.com is the official BP5/BP6 documentation).

Success: the owner names a thing ("the LCD", "this flash chip", "a DS18B20", "what is this chip?") and
Claude shows the wiring and the power plan in one message; after one yes the job is done and the answer
is in real units or plain words.

## 2. Goals, non-goals, anti-goals

Goals
- A separate MCP server, `buspirate mcp-bp6`, registered as `bp6` (real board) and `bp6-demo`
  (simulated BP6, `--demo`).
- A recipe for every documented BP6 use case that can be done safely, delivered in phases (section 6).
- Every BP6 capability reachable: over the binary interface (BPIO2) where it exists, otherwise through
  the BP6's text terminal.
- One confirmation for a recipe's power-on, at the voltage the recipe names.

Non-goals
- The v3/v4 and Bit Pirate servers (later projects; this design only keeps the shared code shareable).
- Replacing PulseView, flashrom or avrdude. Where those tools own the job, the recipe prepares the board
  (binmode) and tells the owner what to run.
- Programming the VPP SMPS plank (high voltage, still in development upstream): knowledge note only.

Anti-goals (would make it a failure even if it works)
- Power switched on without the owner's yes, or at a voltage other than the one shown.
- A destructive action (flash or EEPROM erase/write, DDR SPD write, SLE4442 passcode attempt) run as
  part of the same yes as power-on.
- Breaking the universal `buspirate` server or the desktop app while it is still the only server for
  v3/v4/Bit Pirate.
- Claude having to read long notes before it can act: the server's instructions stay short.

## 3. Constraints

- Core code stays Python 3.8-clean; only the server module imports the `mcp` SDK (needs 3.10+), same as
  stage 1. Registered through `uv run --isolated --python 3.13 ... [mcp]` like the existing servers.
- BPIO2 is one of several mutually exclusive binmodes on the BP6's second USB serial port. SUMP
  (PulseView), follow-along logic analyser, Legacy (flashrom/avrdude) and AnalysIR take the same port.
  The terminal is the first port. Only one path talks to the board at a time.
- Board limits (bp6rev2): supply 0.8–5.0 V, 300 mA rated, current limit 0–500 mA; IO 1.2–5 V; 10 kΩ
  pull-ups on every pin, powered from VOUT/VREF; frequency measure only on IO1/3/5/7; adjacent PWM pins
  share a frequency.
- Leaving a mode on the BP6 keeps the supply on; `close()` puts it in HiZ (supply off). A recipe that
  must keep a display lit must not close the board while the session runs.
- **When the server exits (owner's decision), the supply goes off:** the board goes to HiZ, so the supply
  and pull-ups are off and an LCD loses its text. Power never outlives the Claude Code session. Because a
  freshly started server never inherits a powered board, connecting on first use may reset the board to
  HiZ.

## 4. How it works (decided)

### 4.1 Shape

- New package `buspirate/mcp_bp6/`, a thin layer over the stage 1 core: `session`, `power`, `confirm`,
  `wiring`, `jobs` and `knowledge` are reused, not copied. Anything that is BP6-specific moves behind a
  parameter rather than a fork, so the later v3/v4 and Bit Pirate servers reuse the same core.
- The server knows it is talking to a BP6. All its tools are listed from the start, and there is no
  `find_boards`. It connects on first use, not at start-up, so registering it next to the `buspirate`
  server or opening the desktop app doesn't fight over the port. If the port is busy, the tool says which
  program to close. With two BP6s plugged in, it uses the first one found and `connect(port)` can pick
  another (Claude's call).
- Its instructions to Claude are a few lines: use a recipe when one matches; show wiring and the plan
  in one message; never apply power without a yes; destructive steps need their own yes.

### 4.2 Recipes

A recipe is data, one entry per use case, in `buspirate/mcp_bp6/recipes/` (one module per bus):

- name and the words people use for it ("lcd", "character display", "1602", "hd44780")
- mode and settings (speed, address, SPI mode, baud…)
- voltage: default, allowed range, and a hard maximum (e.g. SHT4x 3.6 V); current limit
- pull-ups on/off
- wiring: target pin → BP6 pin and cable colour (from the existing wiring tables)
- check: how to confirm the target is there (I2C address answers, JEDEC ID reads, 1-Wire presence…)
- action: the job, and what it returns in real units or plain words
- risk: `none`, `destructive` (needs its own yes), or `owner-only` (e.g. keyboard sniffers: Claude asks
  the owner to confirm the device is theirs)
- transport: `bpio2` or `terminal`
- source: the docs.buspirate.com page it comes from

Tools:

- `recipes(query)` — finds matching recipes by name or words; with no query, lists them by bus.
- `recipe_plan(name, options)` — returns, in one result: the wiring steps, the power plan (voltage,
  limit, pull-ups) with a confirmation token, what the action will do, and any warnings. Options let the
  owner override the voltage or address within the recipe's allowed range.
- `recipe_run(token, options)` — applies the planned power, runs the check, then the action. If the
  check fails it stops and says what to look at (wiring, address, contrast for an LCD…), leaving power
  on so the owner can fix and re-run with `recipe_run(token=None, …)` on the same session.

Target power (Claude's call, see section 8): `recipe_plan` always measures VOUT and IO0–IO7 first.
- Nothing there: the plan proposes the recipe's default voltage, and the owner's yes is the stated
  voltage that stage 1 requires.
- A voltage is already present (the target has its own power): the plan switches to *target-powered*.
  The supply stays off, the measured voltage is the reference, and pull-ups run from VOUT if it is wired.
  The plan says so. A measured voltage outside the recipe's range is refused, with the reason.
- "Identify an unknown chip": never guesses a voltage. If nothing is measured, it asks the owner, offering
  3.3 V as the usual choice.

Re-running (Claude's call): `recipe_run(token=None)` may re-run the check and the action only while the
supply is still on at the planned voltage, within the token's 5 minutes. It never switches power back on
and never changes the voltage or address. Anything else needs a fresh `recipe_plan`.

Confirmation rule: the recipe's plan names the voltage and the current limit, so the owner's one yes
covers power-on even above 3.6 V. A voltage the owner overrides above the recipe's default, or any plan
with no current limit, still asks twice (the stage 1 rule). Tokens stay single-use and expire after
5 minutes. A `destructive` action never runs on the power yes: `recipe_run` stops before it and returns
a second token that names exactly what will be erased or written (and, where possible, a backup is taken
first).

### 4.3 Primitive tools

Kept for ad-hoc work and for recipes to build on: `board_status`, `wiring`, `measure_voltages`,
`power_plan`/`power_apply`/`power_off`, `hiz`, `i2c_scan/read/write`, `spi_transfer`, `uart_send/listen`,
`onewire_scan`, plus BP6 primitives that are missing today: pin direction/value (DIO and aux pins), pin
voltages, onboard LEDs (all over BPIO2, phase 1). Pin voltages come from the BPIO2 status. `pwm` and
`frequency` need the terminal, so they arrive in phase 3. The BP6 support for all of these lives in
`mcp_bp6`, and the shared driver's capability gating is left alone, so the universal server doesn't
change before phase 4 (Claude's call).

### 4.4 The terminal path

For capabilities BPIO2 lacks (PWM, frequency, sniffers, blueTag, IR, logic analyser, scope, GPS, glitch,
macros, disk, self-test report, the binmodes for PulseView/flashrom/avrdude), the server drives the BP6
text terminal (first USB port) using the existing `bp6/terminal.py` and `release_to_terminal()`:

- one lock serialises BPIO2 and terminal use; switching back re-selects BPIO2;
- each terminal recipe sends a fixed, known command sequence and parses the output it expects;
- long-running jobs (sniffers, logic capture) have a time limit and are stopped by `hiz`.

### 4.5 Knowledge

The BP6 notes shrink to what Claude needs while running recipes: limits, pin map, the pull-up rule,
risks. Each recipe carries its own docs.buspirate.com source link. The research catalogue is not loaded
by the server.

## 5. Safety rules per risk (decided)

- SHT4x and anything with a lower hard maximum: the recipe caps the supply at that maximum.
- SPI/I2C EEPROM, FRAM and flash erase or write: separate yes naming the chip, address range and size;
  read a backup to the owner's disk first unless the owner declines.
- DDR4/DDR5 SPD: read only. Writes are out of scope (can brick a module; DDR4 unlock needs 9 V).
- SLE4442: read only automatically; a passcode attempt needs its own yes and shows the attempts left;
  never retried automatically.
- USB-PD plank: reading the source's offers is fine; requesting a voltage above 5 V needs its own yes
  naming the voltage (up to 28 V).
- PS/2 and USB keyboard sniffers: `owner-only`.
- UART glitching: its own yes; it is fault injection on the target.
- VPP SMPS: not automated.

## 6. Phases (decided order, each its own plan)

1. **The BP6 server and the BPIO2 recipes.** Server, recipe engine, confirmation rule, and recipes for:
   HD44780 LCD; I2C sensors (AHT20, BMP280/BME280, SHT3x, SHT4x, SI7021/HTU21, TSL2561, TCS3472x,
   MS5611); I2C EEPROM and FRAM read/dump; SPI flash identify and backup; MAX31855; DS18B20; UART console
   and NMEA GPS; WS2812, APA102 and onboard LEDs; GPIO/aux pins; "identify an unknown chip" (I2C scan,
   1-Wire search, SPI JEDEC). Plus `bp6-demo`.
2. **Destructive BPIO2 recipes:** EEPROM/FRAM/flash erase, write and verify; SPI EEPROM and Microwire;
   1-Wire EEPROM; DDR4/DDR5 SPD read; MIDI.
3. **The terminal path:** PWM and frequency, self-test, I2C/2WIRE/PS2/USB sniffers, blueTag, NMEA via
   `gps`, IR receive/transmit, logic analyser (`logic` and handing the port to PulseView), binmode
   hand-off for flashrom/avrdude, smart cards (SIM ATR, SLE4442), USB-PD, UART glitch, disk and macros.
4. **Retire the universal server for the BP6:** the `buspirate` server keeps v3/v4/Bit Pirate until their
   own servers exist.

## 7. Left to the builder

- Tool and parameter names beyond those above, file layout inside `mcp_bp6/`, the recipe data format.
- How recipes match words (simple aliases are enough).
- Terminal output parsing details, per command, from the docs and a real board.
- Which demo-simulator devices to add so each phase 1 recipe can be tested without hardware.
