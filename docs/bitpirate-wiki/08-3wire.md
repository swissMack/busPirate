# 3WIRE Mode

This mode allows interaction with 3-wire EEPROM chips such as the 93C46/56/66/76/86 series. It supports both 8-bit and 16-bit memory organization depending on the ORG pin.



## 🧩 Commands

| Command                     | Description                                                   |
|-----------------------------|---------------------------------------------------------------|
| `eeprom`              | Launch an interactive EEPROM shell with 3WIRE EEPROM operations              |
| `config`                    | Configure 3-wire pin mapping                    |

## 🧪 Recipes

- [Dump a 93Cxx Microwire EEPROM](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/dump-microwire-93c-eeprom/)
- [Write bytes to a 93Cxx EEPROM](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/write-93cxx-eeprom-bytes/)
- [Erase a lab 93Cxx EEPROM](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/erase-lab-93cxx-eeprom/)


## ⚙️ EEPROM Shell

The **`eeprom`** command provides an interactive environment to explore, manage, and erase  3wire eeprom chips.

### Actions

- 🔍 **Probe** – Detects the connected EEPROM, identifying size, organization (x8 / x16), and features.
- 📖 **Read bytes** – Reads a sequence of bytes starting at a given address.
- ✏️ **Write bytes** – Writes one or more bytes to the specified address.
- 🗃️ **Dump EEPROM** – Outputs the entire EEPROM contents in hex format.
- 💣 **Erase EEPROM** – Wipes all memory by setting all bits to `1`.
- 🚪 **Exit Shell** – Leaves the shell and returns to the previous menu.

### Supported Models

| Model  | Capacity (x8) | Capacity (x16) |
|--------|--------------:|---------------:|
| 93C46  | 128 bytes     | 64 bytes       |
| 93C56  | 256 bytes     | 128 bytes      |
| 93C66  | 512 bytes     | 256 bytes      |
| 93C76  | 1024 bytes    | 512 bytes      |
| 93C86  | 2048 bytes    | 1024 bytes     |

### Note
- **ORG** pin selects organization mode:  
  - ORG tied to **GND** → x8 (8-bit) mode  
  - ORG tied to **VCC** → x16 (16-bit) mode  
- EEPROMs with all bits set to `1` may be misdetected during probe.
- **93XX56A** devices are always x8, **93XX56B** devices are always x16.  
- Pinout for 93CX6 series: 
![56](bitpirate-wiki/images/47ab1da6e26cc355.png)

---

## 📌 Example Usage

```bash
eeprom  # Open an interactive shell for EEPROM operations
config
```
## 🔧 Hardware
![image](bitpirate-wiki/images/0751186b66a96d17.png)

![AD56042 uJPM](bitpirate-wiki/images/f01830560c0a90de.jpg)
