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
