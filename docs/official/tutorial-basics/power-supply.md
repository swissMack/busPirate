# Programmable Power Supply

[▶ Watch this as a recording on docs.buspirate.com](https://docs.buspirate.com/docs/tutorial-basics/power-supply/)

The Bus Pirate has a 'Programmable Power Supply Unit' (PPSU) that can power devices from the VOUT/VREF pin of the main connector.

- 1-5volts adjustable output, 300mA max
- 0-500mA current sense 
- 0-500mA current limit with digital fuse
- Backflow prevention to protect the PPSU when an external voltage is applied to the VREF/VOUT pin

## Overview

|Command|Description|
|---|---|
|```W```|Enable the power supply, configure voltage and current limit.|
|```w```|Disable the power supply.|
|```v```|Show the power supply voltage report.|

## Enable
```text
I2C> W
Power supply
Volts (0.80V-5.00V)
x to exit (3.30) > 5
Maximum current (0mA-500mA), 0 for none
x to exit (300) > 100
5.00V requested, closest value: 5.00V
100.0mA requested, closest value: 100.0mA

Power supply:Enabled
Vreg output: 5.0V, Vref/Vout pin: 5.0V, Current: 3.0mA

I2C>
```

> **Note:**
> Enter any protocol mode (```m```) to use the power supply. The power supply is always disabled in HiZ safe mode.

Type uppercase ```W``` followed by ```enter``` to enable the power supply. 

- Enter the desired output in volts, for example ```5``` followed by ```enter```.
- Enter the desired current limit in milliamps, for example ```100``` followed by ```enter```.

The Bus Pirate will calculate the closest possible values and enable the PPSU.

> **Note:**
> Press enter to accept the default values of 3.3 volts and 300mA current limit fuse.

### Quick enable

```text
I2C> W 5 100
5.00V requested, closest value: 5.00V
100.0mA requested, closest value: 100.0mA

Power supply:Enabled
Vreg output: 5.0V, Vref/Vout pin: 5.0V, Current: 2.3mA
```

The ```W``` command accepts voltage and current as command line options. ```W 5 100``` is equivalent to the previous example.
- The first parameter specifies the voltage
- The second parameter specifies the current limit (omit for no current limit)

```text
I2C> W 5
5.00V requested, closest value: 5.00V
Current limit:300mA
```

Omit the second parameter for the default 300mA current limit fuse.

## Check voltage and current

![](official/images/fw/psu-statusbar1a.png)

Check the voltage and current in the live view statusbar if active, or show the power supply voltage report using the ```v``` command followed by ```enter```.

- The top line indicates the power supply is set at 5.0 volts with a 100mA current limit. 
- The third line shows that 2.1mA is being consumed on VOUT/VREF. Since nothing is connected this is the power used by the IO pin buffers, current leakage, offset error and noise in the RP chip's analog to digital converter.
- The last line shows that VOUT currently measures 5.0 volts, and all IO pins measure 0 volts.

> **Warning:**
> 300mA is the rated maximum of the PPSU, but we added some headroom in the current limit to account for current spikes.

## Current limit

```text
I2C> W 5 10
5.00V requested, closest value: 5.00V
10.0mA requested, closest value: 10.0mA

Power supply:Enabled
Vreg output: 5.0V, Vref/Vout pin: 5.0V, Current: 2.3mA

I2C>
Error: Current over limit, power supply disabled

I2C>
```

When the programmed current limit is exceeded the PPSU hardware fuse disables the power supply. 
- The terminal colors invert repeatedly.
- An alarm bell sounds
- An error message is shown 
- Command execution is halted. 

Use the ```W``` command to restart the PPSU again, or the ```w``` command to disable.

> **Note:**
> Test the current limit:
> 1. Set the current limit to 10mA
> 2. Connect a wire from the VOUT pin to the GND pin.
>
> The Bus Pirate will disable the power supply when the current exceeds 10mA.

## Disable

```text
I2C>w
Power supply: Disabled
I2C>
```

Lowercase ```w``` disables the PPSU.
