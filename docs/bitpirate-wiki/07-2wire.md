# 2WIRE Mode

This mode is designed for interacting with smartcards and synchronous serial devices over a simple 2-wire interface, typically used in memory cards.


## 🧩 Commands

| Command                | Description                                              |
|------------------------|----------------------------------------------------------|
| `sniff`                | Sniff data on IO/CLK with start/stop bits and commands description                   |
| `config`               | Configure pins and frequency                 |
| `smartcard`      | Open an interactive shell for smartcard (SLE44XX) operations |
| `[0xAB r:4]`           | Raw instruction syntax for 2WIRE bit patterns [NYI]      |


## 🧪 Recipes

- [Read an SLE4442 smartcard](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/read-sle4442-smartcard/)
- [Probe an SLE4442 smartcard ATR](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/probe-sle4442-smartcard-atr/)
- [Check SLE4442 security status](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/check-sle4442-security-status/)

## 💳 Smartcard SLE44XX Shell

The **`smartcard`** command provides an interactive environment to explore, manage, and erase SLE44XX cards.

### Actions

- 🔍 **Probe** – Detects the card type and reads the ATR (Answer To Reset).
- 🛡️ **Security check** – Verifies the current PSC (PIN) attempt counter and status.
- 🔓 **Unlock card** – Enters the PSC to unlock protected areas.
- 📝 **PSC Set** – Changes the PSC code to a new value.
- 📋 **PSC Get** – Reads the current PSC (if security settings allow).
- ✏️ **Write** – Writes data to a specified memory address.
- 🗃️ **Dump** – Reads and displays the entire card memory contents.
- 🚫 **Protect** – Permanently write-protect specific memory zones.
- 🚪 **Exit Shell** – Leaves the shell and returns to the previous menu.


### Supported Models

| Model     | Memory Size | Security Features                          |
|-----------|------------:|--------------------------------------------|
| SLE4442   | 256 bytes   | PSC protection, write-protect zones, retry counter |
| Compatible clones | Various | Same protocol and features as above      |


### Notes
- SLE44XX smartcards use the **2-Wire protocol** (not I²C, not ISO7816).  
- Probe executes an ATR (Answer to reset) for SLE4442 cards.  
- **PSC (Personal Security Code)** is usually 3 bytes long.  
- Exceeding the allowed number of incorrect PSC attempts will permanently lock the protected zones.  
- Some SLE44XX clone cards ignore the protection memory, even after setting protection bits, writing to memory may still be possible.
- Most SLE44XX cards require a 5V power supply to operate reliably
- SLE44XX pinout:

![Smart-Card-Pin-out-3](bitpirate-wiki/images/b45b2d2508dfe037.jpg)



## 📌 Example Usage

```bash
smartcard   # Operations on smartcard
sniff
config
[0x5A r:1]
```
## ▶️ Demo
![2wiresmartcard](bitpirate-wiki/images/da90eeffdaf9a174.png)



## 🔧 Hardware

![flash_sim8_front](bitpirate-wiki/images/d10dc60ff369f147.jpg)
![smart-costa-card-500x500](bitpirate-wiki/images/aa7ba0b6c364cd6e.jpg)
