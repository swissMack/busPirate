# Troubleshooting

## The port

**Look at the board first.** The four LEDs along the top edge answer the first
question for free, and neither result is a Bus Pirate fault: **PWR** dark is
power or cable, on either board. **USB** dark with PWR lit means drivers or
enumeration **on a v3** — but on a **v4** it's firmware-driven and goes out
once enumeration completes, so dark there is the healthy state, not a
symptom. The full table is in
[Pins & power](pins-and-power.md#the-four-leds).

### "no USB serial ports found"

The Mac cannot see the adapter at all.

1. Try another USB cable — many micro-USB cables carry power only.
2. Plug straight into the Mac, not a hub or a monitor.
3. `ioreg -p IOUSB -l -w 0 | grep -i "USB Product Name"` — if the device is
   not there, it is hardware or cable, not drivers.
4. `buspirate ports --all` to see everything macOS has, including Bluetooth.

### "cannot open /dev/cu.…: Resource busy"

Something else holds the port. Usually a `screen` you forgot:

```bash
lsof | grep cu.usbserial          # what has it open
screen -ls                        # list detached sessions
screen -X -S <session> quit       # kill one
pkill -f "screen.*usbserial"      # or all of them
```

The dashboard also holds the port while connected — disconnect it first.

### It hangs forever with no error

You are on `/dev/tty.*`. That device blocks until carrier detect, which the
Bus Pirate never asserts. Use the `/dev/cu.*` device with the same name.
`--port auto` does this for you.

## The device

### "no BBIO response after 25 attempts"

The Bus Pirate is not answering the binary handshake.

1. Wrong port — check `buspirate ports`.
2. Wrong baud. The Bus Pirate is 115200 8N1. If you changed it in the
   terminal, it may have stuck.
3. The firmware is mid-command from a previous session. Unplug it for a few
   seconds and try again — a power cycle always resolves this.
4. Very old firmware. Binary modes need v2.6 or newer; `write_then_read`
   needs v5.1.

### "expected a BBIO<version> banner, got …"

The device is mid-stream from an earlier command. Reconnecting resynchronises;
the driver also does this automatically after a failed mode entry.

### Self-test reports errors

Disconnect the probe cable from everything and run it again. Anything
attached to the pins will fail the test. Self-test is v3 hardware only.

## The bus

### An I2C scan finds nothing

In order of likelihood: pull-ups off or VPU floating; target unpowered; SDA
and SCL swapped; no common ground. See [I2C](i2c.md).

### SPI returns all `00` or all `FF`

MISO is not connected, or WP/HOLD are not tied high. The chip is not blank.

### UART shows garbage

Wrong baud rate. Wiring faults give silence, not nonsense. See
[UART](uart.md).

### 1-Wire finds nothing

Fit a 4k7 pull-up from DQ to VCC. See [1-Wire](onewire.md).

### A DS18B20 reads exactly 85.0 °C

That is the power-on default: the conversion never completed. Wait the full
750 ms, or give a parasite-powered sensor a real VDD wire.

### It worked yesterday and not today

Swap the probe cable. Dupont leads fail intermittently, and a single bad
conductor gives exactly this — mostly working, occasionally not.

## The software

### The dashboard will not start

```bash
make test        # does the package still import and pass?
make demo        # does the UI work without hardware?
```

If `demo` works and `dash` does not, the problem is the port or the device,
not the software.

### The first double-click is refused

Gatekeeper. Right-click → **Open** → **Open**, once. Or:

```bash
xattr -d com.apple.quarantine bin/*.command
```

### After a macOS upgrade

The system Python may have changed. `make clean && make setup` rebuilds the
virtualenv.

---

## Verified against hardware

Checked on 2026-09-25 on a **Bus Pirate v3.a, firmware v6.1 r1676** and a
**Bus Pirate v4, firmware v6.0-a3**:

- [x] `buspirate ping` on a v3, and on a v4
- [x] `identify()` parses both boards' real `i` banners — the v4's has no
      build number and no bootloader line
- [x] SPI `spi-id` on a bare bus: a clean `00 00 00` and the MISO warning
- [x] `i2c-scan` on a bare bus: with VPU floating every address "answers"
      (SDA held low reads as an ACK); the scan now says so. With VPU tied to
      a supply it finds nothing, as it should
- [x] The probe cable colour table against a real v3 cable and the
      firmware's own `v` pin table — CLK is **purple** (the table said pink)
- [x] v3: the LED model — MODE lit from connect, USB flickering on traffic,
      VREG following the supplies
- [x] v4: MODE lit from connect, and the USB LED **dark** once enumerated
- [x] v3: opening the terminal resets the board — supplies measured at
      0.00 V, pins to input
- [x] v4: opening the terminal **also** resets the board — the claim that it
      does not was wrong. It drops off USB (gone at 188 ms, back at 463 ms);
      the dashboard now follows it
- [x] Both: MODE goes dark while the terminal is open, and comes back after
- [x] The first prompt after leaving binary mode arrives complete
- [x] Returning to binary mode works reliably, including straight after a
      reset — 10 of 10 on a v3; now 0.4 s on both boards (it was 4.3 s)
- [x] `~` self-test runs to completion through the console, stopping at
      "Space to continue" and "Any key to exit" — 0 errors on a v3, with MODE
      and VREG lit at the end
- [x] A board left at a menu question, or left in binary mode, still
      connects and is identified

## Not yet verified against hardware

These still deserve a check the first time you have the hardware, and a bug
report here if they are wrong:

- [ ] `write_then_read()` against a real 24Cxx EEPROM — the wire format is
      taken from the documented command, not from observation
- [ ] SPI `set_mode()` against a real flash chip. The CKP/CKE mapping follows
      the documented startup default (mode 0 = CKP 0, CKE 1), but it has only
      been checked against the documentation, not a scope.
- [ ] A flash erase/write/verify round trip on a real chip, ideally one you
      have dumped first
- [ ] The I2C and SPI sniffers against real traffic — in particular whether
      stopping resynchronises cleanly on your firmware version
- [ ] The v4 pull-up rail command on firmware that actually implements it
- [ ] v4: the 2x6 header order against your own silkscreen (see
      [the wiring card](wiring-card.html))
- [ ] v4: the measured LED and pin coordinates land on the real parts
- [ ] v4: AUX and CS actually move from the I2C panel's "Drive AUX or CS"
- [ ] v4: AUX1 and AUX2 stay inert — nothing in the dashboard should move them
- [ ] v4: extended AUX's `read` sub-command (`0x03`) reply is the pin state
      (0 or 1), not an ack — every other sub-command replies `0x01`. Taken
      from a reading of the firmware, not observed on hardware.
- [ ] v4: the `~` self-test and its jumpers
