# Pull-up Resistors and IO

[▶ Watch this as a recording on docs.buspirate.com](https://docs.buspirate.com/docs/tutorial-basics/pullup-resistors/)

Protocols such as I2C and 1-Wire use open collector outputs for two way communication on a single data wire. In this type of protocol there is no 1/high level without a pull-up resistor. The pull-up resistor connects to a voltage that "pulls" the wire high. Devices use their output to ground the wire and pull it low.

The Bus Pirate has 10KΩ onboard pull-up resistors that can be toggled with the ```p``` and ```P``` commands.

# Overview

|Command|Description|
|---|---|
|```p```|Disable pull-up resistors.|
|```P```|Enable pull-up resistors.|
|```a X```|Set pin X to output and low.|
|```A X```|Set pin X to output and high.|
|```@ X```|Set pin X to input.|
|```W```|Enable the power supply, configure voltage and current limit.|

## Enter LED mode

This tutorial uses LED mode configured for the onboard LEDs, see [Blink Some LEDs tutorial](official/tutorial-basics/leds-demo.md). In this mode all the Bus Pirate IO pins are free for experimenting.

> **Note:**
> See the 'Blink Some LEDs' tutorial to enter and configure LED mode.

## Voltage Source

The pull-up resistors are powered by the voltage on the VOUT/VREF pin. This can come from two sources:

- The onboard [programmable power supply unit](official/tutorial-basics/power-supply.md)
- Externally through the VOUT/VREF pin on the Bus Pirate main connector

For this tutorial let's use the onboard power supply.

### Programmable Power Supply Unit

```text
LED-()>  W 5 100
5.00V requested, closest value: 5.00V
100.0mA requested, closest value: 100.0mA

Power supply:Enabled
Vreg output: 5.00V, Vref/Vout pin: 5.00V, Current: 2.3mA

LED-()>
```

Enable the power supply, this will power the pull-up resistors and the IO buffers.

> **Note:**
> Here, we use ```W 5 100``` to quickly enable a 5 volt supply and 100mA current limit fuse.
>
> You can also use the ```W``` command with no options to see the configuration menu.

![](official/images/fw/pullup-statusbar-3.png)

Check the live view statusbar at the bottom of the terminal. 
- The top line indicates the power supply is set at 5 volts with a 100mA current limit. 
- The third line shows that 7.8mA is being consumed on VOUT. Since nothing is connected this represents the IO buffer current, base current of the PPSU, op-amp offset error and noise in the RPi chip analog to digital converter.
- The last line shows that VOUT currently measures 5volts, and other pins measure 0 volts.

### External Power Supply

Hacking a device with its own power supply? You can use that instead. 

- Connect the device power to the Bus Pirate VOUT/VREF pin
- Connect the device ground to the Bus Pirate ground pin.

> **Danger:**
> The Bus Pirate is rated for 5volts DC maximum. Exceeding this limit will damage the Bus Pirate and your computer.

## Enable Pull-up Resistors

```text
LED-()> P
Pull-up resistors: Enabled (10K ohms @ 5.0V)

LED-()>
```

Type uppercase ```P``` followed by ```enter``` to activate the pull-up resistors.

![](official/images/fw/pullup-statusbar-1.png)

In the live view statusbar all pins should be high, close to 5.0 volts.
- The top line now shows that the pull-up resistors are enabled.
- The bottom line shows that IO0 to IO7 all measure 4.9 volts.

> **Note:**
> 4.9volts isn't exactly 5, but that's not a problem.

## Controlling IO Pins

Sometimes it's helpful to toggle or read a pin. The ```a```/```A```/```@``` commands toggle the Bus Pirate pins low, high and input.

### Auxiliary Pins Low

```text
LED-()> a 0
IO0 set to OUTPUT: 0

LED-()> a 1; a 2; a 3;
IO1 set to OUTPUT: 0
IO2 set to OUTPUT: 0
IO3 set to OUTPUT: 0

LED-()>
```

```a 0``` configures IO 0 as output and low. Multiple commands can be chained with the ```;```, ```||``` and ```&&``` operators.

- Type ```a 0; a 1; a 2; a 3``` and press ```enter``` to configure IO0 to IO3 as output and low.

![](official/images/fw/pullup-statusbar-2.png)

Verify that the pins are low in the live view statusbar if active, or use the ```v``` command to view a voltage report.
- The third line shows that IO0 to IO3 are configured as auxiliary-low (AUXL).
- The last line shows that IO0 to IO3 now measure close to ground (0.1volt).

### Auxiliary Pins Input

```text
LED-()> @ 0; @ 1; @ 2; @ 3
IO0 set to INPUT: 1
IO1 set to INPUT: 1
IO2 set to INPUT: 1
IO3 set to INPUT: 1
```

```@ X``` makes the corresponding Bus Pirate pin an input, allowing the pull-up resistors to hold the pin high again.  
- Type ```@ 0; @ 1; @ 2; @ 3``` followed by ```enter```.

> **Note:**
> ```@ X``` also reads the state of the input pin. In this case the Bus Pirate reads '1' because the pull-up resistors are holding the pin high.

![](official/images/fw/pullup-statusbar-1.png)

Verify that all the pins are around 5volts in the live monitor statusbar, or by using the voltage report command ```v```.
- All pins should be pulled high again.

### Disable Pull-ups
```text
LED-()> p
Pull-up resistors: Disabled
LED-()>
```

- Type lowercase ```p``` then hit ```enter``` to disable the pull-up resistors.

![](official/images/fw/pullup-statusbar-4.png)

Verify that all the pins show 0volts in the live monitor statusbar or voltage report.
- All pins should now be at 0volts because the pull-up are disabled.

### Auxiliary Pins High
```text
LED-()> A 0
IO0 set to OUTPUT: 1
LED-()>
```
![](official/images/fw/aux-a.png)

```A X``` sets the corresponding Bus Pirate pin to output and high.
- Type ```A 0``` followed by ```enter``` to set IO0 high.
- The live view statusbar should show that IO0 is now high (AUXH) and measures 5 volts.
