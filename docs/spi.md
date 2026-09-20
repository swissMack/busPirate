# SPI

Four wires, one chip selected at a time.

## Wiring

| Probe wire | Seeed colour | Target |
|-----------|--------------|--------|
| CLK | pink | SCK / CLK |
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
