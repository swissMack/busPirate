# The dashboard

```
bin/dashboard.command          # real hardware, opens its own window
bin/demo.command               # simulated, no hardware needed
buspirate app                  # the window, from a terminal
buspirate dashboard            # the same UI, served to your browser
buspirate dashboard --demo --variant v4
make dash / make demo
```

It serves on `http://127.0.0.1:8765/` and **refuses to bind anything but the
loopback address** — it drives hardware and has no authentication, so it is
not something to expose.

## Window or browser

`buspirate app` opens the dashboard in its own window instead of a browser
tab. It is the same server and the same UI — nothing about a panel, a
recipe, or a stream behaves differently. Neither command replaces the other:
`buspirate dashboard` is still what the frontend test suite drives against,
and it is the one to reach for if you'd rather keep the dashboard in a
regular browser tab (bookmarks, extensions, a second monitor's window
manager).

The window needs one extra package, on top of the usual `[web]` install:

```bash
pip install -e '.[app]'
```

It is kept separate from `[web]` on purpose. On macOS, `pywebview` pulls in
six `pyobjc-*` packages — weight that a plain test run or CI install should
never have to carry. The GitHub Actions workflow (`.github/workflows/tests.yml`)
installs only `.[dev]`, so it never touches `[app]`.

Closing the window shuts down cleanly in the normal case: any running stream
is stopped, the board is disconnected, and the serial port is released before
the process exits. The one exception is a reader thread that will not let go —
the stream stop then times out, the disconnect is abandoned, and the process
exits anyway, so the OS releases the port and the board is left in whatever
mode it was in. Either way there is no background process left holding the
port — a hidden process still holding the device is exactly what makes the
*next* connection fail for no visible reason.

`bin/dashboard.command` now opens the window by default. It installs the
`[app]` extra if it can; if there is no usable window toolkit, it says so and
falls back to the browser dashboard instead. A tool whose job is driving
hardware should not become unlaunchable because a GUI dependency failed to
build. Any other failure — a busy port, say — keeps its own message and does
not fall back, because retrying on the same port would only fail again.

`bin/BusPirate.app` gives the window a real identity: a Dock icon and the
name "Bus Pirate" instead of the Python interpreter. See "The app bundle"
below.

**Not yet checked, because it needs a real window:** closing the window and
confirming the shutdown is actually clean — board released, no process left
holding the port — has not been exercised end to end; the automated tests
stop at proving the server starts and answers under the window (see
`tests/test_window.py`). Driving a real close needs macOS Accessibility
permission for whatever automates it, which this environment did not have.
The window's feel day to day — resizing, the Dock entry, whether the live
log and the board's terminal read well inside WKWebView — is also unchecked
for the same reason. Worth a look the first time you actually use the
window, not the demo.

## The app bundle

`bin/BusPirate.app` gives `buspirate app` a real macOS app identity: a Dock
icon and the name "Bus Pirate", instead of the Python interpreter with a
generic icon. Launch it like any other app — double-click it in Finder, or
`open bin/BusPirate.app`.

It is a hand-written bundle (`Info.plist`, an icon, a small shell stub), not
a py2app build — nothing to rebuild when Python is upgraded. The stub finds
the repo relative to its own location inside `bin/`, so **the bundle must
stay inside the repo checkout** to work; moving it out on its own breaks it.
It execs `bin/dashboard.command` directly rather than duplicating its venv
bootstrap and window/browser fallback logic, so there is exactly one
implementation of that behaviour.

It is unsigned — deliberately, since signing was out of scope here.
Gatekeeper will refuse the first launch; right-click (or Control-click) the
app and choose **Open**, then confirm, and it launches normally from then on.

## The distributable build

`bin/BusPirate.app` is a *shim*: it still needs this checkout and a Python.
For handing the dashboard to someone else there is a second, unrelated
artifact — a frozen bundle with its own interpreter, FastAPI, pywebview, the
frontend and this documentation inside it. It needs no Python, no `pip`, no
repo.

Build it:

```
bin/build-dmg.sh
```

