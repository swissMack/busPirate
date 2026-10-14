# Bus Pirate 6 support — design

**Date:** 2026-10-14
**Status:** approved design, not yet implemented
**Branch:** `bus-pirate-6-support`

## The goal

The owner now has a Bus Pirate 6. It becomes the fourth board in the app, next
to v3, v4 and the ESP32 Bit Pirate:

- the app detects it automatically;
- it works in the dashboard and the CLI;
- it follows the project rules: a simple UI with one-click controls, and the
  app identifies chips and shows real units.

The app also ships both kinds of documentation: **our own BP6 guides** and **a
bundled copy of the official Bus Pirate 5/6 manual**.

## Decisions taken

| Question | Decision |
|---|---|
| Scope | Parity with v3/v4 (I2C, SPI, UART, 1-Wire, pins and power, Terminal, chip identification), **plus** the BP6's programmable supply: voltage, current limit, measured current |
| Protocol | **BPIO2** (FlatBuffers over COBS) on the binary USB port. No text parsing of the terminal |
| Firmware | Updated to current main (see below). The driver targets this firmware and later builds |
| Documentation | Both: our own app guides **and** the official manual, imported as Markdown |
| Raw-wire, DIO, IR, JTAG, PS/2, USB modes | Not in the dashboard. They're still reachable by typing in the Terminal panel |

Rejected:

- **Keep firmware `985173b` and drive UART through the text terminal.** That
  means two code paths, and the text one is fragile.
- **A text-terminal driver for everything,** the Bit Pirate approach. It parses
  coloured terminal output when a structured protocol is available.

## What we established on the real board (2026-10-14)

- **Hardware:** Bus Pirate 6, RP2350B, hardware version 6.2, 18 LEDs, 98 MB
  storage. USB ID **`1209:7331`**, product string "Bus Pirate 6", USB serial
  number `6buspirate`. That serial number is the same on every unit, so it
  can't tell two BP6s apart.
- **Ports:** two CDC ports. On macOS they are `/dev/cu.usbmodem6buspirate1`, the
  **terminal**, and `/dev/cu.usbmodem6buspirate3`, the **binary/BPIO2** port.
- **Firmware update done:** from `main @ 985173b` (29 Jan 2026) to the
  `main @ 322c452` CI build (built 12 Oct 2026, from
  `firmware-rp2350-ubuntu-latest`, file `bus_pirate6.uf2`). The method:
  1. Type `$` in the terminal. The board reboots into its ROM bootloader and a
     disk named `RP2350` appears.
  2. Copy the `.uf2` onto that disk.

  The board re-enumerates on the same port names.
- **CI builds report the git hash as `unknown`,** both in `i` and in BPIO2's
  `version_firmware_git_hash`. `version_firmware_major/minor` are always 0.
  **Identify the firmware by build date** (`version_firmware_date`, for example
  `Oct 12 2026 09:05:15`).
- **Terminal behaviour on the new firmware:**
  - Only **`\r`** is Enter. A `\n` is typed into the line as a character.
  - The terminal does its own line editing and redraws the line with escape
    sequences such as `\x1b[0K` and `\x1b[NC`.
  - The first-connect prompt `VT100 compatible color mode? (Y/n)>` only takes
    an answer sent in **one write**, as `n\r`. When `n` and `\r` arrive in
    separate writes, it shows the prompt again.
- **BPIO2 selection:** `binmode` → `2` → `Save setting? y/n` → `n`. This makes
  BPIO2 active until the next reboot and changes nothing on the board. The
  default binmode stays SUMP.
- **One BPIO2 status request answered fully:**
  - `modes_available` = HiZ, 1WIRE, UART, HDUART, I2C, SPI, 2WIRE, 3WIRE, DIO,
    LED, INFRARED, JTAG, PS2, USB
  - `mode_max_packet_size` 640, `mode_max_write` 512, `mode_max_read` 512
  - `adc_mv[8]`
  - PSU set and measured values, plus `psu_current_error`
  - `pullup_enabled`
  - `mode_pin_labels` (10 entries: VOUT, IO0–7, GND)
