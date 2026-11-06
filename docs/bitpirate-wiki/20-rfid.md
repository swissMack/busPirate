# RFID Mode

RFID mode targets **13.56 MHz NFC/RFID** tags using the **PN532** reader (I²C). It supports common tag families such as **MIFARE Classic (1K/4K/Mini)**, **NTAG/Ultralight**, and basic **FeliCa** operations.


## 🧩 Commands

| Command  | Description |
|----------|-------------|
| `read`   | Polls for a tag and prints **UID / ATQA / SAK / Type** every ~300 ms (press **ENTER** to stop) |
| `write`  | Two flows: **UID (magic card)** or **Block/Page data** write (prompts for family, index, and hex data) |
| `clone`  | **UID clone**: read a **source** tag, then write its UID to a **target** (requires **magic** MIFARE card) |
| `erase`  | Wipes user data on the tag (Classic or NTAG/Ultralight) once the tag is detected |
| `config` | Interactive setup of **I²C pins (SDA/SCL)** and PN532 initialization |

## 🧪 Recipes

- [Wire a PN532 RFID reader in I2C mode](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/wire-pn532-rfid-reader-i2c/)
- [Read a PN532 RFID tag UID](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/read-rfid-tag-pn532/)
- [Write a test page to an NFC tag](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/write-rfid-ntag-page-pn532/)
- [Erase a lab NFC/RFID tag](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/erase-rfid-test-tag-pn532/)
- [Clone a MIFARE UID to a magic card](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/clone-mifare-uid-magic-card/)

## 📝 Notes

- **Frequency**: PN532 operates at **13.56 MHz** (NFC).  
- **Tag families** (ISO14443A unless noted):  
  - **MIFARE Classic** (Mini/1K/4K): 16‑byte **blocks** with sector trailers; read/write requires **authentication** (Key A/B).  
  - **NTAG/Ultralight**: 4‑byte **pages**; simple read/write but can be **lock‑protected**.  
  - **FeliCa** (ISO18092): basic polling and block read/write paths exist but are limited in this tooling.
- **Write UID** and **Clone** require a **“magic” Classic card** (block‑0 rewritable using the special backdoor). Normal Classic cards **cannot** change UID.
- **Erase** on Classic performs per‑block authentication. If keys are not default, you’ll get **authentication failed** and the erase will stop.
- Original code from Rennan Cockles (https://github.com/rennancockles), adapted for the ESP32 Bus Pirate.


## ⚙️ `config`

**Configure the PN532 (I2C):**
- **SDA** pin
- **SCL** pin
- After configuration, the PN532 should be detected and initialized. 
- If detection fails, check wiring and pins selection on **SDA/SCL**. 
- The PN532 must be in I2C MODE.
![i2c-mode](bitpirate-wiki/images/5cf856e4cbf48841.png)


## 📌 Example Usage

```bash
config             # Configure I²C pins (SDA/SCL) and initialize PN532
read               # Show UID/ATQA/SAK/Type every ~300 ms (ENTER to stop)
write              # Choose between "UID (magic card)" or "Block/Page data"
clone              # Read source → write UID to target (magic Classic only)
erase              # Erase user data (auth required on Classic)
```


## ▶️ Demo
![rfid](bitpirate-wiki/images/dc8b04269655dc91.png)


## 🔧 Hardware

- [PN532 NFC/RFID module](https://geo-tp.github.io/ESP32-Bit-Pirate/modules/pn532/) — RFID/NFC reader target.

![08240_3](bitpirate-wiki/images/c0382fbd0a02216a.jpg)
