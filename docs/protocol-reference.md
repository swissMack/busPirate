# Binary protocol reference

The tables the driver is built on, with the page each came from. All of these
are from the Dangerous Prototypes wiki (`dangerousprototypes.com/docs/…`,
readable via the Internet Archive).

Binary modes need firmware v2.6 or newer. Enter binary mode by sending `0x00`
repeatedly until the device answers `BBIOx` — up to 25 times; it only replies
once enough nulls have arrived.

## Raw bitbang (`BBIOx`) — page *Bitbang*

| Command | Meaning |
|---------|---------|
| `0000 0000` | reset into bitbang, answers `BBIOx` |
| `0000 0001` | enter SPI, answers `SPIx` |
| `0000 0010` | enter I2C, answers `I2Cx` |
| `0000 0011` | enter UART, answers `ARTx` |
| `0000 0100` | enter 1-Wire, answers `1W0x` |
| `0000 0101` | enter raw wire, answers `RAWx` |
| `0000 0110` | enter OpenOCD JTAG |
| `0000 1111` | reset the Bus Pirate to its terminal |
| `0001 000x` | self-test (**v2go and v3 hardware only**) |
| `0001 0010` | set up PWM on AUX — command plus 5 config bytes |
| `0001 0011` | clear PWM |
| `0001 0100` | take one ADC reading, returns 2 bytes |
| `0001 0101` | continuous ADC readings |
| `0001 0110` | frequency on AUX, returns 4 bytes, MSB first |
| `010x xxxx` | pin directions, `AUX MOSI CLK MISO CS`, 1 = input |
| `1xxx xxxx` | pin states, `POWER PULLUP AUX MOSI CLK MISO CS` |

Both pin commands answer with a byte in the state format showing all pins,
whatever their direction.

PWM registers follow the PIC24F output compare: the first config byte's low
two bits are the prescaler (1, 8, 64, 256), then the duty register and the
period register, each two bytes, high byte first. **PWM stays on after you
leave bitbang mode.**

## I2C (`I2Cx`) — page *I2C (binary)*

| Command | Meaning |
|---------|---------|
| `0000 0000` | exit to bitbang, answers `BBIOx` |
| `0000 0001` | mode version, answers `I2Cx` |
| `0000 0010` | start bit |
| `0000 0011` | stop bit |
| `0000 0100` | read one byte |
| `0000 0110` | send ACK |
| `0000 0111` | send NACK |
| `0000 1000` | write-then-read (**firmware v5.1+**) |
| `0000 1001` | extended AUX (**v4 only**) |
| `0000 1111` | start the bus sniffer |
| `0001 xxxx` | bulk write 1–16 bytes (`0000` = 1 byte) |
| `0100 wxyz` | peripherals: `w` power, `x` pull-ups, `y` AUX, `z` CS |
| `0101 00xy` | pull-up rail (**v4 only**): `x` 5V, `y` 3.3V |
| `0110 00xx` | speed: 0 = 5 kHz, 1 = 50 kHz, 2 = 100 kHz, 3 = 400 kHz |

A bulk write answers `0x01`, then one status byte per written byte: **`0x00`
is ACK and `0x01` is NACK** — the opposite sense to the command ack.

Write-then-read takes the command, a 2-byte write count, a 2-byte read count,
then the bytes to write; it answers `0x01` plus the read bytes, or `0x00` if
the target did not acknowledge or the counts are out of range. It sends one
start, writes the bytes **exactly as given** — including the address byte,
which it does not add for you — reads while ACKing, and NACKs the last byte
before stopping. **There is no repeated start**, so a register read needs the
primitives instead.

Before firmware v4.2 the speed command had only two values: 1 = 50 kHz,
0 = 5 kHz.

The v4 pull-up rail command returns `0x00` and makes no connection if a
voltage is already present on VEXTERN (the VPU pin). Extended AUX takes one
argument byte: `0x00` low, `0x01` high, `0x02` Hi-Z, `0x03` read, `0x10` use
AUX, `0x20` use CS.

## SPI (`SPIx`) — page *SPI (binary)*

| Command | Meaning |
|---------|---------|
| `0000 0000` | exit to bitbang |
| `0000 0001` | mode version |
| `0000 0010` | CS low |
| `0000 0011` | CS high |
| `0000 0100` | write-then-read, CS handled by the firmware |
| `0000 0101` | write-then-read, CS left alone |
| `0001 xxxx` | bulk transfer 1–16 bytes, answers `0x01` then the bytes read |
| `0100 wxyz` | peripherals, as I2C |
| `0110 0xxx` | speed: 30 k, 125 k, 250 k, 1 M, 2 M, 2.6 M, 4 M, 8 M |
| `1000 wxyz` | `w` push-pull, `x` clock idle phase, `y` clock edge, `z` sample time |

## UART (`ARTx`) — page *UART (binary)*

| Command | Meaning |
|---------|---------|
| `0000 0000` | exit to bitbang |
| `0000 0010` | start echoing received bytes |
| `0000 0011` | stop echoing |
| `0000 0111` | set the raw BRG divisor, two bytes follow |
| `0000 1111` | transparent bridge (needs a power cycle to leave) |
| `0001 xxxx` | bulk write 1–16 bytes |
| `0110 xxxx` | baud rate index |
| `100w xxyz` | `w` pin output, `xx` data bits and parity, `y` stop bits, `z` RX polarity |

## 1-Wire (`1W0x`) — page *1-Wire (binary)*

| Command | Meaning |
|---------|---------|
| `0000 0000` | exit to bitbang |
| `0000 0010` | reset pulse |
| `0000 0100` | read one byte |
| `0000 1000` | ROM search, returns 32 slots of 8 bytes |
| `0000 1001` | ALARM search |
| `0001 xxxx` | bulk write 1–16 bytes |

Unused search slots come back as all `FF` and are dropped by the driver.

## Raw wire (`RAWx`) — page *Raw wire (binary)*

Start/stop bits, CS high and low, read byte and read bit, a clock tick, and
direct control of the clock and data lines. Use it for buses that are nearly
SPI or I2C but not quite.
