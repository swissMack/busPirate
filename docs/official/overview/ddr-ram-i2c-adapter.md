# DDR5 RAM SPD I2C Adapter

![alt text](official/images/ddr-ram-i2c-adapter/image.png)

The DDR5 adapter plank makes it easy to read and write the SPD chip on DDR5 UDIMM and SODIMM computer memory modules. 

Use the Bus Pirate [```ddr5``` command](official/command-reference.md#ddr5-probe-read-write-unlock-ddr5-sdram-modules) to read and write the SPD EEPROM on a DDR5 module, or follow the [DDR5 device demo](official/devices/ddr5.md) to learn about the technical details.

DDR5 adapter plank features:
- 288 pin DDR5 UDIMM socket for standard desktop memory modules
- 262 pin DDR5 SODIMM socket for laptop memory modules
- Accepts a single 5 volt power supply
- A 3.3 volt regulator supplies the I2C and PWR_EN pins
- A level shifter ensures the I2C pins HSDA and HSCL are never more than 3.3 volts
- HSA is pulled to ground to put the module in offline mode
- PWR_GOOD is connected to an LED indicator that lights when the PMIC reports a voltage error

The DDR5 plank is ready to use.

[Get Bus Pirate & Accessories](https://buspirate.com/get)

## Adapter Pinout
|DDR5 adapter plank|Description|
|-|-|
|BULK_VIN|5 volt power supply for the DDR5 module|
|HSDA|Level translated I2C Data|
|HSCL|Level translated I2C Clock|
|PGOOD|Power Good signal from the DDR5 PMIC, low for error|
|GND|Common ground for the DDR5 module and the Bus Pirate|

> **Warning:**
> When inserting a DDR5 module into the adapter plank, **hold the bottom of the PCB with both hands and press the module firmly into the socket**. The retaining clips should click into place. 

## SODIMM and UDIMM Connections

![](official/images/demo/ddr5-connection.png)

|DDR5 UDIMM (288 pins)|DDR5 SODIMM (262 pins)|Description|   
|-|-|-|
|HSDA (5)|HSDA (6)|I2C Data (3.3volt) **must be level shifted**|
|HSCL (4)|HSCL (4)|I2C Clock (3.3volt) **must be level shifted**|
|PWR_EN(151)|PWR_EN (8)|Power Enable, connect to 3.3 volts|
|HSA (148)|HSA (2)|Host Sideband Address, connect to ground for address 0 (Offline Mode)|
|PWR_GOOD (147)|PWR_GOOD (7)|Power Good, optional (low for error)|
|BULK_VIN (3)|BULK_VIN (1)|Bulk Voltage Input, connect to 5 volts|
|GND (150)|GND(9)|Ground|

We only need to connect a few pins to access the SPD hub on a DDR5 module. The rest of the pins are used for power, data, and control signals.

- **HSDA** and **HSCL** are the I2C data and clock pins. While the DDR5 module is powered by 5 volts, the I2C pins must be no more than 3.3 volts. The adapter includes a level shifter to safely connect these pins to the Bus Pirate.
- **HSA** sets the SPD and PMIC I2C address. Motherboards accept multiple DDR5 modules, so each module needs a unique I2C address. A pull-down resistor connected to the HSA pin sets the last four bits of the base I2C address (0x50). When HSA is connected to ground the module goes into a special *offline service mode* that allows us to change write protected portions of the EEPROM. 
- **PWR_EN** enables the DDR5 module power supply when connected to 3.3 volts.
- **PWR_GOOD** is an open drain output signal from the PMIC. If the power is stable this pin will float, but if the supply is interrupted it will pull low. This might be useful for diagnosing a faulty DDR5 module power supply.
- **BULK_VIN** is the single 5 volt power supply for the SDP hub and PMIC. There are multiple BULK_VIN pins on a DDR5 module, but only one needs to be connected to access the SPD hub. 
- **GND** is the ground pin. There are multiple GND pins on a DDR5 module, but only one needs to be connected to access the SPD hub.

> **Warning:**
> There are multiple **BULK_VIN** and **GND** pins on a DDR5 module, but only one of each needs to be connected to access the SPD hub.

## Warning and Disclaimer

**Use the DDR5 adapter at your own risk.** Don't experiment with expensive high capacity, high speed, overclocker-special DDR5. We picked up cheap 8GB sticks from an e-Waste recycler, and we don't care if they get damaged.

> **Danger:**
> THE SOFTWARE, HARDWARE, AND TUTORIAL ARE PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
> IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
> FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
> AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
> LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
> OUT OF OR IN CONNECTION WITH THE SOFTWARE, HARDWARE, AND TUTORIAL OR THE USE OR OTHER DEALINGS IN THE
> SOFTWARE, HARDWARE, AND TUTORIAL.

## Resources

- [Schematic and PCB]()
- [Development thread]()

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
