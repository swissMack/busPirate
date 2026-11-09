# A Bus Pirate MCP server: Claude as a universal debugging front end

Proposal, 2026-11-09. Status: **for review, nothing built.**

## Intent

The owner uses a Bus Pirate rarely enough that the mode setup is forgotten
between sessions: which mode, which speed, pull-ups or not, which voltage,
which wire where. The goal is to say *what* is wanted ("read the sensor on
I2C", "flash this ESP32", "program this ATtiny") and have Claude do the rest
on whichever board is plugged in. Claude identifies the board, picks the
settings that board needs, and tells the owner which wire goes to which pin
on the target. **The owner's job shrinks to wiring.**

It is meant to be a **universal debugging front end**: everything the
Dangerous Prototypes wiki (v3/v4), the Bus Pirate 5/6 manual and the ESP32
Bit Pirate wiki describe, plus programming ESP, AVR and low-voltage PIC
targets, with the Bus Pirate as Claude's hands.

The repo already does the hard parts: board detection (`connect.open_device`),
one definition per board (`buspirate/boards/`, see
`2026-11-06-board-driven-app-design.md`), per-board capabilities
(`buspirate/capabilities.py`), the Bit Pirate's own modes (`CliMode` in
`boards/bitpirate_modes.py`), chip identification and decoding
(`buspirate/devices/`), SPI flash (`spiflash.py`) and simulators for all four
boards. **The MCP server is a new front end over that driver, beside the
dashboard. It is not a new driver.**

## Goals

1. **Board-driven tools.** On connect, the server identifies the board
   (v3, v4, BP6, Bit Pirate) and its firmware, and offers **only** the tools
   that board can do. A request for something it cannot do gets a plain
   answer that names a board that can, for example "PIC programming needs a
   v3 or v4; the BP6 has no PIC mode."
2. **Intent in, settings out.** Each tool takes the goal and the target
   facts, and the server chooses mode, speed, pins, pull-ups and supply for
   the connected board. The owner never has to know per-board quirks such
   as the BP6 current limit, the Bit Pirate's dock pins, or v4 firmware speed
   limits.
