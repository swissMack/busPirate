# One board, one definition: a board-driven dashboard

Proposal, 2026-11-06. Status: **for review, nothing built.**

## Why

The app grew one board at a time (v3, v4, Bit Pirate, Bus Pirate 6), and each
board was added by touching whatever file needed it. The result:

- **What a board is, is spread over five places**, all keyed by the variant
  string: capabilities (`device.py`), wiring and per-panel wording
  (`web/wiring.py` `BOARDS` and its `panels` overrides), LED rules
  (`wiring.py`), the guide's manual and board page (`web/docs.py` `MANUALS`,
  `BOARD_PAGE`), and the docs themselves.
- **The docs repeat each other.** `user-guide.md` carries a 200-line Bit
  Pirate section that restates `bitpirate.md` (wiring, limits, setup), plus
  sections for the v3 cable and the Bus Pirate 6. `troubleshooting.md` has
  per-board sections too. When the dock arrived, its pinout had to be written
  into both pages, and the next change will drift.
- **`bitpirate.md` now re-lists the wiki.** The new mode table copies what
  the imported wiki already says, with less detail.
- **The left-hand menu only knows the Bus Pirate's job list.** It does adapt
  per board (panels and actions are hidden by capability), but it can only
  *remove*. A Bit Pirate shows Connection, I2C, SPI, UART, Terminal, and
  nothing for the 20-odd things it can do that a Bus Pirate cannot.

## The rule

**The connected board decides what the app shows: menu, actions, wiring,
LEDs and guide. Each board is described once, and every fact lives in
exactly one place.**

## 1. One board definition per variant

A `buspirate/boards/` package with one module per board (`v3.py`, `v4.py`,
`bp6.py`, `bitpirate.py`), each exporting a single `Board` object holding:

- identity and label, capabilities
- the picture, pin geometry and LEDs (what `wiring.py` holds today)
- per-panel wording overrides and wiring tables
- its guide page and its manual (official BP5/6 manual, or the Bit Pirate wiki)
- **its extra panels** (section 3)

`device.py`, `wiring.py` and `docs.py` read from the registry instead of
keeping their own per-variant dicts. Adding a fifth board means adding one
file.

## 2. Docs: three layers, no overlap

| Layer | Pages | Holds | Never holds |
|---|---|---|---|
| Start | `user-guide.md` | install, connect, "I want to…", where things live | anything about one board |
| Topics | `i2c.md`, `spi.md`, `uart.md`, … , `troubleshooting.md` | how to do a job, on any board | per-board wiring or limits |
| Boards | `bus-pirate-v3.md` (new, from the user guide), `bus-pirate-v4.md`, `bus-pirate-6.md`, `bitpirate.md` | wiring, limits, LEDs, setup, that board's hardware checklist | content its manual already covers |
| Manuals | `official/`, `bitpirate-wiki/` | the maker's own reference, imported unedited | our wording |

Concretely:

- `user-guide.md` loses its v3-cable, Bus Pirate 6 and Bit Pirate sections;
  each moves (merged, not copied) into that board's page. The guide opens
  with one line: "Connected: *Bit Pirate* → its page".
- Per-board troubleshooting moves to the board pages; `troubleshooting.md`
  keeps the general port, device, bus and software sections.
- `bitpirate.md` drops the mode table added today and links to the wiki's
  home page instead. The menu (section 3) is how modes are discovered.
- Each panel's **Guide** link goes to the board's own reference for that job
  where one exists: on a Bit Pirate, the I2C panel links to the wiki's I2C
  Mode page, not our Bus Pirate-oriented `i2c.md`.

## 3. The menu grows per board

The menu is built from the board: the shared panels it can drive, then its
own. For the Bit Pirate, its own panels follow the firmware's modes, grouped:

- **Shared, extended:** I2C, SPI, UART gain the Bit Pirate's extra actions
  (I2C `identify`, `dump`, `sniff`, `eeprom`, `recover`; UART `autobaud`,
  `scan`; SPI `sdcard`, `eeprom`), gated by capability as today.
