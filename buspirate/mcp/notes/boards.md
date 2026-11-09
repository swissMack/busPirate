# Boards: what each one can do, and the traps

Four boards are supported. The Bus Pirate 5 is treated as a BP6 (same
firmware, same BPIO2), labelled untested.

## The constraints table

| | v3 | v4 | BP6 | Bit Pirate |
|---|---|---|---|---|
| Protocol | BBIO | BBIO (features by firmware) | BPIO2 + terminal | text CLI |
| Supply | 3.3 V **and** 5 V together, ~150 mA each | same | VOUT 0.8–5 V, limit 1–500 mA | dock switch 5V / 3V3 / 1V8, not software-readable |
| Measure target V | ADC pin (one probe) | ADC pin | every IO pin + VOUT | **no** (on-screen only) |
| UART bridge | yes, reset to exit; CTS/RTS v3 only | yes, reset to exit | `bridge` on terminal port, button to exit | `bridge`, button to exit |
| DTR/RTS passthrough | no | no | no | no |
| AVR | `avrdude -c buspirate` / `buspirate_bb` | same | binmode 5 Legacy, replug afterwards | USB "adapter" mode |
| SPI flash | driver, or flashrom `buspirate_spi` | same | driver, or flashrom via binmode 5 | driver read/dump/verify; flashrom `serprog` adapter |
| PIC | low-voltage only, PiratePICprog | same | **none** | **none** |
| Logic analyser | SUMP | SUMP | SUMP binmode, follow-along | SUMP adapter |

I/O levels: v3/v4 are 3.3 V logic, 5 V tolerant (5.5 V absolute maximum).
The BP6's IO pins are buffered and work from 1.2 to 5 V, following VOUT. A bare
Bit Pirate DevKit is 3.3 V only and not 5 V tolerant; the dock's level
shifters give 5V, 3V3 or 1V8. UART is never RS-232 on any of them.

## v3 and v4

- Pick the voltage **by wire**: the power switch turns on the 3.3 V and 5 V
  regulators together. Never connect both to one target.
- The pull-ups pull to whatever is on **VPU**. VPU floating = pull-ups do
  nothing, and an I2C scan with VPU floating sees every address "answer".
- The v4 can connect VPU to its own 3.3 V or 5 V rail in software; it
  refuses if a voltage is already on VPU. Older v4 firmware may ignore it.
- I2C 100/400 kHz need firmware v4.2+; `write_then_read` needs v5.1+.
- Binary modes need firmware v2.6+. The board is 115200 8N1.
- **v4 extended AUX (`0x09`) hangs the board** on firmware 7.0 (6.0-a3
  refuses it). Drive AUX from the pins page on a v4.
- AUX1 and AUX2 on the v4 are terminal-only; the binary protocol cannot reach
  them.
- Self-test is v3 hardware only. Disconnect the probe cable from any target.
- Opening the terminal resets both boards (supplies off, pins to input). The
  v4 drops off USB and comes back about half a second later.
- The transparent UART bridge has no software exit: unplug and replug.
- PWM keeps running after you leave bitbang mode. Stop it explicitly.
- v4 USB LED dark once enumerated is **healthy**; on a v3 a dark USB LED
  with PWR lit is a driver or cable problem.
- MODE going dark mid-session: either the terminal was opened, or the
  firmware dropped something (SPI sniff overrun, UART overrun, buffer full).

## Bus Pirate 6

- Two serial ports: the terminal (`…buspirate1`) and the binary port
  (`…buspirate3`) where BPIO2 runs. Only one program can hold each.
- After every unplug it starts in the logic-analyzer binmode; BPIO2 is
  selected through the terminal with `binmode`, 2, and **no** to "Save
  setting?".
- Firmware must be built 2026-10-12 or later for UART in BPIO2.
- **Traps that each cost a replug** (the driver avoids them):
  - Ctrl-C at "VT100 compatible color mode?" hangs the terminal. Answer
    `n` or `y`, never Ctrl-C.
  - A BPIO2 reply sent to a closed port hangs the whole board: always read
    every reply before closing.
  - BPIO2 takes about 3 s to answer after it is selected, and the first reply
    after opening the terminal port is seconds late. Wait; do not re-send.
- Current limit default is 300 mA on the board (the MCP server uses 100 mA).
  A trip cuts the supply and sets a flag that survives switch-off and
  reconnect; fix the fault, then re-enable. Switching on into a load already
  over the limit is refused instead ("Power supply initialization failed").
- The supply is always off in HiZ.
- **Go by the heat-shrink labels on the cable ends.** The labels by the
  board's connector do not line up exactly with the pins; that once put a
  MAX31855 one pin off.
- BPIO2 has no raw-wire, DIO, infrared, JTAG, LED or logic-analyzer handler;
  UART is 8 bits with no or even parity only; it reports one I2C ACK/NACK per
  transaction; 1-Wire search finds one device only (use `m 1wire`, `scan` in
  the terminal for several).
- binmode 5 (Legacy, for flashrom and avrdude) locks the terminal: replug to
  leave it.
- "Disk Not Ejected Properly" on unplug is the BP6's storage drive; harmless.

## ESP32 Bit Pirate

- Plug the DevKit's **USB** (or **USB OTG**) port, not UART / USB TTL.
- A freshly plugged board takes about 3 s before it listens.
- The dock header follows the BP6 layout: IO0–IO7 = GPIO 15, 16, 17, 18,
  10, 11, 12, 13. Stock firmware's I2C default (GPIO 6/7) is not on the dock.
- No software-controlled supply: VIO is the dock's slide switch.
- Pull-ups are the ESP32's internal ones (about 45 kΩ).
- SPI: mode 0 only, 1/2/4/8 MHz; flash read, dump and verify only.
- I2C writes check the address with `ping`; later bytes are not reported.
- The Web CLI runs *instead of* the USB terminal, chosen at power-up.

Sources:
- docs/superpowers/specs/2026-11-09-buspirate-mcp-design.md (constraints table)
- docs/troubleshooting.md
- docs/bus-pirate-6.md
- docs/bus-pirate-v4.md
- docs/pins-and-power.md
- docs/bitpirate.md
- docs/i2c.md, docs/uart.md
- docs/official/tutorial-basics/power-supply.md
- docs/official/software/flashrom.md, docs/official/software/avrdude.md