That produces `dist/BusPirate.app` and `dist/BusPirate-<version>-arm64.dmg`
— attach the `.dmg` to a GitHub release. The version comes from
`pyproject.toml`; there is no second copy to keep in step. The script builds
its own environment in `build/dmg-venv` and leaves `.venv` alone, and both
`dist/` and `build/` are gitignored — the build output is never committed.
It freezes with PyInstaller, driven by `packaging/BusPirate.spec`.

**Apple Silicon only.** There is no Intel or universal build.

**It is unsigned and not notarized**, so macOS will refuse to open it on the
first attempt — this is the first thing anyone downloading it will hit, and
it is expected, not a broken download. Either:

- right-click (or Control-click) the app in Finder and choose **Open**, then
  confirm; or
- try to open it, then go to **System Settings → Privacy & Security** and
  click **Open Anyway** next to the message about Bus Pirate.

Once done, it opens normally from then on.

One behaviour differs from running in the checkout: dumps and logs. From a
checkout they go to `./captures`. A Finder-launched app has a current
directory of `/`, which is not writable, so the built app writes to
**`~/BusPirate/captures`** instead. That is outside `~/Documents`,
`~/Desktop` and `~/Downloads` on purpose — an unsigned app touching those
triggers a macOS privacy consent prompt.

## Layout

```
┌──────────────────────────────────────────────┐
│ busPirate   [recipes…]    ● SIMULATED v3 · i2c│
├────────────┬─────────────────────────────────┤
│ Connection │  I2C                            │
│ ▸ I2C      │  Wiring: CLK→SCL  MOSI→SDA …    │
│   SPI      │  ┌ Scan the bus ──────────────┐ │
│   UART     │  │ ☑Power ☑Pull-ups [100kHz]  │ │
│   1-Wire   │  │ 0x50 EEPROM   0x68 RTC     │ │
│   Pins     │  └────────────────────────────┘ │
│   Guide    │                                 │
│ ────────── │                                 │
│ [  HiZ   ] │                                 │
├────────────┴─────────────────────────────────┤
│ 11:39:13 -> 02   <- 01   -> 10 a0   <- 01 00 │
└──────────────────────────────────────────────┘
```

- **Recipe strip** — the jobs worth a single click. Selecting one jumps to it.
- **Panels** — one per protocol. Each opens with what it is for, a **hook-up
  diagram**, and the warnings that matter for that bus.
- **Hook-up diagram** — a photograph of the board with the pins this panel
  needs ringed and labelled (`CLK → SCL`), above the Bus Pirate's own
  reference cards with the bus marked on them: the protocol's column on the
  pin-function card, and the probe wires it uses on the cable card. Nothing to
  translate in your head.
- **Guide** — the whole user guide is in the sidebar, and every panel links to
  its own page.
- **HiZ** — at the foot of the left column on every page, once a board is
  connected. One click lets go of the target: it stops anything running,
  leaves the protocol mode, makes every pin an input and switches the supplies
  and pull-ups off, then stays connected. On a Bit Pirate it is `m hiz`. It
  works while a stream runs, which is when you want it most. **Disconnect**
  does all that and releases the port as well.
  The button is also the indicator. It reads **HiZ**, quietly, while nothing
  holds the target, and **Live**, highlighted, while something does: a
  protocol mode, a stream (the terminal included), the supplies, the
  pull-ups, pins driven from Pins & power, or PWM. Hover over it to see
  which. Like the LEDs, it is worked out from what the dashboard did, not
  read back from the board.
- **Traffic log** — every byte in both directions, live. `->` is what the Mac
  sent, `<-` what the Bus Pirate replied. This is the fastest way to tell a
  wiring fault from a protocol one.

Switching panels switches the device's mode for you. The Pins & power panel
works in bitbang mode, so selecting it leaves whatever protocol mode you were
in — that is expected.

## Panels

### Connection
Connect (leave the port blank to auto-detect), disconnect, **What is this
device?** (hardware, firmware, feature list) and **Show the cable legend**
(which probe wire is which signal). On a v3 there is also a self-test —
unplug the probe from your target first.

