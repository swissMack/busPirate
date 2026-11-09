# Power: choosing a target voltage

The owner's rule: **power is asked, never guessed.** Before any supply goes
on, ask whether the owner knows the target's voltage.

## The flow

1. Ask: "Do you know the target's supply voltage?"
2. Known: plan that level on the connected board, show the plan, and switch
   on only after the owner confirms it.
3. Unknown: **measure first**, suggest a level, and let the owner confirm.
   Never pick a level because it is "usual".
4. A board that cannot measure (Bit Pirate) asks for the part number or the
   owner's meter reading instead.

Every power-on goes through a plan and a single-use confirmation token
(expires after 300 s). The token records where the voltage came from:
`owner`, or `measured` and then confirmed by the owner.

## How to choose a level

- The target's datasheet or silkscreen is the authority. Serial flash is
  mostly 3.3 V only, and 5 V destroys it.
- ESP chips are 3.3 V logic only.
- A target that already has its own supply: do **not** switch on the Bus
  Pirate's supply. Share GND only (and feed VPU / VOUT from the target if
  pull-ups are needed). Two supplies fighting is a good way to lose a board.
- A hungry target (anything with Wi-Fi, motors, LEDs) uses its own supply,
  with the grounds tied together.

## Per board

| | Levels | Current | 5 V tolerance | Measure |
|---|---|---|---|---|
| v3 / v4 | 3.3 V or 5 V, **picked by wire** | about 150 mA per supply | I/O 3.3 V, 5 V tolerant (5.5 V abs. max) | ADC pin, 0–6 V |
| BP6 (BP5) | 0.8–5.0 V on VOUT | limit 1–500 mA; server default 100 mA | IO buffered 1.2–5 V, follows VOUT | every IO pin + VOUT |
| Bit Pirate dock | 1V8, 3V3 or 5V by the dock's slide switch | not stated | via the dock's shifters; bare DevKit 3.3 V only, **not** 5 V tolerant | **no** |

### v3 / v4

- One switch turns on the 3.3 V **and** 5 V regulators together. The level
  is chosen by which wire is connected: +3.3V red (pin 9) or +5V orange
  (pin 8). Never connect both.
- Any other level (for example 1.8 V) is refused for board power. Use the
  target's own supply with GND shared, or a BP6.
- About 150 mA each. That is not enough for an ESP32 running Wi-Fi: power it
  from its own USB and share GND.
- The ADC is 10-bit behind a divide-by-two, reads up to about 6 V, and
  needs a shared ground. Against a meter it read 2–3 % high between 3 and
  5 V. It is a rail check, not a multimeter.

### BP6

- 0.8 to 5.0 V. The board's own default limit is 300 mA; the MCP server uses
  **100 mA** unless the owner asks otherwise. The official manual rates the
  output at 300 mA maximum.
- Above 3.6 V, or a limit of 0 (none), needs extra confirmation.
- A trip cuts the supply: find the short, then re-enable. "The supply would
  not start" means the target already draws more than the limit at switch-on.
- The supply has backflow prevention, so a target's own voltage may be fed
  into VOUT to set the IO level. The supply is always off in HiZ.

### Bit Pirate

- Software cannot set or read the dock switch. The owner sets it and
  confirms. With the voltage unknown, ask for the part number or a meter
  reading; the board cannot measure.
- The 3V3 pin of a bare DevKit is live whenever the board has USB power.

## Measuring an unknown target

- Connect GND first, then the measuring lead to the target's VCC, with the
  Bus Pirate's supply **off**.
- v3/v4: ADC lead (yellow). BP6: any IO pin, or VOUT, read from the status.
- Suggest the nearest standard level (1.8, 3.3 or 5.0 V) and ask the owner to
  confirm it before anything is switched on. If the target is already
  powered, the right answer is usually "leave the supply off, share GND".

Sources:
- docs/superpowers/specs/2026-11-09-buspirate-mcp-design.md (goal 3, power constraints)
- buspirate/mcp/power.py and buspirate/mcp/confirm.py (supply rules, 300 s tokens)
- docs/pins-and-power.md
- docs/troubleshooting.md (ADC against a multimeter; BP6 current limit)
- docs/bus-pirate-6.md (power and the current limit)
- docs/official/tutorial-basics/power-supply.md
- docs/bitpirate.md
- docs/spi.md, docs/uart.md
- https://docs.espressif.com/projects/esptool/en/latest/esp32/troubleshooting.html (Insufficient Power)
