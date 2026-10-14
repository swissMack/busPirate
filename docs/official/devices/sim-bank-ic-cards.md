# Mobile SIMs & Bank IC Cards HDUART

![](official/images/demo/sim-adapter.jpg)

Mobile phone SIM cards and most bank IC cards will output some useful information in response to an Answer To Reset command. The Bus Pirate can interact with these cards in [Half-Duplex UART mode](official/command-reference.md#hduart).

> **Note:**
> Mobile phone SIMs and bank IC cards are usually based on "Java Cards" that are specially programmed and have advanced cryptographic features to keep data secure. We're evaluating blank, programmable cards for future tutorials.

[Get Bus Pirate & Accessories](https://buspirate.com/get)

## Connections

![](official/images/demo/ic-card-pinout.png)

Common IC cards usually follow the [ISO 7816-3 standard](https://en.wikipedia.org/wiki/ISO/IEC_7816) and have the same pinout and contact shape. [Image source](https://commons.wikimedia.org/wiki/File:SmartCardPinout.svg).

|Bus Pirate|24C02|Description|
|-|-|-|
|IO0/RXTX|C7 - I/O|Bidirectional half-duplex UART|
|IO1/PWM|C3 - CLK|Continuous clock signal from PWM|
|IO2|C2 - RST|Reset signal|
|Vout|C1 - VCC|3.3volt power supply|
|GND|C5 - GND|Ground|

Connect the Bus Pirate to the SIM as shown in the table above. 

### Smart IC Card and SIM card adapter

![](official/images/fw/sim-iccard-all.jpg)

It's possible to gently solder wires on to each pad of the chip, but SIM and smart card sockets are useful if you don't want to destroy the card.

> **Note:**
> A [smart IC card and SIM card adapter](official/overview/sim-iccard-adapter.md) is available for Bus Pirate 5 with the correct connections already set. The adapter accepts most ISO 7816-3 smart cards and mini/micro/nano SIM cards. 

## See it in action

[▶ Watch this as a recording on docs.buspirate.com](https://docs.buspirate.com/docs/devices/sim-bank-ic-cards/)

## Setup

```text
HiZ> m hduart

Mode: HDUART
UART speed
 1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200 etc
 x. Exit
Baud (115200*) > 9600
Data bits
 5 to 8 bits
 x. Exit
Bits (8*) > 8
Parity
 1. None*
 2. Even
 3. Odd
 x. Exit
Parity (1) > 2
Stop bits
 1. 1*
 2. 2
 x. Exit
Bits (1) > 2
HDUART>
```

Mobile SIM cards and bank IC cards use a [half-duplex UART](official/command-reference.md#hduart) interface, data travels both directions on a single wire. 
- ```m hduart``` - select half-duplex UART with the [mode](official/command-reference.md#m-set-bus-mode), or just ```m``` to list all modes
- ```9600``` - **9600** baud
- ```8``` - **8** data bits
- ```2``` - **Even** parity
- ```2``` - **2** stop bits

> **Note:**
> The SIM card baud rate depends on the clock signal frequency we provide to the card. We'll calculate the required clock frequency for 9600 baud later.

```text
HDUART> W 3.3
3.30V requested, closest value: 3.30V
300.0mA requested, closest value: 300.0mA

Power supply:Enabled
Vreg output: 3.3V, Vref/Vout pin: 3.2V, Current: 3.0mA

HDUART>
```

Most SIM cards will work fine at 3.3volts.
- ```W 3.3``` - Enable the [onboard power supply](official/command-reference.md#ww-power-supply-offon) at 3.3 volts

> **Danger:**
> Most SIM cards will be okay with 3.3 volts, but some cards may use 2.5 or 1.8 volts. If the SIM or card is valuable, consider starting at a lower voltage and check the power requirements coded in the ATR response.

```text
HDUART> P
Pull-up resistors: Enabled (10K ohms @ 3.3V)

HDUART>
```

Half-duplex UART is an open collector output bus. The Bus Pirate and the SIM can only pull the line low to 0 (ground). A pull-up resistor is needed to pull the line high to 1 (5 volts). The Bus Pirate has built-in pull-up resistors that can be enabled with the ```P``` command.
- ```P``` - Enable the [onboard pull-up resistors](official/command-reference.md#pp-pull-up-resistors).

> **Warning:**
>
> Be sure to enable the pull-up resistors. The data line will never go high without them and you'll read only 0s.

## Setup Clock
A continuous clock signal applied to C3/CLK drives the SIM's microcontroller. After processing commands, the SIM responds on the UART asynchronously at a baud rate determined by the clock frequency. 

> baud * 372 = clock frequency

372 clock ticks are needed for each bit at the selected baud rate.

> 9600 baud * 372 = 3.5712MHz

At 9600 baud the clock frequency should be 9600 * 372 =3.5712MHz.

```text
HDUART> G
Generate frequency
Choose available pin:
 1. IO1
 2. IO2
 3. IO3
 4. IO4
 5. IO5
 6. IO6
 7. IO7
 x. Exit
 > 1
Period or frequency (ns, us, ms, Hz, kHz or Mhz) > 3.5712mhz
Frequency: 3.571MHz = 3571200Hz (3.57MHz)
Period: 280ns (280.02ns)

Actual frequency: 3571428Hz (3.57MHz)
Actual period: 280ns (280.00ns)

Duty cycle (%) > 50%
Duty cycle: 50.00% = 140ns (140.00ns)
Actual duty cycle: 148ns (148.24ns)
Divider: 16, Period: 34, Duty: 18

Generate frequency: Enabled on IO1

HDUART>
```

The Bus Pirate PWM can generate a clock frequency on the IO1/CLK pin.
- ```G``` - Start a [frequency generator](official/command-reference.md#gg-frequency-generator) on the IO1/CLK pin
- ```1``` - Select IO1/CLK pin
- ```3.5712mhz``` - Set the output frequency
- ```50%``` - Set the duty cycle

> **Note:**
> Don't forget to type the units (Hz, kHz, MHz) when setting the frequency, and % when setting the duty cycle.

## Answer To Reset

> **Note:**
> SIM and bank IC cards use the asynchronous ATR standard. This is different than the synchronous ATR standard used by the [SLE4442 smart card](official/devices/sle4442.md).

### Open UART

```text
HDUART> [

UART OPEN (ASYNC READ)
HDUART> 0x3b 0
```

First, ensure the UART is open and printing data values as they arrive.
- ```[``` - [open UART](official/command-reference.md#bus-commands-3) for async data

> **Warning:**
> Many SIM cards will respond as soon as they have power and a clock signal, even before the next step. You can see a portion of the ATR response here as soon as we open the UART.

### Send ATR and get response

```text
HDPLXUART> a 2; @ 2
IO2 set to OUTPUT: 0

IO2 set to INPUT: 1

HDPLXUART> 0x3b 0x9f 0x95 0x80 0x1f 0xc7 0x80 0x31 0xe0 0x73 0xfe 0x21 0x13 0x67 0x22 0x28 0x00 0x40 0x01 0x00 0x01 0x91
```

To perform the ATR command, pull the RESET pin low and then release it high with the [auxiliary pin commands](official/command-reference.md#aa-auxiliary-pin-control-lowhighread).
- ```a 2``` - pull the reset pin low
- ```@ 2``` - make the reset pin input, allow the pull-up resistor to hold it high

![](official/images/demo/atr-sim.png)

The ATR reset (marker 0) is followed by the ATR response beginning at marker 1. The clock signal is continuous, at 372 clock cycles to send each bit it becomes sold orange.

>0x3b 0x9f 0x95 0x80 0x1f 0xc7 0x80 0x31 0xe0 0x73 0xfe 0x21 0x13 0x67 0x22 0x28 0x00 0x40 0x01 0x00 0x01 0x91 

The ATR response generally starts with 0x3b.
  
### Decode ATR

Answer To Reset (ATR) is a standard response from a smart card or IC card. It can be decoded with this handy database:
- [Smart Card ATR database](https://smartcard-atr.apdu.fr/parse?ATR=3B9F95801FC78031E073FE2113672228004001000191)

![](official/images/demo/atr-sim-lycamobile.png)

Decoding the ATR gives us several interesting pieces of info about this SIM:
- **TS=0x3B** - Direct Convention, normal SIM ATR response
- **fMax=5MHz** - maximum clock frequency is 5MHz
- **Class=A 5V B 3V C 1.8V** - the card can operate at 5 volts, 3 volts, or 1.8 volts

![](official/images/demo/atr-sim-lycamobile-id.png)

Based on a [database of ATR responses](http://ludovic.rousseau.free.fr/softwares/pcsc-tools/smartcard_list.txt), the website suggests this is a Lyca Mobile SIM from Austria. That's close enough, it's a free Dutch Lyca Mobile SIM from Amsterdam China Town.

## Hong Kong IMC SIM

```text
HDPLXUART> a 2; @ 2
IO2 set to OUTPUT: 0

IO2 set to INPUT: 1

HDPLXUART>0x3b 0x9e 0x96 0x80 0x1f 0xc7 0x80 0x31 0xe0 0x73 0xfe 0x21 0x1b 0x66 0xd0 0x01 0xa1 0xb8 0x10 0x00 0x08
```

![](official/images/demo/atr-hkimg-sim.png)

A cheap 4G travel SIM from IMG in Hong Kong.
- [ATR lookup](https://smartcard-atr.apdu.fr/parse?ATR=3B9E96801FC78031E073FE211B66D001A1B8100008)

## Hong Kong ValueGB SIM

```text
HDPLXUART> a 2; @ 2
IO2 set to OUTPUT: 0

IO2 set to INPUT: 1

HDPLXUART>0x3b 0x9e 0x95 0x80 0x1f 0xc7 0x80 0x31 0xe0 0x73 0xfe 0x21 0x1b 0x66 0xd0 0x02 0x24 0x7b 0x14 0x00 0x4a
```

![](official/images/demo/atr-hkvaluegb-sim.png)

A cheap 4G travel SIM from ValueGB in Hong Kong.
- [ATR lookup](https://smartcard-atr.apdu.fr/parse?ATR=3B9E95801FC78031E073FE211B66D002247B14004A)

## EU Master Card

```text
HDPLXUART> a 2; @ 2
IO2 set to OUTPUT: 0

IO2 set to INPUT: 1

HDPLXUART>0x3b 0x6e 0x00 0x00 0x80 0x31 0x80 0x66 0xb0 0x84 0x0c 0x01 0x6e 0x01 0x83 0x00 0x90 0x00
```

![](official/images/demo/atr-eumc.png)

Bank card chips respond to the same ATR as mobile SIM cards. This is a Master Card from an EU bank.
- [ATR lookup](https://smartcard-atr.apdu.fr/parse?ATR=3B6E000080318066B0840C016E0183009000)

## US Visa Card

```text
HDPLXUART> a 2; @ 2
IO2 set to OUTPUT: 0

IO2 set to INPUT: 1

HDPLXUART>
0x3b 0x6f 0x00 0x00 0x80 0x31 0xe0 0x6b 0x08 0x24 0x05 0x02 0xb5 0x55 0x55 0x55 0x55 0x55 0x55
```

![](official/images/demo/atr-usvisa.png)

A Visa debit card from a US transit system.
- [ATR lookup](https://smartcard-atr.apdu.fr/parse?ATR=3B6F00008031E06B08240502B5555555555555)

## Hong Kong Union Pay Card
```text
HDPLXUART> a 2; @ 2
IO2 set to OUTPUT: 0

IO2 set to INPUT: 1

HDPLXUART>
0x3b 0x6b 0x00 0x00 0x00 0x31 0xc0 0x64 0x08 0x04 0x61 0x76 0x07 0x90 0x00
```

![](official/images/demo/atr-hkunionpay.png)

Hong Kong Union Pay debit card.
- [ATR lookup](https://smartcard-atr.apdu.fr/parse?ATR=3B6B00000031C06408046176079000)

## Blank Java Cards

> **Note:**
> We're secured a few different "blank" and diagnostic Java cards for further tests. You can find something similar on your favorite China export website. Stay tuned.

## Accessing SIM Data 

Information, such as a phone book and recent calls, may be stored on mobile SIMs. It appears to be stored in a basic file system. This [university thesis](https://is.muni.cz/th/324546/fi_b/text.pdf) has a straight forward and thorough explanation.

A utility like [pySim](https://forum.buspirate.com/t/sle4442-smart-card-adapter-kf-011c/204/107?u=ian) can be used with the Bus Pirate to navigate the contents of a mobile SIM.

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
