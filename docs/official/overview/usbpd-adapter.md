# USB Power Delivery Adapter

> **Note:**
> This page is a work in progress. Some details may be missing or incomplete.

![alt text](official/images/usbpd-adapter/image-3.png)

USB Power Delivery (USB PD) is a standard for negotiating power delivery over USB-C connections. The Bus Pirate USB PD adapter is a breakout board for the AP33772S USB PD **sink** controller, which can be used to test and debug USB PD devices and connections using the [```usbpd``` command](official/command-reference.md#usbpd-usb-power-delivery-with-ap33772s)

The adapter includes TVS diodes for protection, level shifting for the CC lines, an output control FET, a fuse, a current sense resistor, a temperature sensor, and indicator LEDs for power and USB PD status.

<!--
[Get Bus Pirate & Accessories](https://buspirate.com/get)

-->

> **Warning:**
> Coming soon! Manufacturing will begin after Spring Festival (March 2026).

## Features

- Works with the Bus Pirate I2C mode [```usbpd``` command](official/command-reference.md#usbpd-usb-power-delivery-with-ap33772s)
- AP33772S USB PD 3.1 Sink Controller: Manages USB PD communication and power delivery, **sink only**.
- Standard Power Range (SRP) and Programmable Power Supply (PPS) profiles up to 21 volts.
- Adjustable Voltage Supply (AVS) and Extended Power Range profiles up to 28 volts.
- Over/Under Voltage Protections (OVP/UVP), Over Current Protection (OCP), Over Temperature Protection (OTP)
- Moisture Detection in the USB Connector
- TVS diodes shield the USB-C port from voltage spikes and ESD events.
- Output control FET enables/disables power output.
- 30 volt/500 mA fuse to safeguard against high-ish voltage shorts.
- Current sense resistor for real-time tracking of power draw.
- Temperature sensor prevents overheating.
- Level shifting on CC0/CC1 boosts 1.1 volt signals to 5 volts for easy analysis with budget logic analyzers.
- Power and USB PD status LEDs. 

> **Warning:**
> AP33772S is a USB PD **sink** controller, which means it can only be used to test and debug devices that provide power over USB-C (USB chargers). It cannot **source** power to other USB devices (e.g. a phone or power bank).

> **Danger:**
> Many USB power supplies can provide high voltage and current that could potentially be dangerous. We chose to use a fairly **small 500mA fuse** for safety. If you want to pull more current, you will need to replace or bypass the fuse. Be very careful if you choose to do this, and **make sure you understand the risks of working with high voltage and current**.

## Status LEDs

**PWR** indicates that a USB power source is connected and providing power. 

| State | LED Indication | VOUT | Comments |
|-|-|-|-|
| INIT | Off | OFF | VBUS/Rp attached and AP33772S initialization |
| CHARGING | 4-sec Breathing | ON | Successful negotiation or enter Non-PD Mode|
| MISMATCH | Full Light | OFF | VSELMIN mismatch (VREQ < VSELMIN) |
| MOISTURE | 2-sec Flicker | OFF | Abnormal impedance detected in the Type-C connector |
| FAULT | 0.6-sec Flicker | OFF | OVP, OCP, UVP or OTP occurs |

**STAT** indicates the status of the USB PD connection, according to the table above. Source: [AP33772S datasheet](https://www.diodes.com/part/view/AP33772S).

## CC Line Level Shifter

![alt text](official/images/usbpd-adapter/image.png)

USB PD communicates over the CC0 and CC1 lines. The signal levels on these lines are 1.1 volts for a high and 0 volts for a low, which is not a valid range for most cheap logic analyzers.

![alt text](official/images/usbpd-adapter/image-4.png)

The Bus Pirate USB PD adapter includes level shifters that bring these signals up to 3.3/5 volts, making them easier to analyze with common tools. 

The shifter is based on a simple comparator set to flip at a threshold of around 0.628 volts. Output level is determined by the Bus Pirate VOUT voltage.

## Pin Breakouts

### USB Pins
|Pin|Description|
|-|-|
|D+|USB D+ data line|
|D-|USB D- data line|
|SBU2|Sideband use pin 2|
|SBU1|Sideband use pin 1|
|CC2|Configuration channel pin 2|
|CC1|Configuration channel pin 1|

Header J6 breaks out the raw USB-C signals.

### Other Pins
|Pin|Description|
|-|-|
|CC1 Shift|Level shifted CC1 signal|
|CC2 Shift|Level shifted CC2 signal|
|Flip|Indicates the orientation of the USB-C plug|
|VSEL|Startup voltage selection pin, set by a resistor value|
|OTP|Temperature thermistor output pin|
|GND|Ground|

Header J8 breaks out signals from the AP33772S USB PD controller, and the level shifted CC1 and CC2 signals.

## Resources

- USB PD adapter [schematic and PCB]()
- [```usbpd``` command documentation](official/command-reference.md#usbpd-usb-power-delivery-with-ap33772s)
- [I2C mode documentation](official/command-reference.md#i2c)

## Get a Bus Pirate

[Get Bus Pirate & Accessories](https://buspirate.com/get)

- [Browse Complete Bus Pirate hardware collection](https://dirtypcbs.com/store/designer/browse/ian)
- [Bus Pirate 5 REV10 with enclosure](https://dirtypcbs.com/store/designer/details/ian/6633/bus-pirate-5-rev10-with-enclosure)
- [Probe Cable Kit](https://dirtypcbs.com/store/designer/details/ian/6619/bus-pirate-5-probe-cable-kit)
- [Auxiliary Cable Kit](https://dirtypcbs.com/store/designer/details/ian/6620/auxilary-cable-kit)
- [Quick Connect Adapter](https://dirtypcbs.com/store/designer/details/ian/6634/bus-pirate-quick-connect-kf141-adapter)

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
