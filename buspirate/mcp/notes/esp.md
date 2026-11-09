# ESP: flashing an ESP8266 / ESP32 through a Bus Pirate with esptool

First question: **does the target have its own USB port?** Most dev boards
with built-in USB-serial let esptool reset them into the bootloader by
itself. Then no Bus Pirate is needed. The Bus Pirate route is for bare
modules and custom boards.

## Why it is different through a Bus Pirate

- **No auto-reset.** esptool normally toggles DTR/RTS to drive the boot pin
  and EN; **no Bus Pirate passes DTR/RTS through**. Drive the boot pin and EN
  from spare Bus Pirate pins, or have the owner press the buttons.
- Run esptool with **`--before no-reset --after no-reset`**.
- **Fixed 115200 baud** (`--baud 115200`): the bridge cannot follow
  esptool's baud switch.
- **3.3 V logic only.** The ESP needs up to 70 mA continuous and 200–300 mA
  peaks. A v3/v4 supply (about 150 mA) cannot run an ESP32 with Wi-Fi, and
  the BP6's rated 300 mA is no margin. **Power it from its own USB or
  supply, share GND.**
- esptool needs the serial port to itself: configure the bridge, release the
  port, run esptool, reclaim the port. The v3/v4 bridge exits only by replug.

## Wiring

| ESP | Bus Pirate |
|---|---|
| U0RXD (RX) | Bus Pirate TX (v3/v4 MOSI grey; BP6 IO4 purple) |
| U0TXD (TX) | Bus Pirate RX (v3/v4 MISO black; BP6 IO5 brown) |
| GND | GND, first |
| boot pin (below) | a spare pin driven low, or the BOOT/FLASH button |
| EN (CHIP_PU) | a spare pin pulsed low, or the RESET/EN button |

## Strapping pins per chip

The boot pin must be **low on reset** for the ROM serial bootloader; high
(its internal pull-up, if left unconnected) runs the program in flash.

| Chip | Boot pin (low = download) | Other pins for download mode |
|---|---|---|
| ESP8266 | GPIO0 | GPIO15 low (pull-down), GPIO2 high or unconnected. Do not tie GPIO2 straight to VCC: the ROM drives UART TX out on it |
| ESP32 | GPIO0 | GPIO2 floating or low. GPIO12 (MTDI) high selects 1.8 V flash and can brown out 3.3 V flash. GPIO15 (MTDO) low only silences the ROM log |
| ESP32-S2 | GPIO0 | GPIO46 floating or low |
| ESP32-S3 | GPIO0 | GPIO46 floating or low |
| ESP32-C3 | **GPIO9** | GPIO8 **high**. GPIO8 = 0 with GPIO9 = 0 is invalid |
| ESP32-C6 | **GPIO9** | GPIO8 **high**. GPIO8 = 0 with GPIO9 = 0 is invalid |
| ESP32-H2 | **GPIO9** | GPIO8 **high**. GPIO8 = 0 with GPIO9 = 0 is invalid |

The internal pull on the boot pin is about 45 kΩ, so a button or driver needs
a strong pull-down, for example a 10 kΩ resistor to GND.

## The boot sequence (manual)

1. Hold the boot pin low.
2. Pulse EN low, then release it high: the chip resets with the pin low.
3. Release the boot pin.
4. Check the ROM log at 115200: the second line reads
   `rst:0x1 (POWERON_RESET),boot:0x.. (DOWNLOAD_BOOT(...))` or
   `DOWNLOAD(USB/UART0)` in download mode. `SPI_FAST_FLASH_BOOT` means it
   booted normally: the boot pin was not low at reset.
5. Run esptool. With `--after no-reset` the chip stays in the bootloader;
   reset it with the boot pin high to run the new program.

## Commands (esptool v5 spelling)

```
esptool --chip esp32c3 --port <port> --baud 115200 --before no-reset --after no-reset flash-id
esptool ... read-flash 0 ALL dump.bin
esptool ... write-flash 0x0 firmware.bin
esptool ... erase-flash
```

Global options such as `--before` go **before** the command name. Older
esptool releases spell the commands and options with underscores
(`write_flash`, `--before no_reset`), as in docs/bitpirate.md.
`ALL` as the size autodetects the flash size; an explicit size such as
`0x200000` (2 MB) also works. A write or erase needs the owner's confirmation, and a dump
first.

## esptool errors and their causes

| Message | Cause | Fix |
|---|---|---|
| `No serial data received.` | nothing came back: RX/TX not connected or swapped, or the chip was not reset into download mode | check the crossover, then redo the boot sequence |
| `Wrong boot mode detected (0xXX)! The chip needs to be in download mode.` | the chip talks (ROM log seen) but booted normally | boot pin low at reset; redo the sequence |
| `Download mode successfully detected, but getting no sync reply: The serial TX path seems to be down.` | host → ESP line broken | Bus Pirate TX to ESP RX |
| `Invalid head of packet (0xXX): Possible serial noise or corruption.` | bad cable, breadboard shorting flash pins, or brown-out | shorter leads, own supply, `--baud 9600` to test |
| `Failed to connect` | not in the bootloader, wrong port, or the port is held by another program | check port and boot pins; close terminals |
| `A serial exception error occurred` | port in use, missing, unplugged, or no permission | free the port; see the errors note |
| `Failed to write to target RAM (result was 0107: Operation timed out)` | unstable serial path | shorter path, no hubs, other adapter |
| flash fails part way through | power stability, or the baud rate | own supply first; esptool also advises a lower baud |
| writes OK but program does not run | wrong flash mode, or brown-out | try `-fm dio`; check power |
| `Invalid header <value at 0x0>` in the boot log | no bootloader at 0x0, or flash connection/power | flash a bootloader at 0x0 |

Sources:
- https://docs.espressif.com/projects/esptool/en/latest/esp32/advanced-topics/boot-mode-selection.html
- https://docs.espressif.com/projects/esptool/en/latest/esp32s2/advanced-topics/boot-mode-selection.html
- https://docs.espressif.com/projects/esptool/en/latest/esp32s3/advanced-topics/boot-mode-selection.html
- https://docs.espressif.com/projects/esptool/en/latest/esp32c3/advanced-topics/boot-mode-selection.html
- https://docs.espressif.com/projects/esptool/en/latest/esp32c6/advanced-topics/boot-mode-selection.html
- https://docs.espressif.com/projects/esptool/en/latest/esp32h2/advanced-topics/boot-mode-selection.html
- https://docs.espressif.com/projects/esptool/en/latest/esp8266/advanced-topics/boot-mode-selection.html
- https://docs.espressif.com/projects/esptool/en/latest/esp32/esptool/advanced-options.html (`--before`, `--after`)
- https://docs.espressif.com/projects/esptool/en/latest/esp32/troubleshooting.html
- https://docs.espressif.com/projects/esptool/en/latest/esp32/esptool/basic-commands.html
- docs/superpowers/specs/2026-11-09-buspirate-mcp-design.md (no auto-reset, fixed 115200, power)
- docs/bitpirate.md (`--before no_reset`, `write_flash`)
- docs/official/tutorial-basics/power-supply.md (BP6 300 mA)
