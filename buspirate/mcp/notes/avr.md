# AVR: programming with avrdude through a Bus Pirate

## Which programmer type

| Board | avrdude `-c` | Interfaces | Port |
|---|---|---|---|
| v3 / v4 | `buspirate` | ISP (binary SPI) | the board's port |
| v3 / v4 | `buspirate_bb` | ISP and **TPI** (bitbang) | the board's port |
| BP6 (BP5) | `buspirate`, after **binmode 5** | ISP | the **binary** port, not the terminal |
| Bit Pirate | `buspirate`, via its USB AVRDUDE adapter | ISP | the adapter's USB port |

Use `buspirate_bb` for TPI parts, or when `buspirate` fails. On a BP6
**never** use the bitbang type ("The Bus Pirate bitbang interface, supports
TPI"): it will not work.

## ISP wiring

| AVR ISP | v3/v4 (Seeed) | BP6 | Note |
|---|---|---|---|
| RESET | CS, white | CS (IO5, brown) | CS drives RESET by default |
| SCK | CLK, purple | CLK (IO6, grey) | |
| MOSI | MOSI, grey | MOSI (IO7, white) | |
| MISO | MISO, black | MISO (IO4, purple) | |
| GND | brown | black | first |
| VCC | +5V orange or +3.3V red, only if the BP powers it | VOUT, red | |
| XTAL1 (optional) | AUX, blue | | clock for a chip with bad clock fuses (`-x cpufreq=`) |

`buspirate_bb` uses the same pins: RESET = CS, SCK = CLK, SDO = MOSI,
SDI = MISO (avrdude.conf). TPI wiring for `buspirate_bb` is not documented
for the Bus Pirate in the sources here (**unverified**).

The official BP6 guide warns: **power the AVR target externally** (for
example its own USB); it usually works better than Bus Pirate power alone.
Share GND.

## avrdude extended options for `-c buspirate` (`-x ...`)

| Option | Meaning |
|---|---|
| `reset=cs`, `aux`, `aux2` | which pin drives RESET (default CS); AUX2 only on the old v1a |
| `spifreq=0..7` | binary SPI speed: 0 = 30 kHz (default), 1 = 125 kHz, 2 = 250 kHz, 3 = 1 MHz, 4 = 2 MHz, 5 = 2.6 MHz, 6 = 4 MHz, 7 = 8 MHz |
| `rawfreq=0..3` | raw-wire mode instead: 5 kHz, 50 kHz, 100 kHz (fw v4.2+), 400 kHz (v4.2+); no paged write |
| `cpufreq=125..4000` | AUX outputs n kHz to feed XTAL1; keep it at least 4x the SPI clock |
| `pullups` | Bus Pirate pull-ups on; VPU must have a voltage |
| `hiz` | open-collector SPI; needs external pull-ups |
| `ascii` | old ASCII protocol; slow, no `reset=`/`spifreq=`/`rawfreq=` |
| `nopagedwrite` / `nopagedread` | disable the fast paged commands |
| `serial_recv_timeout=n` | prompt timeout in ms (default 100) |
| `help` | list the options and exit |

Set either `spifreq` or `rawfreq`, not both. Start slow (`spifreq=1`) on a
chip running from a slow clock.

## Firmware notes

- v3/v4: binary mode needs firmware 2.7+; paged flash write needs 5.10+
  (avrdude says "disabling paged flash write" otherwise).
- **BP6 binmode 5** ("Legacy Binary Mode for Flashrom and AVRdude",
  EXPERIMENTAL): in the terminal, `binmode`, pick 5. It asks for the supply
  voltage and current limit (the guide uses 5 V and 150 mA for a 5 V
  Leonardo). That is a power-on: it goes through the owner's confirmation
  like any other. The terminal is then **locked: replug the board to leave
  it**. avrdude/AVRDUDESS use 115200 on the binary port.
- Bit Pirate adapter example:
  `avrdude -c buspirate -P <port> -p m328p -v -x spifreq=1`.

## Typical commands

```
avrdude -c buspirate -P <port> -p m328p                          # signature only
avrdude -c buspirate -P <port> -p m32u4 -U flash:r:dump.bin:r     # read flash
avrdude -c buspirate -P <port> -p m328p -U flash:w:app.hex:i      # write (confirm, dump first)
```

Fuse and lock writes, chip erase (`-e`) and EEPROM writes are destructive:
plan, confirm, then run. **A flash write (`-U flash:w:...`) can trigger an
automatic chip erase on classic parts, which also erases the EEPROM** unless
a fuse preserves it, and clears the lock bits. Dump flash and EEPROM first.
Fuses may be read freely. A wrong clock fuse can leave the chip needing an external clock (`-x cpufreq=` on AUX → XTAL1).

## Errors

| Message | Cause | Fix |
|---|---|---|
| `device signature = 0x000000` or `0xffffff`, then `invalid device signature` | no answer from the chip: wiring, no power, RESET not on CS, or SPI too fast for its clock | check wiring and power, lower `spifreq` |
| `expected signature for <part> is ...` | a different part than `-p` | fix `-p`; `-F` only if sure |
| `initialization failed (rc = ...)` | the chip did not enter programming mode | double-check the connections |
| `binary mode not confirmed` | the Bus Pirate did not answer BBIO | wrong port, BP6 not in binmode 5, or replug |
| `programmer is not responding` | no reply on the port | right port, nothing else holding it |
| `SPI mode number not found; does your BusPirate support SPI?` | firmware without binary SPI | power-cycle, check firmware |
| `reset failed; you may need to powercycle it` | the Bus Pirate did not leave binary mode | unplug and replug |

Sources:
- https://avrdudes.github.io/avrdude/8.1/avrdude_6.html (BusPirate extended parameters)
- https://avrdudes.github.io/avrdude/8.1/avrdude_4.html (`-c`, `-p`, `-U`, `-x`)
- https://github.com/avrdudes/avrdude/blob/main/src/avrdude.conf.in (buspirate, buspirate_bb pins)
- https://github.com/avrdudes/avrdude/blob/main/src/buspirate.c (error messages)
- https://github.com/avrdudes/avrdude/blob/main/src/main.c (signature messages)
- docs/official/software/avrdude.md (BP6 binmode 5, wiring, AVRDUDESS warning)
- docs/bitpirate-wiki/99-adapters.md (AVRDUDE adapter)
- docs/superpowers/specs/2026-11-09-buspirate-mcp-design.md (constraints, confirmation)
