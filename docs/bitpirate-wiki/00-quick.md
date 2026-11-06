# Quick Start
![ESP32 Bit Pirate Logo and Supported Protocols](bitpirate-wiki/images/c26647354d4b4f28.png)

## What is ESP32 Bit Pirate?

ESP32 Bit Pirate is a **multi-protocol exploration and debugging tool** for hardware hacking.

It allows you to:

* Explore electronic buses (I2C, SPI, UART, 1-Wire, JTAG, SWD, CAN, etc.)
* Explore radio protocols (RFID, RF, Bluetooth, WiFi, SubGhz)
* Reverse engineer unknown devices
* Send raw transactions
* Read / write memories (EEPROM, Flash, Smartcards)
* Automate tests and scripts

Think of it as a **modern, scriptable toolbox** running on ESP32, with a large range of supported protocols.

---


## What You Need

To get started with ESP32 Bit Pirate, you only need a few basic components.

![ESP32 S3 devkit board](bitpirate-wiki/images/e00ef4868840b2a0.png)
![Grove cable](bitpirate-wiki/images/fec55eaecf4f61b4.png)
![Dupont wires male/female](bitpirate-wiki/images/25cd91736932391f.png)
![test hooks grippers](bitpirate-wiki/images/3e548622ab3c8110.png)




- An **ESP32-S3 board**
  - Any ESP32S3N8 or ESP32S3N16, **at least 8MB Flash**, no PSRAM required
  - For maximum compatibility, use the boards listed in the [README](https://github.com/geo-tp/ESP32-Bus-Pirate?tab=readme-ov-file#supported-devices)
  - You can install the firmware in one click using the [Web Flasher](https://geo-tp.github.io/ESP32-Bit-Pirate/webflasher/)
- Wiring:
  - Dupont jumper wires (male/female)
  - Or Grove → Dupont / Qwiic → Dupont cables
  - Test hooks / grabbers


## Optional Accessories

Additional protocol support and features can be enabled by connecting external modules:

![CC1101 radio module for subghz](bitpirate-wiki/images/f91baff83eecf780.png)
![Bus Pirate DIP8 adapter](bitpirate-wiki/images/5ad366dba2d294e9.png)
![NRF24 module for 2.4Ghz](bitpirate-wiki/images/564ddc928fb976d2.png)
![Bus Pirate SOC8 adapter](bitpirate-wiki/images/34ba7578e2e7e397.png)




- [Accessories from the Original Bus Pirate ecosystem](https://buspirate.com/get/) 
- [ESP32 Bit Pirate Dock for ESP32S3 DevKit](https://github.com/AndreiVladescu/ESP32-Bus-Pirate-Dock)
- [ESP32 Bus Expander for WiFi 5GHZ](https://github.com/geo-tp/ESP32-Bus-Expander)

The connection details, references, and information for each module are described in the corresponding [mode](https://github.com/geo-tp/ESP32-Bus-Pirate/wiki).

---


## Basic Concept

Everything is done using commands.
Don’t worry though, **most commands are intentionally kept very simple**. You even have a [Pirate Assistant](https://github.com/geo-tp/ESP32-Bus-Pirate/wiki/99-Assistant) on the web UI to translate what you want to do into commands.

In many cases, **you only need to type a single word** with no arguments or flags at all, such as `read`, `receive`, or `scan`.
Some commands do accept arguments, but they follow straightforward and **intuitive formats**.

General form:

```
command [arg1] [arg2] ...
```

Examples:

```
scan
monitor 0x13
wizard 1
sniff
logic 1
jam
read 0x13 6
```

* Arguments are space-separated
* Arguments in `< >` are required
* Arguments in `[ ]` are optionnal
* Numbers can be decimal or hex:

```
255
0xFF
```
You can **chain multiple commands**, **repeat commands**, and **insert delays** between actions.  
This makes it possible to build simple scripts directly from the command line interface.

Exemples:
```
m dio || read 1 || set 1 LOW || delayms 1 || set 1 HIGH
repeat 5 scan
repeat 10 set 1 LOW || delayus 100 || set 1 HIGH || delayus 100
```

---

## Switching Protocol Modes

You usually start by selecting a protocol:

Type `m`, `mode` or `m uart`, `m i2c`.

```
m         (prompt for mode)
mode      (prompt for mode)
mode uart (direct mode access)
m dio     (direct mode access)
```

## Example 1 – Some I2C operations

![490790516-229dc03c-cb8a-40f2-935c-096d59462378](bitpirate-wiki/images/285dae4ec43d67aa.png)

## Example 2 – Some UART operations

![466254812-6c6752c8-dc4e-47a8-b10c-7e178987f9b1](bitpirate-wiki/images/d31efb51f6e3cc7a.png)


## Web Serial Tools

The [ESP32 Bit Pirate Web Serial Tools](https://geo-tp.github.io/ESP32-Bit-Pirate/web-tools/) provide direct browser access to embedded hardware utilities, without installing PuTTY, minicom, flashrom, PulseView, or other desktop applications.

![web tools demo](bitpirate-wiki/images/8d57ccc08cef82c6.png)



## Python Scripting

You can control ESP32 Bus Pirate from Python over Serial. See [Python Automation](https://github.com/geo-tp/ESP32-Bus-Pirate/wiki/99-Python)

![ezgif-4508b9f0394d2712](bitpirate-wiki/images/0051c3d3b78b5c98.png)


---


ESP32 Bus Pirate is designed to be **explored**.
Type commands, experiment, break things, learn.
