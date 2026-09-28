# Bus Pirate v4

The v4 speaks nearly the same binary protocol as the v3. This driver
identifies which one is attached from the firmware's `i` banner at connect
time and adjusts, so most of the time you need not care.

```python
with BusPirate("auto") as bp:
    print(bp.profile.variant)        # "v3", "v4" or "unknown"
    print(bp.profile.firmware)       # "v6.1"
    print(sorted(bp.profile.capabilities))
```

## What differs

| Feature | v3 | v4 |
|---------|----|----|
| Pull-up rail select (`010100xy`) | — | yes, connects VPU to 3.3V or 5V |
| Extended AUX command (`0x09`) | yes, firmware v6.1+ | **no** — the firmware hangs on it; see below |
| Binary self-test (`0001000x`) | yes | — (the v4 uses a different mechanism) |
| USB bridge | FTDI FT232R | the PIC's own CDC |
| PWM, ADC, frequency counter | yes | yes |

Actions the connected device cannot do are **not offered**: the dashboard
hides them and the driver raises `UnsupportedFeatureError` naming the variant
that does have the feature.

## Firmware matters as much as hardware

- **Before v4.2**, I2C had two speeds (5 kHz and 50 kHz). From v4.2 the same
  command selects four (5, 50, 100, 400 kHz). The driver reads your firmware
  version and rejects speeds you do not have, listing the ones you do.
- **`write_then_read` (`0x08`) needs firmware v5.1 or newer.** On older
  firmware that byte started the bus sniffer instead. Use `read_register()`,
  which works everywhere.
- The pull-up rail command was documented long before it was implemented.
  Older v4 firmware may accept and ignore it.

## An unidentified device still works

If the banner does not parse — a noisy line, an unusual firmware — the driver
falls back to an `unknown` profile: the shared command set, none of the
variant-specific extras. Everything ordinary keeps working.

## Protocol versions

Mode banners end in a version digit: `BBIO1`, `I2C1`, `SPI1`. The digit is a
*protocol* version, not a hardware one, and the driver accepts any digit. A
future firmware answering `BBIO2` will work here.

## The header: a 2x6, not a 2x5

A v3 probe header is a 2x5 IDC. A v4 header is a **2x6** — two more pins,
both AUX lines. Confirmed three ways: the v4.0 board render, the v4.0e
render's silkscreen, and the firmware's own pin list at
`Firmware/procMenu.c:1692`.

| Left column (top to bottom) | Right column |
|---|---|
| GND | +5V |
| +3.3V | VPU |
| ADC | AUX2 |
| AUX1 | AUX |
| CS | MISO |
| CLK | MOSI |

`AUX` is the same auxiliary pin a v3 has, wired to the same binary commands.
`AUX1` and `AUX2` are new on the v4 and are **terminal-mode only** —
`Firmware/binIOhelpers.c:20-25` gates AUX2 behind
`#if defined(BUSPIRATEV1A)`, and `Firmware/binIO.c:268` and `:308` cover only
five pins. Nothing in the binary protocol reaches them, so the dashboard
cannot drive or read them and does not offer to. Do not confuse this with
`AUX`, which the dashboard *can* drive — see below.

## The LEDs, v4 in particular

Same four LEDs, same left-to-right order — **PWR, USB, MODE, VREG** — but the
v4 drives two of them in firmware where the v3 drives one:

| LED | v4 |
|-----|----|
| **PWR** | Hardware. Unchanged from the v3. |
| **USB** | **Firmware.** `BP_LEDUSB` = RB10 (`Firmware/hardwarev4a.h:65`). `Firmware/main.c:76` lights it while the board is enumerating over USB; `Firmware/main.c:95` turns it **off** once enumeration is configured. |
| **MODE** | Firmware. `BP_LEDMODE` = RB8 (`Firmware/hardwarev4a.h:59`) — same behaviour as a v3, lit for the whole binary session, a different GPIO underneath. |
| **VREG** | Hardware. Unchanged from the v3. |

**This inverts the v3 rule for USB.** On a v3, USB is the FT232RL's
`RXLED#` pin: it pulses on traffic and is dark at idle. **On a v4, there is
no FT232RL at all** — the PIC24FJ256GB106 does USB itself, which is exactly
why the USB LED moved into firmware. A v4's USB LED is lit only while it is
enumerating; **once enumerated, it goes dark and stays dark for the rest of
the session.** A steady dark USB LED on a v4 is the healthy, connected
state — the opposite of what it means on a v3. This is the fact in this
document most likely to look like a bug when you first see it; it is not
one.

The full per-variant LED table, and the `MODE` caveat that applies to both
variants, lives in [Pins & power](pins-and-power.md#the-four-leds).

## Driving AUX and CS from the dashboard

**On a v4, drive `AUX` from Pins & power.** The I2C panel's **Drive AUX or
CS** action is not offered on a v4, and that is deliberate.

It uses the extended AUX command (`0x09`, `Firmware/I2C.c` case 9). Tried on
a real v4 on 2026-09-28, the command fails on both firmware versions:

- **Firmware 6.0-a3** predates the command and answers it with `0x00`.
- **Firmware 7.0** knows it and answers `0x01`, then **hangs** until the
  board is unplugged.

The firmware reads the command's second byte straight from the PIC's hardware
UART (`while(U1STAbits.URXDA == 0)`). A v4 talks to the computer over its own
USB, read through `UART1RX()` = `getc_cdc()`, so nothing ever arrives on that
UART. Every firmware with the command reads it this way, so no update fixes
it.

On a **v3** that UART is the FT232R's link to the computer, so the command
works there, from firmware v6.1, and the dashboard offers it.

`AUX1` and `AUX2` are not reachable from the dashboard either way — see the
header section above.

## Updating the firmware

Done on a real v4 on 2026-09-28, from firmware 6.0-a3 to **7.0**:

1. **Get the tool and the firmware.**
   - Build `pirate-loader` from `Bootloaders/pirate-loader/pirate-loader.c` in
     the [official repository](https://github.com/BusPirate/Bus_Pirate). It is
     one C file: `cc -O2 -o pirate-loader pirate-loader.c`.
   - Download `bp4.0-fw-7.0.hex` from that repository's v7.0 release.
2. **Enter the bootloader with a jumper.** Unplug the board, put a jumper
   between the **PGC** and **PGD** pins, and plug it back in.
   - The **VREG** LED lights with PWR, and the board comes up with a new USB
     ID, `04D8:000A`.
   - `buspirate ports --all` shows which ID it has.
   - The terminal's `$` command did not work on 6.0-a3: the board went
     straight back to its firmware.
3. **Check the bootloader (optional).**
   `pirate-loader --dev=/dev/cu.usbmodem… --hello` reports the bootloader
   (4.06 here) and the chip (PIC24FJ256GB106).
   - It ends with "ERROR, timeout". That is its goodbye, which restarts the
     board, and it is harmless.
   - Because of that restart, unplug and replug (jumper still on) before
     flashing.
4. **Flash.** `pirate-loader --dev=/dev/cu.usbmodem… --hex=bp4.0-fw-7.0.hex`
   takes about a minute.
   - The last page is "SKIPPED by bootloader": that is the protected
     configuration page, and it is expected.
   - It ends with "Firmware updated successfully! :)", then the harmless
     timeout.
5. **Restart normally.** Unplug, remove the jumper, and plug it back in. `i`
   now reads `Community Firmware v7.0`.

The bootloader refuses to overwrite itself, the reset vector or the
configuration page. So an interrupted update leaves it intact: enter it
again with the jumper and flash again.
