# PIC: low-voltage programming with PiratePICprog (v3/v4 only)

## Which boards

- **Only a Bus Pirate v3 or v4.** The BP6/BP5 and the Bit Pirate have no PIC
  mode; offer a v3/v4, or a PICkit.
- **Low-voltage (LVP) parts only.** Parts that need 6–13 V on VPP/MCLR to
  enter programming mode need the high-voltage adapter, which is out of
  scope here (and "not compatible with v4+ pinout").

## Supported parts (PiratePICprog)

| Family | Part(s) in the database | Entry | Status |
|---|---|---|---|
| PIC18F2xJxx / 18F4xJxx | 18F24J50 | low voltage | ID, erase, write, read |
| PIC24FJxxGAxxx | 24FJ64GA002 | low voltage | ID, erase, write; read works but verify fails (the HEX parser does not understand the PIC24F format) |
| PIC24FJxxGBxxx | 24FJ256GB106 | low voltage | in the source's database; status not documented |
| PIC18Fx5xx, PIC16F88x | 18F2550, 18F2553, 18F4550, 16F887 | **high voltage** | out of scope |

PiratePICprog was "in the initial testing phase" with a limited part list.
A part not in its database cannot be programmed without adding it to `pic.c`.
Check the part's datasheet for its supply voltage before choosing a level
(see the power note); the v3/v4 offers only 3.3 V or 5 V.

## Wiring (v3/v4, Seeed colours)

| PIC ICSP | Bus Pirate | Colour |
|---|---|---|
| PGC (clock) | CLK | purple |
| PGD (data) | MOSI | grey |
| MCLR | CS | white |
| GND | GND | brown, first |
| VDD (only if the Bus Pirate powers it) | +3.3V or +5V | red / orange |

AUX (blue) is the VPP control for the high-voltage adapter; not used for LVP.
The Bus Pirate's PIC mode bit-bangs CLK and MOSI, and PiratePICprog drives
MCLR from CS through the raw 2-wire binary mode. Outputs are 3.3 V normal or
open collector with 2–10 kΩ pull-ups; the pins are 5 V safe (5.5 V maximum).

## Commands

```
picprog -p buspirate -u <port> -s 115200 -c 18F24J50 -t HEX -w firmware.hex -E -V
picprog -p buspirate -u <port> -s 115200 -c 18F24J50 -I            # read the chip ID
picprog -p buspirate -u <port> -s 115200 -c 18F24J50 -t HEX -r dump.hex
```

| Option | Meaning |
|---|---|
| `-p buspirate` | the interface |
| `-u PORT`, `-s 115200` | serial port and speed |
| `-c CHIP` | chip type, as named in its database |
| `-t HEX` or `BIN` | file format |
| `-w FILE` / `-r FILE` | write to / read from the PIC |
| `-E` | erase flash |
| `-V` | verify |
| `-I` | read the chip ID |

A successful run prints `Found '<chip>' in programming database` and then
`Found <chip> (0X…, ID: 0X… REV: 0X…)`. Read the ID first (`-I`) to prove the
wiring before any erase. Erase and write are destructive: dump first, plan,
confirm.

**PiratePICprog switches the Bus Pirate's supply on by itself** when it
enters programming mode (`iface->VCCHigh()` in pic18.c / pic24.c, which sets
the power bit). On a v3/v4 that turns on both regulators, so the level is
whichever supply wire is connected. Treat running picprog as a power-on: the
owner confirms the level first. A target with its own supply must not have a
Bus Pirate supply wire connected at all.

The tool is built from source (Code::Blocks / MinGW on Windows; "should
compile on GNU/Linux with GCC"). Building it on macOS is **unverified**.

Sources:
- https://github.com/BusPirate/Bus_Pirate/blob/master/Documentation/pic_programmer.md
- https://github.com/DangerousPrototypes/PiratePICprog (software/buspirate.c, software/pic.c, software/pic18.c, software/pic24.c)
- https://github.com/BusPirate/Bus_Pirate/blob/master/Firmware/pic.c
- docs/superpowers/specs/2026-11-09-buspirate-mcp-design.md (v3/v4 only, low-voltage only)
- docs/troubleshooting.md (v4 7.0 mode menu lists PIC)
- buspirate/web/wiring.py (Seeed colours)
