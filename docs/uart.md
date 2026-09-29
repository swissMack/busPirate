# UART

An asynchronous serial line — no clock, so both ends must agree on speed.

## Wiring

| Probe wire | Seeed colour | Target |
|-----------|--------------|--------|
| MISO | black | the target's **TX** |
| MOSI | grey | the target's **RX** |
| GND | brown | GND — connect this first |

**TX and RX cross over.** The Bus Pirate listens on MISO, so MISO goes to the
pin the target *transmits* from. If you see nothing, swapping these two is
the first thing to try.

Only connect the Bus Pirate's power if the target needs it. Two supplies
fighting each other is a good way to lose a board.

## Using it

```python
with bp.uart() as uart:
    uart.set_baudrate(uart.BAUD_115200)
    uart.configure(databits_parity=0, stop_bits=1)   # 8N1
    uart.write(b"AT\r\n")

    uart.start_receive()          # the Bus Pirate now forwards what it hears
    print(uart.read_available(256))
    uart.stop_receive()
```

In the dashboard: **Set the line up**, then **Send text** — what comes back
within a moment shows up right under it. The dashboard listens the whole
time it is in UART mode, and sets the line up itself if you send first.
**Check for more replies** collects slower answers; **Watch the line** is a
live view for a device that talks on its own, and while it runs nothing can
be sent.

## Baud rates

300, 1200, 2400, 4800, 9600, 19200, 31250 (MIDI), 38400, 57600, 115200.
Anything else goes through `set_manual_baudrate()` with a raw BRG divisor.

## Reading the symptoms

| What you see | What it means |
|--------------|---------------|
| Nothing at all | TX/RX swapped, no common ground, or the target is silent |
| Consistent garbage | wrong baud rate |
| Mostly right, occasional wrong byte | baud rate close but not exact, or a noisy line |
| Every byte doubled | echo is on at both ends |
| Correct text, then nothing | the target stopped, or flow control it expects is missing |
| A stream of the same junk byte (`18` on a v4) with nothing connected | the line was never set up: until **Set the line up** runs, the firmware is at 300 baud with its transmit pin not driving, so a loop or an unconnected RX floats and the noise is received. The dashboard now sets the line up itself before it listens or sends |

Garbled characters are a speed problem, not a wiring problem: wiring faults
give you silence, not nonsense.

**A loopback test** (MOSI jumpered to MISO, no target) checks the Bus
Pirate's own UART: send `Hi` with CR LF and `48 69 0d 0a` comes straight
back. Any length works: while the firmware transmits it cannot forward what
it receives, and its receive buffer holds only about four bytes, so the
dashboard sends four bytes at a time and collects the echo in between.

## Watching, and the bridge

**Watch the line** streams everything received into the dashboard as it
arrives — better than repeated reads for catching boot messages.

**Transparent bridge** turns the Bus Pirate into a plain USB-to-serial
adapter. The firmware documents it as "reset to exit": **there is no way out
in software.** You have to unplug the Bus Pirate and plug it back in. The
dashboard asks before starting it, and says so again afterwards.

## Voltage levels

The Bus Pirate's UART is 3.3V logic and tolerates 5V inputs. It is **not**
RS-232: a real serial port swings ±12V and will damage it. For RS-232 you
need a level shifter such as a MAX3232.
