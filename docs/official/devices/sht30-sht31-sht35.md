# SHT30, SHT31 and SHT35 Humidity & Temperature I2C

![](official/images/sht30-sht31-sht35/sht3x.jpg)

[SHT30, SHT31 and SHT35](https://sensirion.com/media/documents/213E6A3B/63A5A569/Datasheet_SHT3x_DIS.pdf) measure temperature (-40 to 125C) and humidity (0-100%). They're a significant upgrade to the previous [SHT2x](official/devices/si7021.md) series, with a wider temperature and humidity range, higher accuracy, and a simpler interface.

| Feature | SHT30           | SHT31                | SHT35                | SHT2x Series         |
|-------------|-------------|----------------------|----------------------|----------------------|
| Range  | -40 to 125°C (0–100% RH)| -40 to 125°C  (0–100% RH) | -40 to 125°C  (0–100% RH)  | -10 to 85°C  (0–80% RH) |
| Accuracy | ±0.2°C  (±2% RH)  | ±0.2°C  (±2% RH) | ±0.15°C (±1.5% RH) | ±0.3°C (±2% RH)                 |
| Accuracy at Extremes   | Good      | Better    | **Best**   | Lower   |
| Interface Complexity   | Single read | Single read | Single read| Two reads |

Join below for a journey through the SHT30, SHT31 and SHT35 sensors, from setup to reading temperature and humidity.

[Get Bus Pirate & Accessories](https://buspirate.com/get)

## Connections

![alt text](official/images/sht30-sht31-sht35/image-3.png)

|Bus Pirate|SHT3x|Description|
|-|-|-|
|SDA|SDA|I2C Data|
|SCL|SCL|I2C Clock|
|Vout/Vref|VDD|3.3volt power supply|
|GND|GND|Ground|

These sensors are tiny and it's highly likely you're using a breakout board, like us. The important connections are the I2C data (SDA) and clock (SCL) lines, the power supply (Vout/Vref), and ground (GND).

> **Warning:**
> The SHT3x address pin should be connected to power or ground, but breakout boards almost always have this pin connected to ground setting the I2C address to 0x44 (0x88 write, 0x89 read).

Image source: [Sensirion SHT3x Datasheet](https://sensirion.com/media/documents/213E6A3B/63A5A569/Datasheet_SHT3x_DIS.pdf).

## See it in action

[▶ Watch this as a recording on docs.buspirate.com](https://docs.buspirate.com/docs/devices/sht30-sht31-sht35/)

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

SHT3x series sensors have an I2C interface, put the Bus Pirate in I2C mode.

- ```m i2c``` - set the Bus Pirate to I2C [mode](official/command-reference.md#m-set-bus-mode), or just hit ```m``` to select from the menu.
- ```400``` - set the I2C bus speed to 400kHz.
- ```1``` - disable clock stretching.

> **Note:**
> The SHT3x supports clock stretching, which is a way for the device to signal that it needs more time to process a command. It adds some complexity though, so we've disabled it for this demo.

### Power supply
![alt text](official/images/sht30-sht31-sht35/image.png)

According to the datasheet the SHT3x has a wide supply range from 2.15 to 5.5 volts.  

```text
I2C> W 3.3
3.30V requested, closest value: 3.30V
300.0mA requested, closest value: 300.0mA

Power supply:Enabled
Vreg output: 3.3V, Vref/Vout pin: 3.3V, Current: 3.2mA

I2C>
```

Let’s set the Bus Pirate to power the chip at 3.3volts, a very common voltage for current generation I2C devices.
- ```W 3.3``` - enable the [onboard power supply](official/command-reference.md#ww-power-supply-offon) at 3.3volts.

### Pull-up resistors

```text
I2C> P
Pull-up resistors: Enabled (10K ohms @ 3.3V)

I2C>
```

I2C is an open collector output bus, the Bus Pirate and the SHT3x can only pull the line low to 0 (ground). A pull-up resistor is needed to pull the line high to 1 (3.3 volts). The Bus Pirate has built-in pull-up resistors that can be enabled with the ```P``` command.
- ```P``` - Enable the [onboard pull-up resistors](official/command-reference.md#pp-pull-up-resistors).

> **Warning:**
>
> Be sure to enable the pull-up resistors. Without them, the clock data line will never go high and you'll read only 0s.

## I2C address scan

```text
I2C> scan
I2C address search:
0x00 (0x00 W)
0x44 (0x88 W) (0x89 R)

Found 3 addresses, 1 W/R pairs.

I2C>
```

We need the correct I2C address to talk to the sensor. We could look in the datasheet, or we can run the handy [I2C address scanner](official/command-reference.md#scan-i2c-address-search).
- ```scan``` - Scan the I2C bus for devices

The scanner found an I2C device at address 0x44 (0x88 write, 0x89 read). 0x00 is usually a "general call" address which addresses all devices sharing the bus, we'll ignore that for now.

> **Note:**
>
> If the scanner doesn't find the device, ensure the power supply is enabled ```W 3.3``` and the pull-up resistors are enabled ```P```.

## Single shot measurement

> **Note:**
> SHT3x can measure temperature and humidity once (**single shot**) or periodically on a timer. We'll use the single shot mode for this demo.

| Repeatability | Clock Stretching | Cmd. MSB  | Cmd. LSB  |Time Max. (ms)|Repeatability (C) |
|---------------|------------------|------|------|--------------|---------------|
|  High          | **disabled**         | 0x24 | 0x00 |16ms|0.04C|
|  Medium        | **disabled**         | 0x24 | 0x0B |6ms|0.08C|
|  Low           | **disabled**         | 0x24 | 0x16 |4ms|0.15C|
|  High          | enabled          | 0x2C | 0x06 |15ms|0.04C|
|  Medium        | enabled          | 0x2C | 0x0D |6ms|0.08C|
| Low           | enabled          | 0x2C | 0x10 |4ms|0.15C|

Measurements have three repeatability settings: high, medium, and low. The higher the repeatability, the more accurate the measurement, but it takes longer to complete.  

There are two sets of single shot measurement commands, one with clock stretching enabled and one without. 
- **Clock stretching enabled** pauses the master (Bus Pirate) by holding the I2C clock line low until the measurement is complete. 
- **Clock stretching disabled** commands, on the other hand, cause the SHT3x to ignore its I2C read address until the measurement is complete.

> **Note:**
> Let's use the **high repeatability clock stretching disabled command (0x24 0x00)** with a 16ms delay. Clock stretching is useful, but it ties up the I2C bus while the measurement is in progress and no other sensors can be read until it completes.

### Trigger measurement

Triggering a humidity measurement follows the typical I2C transaction pattern: write the command to the write address, then read the result from the read address. The only trick is that we need to add the [correct delay](official/devices/sht30-sht31-sht35.md#single-shot-measurement) before reading the result. If we try to read before the measurement is complete, the SHT3x will not acknowledge (NACK) its read address.

![alt text](official/images/sht30-sht31-sht35/image-2.png)

Let's break down this diagram from the datasheet into three steps: start the measurement, poll for completion, and read the result.

Start the measurement:
1. **S** - Begin with an [I2C START bit](official/command-reference.md#i2c-protocol-overview)
2. **I2C Address + W** - Send the SHT3x write address (0x88)
3. **Command MSB/LSB** - Send the two byte measurement command for the desired repeatability
4. **P** - End with an I2C STOP bit

Poll for measurement complete (or just delay according to the table):
1.  **S** - I2C START bit, begins the next transaction
5. **I2C Address +R, NACK** - The SHT3x will not ACK its read address until the measurement is complete, so we need to wait a bit before reading the result
6. **P** - End with an I2C STOP bit

When the chip ACKs its read address the measurement is complete, we can read the result:
1. **S** - Begin with an I2C START bit
5. **I2C Address + R, ACK** - Send the SHT3x read address (0x81)
6. **Temperature MSB/LSB + CRC** - Read the two byte temperature measurement and checksum byte.
7. **Humidity MSB/LSB + CRC** - Read the two byte humidity measurement and checksum byte.
7. **P** - End with an I2C STOP bit

```text
I2C> [0x88 0x24 0x00] D:15 [0x89 r:6]

I2C START
TX: 0x88 ACK 0x24 ACK 0x00 ACK
I2C STOP
Delay: 15ms
I2C START
TX: 0x89 ACK
RX: 0x65 ACK 0x4F ACK 0xB0 ACK 0xBC ACK 0x7E ACK 0x43 NACK
I2C STOP
I2C>
```

We're going to deviate from the datasheet example a bit here. Instead of repeating the read address until the measurement is complete, we'll end the write command with an I2C STOP bit, then wait for a fixed delay of 15ms before reading the result. 

- ```[``` - I2C START bit
- ```0x88``` - SHT3x write address
- ```0x24 0x00``` - High repeatability measurement command with clock stretching disabled
- ```]``` - I2C STOP bit, ends this transaction
- ```D:15``` - [Delay](official/command-reference.md#dd-delay-1usms) for 15ms while the measurement is in progress
- ```[``` - I2C START bit, begins the read transaction
- ```0x89``` - SHT3x read address
- ```r:6``` - Read six bytes of data
- ```]``` - I2C STOP bit, ends the read transaction

The six byte measurement result is: 0x65 0x4F 0xB0 0xBC 0x7E 0x43

> **Note:**
> 15ms is the [maximum time](official/devices/sht30-sht31-sht35.md#single-shot-measurement) it takes to complete a high repeatability measurement. During this delay we could trigger other sensors or do other tasks, then come back to read the result.

![alt text](official/images/sht30-sht31-sht35/image-4.png)

- Result: ```0x65 0x4F 0xB0 0xBC 0x7E 0x43```

The datasheet shows that the first two bytes are the temperature measurement (0x65 0x4F) plus a CRC error checking byte (0xB0). The next two bytes are the humidity measurement (0xBC 0x7E) and another CRC byte (0x43).

> **Note:**
> The CRC bytes can be used to verify the integrity of the data, but we'll skip that. See the datasheet for details on how to calculate the CRC.

### Convert to temperature

```text
I2C> = 0x654f
 =0x654F.16 =25935.16 =0b0110010101001111.16
I2C>
```

Convert the HEX bytes into a decimal number with the ```=``` convert base command: 0x654f is 25935 in decimal. Now we can calculate the temperature in Celsius using a formula from the datasheet:

$$\text{Temp C} = -45 + 175 \times \left(\frac{\text{St}}{2^{16}-1}\right)$$
$$\text{Temp C} = -45 + 175 \times \left(\frac{\text{25935}}{2^{16}-1}\right)$$
$$\text{Temp C} = -45 + 175 \times \left(\frac{25935}{65535}\right)$$
$$\text{Temp C} = -45 + 175 \times 0.3955$$
$$\text{Temp C} = -45 + 69.2$$
$$\text{Temp C} = 24.2$$

Today in the lab we're experiencing a summer heat wave and the temperature is already 24.2C at 10am.

### Convert to humidity

```text
I2C> = 0xbc7e
 =0xBC7E.16 =48254.16 =0b1011110001111110.16
I2C>
```

Convert the humidity HEX bytes into a decimal number with the ```=``` convert base command: 0xbc7e is 48254 in decimal. Finally, convert the reading to relative humidity using a formula from the datasheet:

$$\text{RH\\%} = 100 \times \left(\frac{\text{Srh}}{2^{16}-1}\right)$$
$$\text{RH\\%} = 100 \times \left(\frac{\text{48254}}{2^{16}-1}\right)$$
$$\text{RH\\%} = 100 \times \left(\frac{48254}{65535}\right)$$
$$\text{RH\\%} = 100 \times 0.7352$$
$$\text{RH\\%} = 73.5$$

A balmy 24C with 73.5% relative humidity, hopefully it rains and cools off soon!

## ```sht3x``` Command
```text
I2C> sht3x
SHT30/31/35 Temperature and Humidity Sensor Demo
Temperature: 25.07 °C (0x66 0x81)
Humidity: 78.37 % (0xC8 0xA2)

I2C>
```

The ```sht3x``` command automates everything we just did, from setup to reading the temperature and humidity. It uses the high repeatability measurement command with clock stretching disabled, waits for the measurement to complete, and reads the result.

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
