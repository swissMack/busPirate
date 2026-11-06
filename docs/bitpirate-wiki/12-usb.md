# USB Mode

This mode allows you to emulate USB HID devices, expose a USB mass storage interface, or turns the device into a dedicated USB tool.


## 🧩 Commands
Arguments in `< >` are required, while arguments in `[ ]` are optional.


| Command                      | Description                                                                  |
|------------------------------|------------------------------------------------------------------------------|
| `keyboard`              | Bridge mode, forwarding all terminal keystrokes as an USB HID keyboard. Press an esp32 button to stop |
| `keyboard <text>`           | Sends the provided text via USB Keyboard HID                                 |
| `mouse`            | Enter mouse shell operations                           |
| `mouse <x> <y>`         | Sends a relative mouse movement (-127 to 127)                                           |
| `mouse jiggle [ms]`   | Randomly move the mouse each interval [ms] until ENTER is pressed (default 1sec interval)                                          |
| `mouse click`           | Sends a single mouse left-click                         |
| `gamepad [key]`             | Emulates a gamepad button press (e.g., `A`, `B`, `LEFT`, etc.)               |
| `sysctrl [action]`             | Emulates hardware controll button press               |
| `storage`                     | Starts USB Mass Storage mode (via SD card)                                   |
| `host`                     | Enable USB host mode to connect USB devices to the ESP32 and dump descriptors                                 |
| `adapters`                     | Turns the device into a dedicated USB tool (see [USB Adapters](bitpirate-wiki/99-adapters.md))                                                     |
| `reset`                     | Resets the USB interface                                                     |
| `config`                    | Sets the SPI pins used for the USB storage interface                         |

## 🧪 Recipes

- [Use USB HID keyboard and mouse mode](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/use-usb-hid-keyboard-mouse/)
- [Expose an SD card as USB storage](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/usb-mass-storage-sd-card/)
- [Read USB host descriptors](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/read-usb-host-descriptors/)
- [Press a USB HID gamepad button](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/press-usb-hid-gamepad-button/)
- [Send a USB system control action](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/send-usb-system-control-action/)
- [Choose a dedicated USB adapter mode](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/choose-dedicated-usb-adapter-mode/)
- [Use ESP32 as a USB-UART dongle](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/use-usb-uart-adapter/)
- [Use the logic analyzer with PulseView](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/use-logic-analyzer-pulseview/)
- [Use OpenOCD adapter mode](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/use-openocd-jtag-adapter/)
- [Use the SubGHz Raw CDC adapter](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/use-subghz-raw-cdc-adapter/)
- [Use the SDR raw 2.4Ghz adapter](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/use-esp-sdr-usb-adapter/)

## 📝 Notes

- HID interfaces (keyboard, mouse, gamepad) send their data via native USB.
- `keyboard` starts a bridge mode where all the keys received in the terminal are sent to USB HID, press any esp32 button to return.
- `keyboard <text>` sends the text provided once.
- `mouse` move values are capped to -127 to 127.
- The `storage` command exposes the SD card over USB as a storage drive (may take up to 30 seconds).
- `host` requires 5V power on the USB port, for the S3devkit, you must bridge "USB-OTG" pad to use this feature.
- The `config` command lets you define the SPI pins used for the SD card:
  - CS (Chip Select)
  - CLK (Clock)
  - MISO (Master In Slave Out)
  - MOSI (Master Out Slave In)


## 🔌 Adapters

The `adapters` command let you choose an USB adapter and reboot the device into dedicated USB modes such as UART bridge, flashrom, AVRDUDE, SUMP logic analyzer, OpenOCD, IR Toy, or SubGHz CC1101 control. [See the full adapter documentation](bitpirate-wiki/99-adapters.md).

## 📌 Example Usage

```bash
mode usb
keyboard
keyboard Hello World
mouse
mouse 100 -120
mouse 10 127
mouse click
mouse jiggle
adapters
gamepad A
gamepad left
storage
reset
```

## ▶️ Demo
![demo15](bitpirate-wiki/images/787fd24e4437a7ca.png)
