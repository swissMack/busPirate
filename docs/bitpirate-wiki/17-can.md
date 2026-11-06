# CAN Mode

These commands are available to manage operations on the CAN bus.  
They allow you to configure and interact with the CAN bus via the MCP2515 module.


## 🧩 Commands
Arguments in `< >` are required, while arguments in `[ ]` are optional.

| Command              | Description                                       |
|----------------------|---------------------------------------------------|
| `sniff`              | Captures and display all CAN frames               |
| `send [id]`          | Send a CAN frame with the specified ID            |
| `receive [id]`       | Wait for CAN frames with the specified ID         |
| `status`             | Show MCP2515 controller status and error flags    |
| `config`             | Configure CAN speed (kbps), pins, and settings    |

## 🧪 Recipes

- [Wire an MCP2515 CAN module](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/wire-mcp2515-can-module/)
- [Sniff CAN frames with MCP2515](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/sniff-can-frames-mcp2515/)
- [Send a CAN frame with MCP2515](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/send-can-frame-mcp2515/)
- [Receive a specific CAN frame ID](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/receive-specific-can-frame-id/)
- [Check MCP2515 CAN status](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/check-mcp2515-can-status/)

## 📝 Notes

 - The `config` command allows setting:
 - CAN speed in kbps (e.g. 125, 250, 500, 1000)
 - The CAN speed will be automatically adjusted to the closest supported bitrate.
 - CS, SO, SI, SCK pins (for CAN module MCP2515)
 - The default CS pin is locked for the device and can't be changed.
 - `send` accepts up to 8 bytes as hexadecimal input, separated by spaces (AA BB 01...)
 - `receive` filters by a specific frame ID.
 - MCP2515 Pinout
 - ![MCP2515-Parts](bitpirate-wiki/images/31c1059038438c49.jpg)




## 📌 Example Usage

```bash
mode can        # Switch to CAN mode
config          # Configure bitrate and pins
sniff           # Captures all CAN frames
send 0x123      # Prompt frame data to send with frame ID 0x123
send            # Prompt frame ID and frame DATA to send
receive         # Prompt for frame ID and capture frames with specified ID
receive 0x123   # Wait for framess ith ID 0x123
status          # Check controller status and errors
```

## 🔧 Hardware
- [MCP2515 CAN module](https://geo-tp.github.io/ESP32-Bit-Pirate/modules/mcp2515/) — CAN sniff/send target.

![71t8urCvZWL _UF1000,1000_QL80_](bitpirate-wiki/images/01e3048b0d7f0ee1.jpg)
