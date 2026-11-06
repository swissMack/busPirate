# JTAG Mode

This mode provides access to JTAG-related utilities.


## 🧩 Commands

| Command     | Description                                                   |
|-------------|---------------------------------------------------------------|
| `scan swd`  | Attempts to detect a SWD device by brute-force pin scanning   |
| `scan jtag` | Performs a JTAGULATOR-style brute-force JTAG pinout scan         |
| `openocd` | Transforms the device into OpenOCD adapter (See [USB Adapter](bitpirate-wiki/99-adapters.md#openocd-bus-pirate-adapter))         |
| `config`    | Configure which GPIOs are used for scanning                   |

## 🧪 Recipes

- [Scan for SWD pins](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/scan-swd-pinout/)
- [Scan for a JTAG pinout](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/scan-jtag-pinout/)
- [Use OpenOCD adapter mode](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/use-openocd-jtag-adapter/)
- [Configure the JTAG/SWD scan pin group](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/configure-jtag-swd-scan-pins/)

## 📝 Notes

- The `scan swd` command will try combinations of GPIOs to identify SWDIO and SWCLK.
- You can select the group of pin to scan with `config` (eg,. 1 3 5 7...).
- The `scan jtag` command tries all permutations of 4 GPIOs to detect TDI, TDO, TCK, TMS (and optionally TRST).
- Original source for RP2040 https://github.com/Aodrulez/blueTag/, ported to ESP32.
- The features are similar to those of the JTAGULATOR.


## 📌 Example Usage

```bash
scan swd
scan jtag
config
```

## ▶️ Demo

![demo11](bitpirate-wiki/images/c64a77605de3e6b8.png)