3. **Power is asked, never guessed** (the owner's rule):
   1. Before switching on the supply, Claude asks whether the owner knows
      the target's voltage.
   2. Known: the server sets that level on the connected board and switches
      it on.
   3. Unknown: the server measures first and suggests a level, and the
      owner confirms.
4. **Wiring instructions.** Every operation that needs wires returns a
   wiring list: board pin → DuPont colour → target pin, using **the colours
   of that board's own cable**:
   - **v3/v4:** the Seeed probe-cable colours already in `boards/v3.py`
     and `v4.py`.
   - **BP6 (and BP5):** the official probe cable's shrink colours
     (`docs/official/cables/cables.md`): VOUT red, IO0 orange, IO1 yellow,
     IO2 green, IO3 blue, IO4 purple, IO5 brown, IO6 grey, IO7 white, GND
     black.
   - **Bit Pirate dock:** the same as the BP6, because its header follows
     the BP6 layout (IO0–IO7 = GPIO 15, 16, 17, 18, 10, 11, 12, 13). The
     owner colours the DuPont jumpers to match.

   Each step names the pin label as well as the colour, because on the BP6
   the shrink label on the cable is the authority and the connector
   silkscreen is not.
5. **Coverage:** every function in the Dangerous Prototypes and Bit Pirate
   wikis and the BP5/6 manual that the driver or the board's terminal can
   reach (catalogue below), each gated by board.
6. **Programming recipes:** ESP (esptool), AVR (avrdude), SPI flash
   (flashrom or the driver), and low-voltage PIC (v3/v4 only).
7. **Knowledge built in:** Claude can answer "how do I…" and "why does…"
   from the wikis and manuals without leaving the conversation.
8. **Results in real units**, following the repo's one-stop-shop rule:
   identified chips and decoded readings, never bare hex for the owner to
   decode.

## Non-goals

- A new driver or protocol work. Gaps in the driver are filled in the driver
  (with simulator tests), and the MCP server calls it.
- High-voltage PIC programming, or any PIC on the BP6 or Bit Pirate. The
  research found no support, so these tools are hidden there.
- Replacing a logic analyser or a PICkit. SUMP capture is offered where the
  board has it, with its real limits stated.
- Network or remote use. The server is local, over stdio, for Claude Code.

## Anti-goals (failure even if it "works")

- **Guessing a voltage, or switching on power without the owner's answer.**
- Offering a tool, letting it fail, and then saying the board cannot do
  that. Gating happens *before* the tool is listed.
- **Leaving a board wedged.** Each of the BP6 traps (Ctrl-C at the VT100
  prompt, closing BPIO2 mid-reply) costs a replug. Every tool closes cleanly
  and drains, and the driver's workarounds stay.
- Running anything destructive without an explicit confirmation: flash
  erase/write, AVR fuse or lock writes, chip erase, EEPROM writes. A flash
  write also needs a dump first.
- Making the owner decode hex, or look up a datasheet that the server's
  knowledge already covers.

## Constraints (from the research, 2026-11-09)

| | v3 | v4 | BP6 | Bit Pirate |
|---|---|---|---|---|
| Protocol | BBIO | BBIO (features by firmware) | BPIO2 + terminal | text CLI |
| Supply | 3.3 V **and** 5 V together, ~150 mA | same | VOUT 0.8–5 V, limit 1–500 mA | dock switch 5/3V3/1V8, not software-readable |
| Measure target V | ADC pin (one probe) | ADC pin | every IO pin + VOUT | **no** (on-screen only) |
| UART bridge | yes, reset to exit; CTS/RTS v3 only | yes, reset to exit | `bridge` on terminal port, button to exit | `bridge`, button to exit |
| DTR/RTS passthrough | no | no | no | no |
| AVR | `avrdude -c buspirate` / `buspirate_bb` (ISP+TPI) | same | binmode 5 Legacy, replug afterwards | USB "adapter" mode |
| SPI flash | driver, or flashrom `buspirate_spi` | same | driver/`flash` command, or flashrom via binmode 5 | driver read/dump/verify; flashrom `serprog` adapter |
| PIC | low-voltage only (PIC18FxxJ, PIC24FJ), PiratePICprog | same | **none** | **none** |
| JTAG | OpenOCD (fw 5.8/6.0/6.1; not 5.9/5.10) | community fw | pinout scan only | pinout scan + OpenOCD adapter |
| Logic analyser | SUMP, 4096 samples ≤1 MHz | SUMP | SUMP binmode, follow-along | SUMP adapter |

Further constraints:
- **The ESP has no auto-reset through any Bus Pirate.** The server drives
  the boot pin (IO0, or IO9 on C3/C6/H2) and EN from spare Bus Pirate pins,
  or tells the owner to press the buttons. It then runs esptool with
  `--before no-reset --after no-reset` at a **fixed 115200**, because the
  bridge cannot follow esptool's baud switch. ESP logic is 3.3 V only, and
  v3/v4 cannot supply an ESP32 running Wi-Fi (150 mA). The server says
  "power it from its own USB, share GND."
- **External tools need the serial port to themselves** (esptool, avrdude,
  flashrom, picprog, openocd). The pattern is: the server configures the
  board, releases the port, runs the tool as a subprocess, then reclaims the
  port. Where a mode only exits by reset or replug (v3/v4 bridge, BP6
  binmode 5), the server tells the owner when to unplug and resumes after.
- **The dashboard and the MCP server cannot both own the port.** The server
  detects a held port ("Resource busy") and says which program holds it.
- I/O on v3/v4 is 3.3 V and 5 V tolerant (5.5 V absolute maximum). The BP6
  runs 1.2–5 V. A bare Bit Pirate DevKit is 3.3 V only. UART is never
  RS-232.
- The repo's CI runs Python 3.8. The MCP SDK needs a newer Python, so the
  server is an **optional extra** (`.[mcp]`), and the core stays 3.8-clean.

## Function catalogue (gated by board)

Each line becomes a tool, or an action of one, offered only where the board
has the capability. "BP" means terminal-only functions reached through the
board's own command line.

- **Board:** detect and identify; status (supplies, pins, mode); HiZ (release
  everything); self-test (v3/v4, with its jumpers); firmware/version report.
- **Power and pins:** measure voltages; set the supply (asked first, per
  goal 3); pull-ups and the VPU rail (v4 software rail; v3 wiring
  instructions); drive or read single pins (bitbang / DIO); PWM; frequency
  counter; ADC.
- **I2C:** scan with identification; read/write registers; decoded sensor
  reads (`devices/`); EEPROM read/write (24Cxx); sniffer; v3 extended AUX.
- **SPI:** identify (JEDEC); transfer; flash dump/erase/write/verify;
  decoded sensors (MAX31855…); sniffer; modes 0–3 where supported.
- **UART:** send/listen/monitor; baud detection by trying rates; transparent
  bridge (for external tools); HDUART on BP6/Bit Pirate.
- **1-Wire:** search; DS18B20/DS18S20 temperatures; ROM read.
- **Raw 2-wire / 3-wire:** bit-level transactions (smartcards, 93Cxx
  EEPROMs on boards that have them).
- **LCD (HD44780 over I2C backpack):** compose and send text.
- **JTAG:** pinout scan (BP6, Bit Pirate); OpenOCD session where supported.
- **Logic analyser:** SUMP capture handed to PulseView or sigrok, where
  supported.
- **Infrared, keyboard and LED strips:** where the board has the mode (v3/v4
  KEYB per firmware; BP6 and Bit Pirate INFRARED, LED).
- **Bit Pirate only** (its CLI modes, already defined as `CliMode`s): USB,
  Bluetooth, Wi-Fi, CAN, Ethernet, Sub-GHz, RFID, RF24, FM, Cell, LoRa, I2S,
  expander. One generic tool runs a defined mode command with its declared
  parameters. Nothing is free-typed, so the Bit Pirate's mode table stays
  the single source.
- **Programming recipes:**
  - **ESP:** chip family → wiring (TX/RX/GND/EN/boot pin) → boot sequence →
    esptool `flash_id` / `read_flash` / `write_flash` / `erase_flash`.
  - **AVR:** wiring (CS→RESET…) → avrdude signature read → flash/EEPROM
    read/write → fuses (read freely, write only with confirmation).
  - **SPI flash:** identify → dump → erase/write/verify (driver), or
    flashrom.
  - **PIC (v3/v4):** low-voltage parts only → picprog → read/write/verify.
- **Terminal escape hatch:** send a single line to the board's own terminal
  for anything not covered. Every output is logged, and the known-dangerous
  inputs are blocked (BP6 Ctrl-C at the VT100 prompt).

## Knowledge (builder's call, as the owner asked)

Two layers, both served by the MCP server:

1. **Distilled notes**, one per topic: each chip family (ESP strapping pins
   per chip, AVR ISP/TPI, low-voltage PIC parts, 25-series flash, common
   sensors), each board's limits, and the common error messages with their
   causes (the esptool troubleshooting table, "no BBIO response", all-FF
   SPI…). They are short, checked against sources, and **cited**.
2. **Search over the bundled sources** for everything else: `docs/official/`
   (BP5/6 manual), `docs/bitpirate-wiki/`, and newly bundled copies of the
   Dangerous Prototypes pages and the esptool/Espressif pages used here. They
   are imported by scripts like the existing `scripts/import_*.py`, pinned
   to a revision, with licence and source recorded. **The live Dangerous
   Prototypes site returns 403**, so the import reads the Wayback Machine
   and the `BusPirate/Bus_Pirate` GitHub docs.

The server's instructions tell Claude to check the notes before acting and
to search the sources when the notes don't cover a question.

## Decided by the owner

- Intent-based. Claude chooses the board settings, and detects and adjusts
  for the variant.
- Power: ask whether the voltage is known → set it and switch on. Unknown
  → measure, suggest, confirm.
- The owner wires. Claude names every connection.
- The capabilities of the connected board enable or disable tools.
- PIC: low-voltage only, v3/v4 only.
- DuPont jumpers coloured to each board's own cable: Seeed on v3/v4, and the
  official BP6 shrink colours on the BP6 and the Bit Pirate dock (2026-11-09).
- Scope: everything in the Dangerous Prototypes and Bit Pirate wikis
  (and the BP5/6 manual), plus ESP/AVR/PIC programming.

## Builder's calls (stated so the owner can reject them)

- **Python, in this repo:** `buspirate/mcp/` with a `buspirate mcp` CLI
  subcommand. Stdio transport, using the official MCP Python SDK as an
  optional extra.
- **Build order**, each stage usable on its own:
  1. Core: detect, gate, power flow, wiring, I2C/SPI/UART/1-Wire/pins,
     knowledge layer 1.
  2. ESP flashing.
  3. AVR.
  4. SPI flash (driver + flashrom).
  5. Remaining modes: raw wire, LCD, sniffers, SUMP, JTAG, Bit Pirate extras.
  6. Low-voltage PIC.
  7. Knowledge layer 2 (bundled-source search) can land alongside stage 1
     or 2.
- **Tests against the existing simulators** for every tool. The simulators
  grow where a tool needs behaviour they lack. External tools (esptool,
  avrdude…) are tested by stubbing the subprocess. Hardware checklists go
  in `docs/troubleshooting.md`, in the repo's existing style.
- **Lifecycle and gating:**
  - At startup the server scans the ports and lists only a `connect`
    tool plus the knowledge tools.
  - `connect` identifies the board. The server then sends
    `tools/list_changed` with that board's tools.
  - If several boards are attached, `connect` lists them and Claude asks
    the owner which one to use.
  - A board that is unplugged or swapped drops back to the `connect`-only
    list.
  - If Claude Code does not refresh on `list_changed`, the fallback is to
    restart the MCP server. The plan's first spike checks this.
- **One open connection, owned by the server**, closed (drained, HiZ) on
  idle, on disconnect and on exit.
- **The server enforces power and destructive steps; Claude does not.**
  - A power or destructive tool runs in two steps. The first call returns
    the plan (voltage, limit, wiring, or what will be erased) plus a
    one-time token.
  - The second call must carry that token, and Claude may only send it
    after the owner's answer.
  - Power tools also record *where the voltage came from*: the owner said
    it, or it was measured and the owner confirmed it.
- **Power on boards that cannot set a level:**
  - **v3/v4** offer only 3.3 V or 5 V, chosen by the wire. A target that
    needs another level (e.g. 1.8 V) is refused for board power. The
    server suggests the target's own supply with GND shared, or the BP6.
  - **Bit Pirate:** the owner sets the dock switch and confirms. With the
    voltage unknown it cannot measure, so it asks for the part number or
    the owner's meter reading.
- **The terminal escape hatch** runs each board's known power-on and
  destructive commands through the same confirmation, and blocks the
  known wedge traps. Everything else passes through, logged.
- **Bundled sources:** the Dangerous Prototypes pages are committed with
  their CC BY-SA notice, as the repo already does for its cards. The
  Espressif/esptool pages are committed only if their licence allows it,
  otherwise fetched into a local, git-ignored cache by the importer.
- **Bus Pirate 5:** gated as a BP6 (same firmware and BPIO2), labelled
  untested, with no separate checklist until one is on the bench.