- **BPIO2 data handlers in the new firmware** (`src/binmode/bpio.c`): HiZ,
  1-Wire, I2C, SPI, **UART (with asynchronous RX)** and LED. 2WIRE, 3WIRE, DIO,
  INFRARED, JTAG and HDUART have no handler, and BPIO2 refuses to switch to
  them.

Protocol references: the schema `bpio.fbs` and the generated Python code are in
<https://github.com/DangerousPrototypes/BusPirate-BPIO2-flatbuffer-interface>
(Apache-2.0). Docs: <https://docs.buspirate.com/docs/binmode-reference/protocol-bpio2/>.

## 1. Architecture and connection

### Detection and port pairing

- `ports.py` learns `(0x1209, 0x7331): "Bus Pirate 5/6"`.
- The two CDC ports of one board are **paired by USB location**, using
  pyserial's `location`, where the interface number is the suffix. The lower
  interface is the terminal and the higher one is BPIO2. If `location` is
  missing, it falls back to the trailing digit of the device name.
- The port picker shows **one entry per board**, labelled "Bus Pirate 6", not
  two raw ports.
- `connect.open_device()` sends VID `0x1209` / PID `0x7331` straight to the new
  driver. It must never fall into the v3/v4 path, which sends nulls and the
  BBIO reset.

### Connecting (one click)

1. Open the BPIO2 port and send a **StatusRequest**.
2. If nothing comes back within about 0.5 s, open the terminal port:
   1. Send `\x03` to clear the line.
   2. If the colour prompt shows, answer `n\r` in one write.
   3. Send `binmode\r`, then `2\r`, then `n\r`, so the setting is not saved.
   4. Retry the StatusRequest.
3. If it still fails, raise `ModeError` with a message that names the likely
   cause. For example: the firmware predates BPIO2, so update with `$` plus
   drag-and-drop (see the guide).
4. The board's identity comes from the StatusResponse. Hardware 6.x is labelled
   "Bus Pirate 6" and 5.x "Bus Pirate 5". Only the BP6 has been verified; the
   BP5 is expected to work but is untested, and the label says so.

### Package `buspirate/bp6/`

This mirrors `buspirate/bitpirate/`.

| File | Purpose |
|---|---|
| `framing.py` | COBS encode/decode and the `0x00` delimiter (about 30 lines, no dependency). Reads one frame at a time with a timeout |
| `bpio/` | Vendored generated FlatBuffers Python code from the official repo, at a pinned commit, with its Apache-2.0 `LICENSE` and a `SOURCE.md` naming that commit |
| `protocol.py` | Builds RequestPackets and parses ResponsePackets. Always sends `version_major=2` and `minimum_version_minor=0`, and **never sends a request without contents**, because that can crash the board (firmware packet-type bug) |
| `device.py` | `BusPirate6(SerialLink-like)`: `open()`, `close()`, `status()`, `configure(...)`, `i2c()`, `spi()`, `uart()`, `onewire()`, pins, power, and the same surface the dashboard uses for the other boards |
| `modes.py` | Thin mode classes. Each turns calls such as `write_then_read` and `scan` into DataRequests, within the 512-byte read and write limits (chunked where the bus allows it) |
| `cli.py` | CLI entry points, matching the existing commands |

- **New dependency:** `flatbuffers`, from PyPI, pinned to a version compatible
  with the vendored generated code.
- **Traffic hooks:** the traffic monitor shows a decoded summary of each
  request and response, not raw COBS bytes.

### Terminal panel

- The Terminal panel opens the **terminal port** directly. BPIO2 keeps running
  on the binary port at the same time.
- It sends `\r` for Enter and passes the firmware's line-editing escape
  sequences through to the green-on-black terminal.
- After any line is sent in the terminal, the dashboard **re-reads BPIO2
  status**. Mode, power and pull-ups typed by hand then show up in the UI.

### Firmware workarounds

