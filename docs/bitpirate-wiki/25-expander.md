# EXPANDER

![bus_pirate_exp](bitpirate-wiki/images/b980c7f9cf845a14.png)

https://github.com/geo-tp/ESP32-Bus-Expander


The **EXPANDER mode** allows the Bit Pirate to communicate with an external **ESP32 Bus Expander** device.


The expander acts as a **radio coprocessor**, extending the capabilities of the main Bit Pirate firmware, notably by **adding 5 GHz Wi-Fi and Zigbee support**.






## ⚡ Flash it


Use the [ESP32 Bit Pirate WebFlasher](https://geo-tp.github.io/ESP32-Bit-Pirate/webflasher/) and select **ESP32 Bus Expander (ESP32-C5/C6, at least 4MB flash, no PSRAM needed)**.

[Bridge the ESP32 Expander](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/bridge-esp32-c5-expander/)

### ESP32-C5

| Bit Pirate | Bus Expander |
|---|---|
| RX | GPIO 9 |
| TX | GPIO 10 |
| GND | GND |

### ESP32-C6

| Bit Pirate | Bus Expander |
|---|---|
| RX | GPIO 19 |
| TX | GPIO 18 |
| GND | GND |
