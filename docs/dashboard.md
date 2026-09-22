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
never have to carry.

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
**Read a register** writes the register number then reads, with a repeated
start — the pattern nearly every sensor expects. **Read a 24Cxx EEPROM**
handles the memory-address width for you. On a v4, **Set the pull-up rail**
connects VPU to 3.3V or 5V. See [I2C](i2c.md).

### SPI
**Identify the chip** sends `0x9F` and decodes manufacturer and capacity.
**Read from flash** and **Dump flash to a file** use the standard `0x03`
read; dumps go to `captures/` with a progress bar. See [SPI](spi.md).

### UART
Set baud and framing, listen, and send text or raw bytes. Remember TX and RX
cross over. See [UART](uart.md).

### 1-Wire
**Find devices** runs the ROM search and names the family.
**Read temperatures** reads every DS18B20-family sensor. See
[1-Wire](onewire.md).

### Raw wire
Bit-level control for buses that are nearly SPI or nearly I2C. See
[Raw wire](rawwire.md).

### Pins & power
Drive each pin, set directions, switch the supplies, measure a voltage on the
ADC pin, measure a frequency on AUX, output PWM. See
[Pins & power](pins-and-power.md).

## Live streams

Sniffers, the UART monitor and the voltage monitor **take the port over** and
stream until you press **Stop**. While one runs, every other action is
refused with a message saying so — a serial port cannot be shared. Connect
and Disconnect still work, and both stop the stream first.

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
**leaves binary mode**. What that costs depends on the hardware:

- **A v3 is hardware-reset** by this — supplies off, every pin back to
  input, everything the session knew forgotten.
- **A v4 is not reset.** It falls back into its terminal loop without
  power-cycling, but the current protocol mode is dropped either way.

**Both** boards go dark on the MODE LED the moment the terminal opens — it
comes back once you leave. That is true even on the v4, where nothing else
about the board changed.

**Nothing is restored when you come back.** The dashboard does not
re-arm the supplies or replay whatever pin state you had — silently
re-energising a target the moment you look away is how hardware gets
damaged. You come back to supplies off, and the dashboard says so.

**The rest of the dashboard is unavailable while the terminal is open.** It
holds the port exactly as a sniffer does — every other action is refused
until you leave. Switching panels takes you away from the console, but it
keeps running, and coming back to the **Terminal** panel shows it again,
live, with a working Stop button and input line — the pane is derived from
the running session, not just from the moment you opened it. You are never
stuck: **Disconnect** on the Connection panel is always available. If the
reader thread still holds the port, the click fails and explains why; trying
again in a moment succeeds.

If leaving the terminal and returning to binary mode fails, the dashboard
**disconnects** rather than pretend the session is still in binary mode.
Reconnecting recovers it: connecting always talks to the terminal first and
knocks its way back into binary mode from there.

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
