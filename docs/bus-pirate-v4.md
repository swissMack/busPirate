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
| Extended AUX command (`0x09`) | — | yes, drives or reads AUX/CS directly |
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

On a v4, the I2C panel's **Drive AUX or CS** action reaches the extended AUX
command (binary sub-command `0x09`, `Firmware/I2C.c:935`) and can drive or
read back `AUX` and `CS` directly, independent of whatever protocol mode is
active. `AUX1` and `AUX2` are not reachable this way — see the header
section above. Keep the two facts separate: `AUX`/`CS` move from the
dashboard, `AUX1`/`AUX2` never do.
