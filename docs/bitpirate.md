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
| Sniffers, 1-Wire, raw wire, Pins & power | yes | not in the dashboard; sniffers and 1-Wire are in its terminal |

Hidden actions are not errors to work around. They are things this board
cannot do through the dashboard. Most can still be done by hand in the
**Terminal** panel; type `help` there.

## Its terminal: far more than the dashboard drives

The dashboard covers the jobs the Bus Pirates share: I2C, SPI and UART. The
Bit Pirate's own command line goes much further: 25 modes, including radios
and USB tricks no Bus Pirate has. Open the **Terminal** panel and type
`mode` (or `m`) to pick one, `help` for that mode's commands, and
`man` for the firmware's own manual.

While a Bit Pirate is connected, the guide's side menu lists the
**ESP32 Bit Pirate wiki**, imported into this app, with a page per mode. The
table below links to each one.

### Wired buses

| Mode | What it is for | Some of its commands |
|---|---|---|
| [I2C](bitpirate-wiki/05-i2c.md) | I2C bus: much more than the dashboard's panel | `discovery`, `identify`, `sniff`, `dump`, `regs`, `monitor`, `eeprom`, `slave`, `recover`, `glitch` |
| [SPI](bitpirate-wiki/06-spi.md) | SPI devices, flash, EEPROMs and SD cards | `flash`, `eeprom`, `sdcard` (with `ls`, `cat`, `cd`), `sniff`, `slave` |
| [UART](bitpirate-wiki/03-uart.md) | Serial ports | `autobaud`, `scan`, `sniff`, `bridge`, `at`, `xmodem`, `emulator`, `trigger` |
| [HDUART](bitpirate-wiki/04-hduart.md) | Half-duplex UART on one wire | `bridge` |
| [1-Wire](bitpirate-wiki/02-1wire.md) | DS18B20 sensors, iButtons, 1-Wire EEPROMs | `scan`, `temp`, `ibutton`, `eeprom`, `sniff` |
| [2-Wire](bitpirate-wiki/07-2wire.md) | Smartcards and memory cards | `smartcard`, `sniff` |
| [3-Wire](bitpirate-wiki/08-3wire.md) | 93Cxx Microwire EEPROMs | `eeprom` |
| [DIO](bitpirate-wiki/09-dio.md) | Any GPIO by hand | `read`, `set`, `pulse`, `pwm`, `servo`, `measure`, `sniff` |
| [JTAG](bitpirate-wiki/15-jtag.md) | Finding JTAG/SWD pins, OpenOCD adapter | `scan`, `openocd` |
| [CAN](bitpirate-wiki/17-can.md) | CAN bus (with a transceiver module) | `sniff`, `send`, `receive` |
| [I2S](bitpirate-wiki/16-i2s.md) | Digital audio in and out | `play`, `record`, `test` |
| [LED](bitpirate-wiki/10-led.md) | Addressable RGB LED strips | `fill`, `set`, `rainbow`, `chase`, `blink` |
| [Ethernet](bitpirate-wiki/18-ethernet.md) | A W5500 Ethernet module | `ping`, `nmap`, `ssh`, `telnet`, `http`, `modbus` |

### Radio and USB

| Mode | What it is for | Some of its commands |
|---|---|---|
| [Wi-Fi](bitpirate-wiki/14-wifi.md) | The ESP32's own Wi-Fi | `scan`, `connect`, `sniff`, `ap`, `repeater`, `waterfall` |
| [Bluetooth](bitpirate-wiki/13-bluetooth.md) | BLE scanning and HID | `scan`, `sniff`, `keyboard`, `mouse` |
| [USB](bitpirate-wiki/12-usb.md) | Act as a keyboard, mouse, gamepad or USB stick | `keyboard`, `mouse`, `storage`, `host`, `adapters` |
| [Infrared](bitpirate-wiki/11-infrared.md) | IR remote controls (with an IR module) | `receive`, `send`, `record`, `replay` |
| [Sub-GHz](bitpirate-wiki/19-subghz.md) | 315/433/868/915 MHz radio (CC1101 module) | `scan`, `sweep`, `receive`, `record`, `replay` |
| [RFID](bitpirate-wiki/20-rfid.md) | 13.56 MHz NFC tags (PN532 module) | `read`, `write`, `clone` |
| [RF24](bitpirate-wiki/21-rf24.md) | 2.4 GHz nRF24L01 modules | `scan`, `receive`, `sweep`, `waterfall` |
| [FM](bitpirate-wiki/22-fm.md) | Si4713 FM transmitter | `broadcast`, `sweep` |
| [Cell](bitpirate-wiki/23-cell.md) | A GSM/LTE modem | `sim`, `sms`, `call`, `network` |
| [LoRa](bitpirate-wiki/24-lora.md) | SX1262 LoRa transceivers | see the page |

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

The dashboard moves only I2C, SPI and UART onto the dock's header (see
[Pins](#pins-the-bit-pirate-dock)). Every other mode starts on the
firmware's own default pins, and many are not on the header. In that mode,
type `config` and give it header pins: IO15 to IO18 and IO10 to IO13
(GPIO numbers). For example, 1-Wire's default GPIO6 is off the header, so
give it 15, which is the Bus Pirate 6's 1-Wire pin. Radio modes for modules
on the DevKit's own headers, and Wi-Fi, Bluetooth and USB, need no header
pins at all.

The dock's slide switch still sets the voltage on the header. A module wired
to the DevKit directly gets 3.3V logic with no protection.

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
