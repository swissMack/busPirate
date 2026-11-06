# Bluetooth Mode

This mode enables various Bluetooth operations such as device scanning, pairing, spoofing, sending HID data (keyboard, mouse), and passive sniffing.


## 🧩 Commands
Arguments in `< >` are required, while arguments in `[ ]` are optional.


| Command                  | Description                                                                 |
|--------------------------|-----------------------------------------------------------------------------|
| `scan`                  | Scans for nearby Bluetooth devices for 10 seconds and lists them            |
| `pair <mac>`            | Attempts to pair with and discover services from a remote device            |
| `spoof <mac>`           | Overrides the ESP32's Bluetooth MAC address (must run before any BT action) |
| `sniff`                 | Starts a passive sniffer that logs nearby Bluetooth traffic                 |
| `status`                | Displays the current Bluetooth mode, MAC address, and connection status     |
| `server [name]`         | Starts a BLE HID server named `name` (default: *Bus-Pirate-Bluetooth*)      |
| `keyboard`              | Bridge mode, forwarding all terminal keystrokes as an BLE HID keyboard. Press a esp32 button to stop (requires `server` to be started)|
| `keyboard <text>`       | Sends a text string over BLE HID keyboard (requires `server` to be started) |
| `mouse`         | Opens dedicated mouse shell to launch actions                                            |
| `mouse <x> <y>`         | Sends a relative mouse movement (requires `server` to be started)                                             |
| `mouse move <x> <y>`    | Alternative form to move the BLE mouse cursor (requires `server` to be started)                            |
| `mouse jiggle [ms]`   | Randomly move the mouse each interval [ms] until ENTER is pressed (default 1sec interval, requires `server` to be started)                                       |
| `mouse click`           | Sends a single mouse left-click over BLE HID (requires `server` to be started)                          |
| `reset`                 | Stops any active Bluetooth session and resets the Bluetooth subsystem       |

## 🧪 Recipes

- [Scan nearby Bluetooth devices](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/scan-bluetooth-devices/)
- [Test BLE HID keyboard and mouse mode](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/use-ble-hid-server/)
- [Start a BLE HID keyboard server](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/start-ble-hid-keyboard-server/)
- [Use BLE mouse movement](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/use-ble-mouse-movement/)

## 📝 Notes

- `scan` is passive and does not connect to found devices.
- `pair` enables client mode and attempts to connect to the provided MAC address.
- `spoof` must be used **before** any connection is established; reboot or use `reset` before.
- `sniff` works even if no connection is active, and logs nearby advertisements and traffic.
- `server` initializes BLE HID mode so the device can act as a keyboard or mouse.
- `keyboard`, `mouse`, and `mouse click` only work in server mode (BLE HID).
- `keyboard` starts a bridge mode where all the keys received in the terminal are sent to BLE HID, press any esp32 button to return.
- `keyboard <text>` sends the text provided once.
- `reset` is useful to clear the Bluetooth state (e.g., before re-pairing or spoofing).
- Keyboard and mouse actions follow standard HID protocol behavior.
- **Bluetooth HID commands will not work unless `server` has been started** and a device is connected.



## 📌 Example Usage

```bash
mode bluetooth
scan
pair 7C:9E:BD:DE:AD:BE
spoof 12:34:56:78:9A:BC
sniff
server My-BLE-Device
server
keyboard
keyboard Hello world
mouse -100 -50
mouse move 100 100
mouse click
reset
```

## ▶️ Demo
![bt](bitpirate-wiki/images/dc7d63fcda89bba2.png)
