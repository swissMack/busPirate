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
   choosing the **s3-devkit** build.
2. Plug in the DevKit's port marked **USB**, not the one marked **UART**. The
   firmware talks over the ESP32-S3's own USB, and the UART port only carries
   boot messages.
3. Connect as usual. The port shows as *Espressif ESP32 USB (ESP32 Bit
   Pirate)*.

A freshly plugged-in board spends about three seconds choosing its terminal
before it listens. If connecting fails straight after plugging in, wait a
moment and connect again.

To try it without hardware, pick **simulated-bitpirate** from the port list,
or run `buspirate dashboard --demo --variant bitpirate`.

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
