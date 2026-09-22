# macOS setup

## Which USB chip, and which driver

The Bus Pirate reaches your Mac through a USB-to-serial bridge. Which one
depends on the hardware:

| Hardware | Bridge chip | USB ID | Driver |
|----------|-------------|--------|--------|
| Bus Pirate v3, v3.5, v3.6 | FTDI FT232R | `0403:6001` | built into macOS |
| Bus Pirate v4 | the PIC's own USB CDC | `04D8:FB00` | built into macOS |
| Clones | CP2102 or CH340 | `10C4:EA60`, `1A86:7523` | usually built in |

Modern macOS has drivers for all of these. **Do not install FTDI's or
Silicon Labs' own kexts** unless a port genuinely never appears — on macOS 11
and later they mostly cause trouble rather than fix it.

## Find the port

```bash
buspirate ports
```

```
 * /dev/cu.usbserial-A700eEoR  [0403:6001]  - FTDI FT232R (Bus Pirate v3)

* = looks like a Bus Pirate; --port auto will choose it.
```

Add `--all` to see everything, including Bluetooth pairings.

### `/dev/cu.*` versus `/dev/tty.*` — this one matters

macOS lists every serial device twice:

- **`/dev/cu.*`** ("call-out") opens immediately. **Use this one.**
- **`/dev/tty.*`** ("call-in") blocks on open until it sees carrier detect.
  The Bus Pirate never asserts it, so your program hangs with no error.

That hang is the single most common "it stopped working" on macOS. Everything
here prefers `cu.` automatically; you only have to care if you type a port by
hand.

## Install

The launcher does this for you. To do it by hand:

```bash
cd ~/Documents/GitHub/busPirate
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,web]"
buspirate ping
```

macOS ships Python 3.9, which is enough. A virtualenv keeps this project's
packages out of the system Python, which Apple's updates periodically reset.

Or simply:

```bash
make setup
```

## The launcher

`bin/dashboard.command` is double-clickable from Finder. It:

1. creates `.venv` if missing, using the newest Python 3 it can find,
2. installs or updates the package when `pyproject.toml` has changed,
3. prints the port list,
4. starts the dashboard and opens it in its own window, falling back to
   your browser if the window can't start (see
   [Dashboard](dashboard.md#window-or-browser)).

`bin/demo.command` does the same with a simulated device.

**Gatekeeper:** the first double-click may be refused because the file came
from the internet. Right-click → **Open** → **Open** once, and macOS
remembers. Or clear the quarantine flag:

```bash
xattr -d com.apple.quarantine bin/*.command
```

To keep it in the Dock, drag `dashboard.command` onto the Dock's right-hand
side, or make an alias on the Desktop.

## Nothing appears at all

1. `buspirate ports --all` — is *any* new device listed?
2. Try a different cable. Many micro-USB cables are charge-only.
3. `ioreg -p IOUSB -l -w 0 | grep -i "USB Product Name"` — does macOS see the
   device on the USB bus at all? If not, it is the cable or the hardware, not
   the driver.
4. Plug directly into the Mac, not through a hub or a monitor.

Then see [troubleshooting](troubleshooting.md).
