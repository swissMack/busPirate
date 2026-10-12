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

With the [mode-LED firmware](#installing-the-mode-led-firmware) (version `1.7-led`), the
DevKit's RGB LED shows which mode the board is in:

| LED | Mode | What it means |
|-----|------|---------------|
| off | HiZ | Every pin released; safe to rewire |
| blue | I2C | SDA 6 / SCL 7 are driven |
| green | SPI | CS 10 / CLK 12 / MISO 11 / MOSI 13 are driven |
| yellow | UART or HDUART | RX 17 / TX 18 are in use |
| cyan | 1-Wire | The 1-Wire pin is in use |
| dim white | any other mode | Pins in use; see the mode's own help |

The Bit Pirate has no switchable power supply, so there is no V-reg colour:
its 3V3 pin is live whenever the board has USB power. Stock firmware leaves
the LED dark after a short Wi-Fi flash at boot (white while trying, then green
when connected, blue when no network is saved, red when it fails).

### Installing the mode-LED firmware

The LED colours come from a small patch to geo-tp's v1.7 firmware, kept in
this repo as `firmware/bitpirate-1.7-mode-led.patch`. It changes nothing the
dashboard relies on; the board reports its version as `1.7-led`. It also
adds pin 48 (the LED) to the protected pins, and puts the colour key in the
board's own `help`.

The patch also pins FastLED to 3.10.3: geo-tp's config asks for `^3.3.3`,
and every FastLED released since no longer builds with this source.

Build it with [PlatformIO](https://platformio.org), then merge the parts
into one image:

```sh
git clone --branch v1.7 https://github.com/geo-tp/ESP32-Bit-Pirate.git
cd ESP32-Bit-Pirate
git apply /path/to/busPirate/firmware/bitpirate-1.7-mode-led.patch
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
[geo-tp's releases](https://github.com/geo-tp/ESP32-Bit-Pirate/releases/tag/v1.7)
at `0x0` the same way.

## How it differs from a Bus Pirate

| | Bus Pirate v3 / v4 | ESP32 Bit Pirate |
|---|---|---|
| How the dashboard talks to it | binary bitbang protocol | its text command line |
| Target power | switchable 3.3V and 5V supplies | none; wire the DevKit's 3V3 pin if needed |
| Voltage | 3.3V and 5V targets | **3.3V only**, and its pins are not 5V tolerant |
| Pull-ups | on-board, fed from VPU | the ESP32's internal ones (about 45 kΩ) |
| Pins | fixed probe cable | any GPIO; the defaults are shown below |
| I2C writes | an ACK reported for every byte | the address is checked with `ping`; later bytes are not reported |
| SPI clock | 30 kHz to 8 MHz | whole MHz: 1, 2, 4 or 8 from the list |
| SPI modes | 0 to 3 | mode 0 only |
| SPI flash | read, dump, write, erase, verify | read, dump and verify |
| UART | send, listen, monitor, bridge | send and monitor |
| Sniffers, 1-Wire, raw wire, Pins & power | yes | not offered |

Hidden actions are not errors to work around. They are things this board
cannot do through the dashboard. Most can still be done by hand in the
**Terminal** panel; type `help` there.

## Default pins (s3-devkit build)

All of these are on header J1, the left-hand one with the USB ports at the
bottom:

| Bus | Signal | GPIO |
|---|---|---|
| I2C | SDA / SCL | 6 / 7 |
| SPI | CS / CLK / MISO / MOSI | 10 / 12 / 11 / 13 |
| UART | RX / TX | 17 / 18 |

Pins can be moved: type `config` in the Terminal panel while in that mode,
and `profile` to keep the change. The dashboard's diagrams always show the
defaults.

## What happens underneath

The dashboard types commands and reads the replies, the way you would at the
board's prompt:

- **Entering a mode:** `m i2c`. The first time after boot, the firmware asks
  its pin and speed questions, which are answered with the current settings.
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