### I2C
**Scan the bus** probes 0x08–0x77 and names the chips it recognises.
**Read the sensors** is one click to real units: it finds the chips on the
bus, makes each one it knows measure, and lists the raw bytes beside what
they mean (°C, %RH, hPa). It knows the AHT20 and the BMP280/BME280 so far;
anything else is listed as not recognised. **Read bytes** and **Read a
register** also add a "What it means" block under the hex when the address
is one of those chips — an AHT20 reply, a BMP280 chip ID, calibration or
measurement.
**Translate for an LCD** goes the other way, for a character LCD on a
PCF8574 backpack (0x27 or 0x3F): type text, one line per row, with plain
words as commands (`clear`, `line 2`, `backlight off`, `cursor on`), and it
fills **Send to an LCD** with the hex — one step per line, each with what it
means. Edit it or not, then send; each line goes as its own transfer with a
pause after it, which the display's slow steps need. The display's size
cannot be read over I2C, so pick it (16×2 is the usual). A row of solid
blocks means it is powered but not set up: power it off and on, then send.
**Read a register** writes the register number then reads, with a repeated
start — the pattern nearly every sensor expects. It and **Read bytes** have a
**Show as** choice: hex, each byte in decimal, or 16-bit words (signed or
not, either byte order) in decimal. Power and pull-ups start unticked, so
nothing is driven until you ask for it. **Read a 24Cxx EEPROM**
handles the memory-address width for you. On a v4, **Set the pull-up rail**
connects VPU to 3.3V or 5V. See [I2C](i2c.md).

### SPI
**Identify the chip** sends `0x9F` and decodes manufacturer and capacity.
**Read a sensor** reads an SPI sensor you pick from a list (SPI has no
addresses, so the app cannot find it for you) and shows the raw bytes with
what they mean — the MAX31855 thermocouple converter so far.
**Read from flash** and **Dump flash to a file** use the standard `0x03`
read; dumps go to `captures/` with a progress bar. See [SPI](spi.md).

### UART
Set baud and framing, listen, and send text or raw bytes. Remember TX and RX
cross over. See [UART](uart.md).

### 1-Wire
**Find devices** runs the ROM search and names the family.
**Read the sensors** reads every device in the catalog — the DS18B20
family so far — and shows its raw scratchpad beside the temperature, with
the checksum checked. See [1-Wire](onewire.md).

### Raw wire
Bit-level control for buses that are nearly SPI or nearly I2C. See
[Raw wire](rawwire.md).

### Pins & power
The **supplies switch** comes first: one button that says whether the 3.3V
and 5V supplies are on, and flips them in a click. Below it, drive each pin
(tick what you want, then **Apply to the board** — nothing changes until you
do), set directions, measure a voltage on the ADC pin, measure a frequency on
AUX, output PWM. **Measure a voltage** has a **Translate as** choice: with
the ADC lead on an analog sensor's output, it shows the voltage and then
what it means — an AD595 thermocouple amplifier's 0.37 V as 36.9 °C. See
[Pins & power](pins-and-power.md).

## Live streams

Sniffers, the UART monitor and the voltage monitor **take the port over** and
stream until you press **Stop**. While one runs, every other action is
refused with a message saying so — a serial port cannot be shared. Connect
HiZ and Disconnect still work, and all three stop the stream first.

Events are decoded as they arrive and batched to ten updates a second, so a
busy bus cannot bury the browser. The counter shows the true total.

Stopping does not rely on the acknowledgement the firmware sends, because
*where* it sends it changed between versions. Instead the device is drained
and knocked back into bitbang mode, which behaves the same on every version —
you can see it happen in the traffic log.

**The UART bridge is the exception**: the firmware has no software exit, so
it needs a physical power cycle. The dashboard asks first.

## The board's terminal

