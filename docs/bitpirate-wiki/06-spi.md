# SPI Mode

This mode allows interaction with devices using the Serial Peripheral Interface (SPI) protocol.  
It supports sniffing, sd operations, and accessing SPI flash and eeprom chips.



## 🧩 Commands

| Command               | Description                                |
|------------------------|--------------------------------------------|
| `sniff`               | Monitor SPI bus traffic           |
| `slave`               | Acts as a slave device logging master input              |
| `sdcard`               | Open an interactive shell to monitor SD card operations          |
| `eeprom`         | Open an interactive shell for SPI EEPROM operations (25X series)  |
| `flash`         | Open an interactive shell for SPI NOR Flash operations  |
| `config`              | Configure SPI pins and settings     |
| `[0x9F r:3]`           | Send raw SPI instructions (e.g., JEDEC ID)  |

## 🧪 Recipes

- [Dump a SPI flash chip from your browser](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/dump-spi-flash-browser/)
- [Open the SPI SD card shell](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/open-spi-sd-card-shell/)
- [Analyze a SPI flash from the CLI](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/analyze-spi-flash-cli/)
- [Read a SPI flash JEDEC ID](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/read-spi-flash-jedec-id/)
- [Dump a SPI EEPROM 25X chip](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/dump-spi-eeprom-25x/)
- [Program an AVR with AVRDUDE](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/program-avr-with-avrdude/)
- [Write a SPI flash image with Flashrom](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/write-spi-flash-with-flashrom/)

## 💾 SD Card Shell

The **`sdcard`** command provides an interactive environment to explore, manage, and edit files stored on an SD card.

### Actions

| Command                              | Description |
|--------------------------------------|-------------|
| `cd [dir]`                           | Change the current working directory to `dir`. |
| `ls`                                 | List files and directories in the current directory. |
| `cat <filepath>`                     | Display the content of a file as plain text. |
| `touch <filepath>`                   | Create an empty file at the specified path. |
| `rm <file\|dir>`                     | Delete a file or an entire directory (recursively). |
| `mkdir <dir>`                        | Create a new directory. |
| `echo TEXT > <filepath>`             | Write `TEXT` to a file (overwriting existing content). |
| `echo TEXT >> <filepath>`            | Append `TEXT` to an existing file. |

- Works with most **microSD** and **SD** cards (FAT/FAT32 formatted).
- Tested with cards from **128 MB** up to **32 GB**.
- Large file operations may take several seconds depending on SPI speed.


## ⚙️ SPI EEPROM Shell
The **`eeprom`** command provides an interactive environment to explore, manage, and erase SPI eeprom chips.

### Actions

- 🔍 **Probe EEPROM** – Detects the connected SPI EEPROM, identifying capacities.
- 📊 **Analyze EEPROM** – Scans the contents for known file signatures, secrets, etc.
- 📖 **Read bytes** – Reads a sequence of bytes starting at a given memory address.
- ✏️ **Write bytes** – Writes one or more bytes to a specific address, with automatic page handling.
- 🗃️ **Dump EEPROM** – Outputs the entire EEPROM contents in hex dump format.
- 💣 **Erase EEPROM** – Wipes the chip by writing 0xFF across all pages.
- 🚪 **Exit Shell** – Leaves the SPI EEPROM shell and returns to the previous menu.

### Supported Models

