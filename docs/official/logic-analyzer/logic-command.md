# Logic Command

![](official/images/fw/logic-command-nav.png)

The ```logic``` command configures the logic analyzer core, and can display logic capture graphs directly in the terminal. It supports the "follow along" logic analyzer mode that triggers each time you send data to a bus. It eliminates the need setup triggers and arm a second tool for debugging. 

The Bus Pirate can be [used as a logic analyzer in multiple ways](https://docs.buspirate.com/docs/logicanalyzer/). This page documents the ```logic``` command in the terminal.

> **Danger:**
> All Bus Pirate hardware supports the follow along logic analyzer, however only Bus Pirate 6 has a second buffer for the follow along mode. In earlier hardware **all output pins are measured behind the IO buffer**. This means the logic capture may not match the actual output of the IO buffer. **This is not a problem when the Bus Pirate is used as a logic analyzer only and all pins are inputs**.

## Capabilities

- 62.5MSPS (or more if overclocked)
- 131K samples
- 8 channels
- Trigger: single pin, high or low
- Follow along logic analyzer mode
- Base pin can be set to an internal pin for debugging the Bus Pirate itself

## Latest Features and Help

```text
SPI> logic -? h
usage:
logic analyzer usage
logic	[start|stop|hide|show|nav]
	[-i] [-g] [-o oversample] [-f frequency] [-d debug]
start logic analyzer: logic start
stop logic analyzer: logic stop
hide logic analyzer: logic hide
show logic analyzer: logic show
navigate logic analyzer: logic nav
configure logic analyzer: logic -i -o 8 -f 1000000 -d 0
undocumented: set base pin (0=bufdir, 8=bufio, 20=follow along) -b: logic -b 20

logic analyzer control
start	start logic analyzer
stop	stop logic analyzer
hide	hide logic graph
show	show logic graph
nav	navigate logic graph with arrow keys, x to exit
-i	show configuration info
-o	set oversample rate, multiplies the sample frequency
-f	set sample frequency in Hz
-0	set character used for low in graph (ex:_)
-1	set character used for high in graph (ex:*)
-d	set debug level: 0-2
-h	Get additional help

SPI>
```

```logic -h``` will display the help menu with the latest options for the ```logic``` command.

## Start Logic Analyzer
![](official/images/fw/logic-start.png)

```logic start``` configures the logic analyzer core for follow along mode and draws a blank logic graph. Use ```logic stop``` to stop the logic analyzer and release any resources used.

> **Note:**
> The ```logic``` command and the [follow along binmode interface](https://docs.buspirate.com/docs/pulseview-fala/) can be run at the same time. However, the capture buffer is shared with [SUMP logic analyzer mode](https://docs.buspirate.com/docs/pulseview-sump/). SUMP and follow along logic analyzer modes cannot be used at the same time and will result in a memory error warning.

### Show/Hide Logic Graph

![](official/images/fw/logic-hide.png)

If the graph isn't needed, use ```logic hide``` to release it from the toolbar. Use ```logic show``` to draw the graph again showing the current capture buffer.

## Auto Capture Speed
```text
Actual speed: 10kHz
Logic analyzer speed: 80000Hz (8x oversampling)
Use the 'logic' command to change capture settings

Mode: SPI
SPI>
```

When changing protocol modes with the ```m``` command, FALA will automatically set the capture speed to oversample the bus speed by a factor of 8. 

### Change Capture Speed
```text
SPI> logic -o 16
Oversample rate set to: 16

Logic Analyzer settings
 Oversample rate: 16
 Sample frequency: 10000Hz

Note: oversample rate is not 1
Actual sample frequency: 160000Hz (16 * 10000Hz)

SPI>
```

The base capture speed or the oversample rate can can be changed with the ```logic``` command. Changing the oversample rate with the ```-o``` flag is probably easiest as the Bus Pirate will calculate the new sample frequency for you.

## Capture Samples

```text
SPI> [ 0xaa 0x55]

CS Enabled
TX: 0xAA 0x55
CS Disabled

Logic analyzer: 144 samples captured
SPI>
```

Every time you send data to the bus, the logic analyzer will capture samples and the logic graph will update (if visible).

> **Note:**
> Currently the ```logic``` command only supports automatic capture in follow along mode. It does not currently support pin triggers, but it will eventually. Use ```logic -h``` to see the most recent features.

## Navigation

![](official/images/fw/logic-command-nav.png)

If there are too many samples to display at once, use ```logic nav``` to navigate the graph. The arrow keys will move the graph left and right, and ```x``` will exit the navigation mode.

## Logic Analyzer System

![](official/images/fw/logic-system.png)

> **Note:**
> The ```logic``` command and the [follow along binmode interface](https://docs.buspirate.com/docs/pulseview-fala/) can be run at the same time. However, the capture buffer is shared with [SUMP logic analyzer mode](https://docs.buspirate.com/docs/pulseview-sump/). SUMP and follow along logic analyzer modes cannot be used at the same time and will result in a memory error warning.