The Bus Pirate has two personalities. The dashboard normally speaks its
**binary protocol** — that is everything above, and it's what the Traffic
log shows: a **protocol log**, hex bytes in both directions, decoded by
whichever panel sent them. The board also has its own **text terminal**,
the `HiZ>` prompt with `?`, `i`, `v`, `m`, `W`, `~` — the same console you'd
get talking to it over `screen` or a serial monitor. That is a **console**,
not a log: you type commands and read the board's own replies. The
**Terminal** panel's **Open the board's terminal** gets you there.

The board can only be in one personality at a time, so opening the terminal
**leaves binary mode**, and that **resets the board — a v3 and a v4 alike**:
supplies off, every pin back to input, everything the session knew
forgotten. A v4 also **drops off USB for about half a second** and comes
back (measured on firmware 6.0-a3); the dashboard watches for that and
reconnects to it, so opening the terminal just takes a moment longer.

It works like `screen`: **every key goes to the board as you type it**, and
what you see is the board's own echo. Return sends a single CR, Backspace
works, and a key the board asks for on its own — "Space to continue", "Any
key to exit" — is answered by exactly the key you press. Dead keys (`~` on a
Swiss or German layout) work too. Copy and paste work as usual.

While the terminal is open, **MODE and VREG show as unknown** (dashed, with
a "?"). The board's own commands drive them — `W` switches the supplies on
in a bus mode, the `~` self-test lights both — and the dashboard cannot see
that. PWR stays accurate.

**Nothing is restored when you come back.** The dashboard does not
re-arm the supplies or replay whatever pin state you had — silently
re-energising a target the moment you look away is how hardware gets
damaged. You come back to supplies off, and the dashboard says so.

**The rest of the dashboard is unavailable while the terminal is open.** It
holds the port exactly as a sniffer does — every other action is refused
until you leave. Switching panels takes you away from the console, but it
keeps running, and coming back to the **Terminal** panel shows it again,
live, with a working Stop button and its typing surface — the pane is derived from
the running session, not just from the moment you opened it. You are never
stuck: **Disconnect** on the Connection panel is always available. If the
reader thread still holds the port, the click fails and explains why; trying
again in a moment succeeds.

If leaving the terminal and returning to binary mode fails, the dashboard
**disconnects** rather than pretend the session is still in binary mode.
Reconnecting recovers it: connecting answers any menu question the board
was left at, resets a board left in binary mode, waits out a v4 that is
still coming back to USB, and knocks its way into binary mode from there.

## Things you will wonder about later

- **Controls that are missing** are missing on purpose: an action declares the
  capability it needs, and the dashboard hides what your hardware cannot do.
  The pull-up rail selector appears only on a v4; the self-test only on a v3.
- **The board follows what is plugged in.** Connect, and the dashboard
  detects v3 or v4 and serves that board's photo, pinout and LED behaviour
  from then on. The **Board to show** picker (top bar and Connection panel)
  overrides this if you want to read about the other version without owning
  one. Override to something that disagrees with what is actually connected
  and a badge next to the picker says so, naming both — that badge is the
  only warning; nothing else in the page second-guesses it.
- **State lives on the server.** Reloading the browser does not disconnect the
  Bus Pirate, which is what you want when a page gets into a mess.
- **One caller at a time.** A serial port cannot be shared, so actions are
  serialised. If two clicks overlap, the second waits.
- **Simulated boards** are always in the port list as `simulated-v3` and
  `simulated-v4`, with a **Try a simulated one** button on the connect
  screen. Automatic detection never picks them. `--demo` only makes a
  simulator the default and hides the real ports.
- **Demo mode** (`--demo`) is the full UI against a simulated device. Use it
  to re-learn the tool without wiring anything up, and to check the software
  still works after an OS upgrade.

## Credits

The two reference cards shown in the hook-up diagrams are from the Dangerous
Prototypes wiki (dangerousprototypes.com), used under CC BY-SA. The board
photograph is a Bus Pirate v3.6 supplied by the repository owner and its
licence has not been established — see
`buspirate/web/static/img/CREDITS.md` before publishing this repository.

The pin coordinates were measured from the photograph and checked against the
board's silkscreen; replacing the photo means re-measuring them, in
`buspirate/web/wiring.py`.

To add a panel of your own, see [extending](extending.md).
