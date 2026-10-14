# SPI

Four wires, one chip selected at a time.

## Wiring

| Probe wire | Seeed colour | Target |
|-----------|--------------|--------|
| CLK | purple | SCK / CLK |
| MOSI | grey | DI / MOSI — Bus Pirate out, chip in |
| MISO | black | DO / MISO — chip out, Bus Pirate in |
| CS | white | CS / SS, active low |
| GND | brown | GND — connect this first |
| +3.3V | red | VCC |

**Serial flash also has WP and HOLD pins. Tie both high**, or the chip may
ignore you completely. This catches people every time.

Most serial flash is 3.3V only. Feeding it 5V will destroy it — and the
Bus Pirate's power switch turns *both* rails on together, so the choice is
made by which wire you connect, not in software.

## Identify first

```python
with bp.spi() as spi:
    spi.configure_peripherals(power=True)
    spi.set_speed(spi.SPEED_1MHZ)
    spi.set_mode(0)
    print(spi.write_then_read(b"\x9f", 3).hex(" "))   # JEDEC ID
```

| Byte | Meaning |
|------|---------|
| 1 | manufacturer — `EF` Winbond, `C2` Macronix, `20` Micron, `BF` SST, `1F` Atmel |
| 2 | memory type |
| 3 | capacity as a power of two — `18` is 2^24 = 16 MB |

**All `00` or all `FF` means MISO is not connected.** It does not mean the
chip is blank.

## Reading

```python
# 0x03 = read, followed by a 24-bit address
page = spi.write_then_read(bytes([0x03, 0x00, 0x00, 0x00]), 256)
```

The dashboard's **Dump flash to a file** does this in 1 KB chunks into
`captures/`, with progress. At 1 MHz expect roughly 100 KB/s, so a 16 MB chip
is a long coffee break — raise the clock if the wiring is short and tidy.

## Writing to flash

Two facts govern everything:

1. **Programming only clears bits.** A write turns 1s into 0s, never back, so
   a region must be erased to `0xFF` first.
2. **Erasing works in blocks**, not bytes — 4 KB sectors typically. Erasing a
   sector wipes all 4 KB of it, including anything outside the range you meant.

So the safe sequence is erase, program, verify. The dashboard's **Write a file
to flash** does exactly that, from a file in `captures/`:

```python
from buspirate.spiflash import SPIFlash

flash = SPIFlash(spi)
flash.erase_write_verify(0x0000, open("captures/flash.bin", "rb").read())
```

Or each step by hand:

```python
flash.erase_range(0x1000, len(data))   # whole sectors
flash.write(0x1000, data)              # split on page boundaries for you
bad = flash.verify(0x1000, data)       # None if it matches
```

A page program may not cross a 256-byte page boundary — the chip wraps back
to the start of the page instead of carrying on, silently corrupting the
write. `write()` splits on page boundaries so you do not have to think about
it; `program_page()` refuses rather than let it happen.

**Dump before you erase.** `flash_dump` writes the whole chip to `captures/`
in a couple of minutes, and it is the only way back.

### When writes appear to do nothing

Almost always the **WP pin is held low**, which write-protects the chip. The
commands are accepted and silently ignored — which is why this library reads
the status register back after enabling writes, and raises rather than
carrying on.

## Sniffing

**Sniff the bus** watches an existing master and chip without driving
anything. Wire CLK, MOSI, MISO and CS in parallel with them and share the
ground. The sniffer is hardware and good to about 10 MHz; if it cannot keep
up the firmware aborts and the MODE LED goes out.

Filtering to "only while CS is low" hides the idle chatter between
transactions, which is usually what you want.

## Clock mode

`set_mode(0..3)` sets polarity and phase together:

| Mode | Clock idles | Data sampled |
|------|-------------|--------------|
| 0 | low | rising edge — **the usual one** |
| 1 | low | falling edge |
| 2 | high | falling edge |
| 3 | high | rising edge |

Nearly all serial flash is mode 0 (and mode 3 works too). If a chip returns
data that looks shifted by a bit, the mode is wrong.

## Speeds

30 kHz, 125 kHz, 250 kHz, 1 MHz, 2 MHz, 2.6 MHz, 4 MHz, 8 MHz. Start at
1 MHz. Above 2 MHz, breadboards and long probe leads start to matter more
than the chip does.

## Chip select

```python
with spi.select():          # CS low for the block, high afterwards
    spi.transfer(b"\x9f")
```

`write_then_read()` handles CS itself unless you pass `assert_cs=False`.

## Bus Pirate 6

CLK is **IO6**, MOSI **IO7**, MISO **IO4** and CS **IO5**. All four SPI
modes work. Reads and writes longer than 512 bytes are split by the app with
CS held low throughout, so a long flash dump is one transaction to the chip.
See [Bus Pirate 6](bus-pirate-6.md), the manual's
[SPI section](official/command-reference.md#spi) and its
[SPI flash chips](official/devices/spi-flash-chips.md) demo.
