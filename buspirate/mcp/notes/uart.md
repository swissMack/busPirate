# UART: asynchronous serial

No clock: both ends must agree on the baud rate.

## Wiring (TX and RX cross over)

| Bus Pirate | v3/v4 (Seeed) | BP6 | Bit Pirate dock | goes to target |
|---|---|---|---|---|
| RX (listens) | MISO, black | IO5, brown | IO11, brown | the target's **TX** |
| TX (sends) | MOSI, grey | IO4, purple | IO10, purple | the target's **RX** |
| GND | brown | black | black | GND, first |

Connect the Bus Pirate's supply only if the target needs it. A target with its
own supply shares GND only.

## Settings

- Usually 115200 8N1. v3/v4 rates: 300, 1200, 2400, 4800, 9600, 19200,
  31250 (MIDI), 38400, 57600, 115200; others by a raw BRG divisor.
- **Set the line up before listening.** Until it is set up, a v4 sits at
  300 baud with its TX pin not driving, and a floating RX forwards noise (a
  stream of `18` on a v4).
- BP6 binary interface: 8 data bits, **no or even parity only**. Odd parity
  and 9 bits are only in the board's own terminal.
- Bit Pirate: `autobaud` (Find the baud rate) tries to detect the rate and
  saves it.

## Reading the symptoms

| What you see | What it means |
|---|---|
| Nothing at all | TX/RX swapped, no common ground, or the target is silent |
| Consistent garbage | wrong baud rate |
| Mostly right, the odd wrong byte | baud close but not exact, or a noisy line |
| Every byte doubled | echo on at both ends |
| Correct text, then nothing | the target stopped, or expects flow control |
| A stream of one junk byte with nothing connected | the line was never set up |

Garbage is a speed problem; wiring faults give silence, not nonsense.

## Loopback self-check

Jumper the Bus Pirate's TX to its RX (v3/v4 MOSI to MISO; BP6 IO4 to IO5) with
no target. Send `Hi` + CR LF and `48 69 0d 0a` comes back. The v3/v4 receive
buffer holds only about four bytes while it transmits, so long messages are
sent four bytes at a time.

## The transparent bridge

Turns the board into a plain USB-to-serial adapter for an external tool.

- **v3/v4:** "reset to exit": there is no way out in software. Unplug and
  replug afterwards. CTS/RTS on the v3 only.
- **BP6:** `bridge` on the terminal port; press the button to exit.
- **Bit Pirate:** `bridge` in UART mode; press any ESP32 button to stop.
- **No board passes DTR/RTS through**, so tools that auto-reset a target
  (esptool, Arduino upload) cannot reset it. See the esp note.

## Voltage

3.3 V logic on the v3/v4, tolerating 5 V inputs. **Never RS-232**: a real
serial port swings ±12 V and damages it. Use a level shifter such as a
MAX3232.

Sources:
- docs/uart.md
- docs/troubleshooting.md (UART loopback on v4 and BP6)
- docs/bus-pirate-6.md (pins, parity limits)
- docs/bitpirate.md (dock pins, autobaud)
- docs/bitpirate-wiki/03-uart.md (`bridge`)
- docs/superpowers/specs/2026-11-09-buspirate-mcp-design.md (constraints table: bridge exits, DTR/RTS)
- buspirate/web/wiring.py (Seeed colours)
