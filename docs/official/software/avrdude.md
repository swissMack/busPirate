# AVRDUDE Programmer

![](official/images/fw/leonardo-icsp-bp-connected.png)

The Bus Pirate can serve as a programmer and dumper for AVR chips, using the command-line utility AVRDUDE. 

- [AVRDUDE command line programmer](https://github.com/avrdudes/avrdude)
- [AVRDUDESS graphical user interface](https://github.com/ZakKemble/AVRDUDESS)

For those who prefer a graphical user interface, AVRDUDESS offers a user-friendly front-end for AVRDUDE. Both tools together provide a powerful setup for working with AVR chips.

In this demo we'll program the ATmega32U4 chip found on the Arduino Leonardo through the ICSP header. 

> **Warning:**
> Always power the AVR target board externally (e.g., via USB) — it usually works better than powering it only from the Bus Pirate.

## Connections

![](official/images/fw/leonardo-icsp-pinout.png)

|Bus Pirate|Arduino Leonardo|Description|
|-|-|-|
|MISO|ICSP-1|Master In Slave Out|
|VOUT|ICSP-2|Power Supply (5 volts)|
|CLK|ICSP-3|Clock|
|MOSI|ICSP-4|Master Out Slave In|
|CS|ICSP-5(RST/RESET)|Chip Select|
|GND|ICSP-6|Ground|

Connect the Bus Pirate to the ICSP header according to the table above.

> **Note:**
> RESET is connected to the CS pin on the Bus Pirate. The CS pin is used to reset the AVR chip.

## Setup
```text
HiZ> binmode

Select binary mode
 1. SUMP logic analyzer
 2. Binmode test framework
 3. Arduino CH32V003 SWIO
 4. Follow along logic analyzer
 5. Legacy Binary Mode for Flashrom and AVRdude (EXPERIMENTAL)
 x. Exit
 > 5
Binmode selected:
 Legacy Binary Mode for Flashrom and AVRdude (EXPERIMENTAL)
Binmode active. Terminal locked
```

In the Bus Pirate terminal use the ```binmode``` command to select the "Legacy Binary Mode for Flashrom and AVRdude".

> **Warning:**
>
> This mode is experimental, use at your own risk.

```text
Power supply
Volts (0.80V-5.00V)
x to exit (3.30) > 5
5.00V requested, closest value: 5.00V
Set current limit?
y

Maximum current (0mA-500mA)
x to exit (100.00) > 150
150.0mA requested, closest value: 150.0mA

Power supply:Enabled

Vreg output: 4.9V, Vref/Vout pin: 4.9V, Current sense: 9.2mA
```

When entering this mode, it asks for the power supply voltage. Select 5 volts. It also asks for the current limit. 150 mA is a good value for the current limit.

The terminal is locked in this mode. To exit, re-plug the Bus Pirate.

> **Warning:**
>
> Arduino Leonardo runs at 5 volts. Make sure the Bus Pirate power supply is set to 5 volts.

## Dumping Flash memory

### Command Line

```bash
avrdude -c buspirate -P COM5 -p m32u4 -U flash:r:dump.bin:r
```
This command uses avrdude to read the flash memory of the ATmega32U4 and saves it to a file named `dump.bin`.

- The correct COM/serial port is the Bus Pirate binary interface, this **is not the same** as the terminal serial port used to enter binmode.
- For Linux, the serial port usually starts with `/dev/ttyUSB`

```bash
attempting to initiate BusPirate binary mode ...
avrdude: paged flash write enabled
avrdude: AVR device initialized and ready to accept instructions
avrdude: device signature = 0x1e9587 (probably m32u4)

avrdude: processing -U flash:r:dump.bin:r
avrdude: reading flash memory ...
Reading | ################################################## | 100% 42.14 s
avrdude: writing output file dump.bin

avrdude done.  Thank you.
```
### AVRDUDESS

![](official/images/fw/avrdudess.png)

Using AVRDUDESS is easy and straightforward. Just select:

- "The Bus Pirate" as the programmer
- ATmega32U4 as the target (MCU)
- Port COM (the port where the Bus Pirate binmode is connected)
- Baud rate: 115200

Select "Read" and click "Go" button to dump the flash memory.

> **Warning:**
>
> Never select "The Bus Pirate bitbang interface, supports TPI" as the programmer. It will not work.
