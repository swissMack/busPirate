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
| `0000 1001` | extended AUX (**v3, firmware v6.1+**; hangs a v4) |
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
| `0000 0110` | AVR extended commands (null op, version, bulk flash read) |
| `0000 11xx` | sniffer: `01` sniffs everything, `10` only while CS is low |
| `0001 xxxx` | bulk transfer 1–16 bytes, answers `0x01` then the bytes read |
| `0100 wxyz` | peripherals, as I2C |
| `0110 0xxx` | speed: 30 k, 125 k, 250 k, 1 M, 2 M, 2.6 M, 4 M, 8 M |
| `1000 wxyz` | `w` pin output HiZ(0)/3.3V(1), `x` CKP clock idle, `y` CKE clock edge, `z` SMP sample time |

The config bits are not CPOL/CPHA directly. **CKP is CPOL, but CKE is the
inverse of CPHA and does not depend on CPOL.** The documented startup default
is `0010` — CKP 0, CKE 1 — which is SPI mode 0:

| SPI mode | CPOL | CPHA | CKP | CKE |
|----------|------|------|-----|-----|
| 0 | 0 | 0 | 0 | 1 |
| 1 | 0 | 1 | 0 | 0 |
| 2 | 1 | 0 | 1 | 1 |
| 3 | 1 | 1 | 1 | 0 |

The sniffer is implemented in hardware and is good to about 10 MHz. It
answers `0x01`, then traffic flows: `[` and `]` mark CS going low and high,
and `\` escapes a **pair** of bytes, MOSI then MISO (firmware v5.1 and later).
If it cannot keep up, the firmware aborts the sniff and turns the MODE LED
off. Any byte stops it — but *where* the firmware puts its acknowledgement
changed in v5.8, so the safe way back is to drain whatever arrives and then
re-enter bitbang mode, which is unambiguous on every version.

## UART (`ARTx`) — page *UART (binary)*

| Command | Meaning |
|---------|---------|
| `0000 0000` | exit to bitbang |
| `0000 0010` | start echoing received bytes |
| `0000 0011` | stop echoing |
| `0000 0111` | set the raw BRG divisor, two bytes follow (fosc 32 MHz, divider 2, BRGH=1) |
| `0000 1111` | transparent bridge — **only a power cycle leaves it** |
| `0001 xxxx` | bulk write 1–16 bytes |
| `0110 xxxx` | baud rate index |
| `100w xxyz` | `w` pin output HiZ(0)/3.3V(1), `xx` 8/N(0) 8/E(1) 8/O(2) 9/N(3), `y` stop bits 1(0)/2(1), `z` RX idle high(0)/low(1) |

In binary UART mode the receiver is always running; the echo commands only
control whether what it hears is copied to USB. Echo starts *disabled*, so a
configuration reply is never mixed with line traffic. The manual baud command
is documented as answering `0x01` "to each byte", which is ambiguous — this
driver reads one acknowledgement and drains any extra.

## 1-Wire (`1W0x`) — page *1-Wire (binary)*

| Command | Meaning |
|---------|---------|
| `0000 0000` | exit to bitbang |
| `0000 0010` | reset pulse |
| `0000 0100` | read one byte |
| `0000 1000` | ROM search: `01`, then 8 bytes per device, then eight `FF` |
| `0000 1001` | ALARM search |
| `0001 xxxx` | bulk write 1–16 bytes |

The search reply has no fixed length: the eight `FF` bytes end it, so an empty
bus answers `01 ff ff ff ff ff ff ff ff` (measured on a v4, firmware 7.0).

## Raw wire (`RAWx`) — page *Raw wire (binary)*

| Command | Meaning |
|---------|---------|
| `0000 0010` / `0000 0011` | start bit / stop bit |
| `0000 0100` / `0000 0101` | CS low / CS high |
| `0000 0110` | read one byte |
| `0000 0111` | read one bit |
| `0000 1000` | read the data pin without clocking |
| `0000 1001` | one clock pulse |
| `0000 1010` / `0000 1011` | clock low / clock high |
| `0000 1100` / `0000 1101` | data low / data high |
| `0001 xxxx` | bulk write 1–16 bytes |
| `0110 00xx` | speed |
| `1000 wxyz` | `w` push-pull, `x` three-wire, `y` LSB first |

Use it for buses that are nearly SPI or I2C but not quite.

## OpenOCD JTAG (`OCD1`) — bitbang command `0000 0110`

The mode exists, but its command set is documented only in the firmware
source. This driver enters no such mode: point OpenOCD at the Bus Pirate
directly. To poke at JTAG by hand, the reference card maps MOSI to TDI, CLK to
TCK, MISO to TDO and CS to TMS, all of which the raw-wire mode can clock.
