# The dashboard

```
bin/dashboard.command          # real hardware
bin/demo.command               # simulated, no hardware needed
buspirate dashboard            # the same, from a terminal
buspirate dashboard --demo --variant v4
make dash / make demo
```

It serves on `http://127.0.0.1:8765/` and **refuses to bind anything but the
loopback address** — it drives hardware and has no authentication, so it is
not something to expose.

## Layout

```
┌──────────────────────────────────────────────┐
│ busPirate   [recipes…]    ● SIMULATED v3 · i2c│
├────────────┬─────────────────────────────────┤
│ Connection │  I2C                            │
│ ▸ I2C      │  Wiring: CLK→SCL  MOSI→SDA …    │
│   SPI      │  ┌ Scan the bus ──────────────┐ │
│   UART     │  │ ☑Power ☑Pull-ups [100kHz]  │ │
│   1-Wire   │  │ 0x50 EEPROM   0x68 RTC     │ │
│   Pins     │  └────────────────────────────┘ │
├────────────┴─────────────────────────────────┤
│ 11:39:13 -> 02   <- 01   -> 10 a0   <- 01 00 │
└──────────────────────────────────────────────┘
```

- **Recipe strip** — the jobs worth a single click. Selecting one jumps to it.
- **Panels** — one per protocol. Each opens with what it is for, a **hook-up
  diagram**, and the warnings that matter for that bus.
- **Hook-up diagram** — the Bus Pirate's own reference cards with *this* bus
  marked on them: the protocol's column on the pin-function card, and the
  probe wires it uses on the cable card. Nothing to translate in your head.
- **Guide** — the whole user guide is in the sidebar, and every panel links to
  its own page.
- **Traffic log** — every byte in both directions, live. `->` is what the Mac
  sent, `<-` what the Bus Pirate replied. This is the fastest way to tell a
  wiring fault from a protocol one.

Switching panels switches the device's mode for you. The Pins & power panel
works in bitbang mode, so selecting it leaves whatever protocol mode you were
in — that is expected.

## Panels

### Connection
Connect (leave the port blank to auto-detect), disconnect, **What is this
device?** (hardware, firmware, feature list) and **Show the cable legend**
(which probe wire is which signal). On a v3 there is also a self-test —
unplug the probe from your target first.

### I2C
**Scan the bus** probes 0x08–0x77 and names the chips it recognises.
**Read a register** writes the register number then reads, with a repeated
start — the pattern nearly every sensor expects. **Read a 24Cxx EEPROM**
handles the memory-address width for you. On a v4, **Set the pull-up rail**
connects VPU to 3.3V or 5V. See [I2C](i2c.md).

### SPI
**Identify the chip** sends `0x9F` and decodes manufacturer and capacity.
**Read from flash** and **Dump flash to a file** use the standard `0x03`
read; dumps go to `captures/` with a progress bar. See [SPI](spi.md).

### UART
Set baud and framing, listen, and send text or raw bytes. Remember TX and RX
cross over. See [UART](uart.md).

### 1-Wire
**Find devices** runs the ROM search and names the family.
**Read temperatures** reads every DS18B20-family sensor. See
[1-Wire](onewire.md).

### Pins & power
Drive each pin, set directions, switch the supplies, measure a voltage on the
ADC pin, measure a frequency on AUX, output PWM. See
[Pins & power](pins-and-power.md).

## Things you will wonder about later

- **Controls that are missing** are missing on purpose: an action declares the
  capability it needs, and the dashboard hides what your hardware cannot do.
  The pull-up rail selector appears only on a v4; the self-test only on a v3.
- **State lives on the server.** Reloading the browser does not disconnect the
  Bus Pirate, which is what you want when a page gets into a mess.
- **One caller at a time.** A serial port cannot be shared, so actions are
  serialised. If two clicks overlap, the second waits.
- **Demo mode** (`--demo`) is the full UI against a simulated device. Use it
  to re-learn the tool without wiring anything up, and to check the software
  still works after an OS upgrade.

## Credits

The two reference cards shown in the hook-up diagrams are from the Dangerous
Prototypes wiki (dangerousprototypes.com), used under CC BY-SA. See
`buspirate/web/static/img/CREDITS.md`.

To add a panel of your own, see [extending](extending.md).
