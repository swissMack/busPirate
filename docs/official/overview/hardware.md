# Bus Pirate Hardware

![](official/images/fw/bp5rev10-cover-angle.jpg)

Bus Pirate is the universal serial interface tool trusted by hackers since 2008.

What can the Bus Pirate do? Probe and debug serial protocols like [I2C](official/command-reference.md#i2c), [SPI](official/command-reference.md#spi), [UART](official/command-reference.md#uart), [1-Wire](official/command-reference.md#1-wire) and more - without writing code! Read and write [Flash memory](official/command-reference.md#flash-readwriteerase-common-flash-chips), [24x/25x/93x/95x EEPROMs](official/command-reference.md#eeprom-read-write-erase-verify-test-dump-i2c-eeproms), [DDR5 SPD](official/devices/ddr5.md), [smart cards](official/devices/sle4442.md), and [FRAM](official/devices/identify-serial-memory-chips.md#fram-memory). Several types of [logic analyzer support](official/logic-analyzer/logicanalyzer.md), and a [low speed oscilloscope](https://docs.buspirate.com/docs/scope/). Discover [JTAG and SWD debug ports](official/devices/jtag-swd-pin-finder.md). [Sniff I2C](official/command-reference.md#sniff-i2c-bus-sniffer) and other busses. Glitch hack an [Arduino](official/devices/uart-glitch-command.md). [Record](official/command-reference.md#irrx) and [playback](official/command-reference.md#irtx) infrared remote control signals, also works with [AnalysIR software](official/software/analysir.md). Control common serial LEDs like [WS2812, SK6812](official/devices/ws2812-sk6812-neopixel.md), [APA102](official/devices/apa102-sk9822.md), and read [RGB color sensors](official/devices/tcs3472x.md). Works with [FlashRom](official/software/flashrom.md) and [AVRDUDE](official/software/avrdude.md). Nearly constant [firmware releases](https://docs.buspirate.com/docs/downloads/) and updates, active community support.

Can't get a chip to work? Is it the circuit, code, bad part or a burned out pin? The Bus Pirate sends commands over common serial protocols (1-Wire, I2C, SPI, UART, MIDI, serial LEDs, etc) so you can get to know a chip before prototyping. Updated with tons of new features, talking to chips and probing interfaces is more fun than ever!

[Get Bus Pirate & Accessories](https://buspirate.com/get)

## Version comparison
|Feature|Bus Pirate 5|Bus Pirate 6|
|-|-|-|
|Microcontroller|RP2040 dual core 125MHz|RP2350 dual core 133MHz|
|RAM|264KB|512KB|
|PIO state machines|8|12|
|Follow Along Logic Analyzer|No|Yes|

> **Note:**
> There isn't a huge difference between Bus Pirate 5 and Bus Pirate 6. The Bus Pirate 6 uses the new RP2350 microcontroller which is slight faster, has more RAM and an addition PIO module. Eventually that extra RAM and PIO will enable things that aren't possible on Bus Pirate 5, but for now both versions have the same firmware features.

The Bus Pirate 6 killer feature is the [follow along logic analyzer](official/logic-analyzer/pulseview-fala.md) that displays protocol activity in real time on Sigrok/Pulseview. You see exactly what happened on the pins during every transaction, no need to configure a separate logic analyzer and set triggers. This is made possible by the extra pins on the RP2350B microcontroller.

Bus Pirate 5 is in active volume production, is super well tested, and is the primary development platform for new firmware features. The cost is low so it can be as widely accessible as possible.

Bus Pirate 6 is in initial production, is available in limited quantities, and is much more expensive. The goal is not to replace the Bus Pirate 5, but to offer a more "luxury" version for those who want to support the project and get a few bonus features.

## VT100 terminal interface

<!-- ![](official/images/fw/teraterm-done.png) -->

[▶ Watch this as a recording on docs.buspirate.com](https://docs.buspirate.com/docs/overview/hardware/)

VT100 terminal emulation supports color and a live statusbar view of the voltage and functions on each pin. Type simple commands into the terminal, the Bus Pirate translates them into popular serial protocols and displays the response. Learn how a chip works without touching a line of code.

## Specifications

- Raspberry Pi RP chip paired with 128Mbit program flash
- 8 powerful IO pins - Support multiple protocols from 1.2-5volts. Analog voltage measurement and optional 10K pull-ups on all pins
- 1-5volt output power supply - 0-500mA current limit, current sense, resettable fuse and protection circuit
- 1Gbit NAND flash - Store settings and files. Appears as a USB drive.
- LCD - A beautiful 240x320 pixel color IPS (all angle viewing) LCD acts as a pin label, while also showing the voltage on each pin and the current consumption of the programmable power supply unit
- 18 RGB LEDs - It's customary to have an indicator LED, so to check that box we added 16 SK6812 RGB LEDs.
- Just one button - 18 party LEDs but just one button!
- 1-Wire, I2C, SPI, UART, MIDI, serial LEDs supported, more to come!

Bus Pirate is the universal serial interface tool designed by hackers, for hackers. It's crammed full of hardware and firmware features to make probing chips pleasant and easy.

### Get a Bus Pirate
 

[Get Bus Pirate & Accessories](https://buspirate.com/get)

- [Browse Complete Bus Pirate hardware collection](https://dirtypcbs.com/store/designer/browse/ian)
- [Bus Pirate 5 REV10 with enclosure](https://dirtypcbs.com/store/designer/details/ian/6633/bus-pirate-5-rev10-with-enclosure)
- [Probe Cable Kit](https://dirtypcbs.com/store/designer/details/ian/6619/bus-pirate-5-probe-cable-kit)
- [Auxiliary Cable Kit](https://dirtypcbs.com/store/designer/details/ian/6620/auxilary-cable-kit)
- [Quick Connect Adapter](https://dirtypcbs.com/store/designer/details/ian/6634/bus-pirate-quick-connect-kf141-adapter)
  

> **Note:**
> This is the user guide for Bus Pirate 5. See the [hardware documentation](https://docs.buspirate.com/docs/hardware/) for all the technical details.

## Color IPS LCD

![](official/images/fw/bp5rev10-cover-2.jpg)

A beautiful 240x320 pixel color IPS (all angle viewing) LCD acts as a pin label, while also showing the voltage on each pin and the current consumption of the programmable power supply unit

## Main connector
![](official/images/hw/bp6rev2/connectors.jpg)

2.54mm 10 pin connector - A keyed locking connector that works just as well with common jumper wires and 2.54mm 'DuPont' style connectors.

|Pin|Label|Description|
|-|-|-|
|1|VOUT/VREF|Pin supplies 1-5volts up to 300mA with current limit and resetable fuse (VOUT) **OR** connects an external voltage source to the Bus Pirate IO interface|
|2-9|IO0 - IO7|Buffered IO pins 1.2-5volt output with voltage measurement and optional 10K pull-up resistors|
|10|GND| Ground pin|

## Auxiliary connector

![](official/images/fw/bp5-aux.jpg)

1mm 9 pin connector - Intended as a tap point for a logic analyzer. No more trying to balance two or three probes on a single pin, just tap the bus activity from this secondary header.

|Pin|Label|Description|
|-|-|-|
|1-8|IO0 - IO7|Buffered IO pins with voltage measurement and optional 10K pull-up resistors|
|9|GND| Ground pin|

## 1Gbit NAND flash

![](official/images/fw/bp5rev10-nand.jpg)

1Gbit (~100MB usable) NAND flash - Appears as a readable and writable disk drive when plugged into a USB port. 

![](official/images/fw/json-config.png)

Flash storage is used to save global and mode configuration preferences in simple JSON files. 

## Just one button

![](official/images/fw/bp5-onebutton.jpg)

18 party LEDs but just one button! This is due to the low pin count of the RP2040. The button is used to escape modes, production programming and user defined functions.

## USB C connector
![](official/images/fw/bp5-usbc.jpg)

Modern USB C connector. Only RP2040 supported USB modes are available.

## USB bootloader

![](official/images/fw/bp5-back.jpg)

Updating is as simple as dragging a file onto the disk. 

Normally the ```$``` key in the Bus Pirate terminal enters bootloader mode for firmware upgrades. You can also use the button on the bottom to activate the bootloader manually. 

## JTAG debug header
![](official/images/fw/bp5-debug.jpg)

A three pin debugging port is exposed on the bottom of the board. See the development section for more info on developing for the Bus Pirate.

|Pin|Label|Description|
|-|-|-|
|1|GND|Ground connection (furthest from the edge of the PCB/case)|
|2|SWDIO|JTAG Data IO|
|3|SWCLK|JTAG Clock (closest to the edge of the PCB/case)|

## Get a Bus Pirate

[Get Bus Pirate & Accessories](https://buspirate.com/get)

- [Browse Complete Bus Pirate hardware collection](https://dirtypcbs.com/store/designer/browse/ian)
- [Bus Pirate 5 REV10 with enclosure](https://dirtypcbs.com/store/designer/details/ian/6633/bus-pirate-5-rev10-with-enclosure)
- [Probe Cable Kit](https://dirtypcbs.com/store/designer/details/ian/6619/bus-pirate-5-probe-cable-kit)
- [Auxiliary Cable Kit](https://dirtypcbs.com/store/designer/details/ian/6620/auxilary-cable-kit)
- [Quick Connect Adapter](https://dirtypcbs.com/store/designer/details/ian/6634/bus-pirate-quick-connect-kf141-adapter)

### Files

- [Download latest firmware build](https://forum.buspirate.com/t/bus-pirate-5-auto-build-main-branch/20/99999)
- [Bus Pirate 5 Hardware repo](https://github.com/DangerousPrototypes/BusPirate5-hardware)
- [Bus Pirate 5 Firmware repo](https://github.com/DangerousPrototypes/BusPirate5-firmware)

### Community

- [Forum](https://forum.buspirate.com)
- [Blog](https://buspirate.com/) and mailing list
- [Mastodon](https://mastodon.social/@buspirate)
- [Instagram](https://www.instagram.com/dangerousprototypes)
- [BlueSky](https://bsky.app/profile/buspirate.bsky.social)
- [X (Twitter)](https://twitter.com/dangerousproto)

### Documentation

Here's some other fun stuff you might enjoy.
- [Component selection and sourcing](https://docs.buspirate.com/docs/hardware/bp5rev10/components/introduction/)
- [Cables](official/cables/cables.md) and [Milled breadboard pins](official/cables/milled-pins.md)
- [Injection molded case](https://docs.buspirate.com/docs/enclosure/injection-molded-shell/)
- [Hardware users guide](official/overview/hardware.md)
- [Getting started](official/tutorial-basics/quick-setup.md) and [Command reference](official/command-reference.md)
- [Firmware development](https://docs.buspirate.com/docs/development/code/) and [translation](https://docs.buspirate.com/docs/development/translation/)
- [Manufacturing resources](https://docs.buspirate.com/docs/manufacturing/)

## FCC compliance statement
This device complies with part 15 of the FCC Rules. Operation is subject to the following two conditions: (1) this device may not cause harmful interference, and (2) this device must accept any interference received, including interference that may cause undesired operation.

## CE compliance
The Bus Pirate has been lab tested to comply with European CE requirements.
