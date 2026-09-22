# busPirate — user guide

A Bus Pirate lets you talk to a chip without writing firmware for it. This
repo wraps one in a Python driver, a command line, and a web dashboard.

**If you have not used this in months, read this page and nothing else.**

## 60-second start

1. Plug the Bus Pirate into USB.
2. In Finder, open the `bin` folder and double-click **`dashboard.command`**.
   The first run builds a Python environment; later runs start in a second.
3. The dashboard opens in its own window — or your browser, if the window
   couldn't start (see [Dashboard](dashboard.md#window-or-browser)). Click
   **Connect**.
4. Pick the panel for your bus and press the big button.

No hardware to hand? Double-click **`bin/demo.command`** instead — everything
works against a simulated Bus Pirate, which is the cheapest way to remind
yourself how the tool fits together.

## I want to…

| Goal | Where | Notes |
|------|-------|-------|
| See what is on an I2C bus | Dashboard → I2C → **Scan the bus** | [I2C](i2c.md) |
| Read a sensor or RTC register | Dashboard → I2C → **Read a register** | [I2C](i2c.md) |
| Read a 24Cxx EEPROM | Dashboard → I2C → **Read a 24Cxx EEPROM** | 24C32 and up need a 2-byte address |
| Work out what an SPI flash chip is | Dashboard → SPI → **Identify the chip** | [SPI](spi.md) |
| Dump an SPI flash to a file | Dashboard → SPI → **Dump flash to a file** | lands in `captures/` |
| Watch a serial line | Dashboard → UART → **Set the line up**, then **Start listening** | [UART](uart.md) |
| Read DS18B20 temperatures | Dashboard → 1-Wire → **Read temperatures** | needs a 4k7 pull-up |
| Watch two other devices talk | Dashboard → I2C or SPI → **Sniff the bus** | passive; nothing is driven |
| Get the board's own `HiZ>` prompt | Dashboard → Terminal → **Open the board's terminal** | leaves binary mode; see [Dashboard](dashboard.md#the-boards-terminal) |
| Write a file back to SPI flash | Dashboard → SPI → **Write a file to flash** | erases first, then verifies |
| Erase a flash chip | Dashboard → SPI → **Erase one sector** / **the whole chip** | not reversible |
| Talk to something odd | Dashboard → Raw wire | [Raw wire](rawwire.md) |
| Measure a voltage | Dashboard → Pins & power → **Measure a voltage** | [Pins & power](pins-and-power.md) |
| Drive pins by hand | Dashboard → Pins & power | |
| Watch a voltage over time | Dashboard → Pins & power → **Watch a voltage** | continuous ADC |
| Script any of it | `from buspirate import BusPirate` | [CLI](cli.md), and the examples below |
| Find which port it is on | `buspirate ports` | [macOS setup](macos-setup.md) |

## The three things that go wrong

Almost every failed session is one of these. Check them before anything else.

1. **The wrong port.** On macOS use `/dev/cu.*`, never `/dev/tty.*`. See
   [macOS setup](macos-setup.md).
2. **No pull-ups.** I2C needs them on both lines and 1-Wire needs a real 4k7
   resistor. The Bus Pirate's built-in pull-ups do nothing unless the VPU pin
   is tied to the bus voltage.
3. **A reversed cable.** The colour order is a *Seeed* convention; SparkFun
   cables are usually the other way round. Confirm with Connection →
   **Show the cable legend**.

If none of those, [troubleshooting](troubleshooting.md) has the rest.

## Where things live

| Path | What it is |
|------|-----------|
| `bin/dashboard.command` | Double-click to start. Sets itself up on first run. |
| `bin/demo.command` | The same, against a simulated device. |
| `buspirate/` | The driver. `base.py` is the transport, one module per protocol. |
| `buspirate/web/` | The dashboard. `panels/` is where you add things. |
| `examples/` | Short scripts to copy from. |
| `captures/` | Dumps and logs. Ignored by git. |
| `docs/` | This guide. |

## Reading further

- [macOS setup](macos-setup.md) — drivers, ports, the venv, the launcher
- [Dashboard](dashboard.md) — every panel and recipe
- [Command line](cli.md) — for scripting and CI
- [I2C](i2c.md) · [SPI](spi.md) · [UART](uart.md) · [1-Wire](onewire.md) ·
  [Pins & power](pins-and-power.md)
- [Bus Pirate v4](bus-pirate-v4.md) — what differs from a v3
- [Troubleshooting](troubleshooting.md)
- [Protocol reference](protocol-reference.md) — the binary command tables
- [Extending](extending.md) — add a protocol, end to end

## The probe cable

Pin 1 is **MISO (black)** and pin 10 is **GND (brown)** — not the other way
round, which is the easy mistake to make.

| Pin | Signal | Colour | What it is |
|-----|--------|--------|-----------|
| 1 | MISO | black | data in, the target's TX on a UART |
| 2 | CS | white | chip select, active low |
| 3 | MOSI | grey | data out; SDA on I2C, OWD on 1-Wire |
| 4 | CLK | pink | clock; SCL on I2C |
| 5 | AUX | blue | auxiliary I/O, frequency probe, PWM |
| 6 | VPU | green | input for the pull-up resistors, 0–5V |
| 7 | ADC | yellow | A/D converter, max 6V, 10-bit |
| 8 | +5V | orange | switchable supply, max 150 mA |
| 9 | +3.3V | red | switchable supply, max 150 mA |
| 10 | GND | brown | ground to the test circuit |

This is the Seeed Studio / Adafruit cable, which is the order the firmware
itself uses. **SparkFun cables are usually reversed and the v2go differs** —
check yours with Connection → **Show the cable legend**, or the `i` command.

## The board's header

The probe header is a 2×5 IDC on a **v3.6** and a **2×6** IDC on a **v4** —
two more pins, both AUX lines. On a v3.6 the silkscreen names every pin, and
they sit like this with the USB socket on the left:

```
        left column        right column
   ┌──────────────────────────────────┐
   │  GND   ●          ●   +3.3V      │
   │  +5V   ●          ●   ADC        │
   │  VPU   ●          ●   AUX        │
   │  CLK   ●          ●   MOSI       │
   │  CS    ●          ●   MISO       │
   └──────────────────────────────────┘
```

A v4's header adds a row and carries `AUX1` and `AUX2` alongside the
existing `AUX`:

```
        left column        right column
   ┌──────────────────────────────────┐
   │  GND   ●          ●   +5V        │
   │  +3.3V ●          ●   VPU        │
   │  ADC   ●          ●   AUX2       │
   │  AUX1  ●          ●   AUX        │
   │  CS    ●          ●   MISO       │
   │  CLK   ●          ●   MOSI       │
   └──────────────────────────────────┘
```

The dashboard draws whichever of these matches the connected device on a
photograph of the board, with the pins the current panel needs ringed and
labelled with what they connect to — so you do not have to hold any of it in
your head. The reference card and the cable card sit underneath it.

**A Bus Pirate v4 is laid out differently: it is that extra row of AUX
pins**, not a rearrangement of the ten a v3 has. Read your own silkscreen
before trusting a picture of someone else's board — see
[Bus Pirate v4](bus-pirate-v4.md#the-header-a-2x6-not-a-2x5) for the sourced
pinout and what `AUX1`/`AUX2` can and cannot do from the dashboard.