| Problem | Workaround |
|---|---|
| A request with no contents can crash the board | The protocol layer refuses to send one |
| After an I2C error, the bus may be left mid-transaction with no STOP | The driver follows any I2C error with a stop-only DataRequest |
| An I2C error doesn't say which byte NACKed | Errors are reported as "no ACK from 0x.." for the transaction as a whole |
| The git hash is `unknown` on CI builds | Firmware is shown and compared by build date |
| `io_direction` / `io_value` are raw GPIO bits | Pin directions are shown from what the app set. Levels come from `adc_mv` |
| A frame not finished within 500 ms is rejected | Each frame goes out in one write |

## 2. BP6-specific UI

Rule: one-click controls that show their own state. A confirmation step appears
only where a mis-click could damage the target.

### Pins & power tab (BP6 variant)

- **Supply voltage:**
  - a number box, 0.8–5.0 V, default 3.3 V;
  - quick buttons for **1.8 / 3.3 / 5.0 V**;
  - turning power on above **3.6 V** asks for confirmation once.
- **Current limit:**
  - a number box, 1–500 mA, default 300 mA;
  - "No limit" (0) sits behind the same confirmation.
- **Power on/off:** one button, as on v3/v4.
- **Live readout:** polled about once a second while the tab is visible.
  - It shows measured voltage and current in mA.
  - When `psu_current_error` is set, a red **"Current limit tripped — power
    cut"** banner appears with a one-click **Re-enable**.
- **Pull-ups:** one on/off button.
  - The text explains that the BP6 pull-ups are onboard 10 kΩ resistors to the
    supply.
  - The v4's pull-up voltage selector does not appear.
- **Pins:** IO0–IO7 voltages from `adc_mv`, with the current mode's
  `mode_pin_labels` above them (for example SDA and SCL in I2C mode).

### Board picture, wiring and status

- **Board picture:** a BP6 image on the connection card. It comes from the
  official docs (MIT) and is credited in `static/img/CREDITS.md`.
- **Wiring view:** BP6 pinouts for I2C, SPI, UART and 1-Wire. They're taken
  from the firmware's pin labels, so they always match the board.
- **Status bar:** "Bus Pirate 6 · fw 2026-10-12 · I2C · 3.30 V / 12 mA".

### Capability gating

This uses the existing mechanism.

- **Hidden on the BP6:** the Raw-wire panel (2-wire and 3-wire), and v3/v4-only
  actions such as PWM, the frequency counter, the v4 pull-up rail select, the
  BBIO self-test and the AUX pin.
- **New capabilities for the BP6:** `psu_programmable` (voltage and current)
  and `psu_current_readout`.

### Out of scope (YAGNI)

- LED colour control
- the logic analyzer
- IR, JTAG, PS/2 and USB modes
- self-test

All of these remain available by typing in the Terminal panel.

## 3. Documentation

### 3a. The official manual, bundled

Source: <https://github.com/DangerousPrototypes/BusPirate-docs-hugo>, branch
`main`. It's a Hugo site with 158 Markdown pages, under the **MIT** license
(Copyright (c) 2025 Ian). Branded artwork is CC BY-SA 4.0, and is not imported.

**Import script: `scripts/import_official_docs.py --ref <commit>`**

- **Fetches** the repo at the pinned commit.
- **Keeps** these sections:
  - `tutorial-basics/`
  - `command-reference.md`
  - `devices/`
  - `overview/`
  - `logic-analyzer/`
  - `binmode-reference/`
  - `software/`
  - `license.md`
- **Drops:**
  - `hardware/`, `manufacturing/`, `enclosure/`, `development/`
  - every PDF
  - any image no kept page references
- **Converts the Hugo template tags (shortcodes):**

  | Shortcode | Becomes |
  |---|---|
  | `{{% alert context="…" %}}` | `> **Note:**` / `> **Warning:**` callouts |
  | `{{< termfile source="…" >}}` and `{{< term … >}}` (coloured HTML) | Plain-text code blocks, tags stripped and entities decoded |
  | `{{% readfile "…" %}}` | The included file, inlined |
  | `{{< relref "…" >}}` | In-app links (`official/<path>.md`, keeping `#anchor`) |
  | `{{< tabs >}}` / `{{< tab "X" >}}` | `#### X` sub-headings |
  | `{{< asciicast … >}}` | A link to the page on docs.buspirate.com |
  | `btn`, `openstreetmap` | Plain links |

  TOML front matter (`+++ … +++`) is stripped. Its `title` becomes the `# H1`
  and its `weight` sets the sidebar order.
