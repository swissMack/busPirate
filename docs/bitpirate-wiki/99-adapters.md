# USB Adapters

![ezgif-7bf3420f770591ec](bitpirate-wiki/images/37c7510f33533e39.png)

## What is a USB adapter?

A USB adapter mode temporarily turns the device into a dedicated USB tool instead of the normal interactive CLI.

In normal mode, the firmware behaves like a multi-protocol terminal. In adapter mode, it reboots into one specific USB-compatible protocol so that existing desktop tools can use the ESP32 as if it were a real hardware adapter.

Typical flow:

1. Open the normal firmware CLI.
2. Select a USB adapter mode.
3. Configure the GPIOs used by this adapter.
4. The configuration is saved as a one-shot boot mode.
5. The device reboots and exposes a dedicated USB CDC interface.
6. Use the matching desktop tool on `/dev/ttyACM0`, `/dev/ttyACM1`, etc.
7. Reset the device to return to normal firmware mode.

This makes it possible to reuse mature tools such as `flashrom`, `avrdude`, `OpenOCD`, `sigrok/PulseView`, `LIRC`, or simple serial scripts without adding all of their complexity to the firmware UI.

## Web Serial Tools

Some adapter modes can also be used directly from a web browser through the [ESP32 Bit Pirate Web Tools](https://geo-tp.github.io/ESP32-Bit-Pirate/web-tools/), without installing additional desktop software. It works with ESP32 Bit Pirate and any other compatible devices.

![ESP32 Bit Pirate Web Serial Tools](bitpirate-wiki/images/c24201e650e85f2f.png)

# Available USB adapters

- [USB-UART Bridge](#usb-uart-adapter)
- [Flashrom SPI Programmer](#flashrom-spi-adapter)
- [AVRDUDE Bus Pirate SPI Programmer](#avrdude-bus-pirate-spi-adapter)
- [SUMP logic analyzer](#sump-logic-analyzer)
- [OpenOCD Bus Pirate adapter](#openocd-bus-pirate-adapter)
- [USB IR Toy / LIRC adapter](#usb-ir-toy--lirc-adapter)
- [SubGHz Raw CDC CC1101 adapter](#subghz-raw-cdc-cc1101-adapter)
- [BPIO2 GPIO/I2C/SPI adapter](#bpio2-gpio--i2c--spi-adapter)
- [ESP SDR adapter](#esp-sdr-adapter)

## USB-UART adapter

### Description

The USB-UART adapter exposes one USB CDC serial port and bridges it to two ESP32 GPIOs used as UART RX and TX.

The adapter RX pin is an ESP32 input and must be connected to the target TX pin.  
The adapter TX pin is an ESP32 output and must be connected to the target RX pin.

### What it is useful for

- Reading boot logs from microcontrollers.
- Accessing a serial console.
- Talking to AT-command modules.
- Debugging UART devices.
- Using the ESP32 as a simple USB-to-serial dongle.
- Flashing some targets when their boot/reset sequence is handled manually.

### Compatible tools

- `screen`
- `picocom`
- `minicom`
- `pyserial`
- `esptool.py` in some cases, if the target is already in bootloader mode or reset/boot is handled externally
- Any program able to open a serial port
- [Web Serial Terminal](https://geo-tp.github.io/ESP32-Bit-Pirate/web-tools/web-serial-terminal/)

### Wiring

| Adapter pin | Target pin |
|---|---|
| Adapter RX GPIO | Target TX |
| Adapter TX GPIO | Target RX |
| GND | GND |

### Examples

```bash
picocom -b 115200 /dev/ttyACM0
```

```bash
screen /dev/ttyACM0 115200
```

```bash
python3 -m serial.tools.miniterm /dev/ttyACM0 115200
```

---

## Flashrom SPI adapter

### Description

The Flashrom SPI adapter exposes a `serprog`-compatible SPI programmer over USB CDC. It allows `flashrom` to communicate with SPI flash chips through the ESP32 GPIOs.

This mode is mainly designed for external SPI NOR flash chips.

### What it is useful for

- Reading SPI flash chips.
- Writing SPI flash chips.
- Verifying firmware images.
- Dumping BIOS/UEFI flash memories.
- Testing unknown SPI flash chips.
- Recovering devices when the flash can be accessed externally.

### Compatible tools

- `flashrom`
- Scripts that can speak the `serprog` protocol
- [Web SPI Flash Programmer](https://geo-tp.github.io/ESP32-Bit-Pirate/web-tools/spi-flash-programmer/)

### Wiring

| Adapter pin | Flash chip pin |
|---|---|
| CS GPIO | CS# |
| SCK GPIO | CLK |
| MISO GPIO | DO / IO1 |
| MOSI GPIO | DI / IO0 |
| GND | GND |

Additional notes:

- Connect `WP#` and `HOLD#` high if the chip requires it.
- Power the chip correctly before starting `flashrom`.
- In-circuit flashing may fail if the rest of the board drives the SPI bus.

### Examples

Read a flash chip:

```bash
flashrom -p serprog:dev=/dev/ttyACM0:921600,spispeed=4M -r dump.bin
```

Probe with verbose output:

```bash
flashrom -p serprog:dev=/dev/ttyACM0:921600,spispeed=4M -V
```

Write and verify an image:

```bash
flashrom -p serprog:dev=/dev/ttyACM0:921600,spispeed=4M -w firmware.bin
```

---

## AVRDUDE Bus Pirate SPI adapter

### Description

The AVRDUDE adapter exposes the legacy Bus Pirate binary SPI protocol expected by `avrdude -c buspirate`.

It is intended for AVR ISP programming over SPI. The CS pin is used as the AVR RESET line.

### What it is useful for

- Programming ATmega/ATtiny chips through ISP.
- Reading AVR flash.
- Writing AVR flash.
- Reading or writing fuses.
- Recovering Arduino-compatible boards through the ISP header.

### Compatible tools

- `avrdude`
- `avrdudess`
- [Web AVR Programmer](https://geo-tp.github.io/ESP32-Bit-Pirate/web-tools/avr-programmer/)

### Wiring

| Adapter pin | AVR target pin |
|---|---|
| RESET / CS GPIO | RESET |
| SCK GPIO | SCK |
| MISO GPIO | MISO |
| MOSI GPIO | MOSI |
| GND | GND |

Additional notes:

- Use a safe SPI speed first, especially with low-clocked AVR chips.

### Examples

![avrdudess](bitpirate-wiki/images/41c4b09026813750.png)



Probe an ATmega328P:

```bash
avrdude -c buspirate -P /dev/ttyACM0 -p m328p -v -x spifreq=1
```

Read flash:

```bash
avrdude -c buspirate -P /dev/ttyACM0 -p m328p -U flash:r:dump.hex:i -x spifreq=1
```

Write flash:

```bash
avrdude -c buspirate -P /dev/ttyACM0 -p m328p -U flash:w:firmware.hex:i -x spifreq=1
```

Read fuses:

```bash
avrdude -c buspirate -P /dev/ttyACM0 -p m328p -U lfuse:r:-:h -U hfuse:r:-:h -U efuse:r:-:h
```

---

## SUMP logic analyzer

### Description

The SUMP logic analyzer adapter exposes a SUMP/Open Bench Logic Sniffer-compatible device over USB CDC.

The selected GPIOs are mapped to logic analyzer channels `D0` to `D7`. The sampling rate and capture size are configured by the host tool.

### What it is useful for

- Capturing digital signals.
- Debugging SPI, I2C, UART, 1-Wire, IR, or custom protocols.
- Checking timing issues.
- Verifying bit-banged protocol implementations.
- Exporting captures to `.sr`, `.vcd`, or other formats.

### Compatible tools

- PulseView
- `sigrok-cli`
- Tools compatible with SUMP or Open Bench Logic Sniffer devices
- [Web Logic Analyzer](https://geo-tp.github.io/ESP32-Bit-Pirate/web-tools/logic-analyzer/)


### Wiring

| Adapter channel | Target signal |
|---|---|
| D0 | First selected GPIO signal |
| D1 | Second selected GPIO signal |
| D2 | Third selected GPIO signal |
| ... | ... |
| D7 | Eighth selected GPIO signal |
| GND | GND |

### Examples

Open PulseView:

![image](bitpirate-wiki/images/deecef878f8a1ea4.png)

In PulseView, select a SUMP/Open Bench Logic Sniffer compatible driver and use the serial port exposed by the device, for example `/dev/ttyACM0`.

Capture with `sigrok-cli`:

```bash
sigrok-cli --driver=ols:conn=/dev/ttyACM0 --config samplerate=1m --samples 100000 -o capture.sr
```

Export to VCD:

```bash
sigrok-cli --driver=ols:conn=/dev/ttyACM0 --config samplerate=1m --samples 100000 -O vcd -o capture.vcd
```

---

## OpenOCD Bus Pirate adapter

### Description

The OpenOCD adapter exposes a Bus Pirate-compatible transport for JTAG and SWD through USB CDC.

OpenOCD connects to the adapter through the serial port and selects the transport at runtime. JTAG uses `TCK`, `TMS`, `TDI`, and `TDO`. SWD uses `SWCLK` and `SWDIO`.

### What it is useful for

- Debugging ARM microcontrollers over SWD.
- Debugging JTAG targets.
- Reading target IDs.
- Flashing supported MCUs.
- Using `gdb` through OpenOCD.
- Basic hardware bring-up and recovery.

### Compatible tools

- `openocd`
- `gdb`
- IDEs that use OpenOCD internally

### Wiring

JTAG wiring:

| Adapter pin | Target pin |
|---|---|
| TCK GPIO | TCK |
| TMS GPIO | TMS |
| TDI GPIO | TDI |
| TDO GPIO | TDO |
| GND | GND |

SWD wiring:

| Adapter pin | Target pin |
|---|---|
| SWCLK GPIO | SWCLK |
| SWDIO GPIO | SWDIO |
| GND | GND |

Additional notes:

- Connect target reset if your setup or OpenOCD target config needs it.
- Bus Pirate-compatible transports are usually not as fast as dedicated JTAG/SWD probes.
- This mode is better for debug, probing, recovery, and experimentation than for high-speed production flashing.

### Examples

SWD target example:

```bash
openocd -f interface/buspirate.cfg -c "buspirate port /dev/ttyACM0; transport select swd" -f target/stm32f1x.cfg
```

JTAG target example:

```bash
openocd -f interface/buspirate.cfg -c "buspirate port /dev/ttyACM0; transport select jtag" -f target/stm32f1x.cfg
```

---

## USB IR Toy / LIRC adapter

### Description

The USB IR Toy adapter exposes IR TX/RX through a USB CDC interface compatible with tools that support the USB IR Toy / LIRC `irtoy` driver.

It can be used to receive, inspect, and transmit infrared remote-control signals.

### What it is useful for

- Capturing IR remote signals.
- Visualizing raw IR timings.
- Creating LIRC remote configuration files.
- Sending IR commands.
- Testing IR LEDs and receivers.
- Debugging TV, projector, amplifier, air conditioner, or media remote protocols.

### Compatible tools

- `mode2`
- `xmode2`
- `irrecord`
- `irsend`
- `lircd`
- Other LIRC-compatible tools

### Wiring

| Adapter pin | IR component |
|---|---|
| IR TX GPIO | IR LED driver input |
| IR RX GPIO | IR receiver output |
| GND | GND |

Additional notes:

- For IR TX, use a proper transistor/MOSFET driver if the IR LED needs more current than a GPIO can provide.
- For IR RX, use a demodulated IR receiver module when working with common remote-control protocols.
- Make sure the receiver frequency matches the target protocol, usually around 38 kHz for many remotes.

### Examples

Read raw IR pulses:

```bash
mode2 --driver=irtoy --device=/dev/ttyACM0
```

Visualize IR pulses:

```bash
xmode2 --driver=irtoy --device=/dev/ttyACM0
```

Record a remote:

```bash
irrecord -H irtoy -d /dev/ttyACM0 remote.conf
```

---

## SubGHz Raw CDC CC1101 adapter

### Description

The SubGHz Raw CDC adapter is not really meant to emulate an existing desktop tool or a well-known adapter protocol.

It exposes the CC1101 radio module over USB CDC with a small, firmware-specific ASCII protocol. The host sees a serial port, and a terminal or script can use text commands to tune the radio, start or stop raw reception, measure RSSI, and transmit raw OOK timings.

In other words, this mode is mainly a **USB control interface for the CC1101**, useful when you want to drive the radio from Python, shell scripts, or quick terminal experiments without using the normal interactive firmware UI.

### What it is useful for

- Controlling a CC1101 module from a computer over USB.
- Receiving raw OOK timing frames.
- Transmitting raw mark/space timing sequences.
- Building custom Python tools around the adapter.
- Experimenting with 315 MHz, 433.92 MHz, 868 MHz, or 915 MHz setups depending on the CC1101 module and local regulations.

### Compatible tools

There is no standard desktop tool specifically targeting this protocol yet.

Useful host-side tools are mostly generic serial tools:

- `screen`
- `picocom`
- `minicom`
- Python scripts using `pyserial`
- Custom serial tools
- Firmware-specific test scripts

### Serial protocol

The protocol is line-oriented ASCII over USB CDC.

Commands are sent as printable text followed by `\n` or `\r\n`. Short commands such as `V`, `?`, `R`, `X00`, and `X21` may also be handled immediately by the firmware.

Responses are also ASCII text:

- `OK` means the command was accepted.
- `ERR:<reason>` means the command failed.
- `RAW:<timings>` is an incoming raw RF frame.
- `RSSI:<value>` reports a received signal strength value.
- `V 1.0 ESP32-BitPirate SubGHz Raw CDC` is the version response.

### Commands

| Command | Description | Example |
|---|---|---|
| `V` | Print adapter version. | `V` |
| `?` | Print protocol help. | `?` |
| `F<freq>` | Tune the CC1101 to a frequency in MHz. | `F433.920` |
| `P<freq>` | Apply the raw OOK/sniff preset for a frequency. | `P433.920` |
| `X00` | Disable raw RX reporting. | `X00` |
| `X21` | Enable raw RX reporting. | `X21` |
| `X` | Show current RX reporting state. | `X` |
| `R` | Measure peak RSSI. | `R` |
| `G<timings>` | Transmit raw timings in microseconds. | `G+350,-1050,+350,-350` |

### Raw timing format

Raw RF data is represented as signed durations in microseconds.

Positive values are marks/high levels, and negative values are spaces/low levels after the firmware polarity normalization. A transmitted sequence must contain at least two timings and must contain an even number of entries.

Example TX command:

```text
G+350,-1050,+350,-350
```

The firmware also accepts the same payload with a `RAW:` prefix internally when parsing timings:

```text
GRAW:+350,-1050,+350,-350
```

When RX reporting is enabled with `X21`, received frames are printed like this:

```text
RAW:+350,-1050,+350,-350,+350,-1050
RSSI:-54
```
### Examples

One line script to send a long sequence of random timing for testing TX (replace ttyACM0 and freq if needed):
```bash
PORT=/dev/ttyACM0 FREQ=433.92 python3 -c "import os,random,serial,time,sys; n=2000; p=os.environ.get('PORT','/dev/ttyACM0'); f=os.environ.get('FREQ','433.92'); t=[str(random.randint(100,5000)*(1 if i%2==0 else -1)) for i in range(n)]; cmd='G'+','.join(t)+'\n'; print(f'PORT={p} FREQ={f} CMDlen={len(cmd)} timings={n}'); s=serial.Serial(p,115200,timeout=0.2); time.sleep(0.3); s.reset_input_buffer(); s.write(f'F{f}\n'.encode()); print('Sending...'); t0=time.time(); s.write(cmd.encode()); exec(\"ok=False\\nwhile time.time()-t0<20 and not ok:\\n    b=s.readline()\\n    line=b.decode(errors='ignore').strip() if b else ''\\n    if line: print('RESP:',line)\\n    ok=('OK:TX:' in line or line.startswith('ERR:'))\\n    if not b: time.sleep(0.05)\"); print('RESULT:',('OK' if ok else 'TIMEOUT'),'elapsed=%.2fs'%(time.time()-t0)); s.close(); sys.exit(0 if ok else 1)"
```

One line script to wait and receive timings for testing RX (replace ttyACM0 and freq if needed):

```bash
PORT=/dev/ttyACM0 FREQ=433.92 python3 -c "import os,time,serial; p=os.environ.get('PORT','/dev/ttyACM0'); f=os.environ.get('FREQ','433.92'); s=serial.Serial(p,115200,timeout=0.2); time.sleep(0.3); s.reset_input_buffer(); s.write(f'F{f}\nX21\n'.encode()); print(f'Start listening on {p} @ {f} MHz (Ctrl+C to stop)'); exec('while True:\n b=s.readline()\n if b: print(b.decode(errors=\"ignore\").rstrip())')"
```
---
## BPIO2 GPIO / I2C / SPI adapter

### Description

The BPIO2 adapter exposes eight ESP32 GPIOs over USB CDC using the BPIO2 binary protocol.

It provides a host-controlled interface for direct GPIO access and for I2C and SPI transactions. Unlike the normal interactive CLI, BPIO2 is designed for software and browser tools that need structured, repeatable control of the hardware.

The adapter supports three modes:

- `HiZ` — all eight IOs are available as general-purpose GPIOs.
- `I2C` — IO1 and IO2 are reserved for SCL and SDA.
- `SPI` — IO0 to IO3 are reserved for CS, SCK, MOSI and MISO.

### What it is useful for

- Controlling and monitoring GPIOs from a computer.
- Scanning an I2C bus.
- Reading and writing I2C registers or devices.
- Sending and receiving SPI data.
- Testing SPI peripherals with configurable mode, bit order and clock speed.
- Building repeatable GPIO / I2C / SPI test sequences.
- Automating hardware tests from the browser or Python.
- Using ESP32 Bit Pirate as a generic BPIO2-compatible hardware interface.

### Compatible tools

- [Web BPIO2 GPIO, I2C and SPI Controller](https://geo-tp.github.io/ESP32-Bit-Pirate/web-tools/bpio2/)
- [ESP32 Bit Pirate Python Scripting Lab](https://geo-tp.github.io/ESP32-Bit-Pirate/web-tools/python-lab/)
- Software implementing the BPIO2 protocol

### Wiring

The eight IO pins are selected when enabling the adapter.

Generic GPIO mapping:

| BPIO2 pin | Function |
|---|---|
| IO0 | GPIO / SPI CS |
| IO1 | GPIO / SPI SCK / I2C SCL |
| IO2 | GPIO / SPI MOSI / I2C SDA |
| IO3 | GPIO / SPI MISO |
| IO4 | GPIO |
| IO5 | GPIO |
| IO6 | GPIO |
| IO7 | GPIO |
| GND | Target GND |

SPI mapping:

| BPIO2 pin | SPI signal |
|---|---|
| IO0 | CS |
| IO1 | SCK |
| IO2 | MOSI |
| IO3 | MISO |

I2C mapping:

| BPIO2 pin | I2C signal |
|---|---|
| IO1 | SCL |
| IO2 | SDA |

### Capabilities

#### GPIO

Each available IO can be configured as input (`HiZ`) or output and read or driven HIGH/LOW.

In SPI or I2C mode, pins reserved by the active bus are controlled by the protocol engine while the remaining IOs stay available as auxiliary GPIOs.

#### I2C

The adapter supports configurable I2C clock speeds and combined write/read transactions, including the common register-read pattern.

The Web BPIO2 controller provides:

- I2C bus scanning.
- 7-bit address transactions.
- Write bytes.
- Read bytes.
- Combined register write/read operations.

#### SPI

SPI supports:

- Modes 0, 1, 2 and 3.
- MSB-first or LSB-first transfers.
- Configurable CS idle level.
- Half-duplex and full-duplex transfers.
- Preset or custom clock speeds up to 40 MHz.
- 8-bit transfers.



---

## ESP SDR adapter

### Description

The ESP SDR adapter exposes the ESP32-S3 radio over USB CDC using the firmware-specific `BPRF1` protocol.

It provides low-level I/Q captures for spectrum analysis, waterfall display, wideband scanning, and RF experiments. The ESP32-S3 is fundamentally a 2.4 GHz radio; tuning outside that region is experimental and should not be treated like a calibrated wideband SDR. Antenna quality also has a major impact on what can be observed.

### What it is useful for

- Capturing raw I/Q samples from the ESP32-S3 radio.
- Viewing live spectrum and waterfall data.
- Sweeping a wide frequency range by repeatedly retuning the radio.
- Experimenting with receive bandwidth, sample rate, and RF gain.
- Investigating the ESP32-S3 RF frontend outside its normal Wi-Fi use case.

### Compatible tools

- [Web ESP SDR](https://geo-tp.github.io/ESP32-Bit-Pirate/web-tools/esp-sdr/)
- Custom serial clients or scripts implementing the `BPRF1` protocol

For normal use, the **Web ESP SDR** tool is recommended. It handles the protocol directly and provides the spectrum, waterfall, wideband analyzer, gain controls, and other SDR-specific processing in the browser.

### Serial protocol

`BPRF1` uses simple line-oriented ASCII commands for control and binary `BPRF` frames for high-rate I/Q captures.

Typical commands include:

| Command | Description |
|---|---|
| `INFO` | Show adapter and RF capabilities. |
| `IQ <MHz>` | Capture 256 I/Q samples as text. |
| `FFT <MHz>` | Capture and return a 256-point FFT. |
| `RAW2 <MHz> <samples> [format]` | Capture one binary I/Q block. |
| `STREAM2 <MHz> <samples> [format]` | Continuously capture binary I/Q blocks. |
| `TUNE <MHz>` | Change center frequency while streaming. |
| `STOP` | Stop the active stream. |
| `RATE <80\|40\|16>` | Select the nominal RF sample rate in MS/s. |
| `BANDWIDTH <AUTO\|WIDE\|13..69>` | Configure the receive filter bandwidth. |
| `GAIN HARDWARE` | Restore hardware-controlled gain. |
| `GAIN MANUAL <index>` | Select a manual PHY gain index. |
| `RFSTATE` | Report the current RF state. |
| `REBOOT` | Reboot back into the normal firmware flow. |

Binary captures support `RAW32` and the more compact `IQ10_PACKED` sample format. Frames begin with the `BPRF` magic and include capture metadata such as center frequency, sample rate, sample count, capture time, bandwidth, and sample format.

This adapter builds on the discovery of the undocumented ESP32-S3's internal radio functions:
https://espargos.net/espsdr/
