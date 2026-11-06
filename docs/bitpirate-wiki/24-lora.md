# LoRa Mode

LoRa mode provides access to **SX1262** LoRa transceivers for packet transmission, reception and RF analysis.

It supports raw LoRa communication, RSSI monitoring, frequency scanning, recording/replay and Meshtastic packet analysis.



## 🧩 Commands

Arguments in `< >` are required, while arguments in `[ ]` are optional.

Command | Description
--- | ---
`send <payload>` | Send a text or hexadecimal LoRa payload
`spam <payload> [interval]` | Repeatedly transmit a payload ⚠️
`jam [seconds]` | Transmit a continuous carrier for RF testing ⚠️
`receive` | Receive LoRa packets and display payload, RSSI and SNR
`record` | Receive and save a LoRa packet to LittleFS
`load` | Load and transmit a previously recorded `.lora` packet
`rssi [interval]` | Monitor RSSI at the current frequency
`scan` | Scan a frequency range for RF activity
`waterfall` | Display real-time frequency activity on supported screens
`cad [interval]` | Run LoRa Channel Activity Detection
`ear` | Convert RSSI variations into audio tones
`airtime [bytes]` | Calculate estimated LoRa Time-on-Air
`setfreq <MHz>` | Set the operating frequency
`status` | Display the current radio configuration and statistics
`meshtastic` | Open the Meshtastic analysis shell
`config` | Configure SX1262 pins and LoRa parameters


## ⚠️ Important Warning (Transmission / Jamming)

* RF transmission may be regulated depending on frequency, power and local legislation.
* Jamming can interfere with legitimate radio communications. Use only in controlled test environments.
* Always use an antenna suitable for the selected frequency.

## 🧪 Recipes

* [Wire an SX1262 LoRa module](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/wire-sx1262-lora-module/)
* [Configure an SX1262 LoRa profile](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/configure-sx1262-lora-radio/)
* [Receive a LoRa packet with SX1262](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/receive-lora-packet-sx1262/)
* [Send a LoRa packet with SX1262](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/send-lora-packet-sx1262/)
* [Scan LoRa frequency activity with SX1262](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/scan-lora-frequency-sx1262/)
* [Record and load a LoRa packet](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/record-load-lora-packet-sx1262/)



## ⚙️ `config`

Configure the SX1262 pins and radio parameters:

* SCK / MISO / MOSI / CS
* RESET / BUSY / DIO1
* Frequency
* Bandwidth
* Spreading Factor
* Coding Rate
* TX Power
* Preamble
* Sync Word
* CRC / IQ / TCXO

Default profile: **868 MHz, 125 kHz bandwidth, SF9, CR 4/7, 14 dBm**.


## 📝 Notes

* LoRa mode currently targets the **SX1262**.
* `record` stores the radio configuration together with the payload in a `.lora` file.
* `scan`, `rssi`, `waterfall` and `cad` can be used to identify and analyze LoRa activity.
* `meshtastic` provides a lightweight shell for sending, receiving and inspecting Meshtastic frames using common modem presets and optional channel keys.
* Long-running commands can be stopped by pressing **ENTER**.
* Transmitter and receiver must use compatible frequency and LoRa modulation parameters.


## 📌 Example Usage

    config                 # Configure SX1262 and LoRa parameters
    status                 # Display current configuration
    send Hello             # Send a LoRa packet
    receive                # Receive LoRa packets
    scan                   # Scan for RF activity
    waterfall              # Display frequency activity
    record                 # Save a received packet
    load                   # Replay a saved .lora packet
    meshtastic             # Open Meshtastic analysis shell


## 🔧 Hardware
- [Sx1262 LoRa Module](https://geo-tp.github.io/ESP32-Bit-Pirate/modules/sx1262/)

![SX1262 lora module](bitpirate-wiki/images/53d3e5fbcbdb6eec.png)