- **Images:** absolute `/images/docs/...` paths are rewritten to paths relative
  to the page. Images are resized to at most 1200 px wide.
- **Writes** the result to `docs/official/`, with the upstream `LICENSE`, a
  `SOURCE.md` (commit SHA, date, and how to re-run) and an `order.json` for the
  sidebar.
- **Reports** every shortcode or construct it couldn't convert. Nothing is
  dropped silently.

The output is **committed to the repo**, so the manual works offline and is
bundled by PyInstaller. `packaging/BusPirate.spec` already copies `docs/`. The
target size is **under about 25 MB**. It gets measured during implementation,
and if it's much bigger the owner is asked before committing.

Updating the manual means re-running the script with a newer `--ref`. There are
no automatic updates.

### 3b. Viewer changes

- **`web/docs.py`:**
  - Page names may contain one sub-folder level (`official/command-reference`).
    The same safe-name rules apply to each segment.
  - A new route serves images from under `docs/`. Paths are resolved and checked
    to stay inside `DOCS_DIR`, and only image extensions are served.
  - `available()` returns pages in groups: **"This app"**, then **"Official Bus
    Pirate 5/6 manual"**, in `order.json` order.
  - A new search function scores title matches first, then counts text matches,
    and returns about 20 results with snippets.
- **`app.js` `markdownToHtml`:**
  - learns images, blockquote callouts and heading anchors (slugged `id`s), so a
    link into the 178 KB command reference lands on its section;
  - follows links to `*.md` in sub-folders inside the app.
- **Sidebar:** the two groups, with the manual collapsible, and a **search box**
  above them.
- **Manual banner:** each manual page shows a one-line banner: *"This is the
  official manual for the Bus Pirate's built-in terminal. You can type these
  commands in the Terminal panel."*

### 3c. Our own guides

- **New page `docs/bus-pirate-6.md`.** It covers:
  - what the BP6 is;
  - the two ports;
  - the firmware update (`$` plus drag-and-drop, and where CI builds come from);
  - power, current limit and pull-ups;
  - what the dashboard hides on the BP6 and why;
  - troubleshooting.
  It's added to `docs.ORDER`.
- **BP6 sections added to** `i2c.md`, `spi.md`, `uart.md`, `onewire.md`,
  `pins-and-power.md`, `cli.md` and `user-guide.md`. Each links into the
  matching part of the official manual.
- **`troubleshooting.md` gets a BP6 section and a real-board checklist.**

## 4. Testing

- **`buspirate/simulator_bp6.py`:** a BPIO2 simulator that answers status,
  configuration and data requests for I2C (a few fake chips), SPI (a flash chip
  that returns a JEDEC ID), UART (echo plus async RX) and 1-Wire (a DS18B20).
  It also simulates the PSU, including a current-limit trip. It's used by the
  unit tests and by the dashboard's demo mode.
- **Unit tests:**
  - framing round-trips, including the 0x00 and 254-byte-block edge cases;
  - request building, including that no request is ever sent without contents;
  - port pairing;
  - the connect fallback through `binmode`;
  - each mode;
  - the PSU confirmation rules;
  - capability gating;
  - the docs import's shortcode conversion, against small fixture pages;
  - the docs route's path safety.
- **Real-board checklist** in `troubleshooting.md`, run on the owner's BP6:
  connect; status; PSU at 3.3 V with a current reading; a current-limit trip;
  pull-ups; an I2C scan with a real chip; a SPI flash ID; UART loopback; 1-Wire;
  the Terminal panel running alongside BPIO2.

## Risks

- **BPIO2 changes quickly.** The protocol layer checks `version_flatbuffers`
  (2.x) and refuses older builds with a clear message.
- **Repo size.** The imported manual's images are the risk. They're resized,
  and the owner is asked if the total goes much past 25 MB.
- **Two BP6s plugged in at once** share USB serial number `6buspirate`. Pairing
  by USB location handles that, but it's untested with two boards.
