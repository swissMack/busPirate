# ESP32 Bit Pirate

The [ESP32 Bit Pirate](https://github.com/geo-tp/ESP32-Bit-Pirate) is
firmware that turns an ESP32-S3 board into a Bus Pirate-style tool. The
dashboard drives one on an **ESP32-S3-DevKitC-1** alongside the Bus Pirate v3
and v4: I2C, SPI and UART from the same panels, plus the board's own command
line in the Terminal panel.

It is a different kind of device, and the dashboard shows only what it can
really do.

## Connecting

1. Flash it with the [web flasher](https://geo-tp.github.io/ESP32-Bit-Pirate/webflasher/),
   choosing the **s3-devkit** build (**s3-devkit-n16-r8** for a board with
   16 MB flash and 8 MB PSRAM).
2. Plug in the DevKit's port marked **USB** (on some boards **USB OTG**), not
   the one marked **UART** (or **USB TTL**). The firmware talks over the
   ESP32-S3's own USB, and the UART port only carries boot messages. Flashing
   works on either port.
3. Connect as usual. The port shows as *Espressif ESP32 USB (ESP32 Bit
   Pirate)*.

A freshly plugged-in board spends about three seconds choosing its terminal
before it listens. If connecting fails straight after plugging in, wait a
moment and connect again.

To try it without hardware, pick **simulated-bitpirate** from the port list,
or run `buspirate dashboard --demo --variant bitpirate`.

## The board LED (mode colours)

With the [mode-LED firmware](#installing-the-mode-led-firmware), the DevKit's
RGB LED shows which mode the board is in:

| LED | Mode | What it means |
|-----|------|---------------|
| off | HiZ | Every pin released; safe to rewire |
| blue | I2C | The I2C pins are driven (IO15 / IO16 on the dock) |
| green | SPI | The SPI pins are driven (IO10–IO13 on the dock) |
| yellow | UART or HDUART | The UART pins are in use (IO10 / IO11 on the dock) |
| cyan | 1-Wire | The 1-Wire pin is in use |
| dim white | any other mode | Pins in use; see the mode's own help |

The Bit Pirate has no switchable power supply, so there is no V-reg colour:
its 3V3 pin is live whenever the board has USB power. Stock firmware leaves
the LED dark after a short Wi-Fi flash at boot (white while trying, then green
when connected, blue when no network is saved, red when it fails).

### Installing the mode-LED firmware

The LED colours come from a small patch to geo-tp's v1.8 firmware, kept in
this repo as `firmware/bitpirate-1.8-mode-led.patch` and offered upstream as
[PR #191](https://github.com/geo-tp/ESP32-Bit-Pirate/pull/191). It makes the
LED the DevKit's display (`RgbLedView`): each mode change lights it, and the
**Screen brightness** setting in the board's `system` menu sets how bright it
is (default 9 %). It changes nothing the dashboard relies on; the board still
reports version `1.8`. It also adds pin 48 (the LED) to the protected pins,
and puts the colour key in the board's own `help`.

Build it with [PlatformIO](https://platformio.org), then merge the parts
into one image:

```sh
git clone --branch v1.8 https://github.com/geo-tp/ESP32-Bit-Pirate.git
cd ESP32-Bit-Pirate
git apply /path/to/busPirate/firmware/bitpirate-1.8-mode-led.patch
pio run -e s3-devkit-n16-r8          # or s3-devkit for an 8 MB board
B=.pio/build/s3-devkit-n16-r8
python3 -m esptool --chip esp32s3 merge_bin -o $B/firmware.factory.bin \
  --flash_mode dio --flash_freq 80m --flash_size 16MB \
  0x0 $B/bootloader.bin 0x8000 $B/partitions.bin \
  0xe000 ~/.platformio/packages/framework-arduinoespressif32/tools/partitions/boot_app0.bin \
  0x10000 $B/firmware.bin
```

Flash it without moving the cable: in the board's terminal, type `system`,
pick **Bootloader** and answer `y`. The board restarts into Espressif's
flashing mode, and a new `/dev/cu.usbmodem…` port appears:

```sh
python3 -m esptool --chip esp32s3 --port /dev/cu.usbmodemXXXX \
  --before no_reset --after hard_reset write_flash 0x0 $B/firmware.factory.bin
```

On the USB TTL (CH340) port, use the default reset and `--baud 460800`:
921600 fails there.

**Dock pins as the firmware's own default.** Stock v1.8 starts I2C on
GPIO 6 / 7, which the Bit Pirate Dock does not bring out. This app answers
SDA 15 / SCL 16 each time it enters I2C, but the firmware keeps that only
until a reset, so the Web CLI (which starts after one) was back on 6 / 7.
`firmware/bitpirate-1.8-dock-pins.patch` moves the DevKit builds' default to
**IO15 = SDA, IO16 = SCL**, so both terminals agree from power-up. Apply it
after the mode-LED patch, before `pio run`:

```sh
git apply /path/to/busPirate/firmware/bitpirate-1.8-dock-pins.patch
```

To keep the Wi-Fi network the board has saved, flash only the app
(`$B/firmware.bin` at `0x10000`) rather than the merged image: the merged
image also blanks the settings area at `0x9000`.

To go back to stock, flash the release `.bin` from
[geo-tp's releases](https://github.com/geo-tp/ESP32-Bit-Pirate/releases/tag/v1.8)
at `0x0` the same way.

## How it differs from a Bus Pirate

| | Bus Pirate v3 / v4 | ESP32 Bit Pirate |
|---|---|---|
| How the dashboard talks to it | binary bitbang protocol | its text command line |
| Target power | switchable 3.3V and 5V supplies | the dock's VIO pin: 5V, 3V3 or 1V8 from its slide switch |
| Voltage | 3.3V and 5V targets | 5V, 3V3 or 1V8 through the dock's level shifters (a bare DevKit is **3.3V only** and not 5V tolerant) |
| Pull-ups | on-board, fed from VPU | the ESP32's internal ones (about 45 kΩ) |
| Pins | fixed probe cable | the dock's Bus Pirate 6 header; the firmware can use any GPIO |
| I2C writes | an ACK reported for every byte | the address is checked with `ping`; later bytes are not reported |
| SPI clock | 30 kHz to 8 MHz | whole MHz: 1, 2, 4 or 8 from the list |
| SPI modes | 0 to 3 | mode 0 only |
| SPI flash | read, dump, write, erase, verify | read, dump and verify |
| UART | send, listen, monitor, bridge | send and monitor |
| Sniffers, 1-Wire | yes | its own: see [In the menu](#in-the-menu) |
| Raw wire, Pins & power | yes | not in the dashboard; DIO drives single pins |

Hidden actions are not errors to work around. They are things this board
cannot do through the dashboard. Most can still be done by hand in the
**Terminal** panel; type `help` there.

## In the menu

Beyond I2C, SPI and UART, a connected Bit Pirate adds its own modes to the
left menu, each a panel of one-click actions that shows the board's reply
as it printed it. Every action sends its command with all its arguments
filled in, so the board never stops to ask.

**Buses**

- **1-Wire** (data on IO15): find devices, ping, read the ROM, read a
  DS18B20's temperature, sniff the line.
- **DIO**, any header pin by hand: read, set high, low, input or output,
  pull-up, pull-down, PWM, measure a frequency, pulse, drive a servo, reset.
- **JTAG**: find which header pins a target's SWD or JTAG port is on, and
  its IDCODE. It scans all eight header pins.

**Wireless**

- **Wi-Fi**: scan for networks, status, connect, disconnect, ping a host.
- **Bluetooth**: scan for LE devices, status.

**On the shared panels**

- **I2C** gains Identify, Discovery, Dump, Recover the bus and Sniff.
- **UART** gains Find the baud rate (`autobaud`), which saves the rate it
  finds.

Each panel's guide link opens its page of the
**ESP32 Bit Pirate wiki**, imported into this app.

Everything else stays in the **Terminal** panel: the other modes (most need
an add-on module), the interactive shells (`eeprom`, `smartcard`,
`wizard`), the USB adapter modes, and the commands that jam, flood or spoof
other people's equipment. Type `mode` (or `m`) there to pick a mode and
`help` for its commands.

### Everywhere

- [General commands](bitpirate-wiki/99-general.md): `mode`, `system`,
  `profile` (save settings), `logic` and `analogic` (a terminal logic
  analyser and voltmeter), `listen`, `wizard`.
- [Instruction syntax](bitpirate-wiki/99-instructions.md): the Bus
  Pirate-style `[ 0x.. r:N ]` sequences, also used by this dashboard.
- [LittleFS](bitpirate-wiki/99-littlefs.md), [Python scripts](bitpirate-wiki/99-python.md),
  [USB adapters](bitpirate-wiki/99-adapters.md) and the
  [Pirate Assistant](bitpirate-wiki/99-assistant.md).

### Pins outside the dashboard

The dashboard puts I2C, SPI, UART, 1-Wire and JTAG on the dock's header
(see [Pins](#pins-the-bit-pirate-dock)), and DIO offers header pins only.
A mode started from the Terminal begins on the firmware's own default
pins, and many are not on the header. In that mode, type `config` and give
it header pins: IO15 to IO18 and IO10 to IO13 (GPIO numbers). Wi-Fi,
Bluetooth and USB need no header pins.

The dock's slide switch still sets the voltage on the header. A module wired
to the DevKit directly gets 3.3V logic with no protection.

## The Web CLI (its browser terminal)

The firmware can serve its terminal to a browser over Wi-Fi. It runs that
**instead of** the USB terminal, choosing at power-up, so while you use the
Web CLI this app cannot drive the board.

1. **Save your Wi-Fi once, from this app.** Open **Wi-Fi → Connect** and give
   the network name and password. The firmware keeps them, and the address
   it was given appears at the top of the app as **Web CLI: http://…**.
2. **Reset into Web CLI mode.** Press reset without holding the button, then
   within 3 seconds **short-press** it to join your Wi-Fi, or **hold** it for
   the board's own hotspot.
3. **Watch the LED:** white is connecting, green is ready, blue means no
   Wi-Fi is saved, red means it failed.
4. **Open the address.** It's the one at the top of the app. While the
   board is still on USB it shows as plain text, *Web CLI after a reset*;
   once the board has left USB it becomes a link, marked *last seen*. On the
   hotspot it's always http://192.168.4.1. Give it about 10 seconds after
   the green LED: the board starts its web server before its page, and
   until then it answers "Nothing matches the given URI". Reload.
5. **Back to this app:** reset without pressing the button.

The address is the one your router gave the board last time. If the router
hands out a different one, Wi-Fi → Status (back on USB) shows the new one,
and the top of the app follows. Avoid the Wi-Fi commands (scan, connect,
disconnect) from inside the Web CLI: they drop its own connection.

## Pins: the Bit Pirate Dock

The dashboard expects the DevKit in an
[ESP32 Bit Pirate Dock](https://github.com/AndreiVladescu/ESP32-Bit-Pirate-Hardware).
Its 10-pin header follows the Bus Pirate 6, with IO0–IO7 wired to GPIO15,
16, 17, 18, 10, 11, 12 and 13 (the dock's schematic). Each time the
dashboard enters a mode it sets the firmware's pins to the Bus Pirate 6
layout of that header:

| Bus | Signal | Dock pin (GPIO) | Bus Pirate 6 |
|---|---|---|---|
| I2C | SDA / SCL | IO15 / IO16 | IO0 / IO1 |
| SPI | MISO / CS / CLK / MOSI | IO10 / IO11 / IO12 / IO13 | IO4 / IO5 / IO6 / IO7 |
| UART | TX / RX | IO10 / IO11 | IO4 / IO5 |

The firmware's own s3-devkit defaults (I2C 6 / 7, SPI CS 10 / CLK 12 /
MISO 11 / MOSI 13, UART RX 17 / TX 18) are overridden: GPIO6 and 7 are not on
the dock's header. The dock's slide switch sets 5V, 3V3 or 1V8 for VIO and
its level shifters.

## What happens underneath

The dashboard types commands and reads the replies, the way you would at the
board's prompt:

- **Entering a mode:** `m i2c`. The first time after boot, the firmware asks
  its pin and speed questions. The pins get the dock's layout and the rest
  keep their settings. On a later entry the pins are set with `config`,
  once per connection.
- **Changing speed or baud:** `config`. Only the setting that changed is
  answered; every other question keeps its value.
- **I2C scan:** `scan`.
- **Pull-ups:** `P` and `p`.
- **Transfers:** the firmware's `[ ... ]` instructions. `[0x68 0x00 r:8]`
  writes register 0x00 to the device at 7-bit address 0x68 and reads 8 bytes
  after a repeated start.
- **Watching a UART:** its `read` command, stopped with Enter.

Nothing is ever sent that a Bus Pirate would need, such as the nulls that
enter binary mode or the 0x0F reset. Disconnecting leaves the board in HiZ
(`m hiz`) with every pin released.

## Verified so far

Everything above is written from the firmware's source (v1.7, `pioarduino`
branch) and tested against a simulator built from that source. It has not
yet met a real board; see the checklist in
[troubleshooting](troubleshooting.md).