| Model     | Capacity | Page Size  | Addr Bytes | Block Prot. | Max Clock |
|-----------|----------|------------|------------|-------------|-----------|
| 25X010    | 128 B    | 8 B        | 1          | 0b          | 10 MHz    |
| 25X020    | 256 B    | 8 B        | 1          | 0b          | 10 MHz    |
| 25X040    | 512 B    | 8 B        | 1          | 1b          | 10 MHz    |
| 25X080    | 1 KB     | 16 B       | 2          | 0b          | 10 MHz    |
| 25X160    | 2 KB     | 16 B       | 2          | 0b          | 10 MHz    |
| 25X320    | 4 KB     | 32 B       | 2          | 0b          | 10 MHz    |
| 25X640    | 8 KB     | 32 B       | 2          | 0b          | 10 MHz    |
| 25X128    | 16 KB    | 64 B       | 2          | 0b          | 10 MHz    |
| 25X256    | 32 KB    | 64 B       | 2          | 0b          | 10 MHz    |
| 25X512    | 64 KB    | 128 B      | 2          | 0b          | 10 MHz    |
| 25X1024   | 128 KB   | 256 B      | 3          | 0b          | 10 MHz    |
| 25XM01    | 128 KB   | 256 B      | 3          | 0b          | 10 MHz    |
| 25XM02    | 256 KB   | 256 B      | 3          | 0b          | 5 MHz     |
| 25XM04    | 512 KB   | 256 B      | 3          | 0b          | 8 MHz     |

- Compatible with most **25X-series SPI EEPROMs** from Winbond, Microchip, Atmel, and others.  
- Most **25X-Series** SPI EEPROMS should have **HOLD pin connected to VCC** to be detected.
- See https://github.com/geo-tp/ESP32-Bus-Pirate-Scripts to dump the content of EEPROM in a file.
- Standard SPI `eeprom` pinout:
![image](bitpirate-wiki/images/1d5f9770967ecba2.png)


## ⚙️ SPI Flash Shell

The **`flash`** command provides an interactive environment to explore, manage, and erase flash SPI NOR chips.

### Actions

- 🔍 **Probe Flash** – Detects the connected SPI flash chip, retrieving manufacturer ID, device ID, size.
- 📊 **Analyze Flash** – Scans the contents for known file signatures, firmware headers, etc.
- 🔎 **Search string** – Finds occurrences of a text string or byte pattern in the flash memory.
- 📜 **Extract strings** – Lists all readable ASCII/UTF-8 strings found in the flash.
- 📖 **Read bytes** – Reads a sequence of bytes from a specific address.
- ✏️ **Write bytes** – Writes one or more bytes to the specified address.
- 🗃️ **Dump Flash** – Outputs the entire flash contents in hex dump format.
- 💣 **Erase Flash** – Wipes the chip by erasing all sectors or the entire device.
- 🚪 **Exit Shell** – Leaves the SPI flash shell and returns to the previous menu.

### Supported Models

Compatible with most **SPI NOR Flash chips** from Winbond, Macronix, GigaDevice, ISSI, Micron, etc., using a standard SPI interface (JEDEC-compatible).  
Common series include **W25Qxx**, **MX25Lxx**, **GD25Qxx**, **IS25LPxx**, and similar, with capacities ranging from **512 Kbit** to **256 Mbit** or more.

- See https://github.com/geo-tp/ESP32-Bus-Pirate-Scripts to dump the content of Flash in a file.
- Standard SPI `flash` pinout:
![image](bitpirate-wiki/images/1d5f9770967ecba2.png)


## 📝 Notes

- Slave mode is not available on M5Stick.
- Slave mode uses the following library: https://github.com/hideakitai/ESP32SPISlave




## 📌 Example Usage

```bash
mode spi
config
sniff
slave
sdcard        # Enter SD card operations mode
flash         # Enter Flash operations mode
eeprom        # Enter SPI EEPRIM operations modes (25x series)
[0x9F r:3]    # Read JEDEC ID
```

## ▶️ Demo
![spiflash](bitpirate-wiki/images/7c550bfc1e990cc9.png)


## 🔧 Hardware


![flash-dip8-ff3a91001150163130bcc8f3e015165f](bitpirate-wiki/images/26f3a2085d2172f0.jpg)

![sd](bitpirate-wiki/images/e92c2204a7f4175b.jpg)
![71QG61eK5tL](bitpirate-wiki/images/83d96436dd753831.jpg)
