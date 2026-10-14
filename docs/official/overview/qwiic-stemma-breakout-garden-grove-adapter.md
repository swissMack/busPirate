# Qwiic, Stemma (3P/4P/QT), Breakout Garden, Grove I2C Adapter

![alt text](official/images/qwiic-stemma-breakout-garden-grove-adapter/image-1.png)

One fabulous I2C quick connect adapter to rule them all! The quick connect adapter combines the most popular I2C breakout standards in one Bus Pirate compatible plank.

I2C is a simple communication protocol used by many sensors and devices. Over the years, manufacturers created "standard" I2C breakout board connectors for quick solder-free prototyping. All have the same basic four connections: power (V+), ground (GND), I2C Serial Data (SDA), and I2C Serial Clock (SCL). However, the pinout and connector types vary. 

[Get Bus Pirate & Accessories](https://buspirate.com/get)

## I2C Breakout Standards

- Adafruit Industries: [Stemma 3P, Stemma 4P (I2C), Stemma QT](https://learn.adafruit.com/introducing-adafruit-stemma-qt/technical-specs)
- SparkFun Electronics: [Qwiic](https://www.sparkfun.com/qwiic)
- Seeed Studio: [Grove](https://wiki.seeedstudio.com/Grove_System/)
- DFRobot: [Gravity](https://www.dfrobot.com/gravity)
- Pimoroni: [Breakout Garden](https://shop.pimoroni.com/collections/breakout-garden)

> **Note:**
> Adafruit's Stemma 3P is a single signal connector, not an I2C connector.

## Pinout Table

|Pin| Stemma 3P| Stemma 4P |Stemma QT| Qwiic | Grove | Gravity | Breakout Garden |
|---|---|---|---|---|---|---|---|
|1  |SIGNAL        |   SCL     |GND    |   GND |   GND | SDA       |   V+|
|2  |V+         |   SDA     |V+     |   V+  |   V+  | SCL       |   SDA|
|3  |GND       |   VOUT    |SDA    |   SDA |   SDA | GND       |   SCL|
|4  |--         |   GND     |SCL    |   SCL |   SCL | V+        |   INT|
|5  |--         |   --      |--     |   --  |   --  | --        |   GND|

> **Note:**
> Breakout Garden is a dual row PCB edge connector. The connections on each side are mirrored so boards can be inserted in both directions. The table above shows the pinout for a single row on one side.

## Connector Types

|Standard | Connector | Pitch | Example Part Number |
|---|---|---|---|
| Stemma 3P | JST PH 3P | 2.0mm |JST: S3B-PH-SM4-TB, Generic: HC-PH-3AWT|
| Stemma 4P | JST PH 4P | 2.0mm |JST: S4B-PH-SM4-TB, Generic: HC-PH-4AWT|
| Stemma QT | JST SH 4P | 1.0mm |JST: SM04B-SRSS-TB, Generic: HC-1.0-4PWT|
| Qwiic     | JST SH 4P | 1.0mm |JST: SM04B-SRSS-TB, Generic: HC-1.0-4PWT|
| Grove     | "HY" 4P | 2.0mm |HY-4P, HY2.0-4P-SMD, A2008WR-S-4P|
| Gravity   | JST PH 4P | 2.0mm |JST: S4B-PH-SM4-TB, Generic: HC-PH-4AWT|
| Breakout Garden | PCB edge slot conn. 2 x 5P | 2.54mm |ED10BGFBK|

## Thanks!

A huge thank you to Funcan, kd7eir, grymoire, and henrygab for testing the various connectors with genuine breakout boards! 

## Resources

-  [schematic and PCB]()
- [Development thread](https://forum.buspirate.com/t/qwiic-stemma-qt-breakout-garden-grove-plank/1177)

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
