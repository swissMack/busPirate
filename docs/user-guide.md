# busPirate — user guide

A Bus Pirate lets you talk to a chip without writing firmware for it. This
repo wraps one in a Python driver, a command line, and a web dashboard.

**If you have not used this in months, read this page and nothing else.**

Using an **ESP32 Bit Pirate** rather than a Bus Pirate? The dashboard drives
that too, differently. Everything about it is in one place:
[The ESP32 Bit Pirate](#the-esp32-bit-pirate), at the end of this page.

## 60-second start

1. Plug the Bus Pirate into USB.
2. In Finder, open the `bin` folder and double-click **`dashboard.command`**.
   The first run builds a Python environment; later runs start in a second.
3. The dashboard opens in its own window — or your browser, if the window
   couldn't start (see [Dashboard](dashboard.md#window-or-browser)). Click
   **Connect**.
4. Pick the panel for your bus and press the big button.

No hardware to hand? Press **Try a simulated one** on the connect screen (or
pick `simulated-v3` / `simulated-v4` from the port list), or double-click
**`bin/demo.command`** to start straight into one — everything works against
a simulated Bus Pirate, which is the cheapest way to remind
yourself how the tool fits together.

## I want to…

| Goal | Where | Notes |
|------|-------|-------|
| See what is on an I2C bus | Dashboard → I2C → **Scan the bus** | [I2C](i2c.md) |
| Read a sensor or RTC register | Dashboard → I2C → **Read a register** | [I2C](i2c.md) |
| Read a 24Cxx EEPROM | Dashboard → I2C → **Read a 24Cxx EEPROM** | 24C32 and up need a 2-byte address |
| Work out what an SPI flash chip is | Dashboard → SPI → **Identify the chip** | [SPI](spi.md) |
| Dump an SPI flash to a file | Dashboard → SPI → **Dump flash to a file** | lands in `captures/` |
| Talk to a serial device | Dashboard → UART → **Set the line up**, then **Send text** — replies show under it | [UART](uart.md) |
| Watch a serial line | Dashboard → UART → **Watch the line** | [UART](uart.md) |
| Read DS18B20 temperatures | Dashboard → 1-Wire → **Read the sensors** | needs a 4k7 pull-up |
| Read a sensor in real units | Dashboard → I2C → **Read the sensors** | knows the AHT20 and BMP280/BME280; see [Extending](extending.md#adding-a-device) to add more |
| Watch two other devices talk | Dashboard → I2C or SPI → **Sniff the bus** | passive; nothing is driven |
| Get the board's own `HiZ>` prompt | Dashboard → Terminal → **Open the board's terminal** | leaves binary mode; see [Dashboard](dashboard.md#the-boards-terminal) |
| Write a file back to SPI flash | Dashboard → SPI → **Write a file to flash** | erases first, then verifies |
| Erase a flash chip | Dashboard → SPI → **Erase one sector** / **the whole chip** | not reversible |
| Talk to something odd | Dashboard → Raw wire | [Raw wire](rawwire.md) |
| Switch the supplies on or off | Dashboard → Pins & power → the **supplies switch** | one click, both supplies |
| Let go of the target, now | **HiZ**, under Connection in the left column | every pin an input, supplies and pull-ups off, still connected. It reads **Live**, highlighted, while anything holds the target |
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
- [ESP32 Bit Pirate](bitpirate.md) — the third board, in depth
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
| 4 | CLK | purple | clock; SCL on I2C |
| 5 | AUX | blue | auxiliary I/O, frequency probe, PWM |
| 6 | VPU | green | input for the pull-up resistors, 0–5V |
| 7 | ADC | yellow | A/D converter, max 6V, 10-bit |
| 8 | +5V | orange | switchable supply, max 150 mA |
| 9 | +3.3V | red | switchable supply, max 150 mA |
| 10 | GND | brown | ground to the test circuit |

This is the Seeed Studio / Adafruit cable, which is the order the firmware
itself uses. **SparkFun cables are usually reversed and the v2go differs** —
check yours with Connection → **Show the cable legend**, or the `i` command.

**Go by position, not by colour.** Dyes vary between batches: on one real
cable GND's brown was so light it passed for grey, and +5V's orange read as
pink. Find GND by its place at the edge of the ribbon, count from there, and
if in doubt measure — the ADC probe reads any rail.

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

---

## The ESP32 Bit Pirate

The [ESP32 Bit Pirate](https://github.com/geo-tp/ESP32-Bit-Pirate) is free
firmware that turns an ESP32-S3 board into a Bus Pirate-style tool. The
dashboard supports it on an **ESP32-S3-DevKitC-1** flashed with the
**s3-devkit** build.

Everything above this line is about the Bus Pirate v3 and v4. This section
stands on its own: read it instead of the above when a Bit Pirate is
plugged in. [ESP32 Bit Pirate](bitpirate.md) has the in-depth comparison and
how the dashboard drives it.

**How it differs.** A Bus Pirate speaks a binary protocol; the Bit Pirate
has only a command line, which the dashboard types into for you. It has no
switchable supplies and no probe cable. It is **3.3V only**. Its pins are
plain GPIOs you choose. The dashboard shows only what it can really do, so
some panels and buttons you know from a Bus Pirate are simply not there when
a Bit Pirate is connected.

### 60-second start

1. Flash it once, from the
   [web flasher](https://geo-tp.github.io/ESP32-Bit-Pirate/webflasher/),
   choosing **s3-devkit**.
2. Plug in the DevKit's socket marked **USB**, not the one marked UART.
3. Double-click **`bin/dashboard.command`** and click **Connect**. The port
   shows as *Espressif ESP32 USB (ESP32 Bit Pirate)*. The status bar reads
   *ESP32 Bit Pirate*, with the firmware version if it saw the board start.
4. Pick I2C, SPI or UART and press the big button.

**The board LED.** On the [mode-LED firmware](bitpirate.md#installing-the-mode-led-firmware) the
DevKit's RGB LED shows the mode: **off** HiZ (pins released, safe to rewire),
**blue** I2C, **green** SPI, **yellow** UART, **cyan** 1-Wire, **dim white**
anything else. There is no power-supply colour: the 3V3 pin is always live.
[The board LED](bitpirate.md#the-board-led-mode-colours) has the details.

A board plugged in a moment ago spends about three seconds choosing its
terminal before it listens. If connecting fails straight after plugging in,
wait and connect again.

No hardware? Pick `simulated-bitpirate` from the port list, or run
`buspirate app --demo --variant bitpirate`.

### I want to…

| Goal | Where | Notes |
|------|-------|-------|
| See what is on an I2C bus | I2C → **Scan the bus** | turn the pull-up switch on unless the board has its own |
| Read a sensor or RTC register | I2C → **Read a register** | 7-bit addresses, as the scan shows them |
| Read bytes without a register first | I2C → **Read bytes** | |
| Write bytes to an I2C device | I2C → **Write bytes** | at most 96 bytes; see below on ACKs |
| Read a 24Cxx EEPROM | I2C → **Read a 24Cxx EEPROM** | 24C32 and up need a 2-byte address |
| Change the I2C speed or pull-ups | I2C → **Set speed and power** | no power box: there is nothing to power |
| Work out what an SPI flash chip is | SPI → **Identify the chip** | tie WP and HOLD to 3.3V first |
| Read part of an SPI flash | SPI → **Read from flash** | |
| Dump an SPI flash to a file | SPI → **Dump flash to a file** | lands in `captures/` |
| Check a flash against a file | SPI → **Compare with a file** | names the first byte that differs |
| Send any SPI command | SPI → **Send bytes** | CS held low throughout; at most 96 bytes out |
| Set up a serial line | UART → **Set the line up** | 5 to 8 data bits |
| Watch a serial line | UART → **Watch the line** | live, until you press Stop |
| Send text or bytes down a serial line | UART → **Send text** / **Send raw bytes** | |
| Get the board's own `HIZ>` prompt | Terminal → **Open the board's terminal** | nothing resets; `help` lists commands |
| Check what is connected | Connection → **What is this device?** | |
| Leave it safe | **HiZ** in the left column, or Connection → **Disconnect** | both put it back in HiZ; Disconnect also releases the port |
| Anything else | its own prompt | see [What only its own prompt can do](#what-only-its-own-prompt-can-do) |

**Not in the dashboard for this board:**
- Pins & power, 1-Wire and Raw wire.
- The sniffers.
- Writing or erasing flash.
- SPI modes other than 0.
- The batched UART listen-and-read, and the bridge.

Several of these are still at its own prompt.

### The four things that go wrong

1. **The wrong USB socket.** The DevKit has two. Only the one marked **USB**
   talks to the dashboard; **UART** carries boot messages only.
2. **5V on a pin.** The ESP32-S3 is a 3.3V part and its pins are not 5V
   tolerant. Level-shift anything that drives 5V.
3. **Weak pull-ups.** The pull-up switch uses the ESP32's internal pull-ups,
   about 45 kΩ. That is enough for a short bus at 100 kHz. For anything
   longer or faster, fit 4.7 kΩ resistors to 3.3V.
4. **A moved pin.** Pins can be reassigned at the board's prompt, and the
   dashboard's pictures always show the defaults. If it worked yesterday and
   not today, check `config` in that mode.

Two differences to expect rather than fix:

- **I2C writes check the address, not every byte.** The firmware does not
  report an ACK per byte, so the dashboard pings the address first and says
  only that. A byte the target refused goes unnoticed.
- **The SPI clock is whole MHz.** 1, 2, 4 or 8 MHz from the list. The slower
  settings are refused with a message saying so.

### Wiring it

There is no probe cable; wire GPIOs with jumper leads. The dashboard draws
the DevKit with the pins each panel needs ringed and labelled. These are the
defaults:

| Bus | Wire this GPIO | To the target's |
|-----|----------------|-----------------|
| I2C | GPIO7 | SCL |
| | GPIO6 | SDA |
| SPI | GPIO12 | SCK / CLK |
| | GPIO13 | DI / MOSI |
| | GPIO11 | DO / MISO |
| | GPIO10 | CS |
| UART | GPIO17 (its RX) | TX |
| | GPIO18 (its TX) | RX |
| all | GND | GND — connect it first |
| if needed | 3V3 | VCC, for a small target only |

To move a pin, open the Terminal, enter the mode (`m i2c`), type `config` and
answer its questions. Then type `profile` to keep the change.

All of them are on header **J1**, the left one when the USB sockets point
down. Pin 1 is at the top:

```
   J1 (left)                     J3 (right)
   ┌──────────────────────────────────────┐
   │  3V3    ●                  ●  GND    │
   │  3V3    ●                  ●  GPIO43 │
   │  RST    ●                  ●  GPIO44 │
   │  GPIO4  ●                  ●  GPIO1  │
   │  GPIO5  ●                  ●  GPIO2  │
   │  GPIO6  ●  I2C SDA         ●  GPIO42 │
   │  GPIO7  ●  I2C SCL         ●  GPIO41 │
   │  GPIO15 ●                  ●  GPIO40 │
   │  GPIO16 ●                  ●  GPIO39 │
   │  GPIO17 ●  UART RX         ●  GPIO38 │
   │  GPIO18 ●  UART TX         ●  GPIO37 │
   │  GPIO8  ●                  ●  GPIO36 │
   │  GPIO3  ●                  ●  GPIO35 │
   │  GPIO46 ●                  ●  GPIO0  │
   │  GPIO9  ●                  ●  GPIO45 │
   │  GPIO10 ●  SPI CS          ●  GPIO48 │
   │  GPIO11 ●  SPI MISO        ●  GPIO47 │
   │  GPIO12 ●  SPI CLK         ●  GPIO21 │
   │  GPIO13 ●  SPI MOSI        ●  GPIO20 │
   │  GPIO14 ●                  ●  GPIO19 │
   │  5V     ●                  ●  GND    │
   │  GND    ●                  ●  GND    │
   └──────────[ USB ]──[ UART ]───────────┘
```

This is Espressif's v1.1 pinout. The order of the two USB sockets varies
between revisions, so go by the **USB** and **UART** printed next to them,
and check your own silkscreen before trusting this picture.

### Everyday jobs

**Find and read an I2C device.** I2C → **Scan the bus**, then **Read a
register** with an address it found.

**Read a 24Cxx EEPROM.** I2C → **Read a 24Cxx EEPROM**. Choose the 2-byte
address width for a 24C32 or larger. Long reads go in 128-byte pieces behind
the scenes, but you get one dump.

**Identify and dump an SPI flash.** SPI → **Identify the chip**, then **Dump
flash to a file**. To check a dump later, use **Compare with a file**. To
*write* flash on this board, use its own `flash` tool at the prompt, since
the dashboard cannot.

**Watch a serial console.** UART → **Set the line up** with the baud rate,
then **Watch the line**, and **Stop** to end it. **Send text** and **Send
raw bytes** talk back.

**Use its own prompt.** Terminal → **Open the board's terminal**. Unlike on a
Bus Pirate, nothing resets, so there is no warning to accept. Type as you
would in a serial terminal: `help` lists commands, and `mode` on its own gives
a numbered menu of every mode. Press **Stop** when you are done. The other
panels carry on from there, even if you changed mode at the prompt.

### What only its own prompt can do

The firmware does far more than the dashboard drives. Everything below is
reached from the Terminal panel. `help` in each mode lists its commands, and
anything that streams stops with Enter.

| For | At the prompt | Notes |
|-----|---------------|-------|
| Sniff I2C traffic | `m i2c`, then `sniff` | |
| Map an I2C device's registers | `m i2c`, then `dump`, `regs` or `identify` | |
| Program SPI flash | `m spi`, then `flash` | its own interactive flash tool |
| SPI EEPROMs and SD cards | `m spi`, then `eeprom` or `sdcard` | |
| Sniff SPI | `m spi`, then `sniff` | one line at a time: MOSI or MISO |
| Find a UART's baud rate | `m uart`, then `autobaud` | |
| AT-command modems | `m uart`, then `at` | |
| Bridge USB to the UART | `m uart`, then `bridge` | ends with **a button on the ESP32**, not Enter |
| 1-Wire, 2-wire, 3-wire | `m 1wire`, `m 2wire`, `m 3wire` | |
| Digital I/O, PWM | `m dio` | |
| A logic analyser | `logic` | |
| Other buses and radios | `m` for the menu: `infrared`, `can`, `jtag`, `i2s`, `wifi`, `bluetooth`… | some need extra hardware on the DevKit |
| Keep pin and speed changes | `profile` | |

These are the firmware's commands, not the dashboard's. The
[ESP32 Bit Pirate wiki](https://github.com/geo-tp/ESP32-Bit-Pirate/wiki)
explains each one.

### Scripting a Bit Pirate

The driver has the same shape as the Bus Pirate's, so most scripts only
change the class:

```python
from buspirate.bitpirate import BitPirate

with BitPirate("/dev/cu.usbmodem1101") as bp:
    i2c = bp.i2c()
    print([hex(a) for a in i2c.scan()])
    print(i2c.read_register(0x68, 0x00, 8).hex(" "))
```

- **Not sure which board is plugged in?**
  `buspirate.connect.open_device(port, usb_id=...)` picks the right driver.
- **Sending your own commands:** `bp.cli.command("...")` sends any command
  line and returns its output lines.
- **Where the code is:** the driver is in `buspirate/bitpirate/`, and the
  simulator is `buspirate/simulator_bitpirate.py`.
