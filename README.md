# busPirate

Working repo for Bus Pirate hardware-interface work: scripts, capture logs, and notes.

## Layout

| Path | Purpose |
|------|---------|
| `scripts/` | Host-side scripts driving the Bus Pirate over serial |
| `captures/` | Saved bus captures / logs (gitignored by default except samples) |
| `docs/` | Pinouts, target notes, protocol cheatsheets |

## Quick start

```bash
# find the device
ls /dev/tty.usb*

# open a terminal session (115200 8N1)
screen /dev/tty.usbserial-XXXX 115200
```

## Notes

Nothing here targets hardware you don't own. Keep target-specific credentials
and dumps out of git — see `.gitignore`.
