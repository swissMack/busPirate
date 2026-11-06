# UART Mode

UART mode allows communication over a standard serial interface using TX/RX pins.  
This mode is useful for probing unknown serial devices, sending and receiving data, or bridging traffic.



## 🧩 Commands
Arguments in `< >` are required, while arguments in `[ ]` are optional.

| Command                | Description                                                                 |
|------------------------|-----------------------------------------------------------------------------|
| `scan`                | Monitor a group of pins to detect UART activity      |
| `sniff [raw]` | Passively watch UART activity |
| `autobaud`                | Automatically detect the baud rate on the RX line by analyzing signal timing      |
| `ping`                | Sends probes and collects replies to test if a UART device is responsive    |
| `read`                | Continuously reads ASCII from UART until [ENTER] is pressed                       |
| `raw`                | Continuously reads HEX from UART until [ENTER] is pressed                       |
| `write [text]`        | Sends the specified text to the connected device over UART                  |
| `bridge`              | Starts a real-time full-duplex UART bridge (ESP32 to device)
| `spam [text] [ms]`              |Continuously write text every given ms until ENTER is pressed               |
| `at`              | AT commands with guided input and automatic insertion into the template   |
| `emulator`              | Emulate a UART peripheral device to test communication with external hardware  |
| `trigger [pattern]`              | Automatically send a predefined response when a specific byte pattern is detected   |
| `xmodem <recv/send> <path>` | Transfer file using XMODEM protocol (send or receive from SD)               |
| `swap`                    | Swap the RX/TX pins                       |
| `config`              | Interactive configuration: RX/TX pins, baud rate, data bits, parity, etc.   |
| `['Hello' r:64] ...`  | Sends custom instruction sequences using bytecode-like syntax               |

## 🧪 Recipes

- [Sniff UART between two boards](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/sniff-uart-between-two-boards/)
- [Auto-detect an unknown UART baud rate](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/detect-uart-baudrate-autobaud/)
- [Bridge a UART console](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/bridge-uart-console/)
- [Transfer files over UART with XMODEM](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/transfer-uart-xmodem-sd/)
- [Use the UART AT command helper](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/use-uart-at-shell-modem/)
- [Emulate a UART peripheral for firmware tests](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/emulate-uart-gps-device/)
- [Auto-reply when UART text appears](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/auto-reply-uart-trigger-pattern/)
- [Send repeated UART text with spam](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/send-uart-spam-pattern/)
- [Read UART as raw hex bytes](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/read-uart-raw-hex-stream/)
- [Probe a UART device with ping](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/probe-uart-device-with-ping/)

## 📝 Notes

- `scan` analyzes a group of pin to detect uart activity.
- `autobaud` detects the baudrate on RX by counting edge timings
- `ping` sends predefined probes and analyzes responses to detect UART activity.
- `spam` can send special chars like \n.
- `bridge` connects the terminal input/output to the device in real-time. Press any ESP32 button to stop.
- `at` works with various devices. Each device has its own command set: not all commands are universal.
- `xmodem` send and receive operations require an SD card, as files are read from or written to the SD.
- `xmodem`  at 115200 baud (≈11.5 kB/s), transferring a 1 MB file over XMODEM takes approximately 90 seconds.
- `config` supports full UART parameter customization:
  - RX/TX pins
  - Baudrate
  - Data bits (5–8)
  - Parity (None, Even, Odd)
  - Stop bits (1 or 2)
  - Inversion (for certain logic-level devices)
- The custom instruction syntax (`['Hello' r:64]`) lets you build sequences of writes, delays, and reads manually.


## 📌 Example Usage

```bash
mode uart
config                 # Configure pins and settings
scan                   # Try to find the right baud rate
ping                   # Send probes for a response
write AT               # Send AT text
write                  # Enter write prompt mode
write Hello\n          # Send Hello with a line return
read                   # View device output
bridge                 # Real-time serial passthrough
spam Hello 1000        # Write Hello every second
spam \n 5              # Send ENTER every 5ms
swap                   # RX and TX swap
xmodem send /file.txt  # Send a file via XMODEM from SD
xmodem recv /file.txt  # Receive a file via XMODEM to SD
['AT' r:64]            # Send 'AT' and read 64 bytes
```
## ▶️ Demo

![demo2](bitpirate-wiki/images/d31efb51f6e3cc7a.png)

## 🔧 Hardware

![dupont-male-front](bitpirate-wiki/images/c3e6af94484011c9.png)
