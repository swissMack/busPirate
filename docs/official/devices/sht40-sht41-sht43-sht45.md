# SHT40, SHT41, SHT43 and SHT45 Humidity & Temperature I2C

![](official/images/sht40-sht41-sht43-sht45/sht4x.jpg)

[SHT4x series](https://sensirion.com/media/documents/33FD6951/67EB9032/HT_DS_Datasheet_SHT4x_5.pdf) sensors are the latest generation of temperature and humidity sensors from Sensirion. Accuracy has improved slightly since [SHT3x](official/devices/sht30-sht31-sht35.md), but the main upgrades are faster measurements, smaller size, lower power and standardized calibration. The SHT4x series includes the SHT40, SHT41, SHT43, and SHT45 sensors.

[Get Bus Pirate & Accessories](https://buspirate.com/get)

## Connections

![alt text](official/images/sht40-sht41-sht43-sht45/image-3.png)

|Bus Pirate|SHT4x|Description|
|-|-|-|
|SDA|SDA|I2C Data|
|SCL|SCL|I2C Clock|
|Vout/Vref|VDD|3.3volt power supply|
|GND|GND|Ground|

These sensors are tiny and it's highly likely you're using a breakout board, like us. The important connections are the I2C data (SDA) and clock (SCL) lines, the power supply (Vout/Vref), and ground (GND).

Image source: [Sensirion SHT4x Datasheet](https://sensirion.com/media/documents/33FD6951/67EB9032/HT_DS_Datasheet_SHT4x_5.pdf).

## See it in action

[▶ Watch this as a recording on docs.buspirate.com](https://docs.buspirate.com/docs/devices/sht40-sht41-sht43-sht45/)

## Setup

```text
HiZ> m i2c

Mode: I2C
I2C speed
 1kHz to 1000kHz
 x. Exit
kHz (400kHz*) > 400
Clock stretching
 1. OFF*
 2. ON
 x. Exit
OFF (1) > 1
I2C>
```

SHT4x series sensors have an I2C interface, put the Bus Pirate in I2C mode.

- ```m i2c``` - set the Bus Pirate to I2C [mode](official/command-reference.md#m-set-bus-mode), or just hit ```m``` to select from the menu.
- ```400``` - set the I2C bus speed to 400kHz.
- ```1``` - disable clock stretching.

> **Warning:**
> Unlike the previous SHT2x and SHT3x series, the SHT4x series does not support clock stretching.

### Power supply
![alt text](official/images/sht40-sht41-sht43-sht45/image.png)

SHT4x requires a 1.08 to 3.6 volt power supply. 

> **Danger:**
> Previous SHT2x and SHT3x sensors would accept up to five volts, so take note that **the SHT4x series is not 5 volt tolerant**.

```text
I2C> W 3.3
3.30V requested, closest value: 3.30V
300.0mA requested, closest value: 300.0mA

Power supply:Enabled
Vreg output: 3.3V, Vref/Vout pin: 3.3V, Current: 3.6mA

I2C>
```

Let’s set the Bus Pirate to power the chip at 3.3 volts, a very common voltage for current generation I2C devices.
- ```W 3.3``` - enable the [onboard power supply](official/command-reference.md#ww-power-supply-offon) at 3.3 volts.

### Pull-up resistors

```text
I2C> P
Pull-up resistors: Enabled (10K ohms @ 3.3V)

I2C>
```

I2C is an open collector output bus, the Bus Pirate and the SHT4x can only pull the line low to 0 (ground). A pull-up resistor is needed to pull the line high to 1 (3.3 volts). The Bus Pirate has built-in pull-up resistors that can be enabled with the ```P``` command.
- ```P``` - Enable the [onboard pull-up resistors](official/command-reference.md#pp-pull-up-resistors).

> **Warning:**
>
> Be sure to enable the pull-up resistors. Without them, the clock data line will never go high and you'll read only 0s.

## I2C address scan

```text
I2C> scan
I2C address search:
0x00 (0x00 W)
0x44 (0x88 W)

Found 2 addresses, 0 W/R pairs.

I2C>
```

We need the correct I2C address to talk to the sensor. We could look in the datasheet, or we can run the handy [I2C address scanner](official/command-reference.md#scan-i2c-address-search).
- ```scan``` - Scan the I2C bus for devices

The scanner found an I2C device at address 0x44 (0x88 write). SHT4x doesn't reply to the corresponding I2C read address (0x89), probably because there isn't any data to read yet. 0x00 is usually a "general call" address which addresses all devices sharing the bus, we'll ignore that for now.

> **Note:**
>
> If the scanner doesn't find the device, ensure the power supply is enabled ```W 3.3``` and the pull-up resistors are enabled ```P```.

## Measure temperature and humidity

| Repeatability | Command Byte|Time Max. (ms)|Repeatability (C) |
|---------------|------|--------------|---------------|
|  High          |  0xFD |8.3ms|0.04C|
|  Medium        |  0xF6 |4.5ms|0.07C|
|  Low           |  0xE0 |1.6ms|0.1C|

Measurements have three repeatability settings: high, medium, and low. The higher the repeatability, the more accurate the measurement, but it takes longer to complete. 

If you're not in a hurry we'll use the **high repeatability command (0xfd)**, which takes maximum 8.3ms to complete. Got some place to be? The low repeatability command will have you out the door 6.3ms sooner!

![alt text](official/images/sht40-sht41-sht43-sht45/image-5.png)

> **Note:**
> The result of each command is: 2 bytes of temperature data, 1 byte of temperature checksum, 2 bytes of humidity data, and 1 byte of humidity checksum. The checksums can be used to verify the integrity of the data, but we'll skip that for now.

### Trigger measurement

Triggering a humidity measurement follows the typical I2C transaction pattern: write the command to the write address, then read the result from the read address. The only trick is that we need to add the [correct delay](official/devices/sht40-sht41-sht43-sht45.md#measure-temperature-and-humidity) before reading the result. If we try to read before the measurement is complete, the SHT4x will not acknowledge (NACK) its read address.

![alt text](official/images/sht40-sht41-sht43-sht45/image-2.png)

Let's break down this diagram from the datasheet into three steps: start the measurement, delay, and read the result.

**Start the measurement**:
1. **S** - Begin with an [I2C START bit](official/command-reference.md#i2c-protocol-overview)
2. **I2C Address + W** - Send the SHT4x write address (0x88)
3. **Command MSB/LSB** - Send the command byte for the desired repeatability
4. **P** - End with an I2C STOP bit

**Delay**. While the measurement is in progress the SHT4x will ignore its I2C read address. We need to wait the maximum measurement time before reading the result. For high repeatability measurements the maximum delay is 8.3ms.

**Read the result**:
1. **S** - Begin with an I2C START bit
5. **I2C Address + R, ACK** - Send the SHT4x read address (0x81)
6. **Temperature MSB/LSB + CRC** - Read the two byte temperature measurement and checksum byte.
7. **Humidity MSB/LSB + CRC** - Read the two byte humidity measurement and checksum byte.
7. **P** - End with an I2C STOP bit

> **Warning:**
> The datasheet diagram only shows the first two bytes of the temperature measurement and the CRC byte. We'll read another three bytes to get the humidity measurement and CRC byte as well.

```text
I2C> [ 0x88 0xfd] D:9 [0x89 r:6]

I2C START
TX: 0x88 ACK 0xFD ACK
I2C STOP
Delay: 9ms
I2C START
TX: 0x89 ACK
RX: 0x66 ACK 0x0F ACK 0xA0 ACK 0x91 ACK 0xA3 ACK 0x97 NACK
I2C STOP
I2C>
```

Finally! Let's make some data! Send the high repeatability measurement command (0xfd), wait at least 8.3ms, then read the result.

- ```[``` - I2C START bit
- ```0x88``` - SHT4x write address
- ```0xfd``` - High repeatability measurement command
- ```]``` - I2C STOP bit, ends this transaction
- ```D:9``` - [Delay](official/command-reference.md#dd-delay-1usms) for >8.3ms while the measurement is in progress
- ```[``` - I2C START bit, begins the read transaction
- ```0x89``` - SHT4x read address
- ```r:6``` - Read six bytes of data
- ```]``` - I2C STOP bit, ends the read transaction

The six byte measurement result is: 0x66 0x0F 0xA0 0x91 0xA3 0x97

> **Note:**
> 8.3ms is the [maximum time](official/devices/sht40-sht41-sht43-sht45.md#measure-temperature-and-humidity) it takes to complete a high repeatability measurement. During this delay we could trigger other sensors or do other tasks, then come back to read the result.

![alt text](official/images/sht30-sht31-sht35/image-4.png)

- Result: ```0x66 0x0F 0xA0 0x91 0xA3 0x97```

This diagram from the older [SHT3x datasheet](https://sensirion.com/media/documents/213E6A3B/63A5A569/Datasheet_SHT3x_DIS.pdf) is a better summary of the 6 byte result than anything in the SHT4x datasheet. The first two bytes are the temperature measurement (0x66 0x0F) plus a CRC error checking byte (0xA0). The next two bytes are the humidity measurement (0x91 0xA3) and another CRC byte (0x97).

> **Note:**
> The CRC bytes can be used to verify the integrity of the data, but we'll skip that. See the datasheet for details on how to calculate the CRC.

### Convert to temperature

```text
I2C> = 0x660f
 =0x660F.16 =26127.16 =0b0110011000001111.16
I2C>
```

Convert the HEX bytes into a decimal number with the ```=``` convert base command: 0x660f is 26127 in decimal. Now we can calculate the temperature in Celsius using a formula from the datasheet:

$$\text{Temp C} = -45 + 175 \times \left(\frac{\text{St}}{2^{16}-1}\right)$$
$$\text{Temp C} = -45 + 175 \times \left(\frac{\text{26127}}{2^{16}-1}\right)$$
$$\text{Temp C} = -45 + 175 \times \left(\frac{26127}{65535}\right)$$
$$ \text{Temp C} = -45 + 175 \times 0.3986$$
$$\text{Temp C} = -45 + 69.7677$$
$$\text{Temp C} = 24.8$$

Today in the lab we're experiencing a summer heat wave and the temperature is already 24.8C at 10am.

### Convert to humidity

```text
I2C> = 0x91a3
 =0x91A3.16 =37283.16 =0b1001000110100011.16
I2C>
```

Convert the humidity HEX bytes into a decimal number with the ```=``` convert base command: 0x91a3 is 37283 in decimal. Finally, convert the reading to relative humidity using a formula from the datasheet:

$$\text{RH\\%} = -6 + 125 \times \left(\frac{\text{Srh}}{2^{16}-1}\right)$$
$$\text{RH\\%} = -6 + 125 \times \left(\frac{\text{37283}}{2^{16}-1}\right)$$
$$\text{RH\\%} = -6 + 125 \times \left(\frac{37283}{65535}\right)$$
$$\text{RH\\%} = -6 + 125 \times 0.5689$$
$$\text{RH\\%} = -6 + 71.1128$$
$$\text{RH\\%} = 65$$

Almost 25 degrees at 10am, but at least the humidity is a bearable 65%.

## Unique Serial Number
![alt text](official/images/sht40-sht41-sht43-sht45/image-4.png)

Each SHT4x sensor has a unique serial number to aid in calibration tracking. The serial number is read by sending the 0x89 command and reading 6 bytes of data. It follows the format as temperature and humidity data: 2 bytes of serial number, 1 byte of checksum, 2 bytes of serial number, and 1 byte of checksum.

```text
I2C> [0x88 0x89][0x89 r:6]

I2C START
TX: 0x88 ACK 0x89 ACK
I2C STOP
I2C START
TX: 0x89 ACK
RX: 0x13 ACK 0x51 ACK 0x8D ACK 0xD4 ACK 0x4F ACK 0xD5 NACK
I2C STOP
I2C>
```

Access the serial number with the 0x89 command:
- ```[0x88 0x89]``` - Send the serial command (0x89) to the write address.
- ```[ 0x89 r:6 ]``` - Read 6 bytes of data from the read address.

The result is:  0x13 0x51 0x8D 0xD4 0x4F 0xD5

## ```sht4x``` Command

```text
I2C> sht4x
SHT40/41/43/45 Temperature and Humidity Sensor Demo
Temperature: 24.27 °C (0x65 0x56)
Humidity: 70.17 % (0x9C 0x01)

I2C>
```

The ```sht4x``` command automates everything we've covered here. It triggers a measurement with the high repeatability command, waits for the maximum time (8.3ms), then reads the result.

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
