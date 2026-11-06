# HDUART Mode (Half-Duplex UART)

This mode enables **half-duplex UART** communication, where TX and RX share a single data line.  



## 🧩 Commands

| Command               | Description                                                             |
|------------------------|-------------------------------------------------------------------------|
| `bridge`              | Starts a half-duplex bridge session; input/output share a single pin    |
| `config`              | Configure pin, baud rate, data bits, parity, stop bits, and inversion   |
| `[0x01 D:10 r:255]`    | Execute custom instruction sequences using HDUART bytecode syntax       |


## 🧪 Recipes

- [Bridge a half-duplex UART console](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/bridge-half-duplex-uart/)
- [Bridge a half-duplex UART bus](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/open-hduart-bridge-session/)
- [Send a timed HDUART query](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/send-hduart-bytecode-query/)

## 📝 Notes

- The `bridge` command provides real-time communication. Press any ESP32 button to stop.
- `config` allows you to select the shared TX/RX pin and adjust UART parameters:
  - Baud rate
  - Data bits (5–8)
  - Parity (None, Even, Odd)
  - Stop bits (1 or 2)
  - Inverted logic if needed
- HDUART instructions (`[0x... D:N r:N]`) give full control over transmitted bytes, delays, and response length.
- Since TX and RX share the same line, timing and collisions must be managed carefully.


## 📌 Example Usage

```bash
mode hduart
config                    # Select pin, baud, data bits, etc.
bridge                    # Start interactive session
[0x01 D:10 r:255]         # Send 0x01, wait 10ms, read 255 bytes