- **On the dock header, no extra hardware:** 1-Wire (scan, temperature),
  DIO (read, set, PWM, measure), 3-Wire EEPROM, 2-Wire smartcard, JTAG pin
  scan.
- **No wiring at all:** Wi-Fi scan, Bluetooth scan.
- **Needs an add-on module:** Infrared, Sub-GHz, RFID, RF24, LoRa, CAN,
  Ethernet, FM, Cell, I2S, LED strip. Listed under one collapsed
  "Modules" heading, each saying which module it needs.

The board's own modes are made from one generic, data-driven panel type: a
table per mode of commands (label, the command line, its parameters and
whether it streams). One click runs it and shows the board's output. Every
mode then appears without a hand-written panel each, and a mode can later
get a dedicated panel (decoded values, charts) where it earns one, as I2C,
SPI and UART have.

Pins: every mode is moved onto the dock header on entry, as I2C, SPI and
UART already are, so each panel's wiring diagram is the same dock photo.

## 4. One way to get around

Today there are four overlapping ways to move around (screenshot,
2026-11-06): quick-action buttons and a Guide button in the top bar; the
left column with its own Guide entry; a 53-page drop-down inside the guide,
where a mode's page sits among everything else; and search. You end up
rooting around.

**The left column is the only navigation.** Everything you can go to is in
it, in this order, built from the connected board:

```
Connection          board, port, "Follow the board", HiZ / release pins
──────────
I2C                 the board's jobs, grouped
SPI
UART
1-Wire
DIO
──────────
Wi-Fi               (Bit Pirate: no wiring needed)
Bluetooth
▸ Modules (11)      collapsed: Infrared, Sub-GHz, RFID, …
──────────
Terminal
Guide
```

- **The top bar shows status only:** board, firmware, port, LEDs. The
  quick-action buttons and the second Guide button go. The jobs they jumped
  to are one click away in the column, and the "Follow the board" selector
  moves into Connection.
- **Each panel carries its own help.** A "?" in the panel's header opens
  the reference for *this job on this board* (on a Bit Pirate: the wiki's
  page for that mode) in a side drawer, beside the panel, so you never
  leave the job to read about it.
- **Guide in the column opens the guide's contents in the column itself.**
  The column turns into a table of contents (this app's pages, then the
  board's manual, as collapsible headings, with search at the top) and a
  "← Back" returns to the jobs. The drop-down of 53 pages goes.
- **The Traffic panel speaks the board's language.** For the Bit Pirate,
  which talks text, it shows the text (`I2C> scan`) rather than hex bytes,
  with hex still a toggle away.

Bugs found while doing this, fixed in step 2: imported wiki pages render a
stray "null" above their title.

## Order of work

1. **Board registry** (section 1). No visible change; the tests prove it.
2. **Navigation and docs** (sections 2 and 4): the single left column,
   per-panel help drawer, guide contents in the column, text traffic for
   the Bit Pirate, and the docs moved into their layers with the duplicates
   deleted.
3. **Generic mode panel** plus the dock-only Bit Pirate modes (1-Wire, DIO,
   Wi-Fi/Bluetooth scan) and the extended I2C/SPI/UART actions.
4. **The module modes**, as you get the modules to test them with.

Each step is its own PR, tested on your hardware before the next starts.
PR #27 (the wiki import) stays open and is folded into step 2.

## Non-goals

- Re-implementing the Bit Pirate's terminal. Interactive or menu-heavy
  commands (wizards, the Pirate Assistant, the USB adapter modes) stay in
  the Terminal panel.
- Changing how the Bus Pirates v3, v4 or 6 behave. Only where their facts
  live changes.
- Editing the imported manuals.

## Left open for you

- Should the module panels show when no module is fitted? The proposal shows
  them collapsed under "Modules"; hiding them completely is the alternative.
- Should the `bus-pirate-v3.md` page exist, or does the v3 stay the default
  that the topic pages assume?
