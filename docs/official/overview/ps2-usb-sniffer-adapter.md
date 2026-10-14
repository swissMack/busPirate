# PS/2 & USB Keyboard Sniffer Adapter

![](official/images/fw/plank-ps2usb.jpg)

The PS/2 & USB Sniffer adapter plank sits inline between a keyboard and a computer and passively records everything that crosses the wire. [PS/2 and low speed USB are decoded live](official/devices/ps2-usb-keyboard.md): raw packets scroll past as they happen, and a **key tracker** rebuilds the typed text right next to them, so you read words instead of scan codes.

PS/2 & USB Sniffer plank features:
- Two PS/2 (mini-DIN 6P) connectors and two USB connectors, wired as pass-throughs so the keyboard keeps working while you capture
- PS/2 scan code set 2 decoded to keystrokes
- Low speed USB HID boot protocol decoded to keystrokes
- A key tracker in each mode that reconstructs the typed text as a plain string
- **TRIGGER** output to sync an external logic analyzer to the capture
- **PWR SWITCH** to take bus power from the Bus Pirate **VOUT** supply or from the PC (**EXT**)

<!-- -->

[Get Bus Pirate & Accessories](https://buspirate.com/get)

## Adapter pinout

|Bus Pirate pin|Label|Description|
|-|-|-|
|1|VOUT|Bus power, when the PWR SWITCH is in the VOUT position|
|2|TRIG|Trigger output to sync an external logic analyzer|
|3|D+|USB D+|
|4|D-|USB D-|
|5|RESV|Reserved|
|6|DAT|PS/2 data|
|7|CLK|PS/2 clock|
|8|RESV|Reserved|
|9|RESV|Reserved|
|10|GND|Common ground with the keyboard and the PC|

The Bus Pirate shows these same labels under the pin numbers in the status bar, so you can confirm the plank is wired the right way round at a glance.

## Power switch

![](official/images/fw/ps2usb-pwr-switch.jpg)

**SW1** selects where the sniffed bus takes its power from. Slide it to **VOUT** to power the bus from the Bus Pirate supply, or to **EXT** to let the PC power it, exactly as it would without the plank in the way.

> **Danger:**
> Both of the setups below need the **PWR SWITCH** in the **EXT** position, as in the photo. The keyboard is powered by the PC through the pass-through cables, not by the Bus Pirate.

## Resources
- [PS/2 & USB Keyboard Sniffer demo](official/devices/ps2-usb-keyboard.md)
- [Development thread](https://forum.buspirate.com/t/usb-sniffer-ps2-sniffer-plank-firmware-for-bp/1055)
- [pico-ps2-sniffer](https://github.com/therealdreg/pico-ps2-sniffer)
- [Schematic and PCB](https://github.com/DangerousPrototypes/BusPirate5-hardware/tree/main/development/adapter-kaybee-plank-1REV1)

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
