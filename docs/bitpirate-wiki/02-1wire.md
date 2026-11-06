# 1WIRE Mode

This mode allows communication with devices using the 1-Wire protocol, such as iButtons, EEPROM or temperature sensors (e.g. DS18B20).



## 🧩 Commands
Arguments in `< >` are required, while arguments in `[ ]` are optional.

| Command                  | Description                                                                          |
|--------------------------|--------------------------------------------------------------------------------------|
| `scan`                  | Detects and lists all devices found on the 1-Wire bus with their ROM IDs             |
| `ping`                  | Sends a reset pulse and checks for presence response from a device                   |
| `sniff`                 | Passively monitors the data line, detecting timing patterns (reset, presence, bits)  |
| `read`                  | Reads both the ROM ID and scratchpad of a connected device                           |
| `write id [8 bytes]`    | Programs a new ROM ID to a supported device, prompt for 8 bytes if not given                      |
| `write sp [8 bytes]`    | Writes 8 bytes to the scratchpad memory (via 0x0F command), , prompt for 8 bytes if not given                           |
| `ibutton`          | Open an interactive shell to copy, read and write iButtons (RW1990) |
| `eeprom`          | Open an interactive shell to dump, read write, analyze and erase EEPROM (DS24/28) |
| `temp`                  | Reads and decodes the temperature from a connected DS18B20 sensor                      |
| `config`                | Lets you change the data pin used for 1-Wire communication                           |
| `[0xAA r:8]` ...        | Allows sending manual 1-Wire instructions with precise control over command flow     |


## 🧪 Recipes

- [Read an iButton ID](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/read-ibutton-id/)
- [Read a DS18B20 temperature sensor](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/read-ds18b20-temperature/)
- [Dump a 1-Wire EEPROM](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/dump-one-wire-eeprom/)
- [Sniff 1-Wire bus timing](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/sniff-one-wire-bus-timing/)
- [Copy an RW1990 iButton](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/copy-rw1990-ibutton-shell/)
- [Write a 1-Wire scratchpad test pattern](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/write-one-wire-scratchpad-pattern/)

## ⚙️ 1-Wire EEPROM Shell
The **`eeprom`** command provides an interactive environment to explore, manage, and erase 1-Wire EEPROM chips.

### Actions

- 🔍 **Probe EEPROM** – Detects the connected 1-Wire EEPROM and identifies its model and size.
- 📊 **Analyze EEPROM** – Scans the contents for data summary.
- 📖 **Read bytes** – Reads a sequence of bytes starting at a given memory address.
- ✏️ **Write bytes** – Writes one or more bytes to a specific address, with automatic page handling.
- 🗃️ **Dump EEPROM** – Outputs the entire EEPROM contents in hex dump format.
- 💣 **Erase EEPROM** – Wipes the chip by writing 0x00 across all pages.
- 🚪 **Exit Shell** – Leaves the 1-Wire EEPROM shell and returns to the previous menu.



### Supported Models

| Model      | Capacity | Page Size | Family Code | CRC16 | Notes                              |
|------------|----------|-----------|-------------|--------|-------------------------------------|
| DS2431     | 128 B    | 8 B       | `0x2D`      | ✅     | 1 Kbit – 4 pages of 8 bytes         |
| DS2433     | 512 B    | 32 B      | `0x23`      | ✅     | 4 Kbit – 16 pages of 32 bytes       |
| DS28EC20   | 2560 B   | 32 B      | `0x43`      | ✅     | 20 Kbit – 80 pages of 32 bytes      |

- Only one device should be present on the 1-Wire bus during operations.  
- Pull-up resistor is required on the **DQ** (IO) line.
- ![Pin-Configuration-of-DALLAS-DS2431](bitpirate-wiki/images/7fad2accbbff5be5.png)


## 📝 Notes

- You can use `scan` to discover devices like DS18B20 or iButtons.
- The `read` command shows the device's ID and scratchpad if supported.
- The `write id` and `write sp` commands expect **8 bytes** in hex format (e.g. `write id 0x01 0x02 0x03 0x04 0x05 0x0 0x07 0x08`).
- Without data provided, the `write id|sp` commands will prompt for 8 bytes.
- The `ibutton` implementation follows the **official Dallas 1-Wire protocol** for ID programming, including the proper timing sequence and command structure.
- Prefers USB Serial over WiFi web to copy ibuttons, the timing is critical and the web server could disturb the copy.
- `sniff` is useful when passively monitoring a 1-Wire bus connected to another master device.   It attempts to **automatically detect known 1-Wire timing patterns**, including **reset pulses**, **presence responses**, and **bit-slots**, to reconstruct readable transactions.
- `ibutton` Operations on Rom ID for classic iButtons. Works with RW1990 tag (rewrittable)
- The instruction syntax (`[0x... r:N]`) allows precise control of low-level communication, including bit-level reads, delays, and raw hex sequences.



## 📌 Example Usage

```bash
mode 1wire
scan
read
sniff
write id 0x1 0x2 0x3 0x4 0x5 0x6 0x7 0x8
write id # Prompt for 8 bytes: AA BB 01...
write sp
write sp 0xDE 0xCD 0xAA 0x4 0x5 0x6 0x7 0x8
temp
ibutton   # open interactive shell
eeprom    # open interactive shell
[0x33 r:8] # Send read cmd and read 8 bytes
```

## ▶️ Demo
![demo5](bitpirate-wiki/images/964a232cfe435cc1.png)


## 🔧 Hardware


![ds9092-ibutton-okuyucu-prob-ds1990-ds19xx-maxim-metal-panel-kcm51885337-1-21a27824a758419b9da326c4de49d9f7](bitpirate-wiki/images/e99c3f7d78876034.jpg)

![DS18B20](bitpirate-wiki/images/b2785934c9ff85ca.jpg)
![ibutton-key-tag-ds1990a-f5](bitpirate-wiki/images/010d1a42ad1432e8.jpg)

![fezfzeezf](bitpirate-wiki/images/1efb9c04d90cd194.jpg)
![erger](bitpirate-wiki/images/4bc695771ee0f3d2.jpg)
