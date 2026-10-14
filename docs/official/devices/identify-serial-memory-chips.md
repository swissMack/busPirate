# Identify Serial EEPROM, Flash and FRAM chips

> **Note:**
> Documentation still in progress. Todo:
> - Photographs of common chip markings

The Bus Pirate ```eeprom``` and ```flash``` commands can read, write, erase, verify and test many common serial memory chips: SPI Flash (25Q), SPI EEPROM (25x, 95x), I2C EEPROM (24x), 1-Wire EEPROM, Microwire EEPROM (93x), SPI FRAM and I2C FRAM.

This page will help you identify the type of serial memory chip you have, the pinout, and the voltage requirements.

## Types of Serial memory supported

|Type|Part Number*|Ex. Part Num.|Example Manufacturers|
|-|-|-|-|
|[SPI Flash](official/devices/identify-serial-memory-chips.md#spi-flash-memory)|25Qnnn|W25Q128|Winbond, Micron, GigaDevice, PUYA|
|[SPI EEPROM](official/devices/identify-serial-memory-chips.md#identifying-spi-eeprom-chips)|25xnnn, 95xnnn|25LC040, AT25040|Microchip, Atmel, STMicroelectronics|
|[I2C EEPROM](official/devices/identify-serial-memory-chips.md#identifying-i2c-eeprom-chips)|24xnnn|24LC20, AT24C02|Microchip, Atmel, STMicroelectronics|   
|[1-Wire EEPROM](official/devices/identify-serial-memory-chips.md#identifying-1-wire-eeprom-chips)|243n|DS2341, GX2341, DS24B33|Dallas/Maxim, GX|
|[Microwire EEPROM](official/devices/identify-serial-memory-chips.md#identifying-microwire-eeprom-chips)|93xnn|AT93C46, 93LC56C|Microchip, Atmel, STMicroelectronics|
|[SPI FRAM](official/devices/identify-serial-memory-chips.md#identifying-spi-fram-chips)|FM25xnnn, MB85Xnnn|FM25CL64B, MB85RS512|Ramxeed (Fujitsu), Infineon, ROHM |
|[I2C FRAM](official/devices/identify-serial-memory-chips.md#identifying-i2c-fram-chips)|FM24xnnn, MB85Xnnn|FM24CL64B, MB85RC64|Ramxeed (Fujitsu), Infineon, ROHM |

*n = device size in Kbits, usually.

## SPI Flash Memory

SPI Flash chips use NOR memory, which is cheap, fast, and small. There are several trade offs though:
- **Size**: 1 Mbit to 512 Mbit (128K - 64M)
- **Read**: Not byte addressable, data must be read in whole pages (usually 256 bytes) at a time.
- **Write**: Not byte addressable, data must be written in whole pages (usually 256 bytes) at a time and page aligned.
- **Erase**: Data must be erased in whole sectors (usually 4K, 8K or 64K) at a time.
- **Cost**: SPI Flash is cheap!
- **Write cycles**: 10,000+
- **Data retention**: 20 years

To update existing data, you must first read all the data in the erase sector, modify it in RAM, erase the whole 4K sector, and then write it back to the flash memory. 

### Identifying SPI Flash chips
A really common SPI Flash chip is the Winbond W25Qnnn series. It will be labeled with the Winbond logo and the part number will start with "W25Q" followed by a three digit number indicating the size in Mbits.

Most recent SPI flash chips have their characteristics stored in JEDEC standard **SFDP** (Serial Flash Discoverable Parameters) format. The ```flash``` command in SPI mode will automatically read the SFDP data and display the chip characteristics, including the manufacturer, size, erase sector size, and other parameters.

If SFDP data isn't available, the ```flash``` command has a database of known chips and can identify them by their JEDEC ID.

> **Note:**
> The [```flash``` command](official/command-reference.md#flash-readwriteerase-common-flash-chips) in SPI mode can probe, read, write, erase, verify and test most SPI flash chips.

#### SPI Flash pinout

![alt text](official/images/identify-serial-memory-chips/image-2.png)

|Pin|Name|Description||Pin|Name|Description|
|---|---|---|---|---|---|---|
|1|CS|SPI Chip Select (active low)||8|VCC|Power supply|
|2|SO|SPI Serial Out (MISO)||7|HOLD|Hold (active low)*|
|3|WP|Write Protect (active low)*||6|SCK|SPI Serial Clock|
|4|GND|Ground||5|SI|SPI Serial In (MOSI)|

<br/>

**Write protect pin**

The write protect pin is optional, and may not be present on all chips. If it is present, it is used to protect the chip from being written to. If the pin is connected to ground, the chip can be written to. If the pin is connected to VCC, the chip is write protected and cannot be written to.

**Hold pin**

The hold pin is also optional, and may not be present on all chips. If it is present, it is used to pause the chip's operation without resetting it. If the pin is connected to ground, the chip will pause its operation until the pin is released.

Image source: [Winbond W25Q128JV datasheet](https://www.winbond.com/hq/support/documentation/downloadV2022.jsp?__locale=en&xmlPath=/support/resources/.content/item/DA00-W25Q128JV.html&level=1)

#### SPI Flash voltage requirements

|Family|Minimum Voltage|Maximum Voltage|
|---|---|---|
|W25Q|2.7V|3.6V|

<br/>

> **Note:**
> Most SPI Flash chips will work at 3.3V, but some newer chips may have a lower maximum voltage. Always check the datasheet for the specific chip you are using if possible.

## EEPROM memory
Unlike Flash (NOR) memory, EEPROM memory is byte-addressable and can be written to one byte at a time. 
- **Size**: 1Kbit to 4 Mbit (128B - 512K)
- **Read**: Byte addressable, can read any byte in the chip.
- **Write**: 1 byte up to the page size (8 to 256 bytes, depending on chip) at a time. Writes must be aligned to the page size.
- **Erase**: No separate erase process is needed, bytes are erased individually before writing.
- **Cost**: EEPROM is generally more expensive than NOR Flash memory.
- **Write cycles**: 1,000,000+
- **Data retention**: 100-200 years

### Identifying SPI EEPROM chips
SPI EEPROM chips are usually labeled with a part number starting with "25" or "95". The "25" series is more common and includes chips like AT25C020, 25LC040, 25AA080, etc. The "95" series is STM's name for their 25x compatible EEPROMs, just substitute the same sized 25x part, e.g. 25LC040 is equivalent to 95LC040.

> **Note:**
> The [```eeprom``` command](official/command-reference.md#eeprom-read-write-erase-verify-test-dump-spi-eeproms) in SPI mode can probe, read, write, erase, verify and test most SPI EEPROM chips.

| Device                      | Density   | Size (bytes)| Page Size (Bytes) |Address Bytes| Block Select Bits |B.S. Offset|
|-----------------------------------|-----------|------------|------|-------------------|----------|-------|
| [25X010](https://ww1.microchip.com/downloads/aemDocuments/documents/MPD/ProductDocuments/DataSheets/25AA010A-25LC010A-1-Kbit-SPI-Bus-Serial-EEPROM-20001832J.pdf)| 1 Kbit    | 128        | 8(AT)/16              | 1  |0|
| [25X020](https://ww1.microchip.com/downloads/aemDocuments/documents/MPD/ProductDocuments/DataSheets/25AA020A-25LC020A-2-Kbit-SPI-Bus-Serial-EEPROM-20001833H.pdf)**| 2 Kbit   | 256 | 8(AT)/16 | 1 |0|
| [25X040](https://ww1.microchip.com/downloads/aemDocuments/documents/MPD/ProductDocuments/DataSheets/25AA040A-25LC040A4-Kbit-SPI-Bus-Serial-EEPROM-20001827J.pdf)** | 4 Kbit    | 512        | 8(AT)/16              | 1         |1|3|
| [25X080](https://ww1.microchip.com/downloads/aemDocuments/documents/MPD/ProductDocuments/DataSheets/8-Kbit-SPI-Bus-Serial-EEPROM-20002151C.pdf) | 8 Kbit    | 1024   | 16/32(AT,STM)   | 2   |0|
|[25X160](https://ww1.microchip.com/downloads/aemDocuments/documents/MPD/ProductDocuments/DataSheets/25AA160CD-25LC160CD-16-Kbit-SPI-Bus-Serial-EEPROM-20002150C.pdf)| 16 Kbit   | 2048        | 16/32(AT,STM)   | 2   |0|
|[25X320](https://ww1.microchip.com/downloads/aemDocuments/documents/MPD/ProductDocuments/DataSheets/25AA320A-25LC320A-32K-SPI-Bus-Serial-EEPROM-20001828H.pdf)**| 32 Kbit   | 4096 | 32   | 2  | 0|
|[25X640](https://ww1.microchip.com/downloads/aemDocuments/documents/MPD/ProductDocuments/DataSheets/25AA640A-25LC640A-64K-SPI-Bus-Serial-EEPROM-20001830G.pdf)**  | 64 Kbit   | 8192        | 32                | 2          |0|
|[25X128](https://ww1.microchip.com/downloads/aemDocuments/documents/MPD/ProductDocuments/DataSheets/25AA128-25LC128-128K-SPI-Bus-Serial-EEPROM-20001831G.pdf)**          | 128 Kbit  | 16384         | 64                | 2             |0|
|[25X256](https://ww1.microchip.com/downloads/aemDocuments/documents/MPD/ProductDocuments/DataSheets/25LCXXXX-8K-256K-SPI-Serial-EEPROM-High-Temp-Family-Data-Sheet-DS20002131.pdf)**| 256 Kbit  | 32768        | 64                | 2          | 0|
|[25X512](https://ww1.microchip.com/downloads/aemDocuments/documents/MPD/ProductDocuments/DataSheets/25LC512-512-Kbit-SPI-Bus-Serial-EEPROM-Data-Sheet-20002065.pdf)** | 512 Kbit  | 65536 | 128 |2| 0 |
| [25XM01](https://ww1.microchip.com/downloads/aemDocuments/documents/OTH/ProductDocuments/DataSheets/AT25M01-SPI-Serial-EEPROM-Data-Sheet-20006226A.pdf), [25X1024](https://ww1.microchip.com/downloads/aemDocuments/documents/MPD/ProductDocuments/DataSheets/25LC1024-1-Mbit-SPI-Bus-Serial-EEPROM-20002064E.pdf)**| 1 Mbit | 131072  |  256 | 3  | 0  |
| [25XM02](https://ww1.microchip.com/downloads/aemDocuments/documents/OTH/ProductDocuments/DataSheets/AT25M02-SPI-Serial-EEPROM-Data-Sheet-20006230A.pdf)| 2 Mbit    |262144 | 256         | 3       |0            |
| [25XM04](https://ww1.microchip.com/downloads/aemDocuments/documents/MPD/ProductDocuments/DataSheets/25CSM04-4-Mbit-SPI-Serial-EEPROM-with-128-Bit-Serial-Number-and-Enhanced-Write-Protection-20005817D.pdf)** | 4 Mbit  |524288| 256/512(STM)  |3       | 0             |

**Tested devices

> **Note:**
> 25x/95x chips have a variety of part numbers, but tend to operate in the same way. Often a manufacturer specific part number indicates a different voltage range or upgraded features. AT25, 25LC, 25AA, 25CS and M95 are all part of same basic 25x family of chips.  

#### SPI EEPROM pinout

![alt text](official/images/identify-serial-memory-chips/image-3.png)

|Pin|Name|Description||Pin|Name|Description|
|---|---|---|---|---|---|---|
|1|CS|SPI Chip Select (active low)||8|VCC|Power supply|
|2|SO|SPI Serial Out (MISO)||7|HOLD|Hold (active low)*|
|3|WP|Write Protect (active low)*||6|SCK|SPI Serial Clock|
|4|GND|Ground||5|SI|SPI Serial In (MOSI)|

<br/>

**Write protect pin**

The write protect pin is optional, and may not be present on all chips. If it is present, it is used to protect the chip from being written to. If the pin is connected to ground, the chip can be written to. If the pin is connected to VCC, the chip is write protected and cannot be written to.

**Hold pin**

The hold pin is also optional, and may not be present on all chips. If it is present, it is used to pause the chip's operation without resetting it. If the pin is connected to ground, the chip will pause its operation until the pin is released.

Image source: [Microchip 25x512 datasheet](https://ww1.microchip.com/downloads/aemDocuments/documents/MPD/ProductDocuments/DataSheets/25LC512-512-Kbit-SPI-Bus-Serial-EEPROM-Data-Sheet-20002065.pdf)

#### SPI EEPROM voltage requirements

|25x/95x Family|Minimum Voltage|Maximum Voltage|
|---|---|---|---|
|AT25|1.8V|5.5V|
|25LC|2.5V|5.5V|
|25AA|1.8V|5.5V|
|25CS|1.7V|5.5V|
|M95|2.5V|5.5V|

> **Note:**
> 3.3 volts is a good voltage to use with most 25x/95x chips, but a few newer chips may have a lower maximum voltage. Always check the datasheet for the specific chip you are using if possible.

### Identifying I2C EEPROM chips
I2C EEPROM chips are usually labeled with a part number starting with "24". The "24" series includes chips like 24LC02, 24AA04, AT2402 etc. The "24" series is the most common I2C EEPROM series.

> **Note:**
> The [```eeprom``` command](official/command-reference.md#eeprom-read-write-erase-verify-test-dump-i2c-eeproms) in I2C mode can probe, read, write, erase, verify and test most I2C EEPROM chips.

|Device|Size|Size (bytes)|Page Size|Address Bytes|Block Select Bits|Block Select Bit Offset|
|---|---|---|---|---|---|---|
|[24x01](https://ww1.microchip.com/downloads/en/devicedoc/21711j.pdf)**|1 Kbit|128|8|1|0||
|[24x02](https://ww1.microchip.com/downloads/en/devicedoc/21709c.pdf)**|2 Kbit|256|8|1|0||
|[24x04](https://ww1.microchip.com/downloads/en/DeviceDoc/21708K.pdf)**|4 Kbit|512|16|1|1|0|
|[24x08](https://ww1.microchip.com/downloads/en/devicedoc/21710k.pdf)**|8 Kbit|1024|16|1|2|0|
|[24x16](https://ww1.microchip.com/downloads/en/DeviceDoc/20002213B.pdf)**|16 Kbit|2048|16|1|3|0|
|[24x32](https://ww1.microchip.com/downloads/en/DeviceDoc/21072G.pdf)**|32 Kbit|4096|32|2|0||
|[24x64](https://ww1.microchip.com/downloads/aemDocuments/documents/MPD/ProductDocuments/DataSheets/24AA64-24FC64-24LC64-64-Kbit-I2C-Serial-EEPROM-DS20001189.pdf)**|64Kbit|8192|32|2|0||
|[24x128](https://ww1.microchip.com/downloads/aemDocuments/documents/MPD/ProductDocuments/DataSheets/24AA128-24LC128-24FC128-128-Kbit-I2C-Serial-EEPROM-DS20001191.pdf)**|128 Kbit|16384|64|2|0||
|[24x256](https://ww1.microchip.com/downloads/aemDocuments/documents/MPD/ProductDocuments/DataSheets/24AA256-24LC256-24FC256-256K-I2C-Serial-EEPROM-DS20001203.pdf)**|256 Kbit|32768|64|2|0||
|[24x512](https://ww1.microchip.com/downloads/aemDocuments/documents/MPD/ProductDocuments/DataSheets/24AA512-24LC512-24FC512-512-Kbit-I2C-Serial-EEPROM-DS20001754.pdf)**|512 Kbit|65536|128|2|0||
|[24x102*5*](https://ww1.microchip.com/downloads/en/devicedoc/21941b.pdf)|1 Mbit|131072|128|2|1|3|
|[24x1026](https://ww1.microchip.com/downloads/aemDocuments/documents/MPD/ProductDocuments/DataSheets/24AA1026-24FC1026-24LC1026-1024-Kbit-I2C-Serial-EEPROM-DS20002270.pdf)|1 Mbit|131072|128|2|1|0|   
|[24xM01](https://ww1.microchip.com/downloads/en/DeviceDoc/AT24CM01-I2C-Compatible-Two-Wire-Serial-EEPROM-Data-Sheet-20006170A.pdf)**|1 Mbit|131072|256|2|1|0|
|[24xM02](https://ww1.microchip.com/downloads/aemDocuments/documents/MPD/ProductDocuments/DataSheets/AT24CM02-2-Mbit-I2C-Serial-EEPROM-DS20006197.pdf)|2 Mbit|262144|256|2|2|0|

**Tested devices

> **Note:**
> 24x chips have a variety of part numbers, but tend to operate in the same way. Often a manufacturer specific part number indicates a different voltage range or upgraded features. AT24C, 24C, 24LC, 24AA, 24FC are all generally part of same basic 24x family of chips. 

#### I2C EEPROM pinout
![alt text](official/images/identify-serial-memory-chips/image-4.png)

|Pin|Name|Description||Pin|Name|Description|
|---|---|---|---|---|---|---|
|1|A0|Address select pin 0*||8|VCC|Power supply|
|2|A1|Address select pin 1*||7|WP|Write protect*|
|3|A2|Address select pin 2*||6|SCL|I2C Clock line|
|4|GND|Ground||5|SDA|I2C Data line|

<br/>

**Address select pins**

These pins are optional, and may not be present on all chips. If they are present, they are used to select the I2C address of the chip. The address is 7 bits, with the last bit being the read/write bit. The address is determined by the state of these pins, e.g. A0=0, A1=0, A2=0 gives 7-bit address 0x50, A0=1, A1=0, A2=0 gives address 0x51, etc.

**Write protect pin**

The write protect pin is also optional, and may not be present on all chips. If it is present, it is used to protect the chip from being written to. If the pin is connected to ground, the chip can be written to. If the pin is connected to VCC, the chip is write protected and cannot be written to.

Image source: [Microchip 24x512 datasheet](https://ww1.microchip.com/downloads/aemDocuments/documents/MPD/ProductDocuments/DataSheets/24AA512-24LC512-24FC512-512-Kbit-I2C-Serial-EEPROM-DS20001754.pdf)

#### I2C EEPROM voltage requirements

|24xx Family|Minimum Voltage|Maximum Voltage|Notes|
|---|---|---|---|
|AT24C|2.7V|5.5V|400kHz max|
|24C|2.7V|5.5V|400kHz max|
|24LC|2.5V|5.5V|400kHz max|
|24AA|1.7V|5.5V|400kHz max|
|24FC|1.8V|5.5V|1MHz max|

> **Note:**
> 3.3 volts is a good voltage to use with most 24x chips, but a few newer chips may have a lower maximum voltage. Always check the datasheet for the specific chip you are using if possible.

### Identifying 1-Wire EEPROM chips
1-Wire EEPROMs are slightly different than SPI and I2C EEPROMs. Writes must be a full page (8 or 32 bytes) at a time, and they have much lower write cycles and data retention than SPI or I2C EEPROMs.
- **Write**: A full page (8 or 32 bytes), write aligned to the page size.
- **Write cycles**: 200,000
- **Data retention**: 10-25 years

1-Wire EEPROM chips are usually labeled with a part number starting with "243". The "243" series includes chips like DS2431, DS2432, GX2341, DS24B33, etc. The "243" series is the only known series of 1-Wire EEPROMs.

> **Note:**
> The [```eeprom``` command](official/command-reference.md#eeprom-read-write-erase-verify-test-dump-1-wire-eeproms) in 1-Wire mode can probe, read, write, erase, verify and test most 1-Wire EEPROM chips.

| Device  | Size| Bytes | Page Size | Addr Bytes | Blk Sel Bits | kHz max |
|---------|-----|--|-----------|------------|--------------|---------|
| [DS2431](https://www.analog.com/media/en/technical-documentation/data-sheets/DS2431.pdf)**  | 1K |128   | 8         | 2          | 0            | 16      |
| [DS24B33](https://www.analog.com/media/en/technical-documentation/data-sheets/ds24b33.pdf)**  | 4K |512   | 32        | 2          | 0          | 16      |

**Tested devices

> **Note:**
> There are only two widely used 1-Wire EEPROM: DS2431+ (1Kbit) and DS24B33 (4Kbit). There is also a clone of the DS2431+ called GX2431.

#### 1-Wire EEPROM voltage requirements

|Family|Minimum Voltage|Maximum Voltage|
|---|---|---|---|
|DS243X|2.8V|5.25V|

<br/>
> **Note:**
> This device family is so small, use 3.3 volts or 5 volts and you should be fine.

### Identifying Microwire EEPROM chips
Microwire EEPROM chips are ancient technology that persists today. Microwire EEPROMs are also byte-addressable and can be written to one byte at a time. They use a funky version of SPI and have a drastically different pinout.

Microwire EEPROM chips are usually labeled with a part number starting with "93". The "93" series includes chips like 93C46A, 93C56B, 93C66C, etc. 

> **Danger:**
> 93x is available with 8 bit or 16 bit addressing.
> - In 8 bit mode the memory appears as an array of 8 bit bytes. Each write operation writes one 8 bit byte.
> - In 16 bit mode the memory appears as an array of 16 bit words. Each write operation writes two 8 bit bytes.
>
> "A" part numbers are 8 bit, "B" part numbers are 16 bit. "C" part numbers can be either, depending on the [state of the ORG pin](official/devices/identify-serial-memory-chips.md#microwire-eeprom-pinout).

> **Note:**
> The [```eeprom``` command](official/command-reference.md#eeprom-read-write-erase-verify-test-dump-spi-eeproms) in SPI mode can probe, read, write, erase, verify and test most Microwire EEPROM chips.

|Device|Size|Bytes|Organization|Dummy bits|Address|Total bits|
|-|-|-|-|-|-|-|
|[93x46A](https://www.st.com/resource/en/datasheet/m93c46-w.pdf)**|1Kbit|128|x8 only|0|7bits|10|
|[93x46B](https://www.st.com/resource/en/datasheet/m93c46-w.pdf)**|1Kbit|128|x16 only|0|6bits|9|
|[93x46C/E](https://www.st.com/resource/en/datasheet/m93c46-w.pdf)**|1Kbit|128|x8 or x16|0|7 or 6bits|10 or 9|
|[93x56A](https://www.st.com/resource/en/datasheet/m93c46-w.pdf)**|2Kbit|256|x8 only|1|8bits|12|
|[93x56B](https://www.st.com/resource/en/datasheet/m93c46-w.pdf)**|2Kbit|256|x16 only|1|7bits|11|
|[93x56C](https://www.st.com/resource/en/datasheet/m93c46-w.pdf)**|2Kbit|256|x8 or x16|1|8 or 7bits|12 or 11|
|[93x66A](https://www.st.com/resource/en/datasheet/m93c46-w.pdf)**|4Kbit|512|x8 only|0|9bits|12|
|[93x66B](https://www.st.com/resource/en/datasheet/m93c46-w.pdf)**|4Kbit|512|x16 only|0|8bits|11|
|[93x66C](https://www.st.com/resource/en/datasheet/m93c46-w.pdf)**|4Kbit|512|x8 or x16|0|10 or 9bits|12 or 11|
|[93x76A](https://www.st.com/resource/en/datasheet/m93c46-w.pdf)|8Kbit|1024|x8 only|1|10bits|14|
|[93x76B](https://www.st.com/resource/en/datasheet/m93c46-w.pdf)|8Kbit|1024|x16 only|1|9bits|13|
|[93x76-/C](https://www.st.com/resource/en/datasheet/m93c46-w.pdf)|8Kbit|1024|x8 or x16|1|10 or 9bits|14 or 13|
|[93x86A](https://www.st.com/resource/en/datasheet/m93c46-w.pdf)**|16Kbit|2048|x8 only|0|11bits|14|
|[93x86B](https://www.st.com/resource/en/datasheet/m93c46-w.pdf)**|16Kbit|2048|x16 only|0|10bits|13|
|[93x86-/C](https://www.st.com/resource/en/datasheet/m93c46-w.pdf)**|16Kbit|2048|x8 or x16|0|11 or 10bits|14 or 13|

**Tested devices

> **Warning:**
> **For "C" devices, x8 or x16 bits is selected by the ORG pin. If ORG is low, the device is x8, if ORG is high, the device is x16.**

#### Microwire EEPROM pinout

![alt text](official/images/identify-serial-memory-chips/image-5.png)

|Pin|Name|Description||Pin|Name|Description|
|---|---|---|---|---|---|---|
|1|CS|SPI Chip Select (active **HIGH**)||8|VCC|Power supply|
|2|CLK|SPI Clock||7|NC|Not Connected|
|3|DI|SPI Data In (MOSI)||6|ORG|Address mode*|
|4|DO|SPI Data Out (MISO)||5|GND|Ground|

<br/>

**Chip Select pin**

The chip select pin is active high, which is different than most SPI devices. 

**ORG pin**

The ORG pin is used to select the addressing mode of the chip. It is only present on "C" part numbers.

- **LOW/GROUND**: 8-bit addressing
- **HIGH/VCC**: 16-bit addressing
> **Note:**
> To determine the addressing mode of a "C" part number, you can measure the ORG pin with a multimeter. If it is connected to ground, the chip is in 8-bit mode. If it is connected to VCC, the chip is in 16-bit mode.

Image source: [Microchip 93xx46 datasheet](https://ww1.microchip.com/downloads/aemDocuments/documents/MPD/ProductDocuments/DataSheets/93AA46A-B-C-93LC46A-B-C-93C46A-B-C-1-Kbit-Microwire-Compatible-Serial-EEPROM-Data-Sheet-DS20001749.pdf)

#### Microwire EEPROM voltage requirements
|Family|Minimum Voltage|Maximum Voltage|
|---|---|---|
|93C|4.5V|5.5V|
|M93C|2.5V|5.5V|
|93LC|2.5V|5.5V|
|93AA|1.8V|5.5V|
|AT93C|2.7V|5.5V|

> **Note:**
> 93x chips are quite old, it is generally safe to use 5 volts with all versions. However, some newer chips may have a lower maximum voltage. Always check the datasheet for the specific chip you are using if possible.

## FRAM Memory
SPI FRAM chips are a type of non-volatile memory that uses ferroelectric RAM technology. They are faster than EEPROM and Flash. FRAM can be written one byte at a time, or continuously without stop. FRAM has a very high write endurance and can be used in applications that require frequent writes.
- **Size**: 1Kbit to 4 Mbit (128B - 512K)
- **Read**: Byte addressable, can read any byte in the chip.
- **Write**: Continuous write, can write any byte in the chip. No concept of pages or sectors.
- **Erase**: No separate erase process is needed, bytes are erased individually before writing.
- **Cost**: FRAM is the most expensive memory in wide spread use, but is becoming more affordable.
- **Write cycles**: 10^15+ (1,000,000 times more than EEPROM)
- **Data retention**: 100+ years

### Identifying SPI FRAM chips
SPI FRAM chips are usually labeled with a part number starting with "FM25" or "MB85". The "FM25" series includes chips like FM25CL64B, FM25L04B, etc. The MB85R*S* series is Infineon's name for their FRAM chips, e.g. MB85RS512.        

> **Note:**
> The [```eprom``` command](official/command-reference.md#eeprom-read-write-erase-verify-test-dump-spi-eeproms) in SPI mode can probe, read, write, erase, verify and test most SPI FRAM chips. Choose a 25x EEPROM device with the same size as the FRAM chip you are using, e.g. if you have a 1Mbit FRAM chip, use 25x1024.

### Identifying I2C FRAM chips
I2C FRAM chips are usually labeled with a part number starting with "FM24" or "MB85". The "FM24" series includes chips like FM24CL64B, FM24L04B, etc. The MB85R*C* series is Infineon's name for their FRAM chips, e.g. MB85RC64.  

> **Note:**
> The [```eprom``` command](official/command-reference.md#eeprom-read-write-erase-verify-test-dump-i2c-eeproms) in I2C mode can probe, read, write, erase, verify and test most I2C FRAM chips. Choose a 24x EEPROM device with the same size as the FRAM chip you are using, e.g. if you have a 32Kbit FRAM chip, use 24x32.

### FRAM voltage requirements
|Family|Minimum Voltage|Maximum Voltage|
|---|---|---|
|FM25|2.7V|3.65|
|FM24|2.7V|3.65|
|MB85|2.7V|3.6V|

> **Note:**
> FRAM chips are new and generally tolerate no more than 3.3V. Always check the datasheet for the specific chip you are using if possible.
