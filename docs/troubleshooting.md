# Troubleshooting

## The port

**Look at the board first.** The four LEDs along the top edge answer the first
question for free: **PWR** dark is power or cable, **USB** dark with PWR lit is
drivers or enumeration, and neither is a Bus Pirate fault. The full table is in
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

## Not yet verified against hardware

This driver was written from the published protocol documentation and is
tested against a simulated device. These points deserve a check the first
time you use real hardware, and a bug report here if they are wrong:

- [ ] `buspirate ping` on a v3, and on a v4
- [ ] `identify()` parses your device's real `i` banner
      (`buspirate ping` prints what it made of it)
- [ ] `write_then_read()` against a real 24Cxx EEPROM — the wire format is
      taken from the documented command, not from observation
- [ ] SPI `set_mode()` against a real flash chip. The CKP/CKE mapping now
      follows the documented startup default (mode 0 = CKP 0, CKE 1), but it
      has only been checked against the documentation, not a scope.
- [ ] A flash erase/write/verify round trip on a real chip, ideally one you
      have dumped first
- [ ] The I2C and SPI sniffers against real traffic — in particular whether
      stopping resynchronises cleanly on your firmware version
- [ ] The v4 pull-up rail command on firmware that actually implements it
- [ ] The probe cable colour table against your own cable
      (Connection → **Show the cable legend**)
