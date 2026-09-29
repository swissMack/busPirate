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
- [x] v4: the 2x6 header order against a real BPv4.0's silkscreen — which is
      printed on the underside, so it reads mirrored (see
      [the wiring card](wiring-card.html))

Checked on 2026-09-28 on the same **Bus Pirate v4, firmware v6.0-a3**:

- [x] The one-click supplies switch: one click turns the supplies on — VREG
      lights on the board and in the dashboard — and one click turns them off
- [x] "Apply to the board" on the pin card leaves the supplies as they were:
      VREG stays lit and the switch still says On
- [x] Extended AUX (`0x09`) on a v4: firmware 6.0-a3 refuses it with `0x00`;
      after updating the same board to **firmware 7.0**, it answers `0x01`
      and then hangs for good, waiting on a UART the host is not connected
      to. The dashboard no longer offers it on a v4
- [x] v4 on 7.0: AUX moves from Pins & power — made an output and driven
      high it measured 3.3 V, driven low 0 V, and released as an input again
- [x] The v4 updates to firmware 7.0 with `pirate-loader`, entering its
      bootloader (v4.06) with a PGC–PGD jumper — see
      [Bus Pirate v4](bus-pirate-v4.md#updating-the-firmware)

Checked on 2026-09-29 on the same **Bus Pirate v4, firmware 7.0**, with real
parts and then with the probe cable alone:

- [x] I2C: an AHT20 + BMP280 module (0x38, 0x77) scans cleanly with the
      Bus Pirate's pull-ups **off** (the module has its own); with them on and
      VPU unconnected the scan reported 18 phantom addresses. Read the sensors
      gave 29.1 °C / 44 %RH and 29 °C / 938.8 hPa, the AHT20's CRC OK
- [x] 1-Wire: a DS18B20 probe needed an external 4.7 kΩ pull-up — its
      "module" had none. Search, ROM CRC and scratchpad CRC all OK; 29.69 °C,
      31.9 °C held. The search reply is `01`, 8 bytes per device, eight `FF`
      (the driver had expected a fixed 256 bytes)
- [x] Analog: an AD595 thermocouple amplifier on the ADC read 0.37 V =
      36.9 °C with the probe held
- [x] I2C: a 16×2 HD44780 LCD on a PCF8574 backpack at 0x27, driven from
      Translate for an LCD / Send to an LCD
- [x] The pull-up rail command works on 7.0: VPU measured 3.29 V at 3.3V,
      4.97 V at 5V, 0 V off. With the rail at 3.3V and pull-ups on, MOSI read
      3.29 V; pull-ups off gave 0.02 V, and pull-ups on with the rail off 0 V
- [x] ADC against a multimeter: GND 0.000 V exactly; the 3.3V rail (3.295 V
      on the meter) read 3.403 V and the 5V rail (4.985 V) read 5.066 V — the
      ADC reads 2–3 % high between 3 and 5 V
- [x] UART loopback (MOSI jumpered to MISO): "Hi", "Hello" and a 44-byte
      message come back complete, sent four bytes at a time while listening.
      Listening before the line was set up left it floating at 300 baud and
      forwarded noise (`18`) ahead of every reply — the dashboard now sets the
      line up first and keeps stray bytes out of replies
- [x] AUX1 and AUX2 stay at 0 V while AUX is driven to 3.29 V and to 0 V
- [x] `~` self-test: 0 errors with ADC jumpered to +3.3V (it asks for
      nothing else on a v4). Without the jumper, the only failure is
      `ADC(0.00)`
- [x] The terminal's mode menu lists 11 modes, the same numbering as the v3:
      HiZ, 1-WIRE, UART, I2C, SPI, 2WIRE, 3WIRE, KEYB, LCD, PIC, DIO. `i`
      reports `REVID:0x0004 (24FJ256GB106 UNK)` — an unrecognised silicon
      revision, cosmetic only
- [x] The terminal on 7.0: open, `i`, `m`, `~`, then Stop — the dashboard
      is back in binary mode at once (twenty `00`s answered `BBIO1`) and the
      next Measure a voltage answers normally, with no reconnect. With
      nothing on the ADC lead it reads a clean 0.000 V: the input divider
      pulls it to ground

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
- [ ] SPI "Read a sensor" with a real MAX31855 — checked against its
      datasheet only
- [ ] The I2C and SPI sniffers against real traffic — in particular whether
      stopping resynchronises cleanly on your firmware version
- [ ] v4: the measured LED and pin coordinates land on the real parts
- [ ] v3: AUX and CS actually move from the I2C panel's "Drive AUX or CS"
      (firmware v6.1+), and its `read` sub-command (`0x03`) replies with the
      pin state, 0 or 1. Taken from the firmware source; on a v4 the same
      command hangs the board — see [Bus Pirate v4](bus-pirate-v4.md)

### ESP32 Bit Pirate (ESP32-S3-DevKitC-1, firmware 1.7)

Nothing here has met a real board yet. The driver follows the firmware's
source, so check these first, in this order:

- [ ] The USB ID the port reports (Espressif `303A:`, PID not yet known) and
      that auto-detect picks it
- [ ] Opening the port does not reset the board; a fresh boot's "Press any
      key" is answered and the banner's version is read
- [ ] `m i2c` the first time: the config questions are answered and the
      prompt comes back as `I2C> `
- [ ] `scan` with nothing on the bus, and with one device
- [ ] A register read (`[0x68 0x00 r:8]`) returns the right bytes, and a read
      from an empty address fails cleanly rather than timing out
- [ ] `P` and `p` switch the internal pull-ups (measure SDA to 3V3)
- [ ] SPI JEDEC ID on a real flash chip, and a 64 KB dump at 8 MHz
- [ ] UART send, and the monitor stopping cleanly on Stop
- [ ] Terminal open and close, then an I2C scan — the session back in step
- [ ] Disconnect leaves the board at `HIZ> `
