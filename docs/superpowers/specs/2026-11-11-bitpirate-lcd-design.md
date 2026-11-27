# Bit Pirate status LCD — design

Date: 2026-11-11 · Status: ready for owner approval · Scope: **local only** (owner's dock board; not for upstream)

## Intent

The owner's ESP32 Bit Pirate sits in the AndreiVladescu dock (see `docs/bitpirate.md`).
Today the only on-board status is the RGB mode LED. The owner wants a small screen
that evokes the Bus Pirate 6's LCD utility on hardware they already own: a
**16×2 HD44780 LCD with an FC-113 PCF8574 I²C backpack** (photos:
`docs/BitPirate LCD/IMG_6724.jpeg`, `IMG_6725.jpeg`).

The two moments they look at it:

1. **At start-up** — to learn how to reach the board: on Wi-Fi, its IP (so they can
   open `http://<ip>`); on USB, that it's on USB.
2. **Once in a mode** — to know which wire goes where for that mode
   ("which pins denote which connection … and that changed per use case").

## Goals

- At boot and whenever the mode is HiZ (or any mode without pins): connection screen.
  - Wi-Fi: line 1 `Bit Pirate WiFi`, line 2 the full IP.
  - USB/serial: line 1 `Bit Pirate USB`, line 2 blank or short hint (builder's call).
- On entering a mode with pins: a wiring guide for that mode showing only the pins
  in use, labelled by **signal name + dock silkscreen name** (`IO15`, not `GPIO 15`),
  using the **actually configured** pins (if the user changes pins in the firmware's
  mode setup, the screen follows).
- Layout ("option E", chosen implicitly — the owner liked the flow mockup built on it):

  ```
  I2C  SDA  IO15      CS IO11 CLK IO12      UART TX IO10
  GND  SCL  IO16      MI IO10  MO IO13      GND  RX IO11
  ```
  When a mode has more pins than fit, the builder decides how to fit them
  (e.g. alternating pages every ~3 s). Non-pin details (frequency, baud) are not shown.
- Brief firmware version on boot (e.g. `Bit Pirate 1.8` for ~2 s) before the connection screen.
- Backlight always on.
- The existing RGB mode LED keeps working exactly as now.
- If no LCD is attached (no ACK at 0x27/0x3F), the firmware behaves exactly as today.

## Non-goals

- Upstreaming. This lives as a patch in `firmware/` like the dock-pins patch. Owner:
  "If I wanted to upstream it, I would want a better display."
- Live pin voltages (the dock's TXS0108E level shifters sit in front of the pins; the
  firmware can't read them) and the VIO switch position.
- Backlight timeout, menus, buttons, any interaction with the screen.
- Changes to the Mac dashboard / MCP server.

## Anti-goals

- Anything that costs money — use the LCD and parts on hand (two resistors are fine).
- Putting 5 V on any ESP32-S3 pin.
- The LCD appearing on, or disturbing, the bus under test (e.g. showing up in an I²C scan
  of the target, or breaking the I²C slave/emulation feature).

## Constraints and facts (from firmware recon of v1.8 + mode-led + dock-pins)

- Base: geo-tp ESP32-Bit-Pirate tag `v1.8` + `firmware/bitpirate-1.8-mode-led.patch`
  + `firmware/bitpirate-1.8-dock-pins.patch` + `firmware/bitpirate-1.8-webui-start.patch`
  (always applied — it is part of the app's firmware release). The LCD patch applies
  after all three; only that one order is supported.
  Build env `s3-devkit-n16-r8` (`-DDEVICE_S3DEVKIT`). Build/flash steps: `docs/bitpirate.md`.
  Flash over the UART port (CP2102), app-only `firmware.bin` @ 0x10000.
- View interface: `src/Interfaces/IDeviceView.h`. The board holds **one** view
  (`RgbLedView deviceView{LED_PIN}` in `S3DevKitBoard.h`), so LED + LCD needs a
  **composite view** forwarding every call to both.
  - `welcome(terminalType, terminalInfos)` is called after boot; terminalInfos is the IP
    on Wi-Fi. `GlobalState::getTerminalMode()` / `getTerminalIp()` also hold this.
  - `show(PinoutConfig&)` is called on every mode change (`ActionDispatcher::setCurrentMode`);
    `getMode()` gives the name, `getMappings()` gives strings like `"SDA GPIO 15"`,
    `"FREQ 100000"`. HiZ has no mappings.
- **I²C controllers are both taken**: `Wire` by I2C mode and others, `Wire1` by the
  I²C slave/emulation feature. The LCD therefore uses a **small bit-banged I²C writer**
  on its own pins (the PCF8574 is write-only for this use; 100 kHz or slower is fine).
  No new library dependency required; builder may choose a library if it does not touch
  `Wire`/`Wire1`.
- LCD pins: **GPIO 8 = SDA, GPIO 9 = SCL**, unused in the s3-devkit build. Confirmed from the
  dock photo (`~/Desktop/IMG_6675.jpeg`): 8, 9, 3V3 and 5V are on the **DevKit's own header
  row** (straight from the ESP32, not through the dock's TXS0108E), so the LCD does not
  depend on the VIO switch. Add 8 and 9 to the board's protected pins so no mode can be configured onto them.
- Dock silkscreen ↔ GPIO: connector top→bottom GND, IO15, IO16, IO17, IO18, IO10, IO11,
  IO12, IO13, VIO. Pins not on the connector (e.g. 1-Wire default GPIO 6) still display as
  `IO6`; the screen just names the GPIO.

## Hardware modification (owner does this; plan must include the steps)

- All LCD wiring goes to the **DevKit's left header row** (top→bottom: 3V3, 3V3, RST, 4, 5, 6,
  7, 15, 16, 17, 18, **8**, 3, 46, **9**, 10, 11, 12, 13, 14, **5V**, **G**):
  backpack VCC → **5V**, GND → **G**, SDA → **GPIO 8**, SCL → **GPIO 9**. The dock's POWER
  header stays untouched. 5 V is needed because a blue 16×2 is unreadable at 3.3 V.
- The FC-113 has pull-ups from SDA/SCL to its VCC (5 V). **Remove those two resistors**
  (identify on the owner's board from the photo before desoldering) and fit
  **4.7 kΩ pull-ups from SDA/SCL to 3V3** (top of the same row).
- **Signal level — decided by the owner: direct first, diode as fallback.** Known out of
  spec: the PCF8574 at 5 V wants V_IH ≥ 0.7·VCC = 3.5 V, the ESP32 drives/pulls to 3.3 V.
  Wire it directly first. **Fallback** if the screen shows garbage, misses updates or
  doesn't ACK: put one silicon diode (1N4148 / 1N400x) in series in the backpack's 5 V
  lead (≈4.3 V at the PCF8574 → V_IH ≈ 3.0 V), and re-check contrast. The plan's hardware
  test must include a check that makes this decision (e.g. a long stress run of screen
  updates with verification of ACKs).
- Address: chip reads PCF8574T → expect **0x27** (A0–A2 open); firmware probes 0x27 then 0x3F.
- Contrast pot on the backpack may need adjusting after first power-up.

## Decided by the owner

- Screen behaviour: connection screen at start/HiZ, wiring guide in a mode (the flow mockup).
- Pin labels change per mode and name the connections (VDD/GND/MOSI…).
- Local only, no money spent on a display (screws/small parts for the hat are fine).
- LCD signals wired direct first; diode in the 5 V lead as the fallback.
- LCD power from the DevKit's 5V/G pins, not the dock's POWER header.
- Hat: tilted LCD over the middle band, on the four corner holes, POWER header kept clear,
  owner buys M3 screws to suit.

## My calls (owner has not explicitly confirmed)

- Layout E (only used pins, silkscreen names) over the full-connector layout F.
- Firmware-driven (works without the Mac app), composite view alongside the LED.
- GPIO 8/9, bit-banged I²C, 5 V module with pull-ups moved to 3.3 V.
- Version splash at boot; backlight always on; frequency/baud not shown.
- One-shot boot adapter modes (USB adapter, flashrom serprog, SDR via `adapterMode`):
  adapter name on line 1, line 2 blank.
- Showing `GND` on the wiring screen where there is room; VIO not shown (it's the dock switch).

## Left to the builder

- Exact text per mode, abbreviations, and paging for modes with >4 pins.
- Whether to use a bit-bang library or hand-roll the ~60 lines.
- File layout inside the firmware tree (e.g. `src/Boards/Common/Views/Lcd1602View.*`,
  `CompositeDeviceView.*`), and the patch name (suggest `firmware/bitpirate-1.8-lcd.patch`,
  applied after dock-pins).
- Testing approach: there is no firmware unit-test harness; verification is on hardware
  (boot USB, boot Wi-Fi, enter I2C/SPI/UART/1-Wire, back to HiZ, LCD unplugged, LED still OK,
  I²C scan of a target does not show 0x27).
- Docs: a section in `docs/bitpirate.md` (wiring, resistor mod, patch apply order).


# Part 2 — the LCD hat (3D-printed holder)

## Intent

A printed "hat" that holds the 16×2 LCD above the owner's printed dock case
(`~/Downloads/dock_case_no_logo.step`, printed 2026-11-11), tilted toward the owner,
so the screen is readable at the bench without blocking the dock's controls.
Photos of the intended position: `docs/BitPirate LCD/IMG_6727–6730.jpeg` (6730 shows the
tilt, the owner holding the LCD in place).

## Orientation (owner's view)

The owner sits at the **10-pin probe connector edge**; the ESP32 DevKit is at the back,
USB ports back-right. "Left/right/front/back" below are from the owner's seat.

## Goals

- LCD spans the case **width** (side to side), floating above the middle band between the
  DevKit (back) and the probe connector (front), **tilted back toward the owner**, about
  55–60° from the desk (estimate from IMG_6730; builder fixes the angle in the model).
- Attaches through the case's **four corner screw holes** (Top Case: Ø3.1 mm through,
  Ø6 mm counterbore; Bottom Case: Ø2.86 mm pilot holes; hole spacing 70.9 × 64.6 mm —
  measured from the STEP). There are no screws in the case today; the owner will buy M3
  screws to suit, so the design states the **exact length and head type** needed.
- Must leave clear and usable:
  - the **POWER header** (2×3 male pins, 1V8/3V3/5V/GND, front-right) — the one hard
    keep-out: nothing above it, room for a jumper or a probe lead;
  - the 10-pin probe connector (front centre) incl. plugging/unplugging the cable;
  - SW1 voltage switch and the voltage LEDs (left), Wi-Fi Mode button (front-right);
  - the DevKit's USB-C ports and BOOT/RESET (back-right), and the DevKit header pins the
    LCD wires plug into (GPIO 8/9, 5V, GND).
- Space under the tilted LCD is free for the backpack, its wiring, or anything else.
- LCD held by its four mounting holes (1602 standard: PCB ~80 × 36 mm, M3 holes on
  ~75 × 31 mm — **builder measures the owner's module** before finalising). The backpack's
  4-pin header exits to the **right** (as in IMG_6727).
- Printable on the owner's Bambu X1C without supports where possible; it will be printed
  with the owner's raft preset `0.20mm Raft Easy-Release @BBL X1C`.

## Non-goals

- Changing the existing case parts.
- Enclosing the LCD fully or protecting it; a bracket/frame is enough.

## My calls (not confirmed by the owner)

- Two side supports (left and right), each standing on that side's front and back corner
  holes and arching up so the middle stays open, plus an LCD frame between them; screwed
  together, so each part prints flat. Builder may choose a different split.
- Modelled as a parametric FreeCAD Python script (FreeCAD is installed) using the STEP for
  hole positions; output STL/3MF per part, plus a render to check the fit before printing.
- Tilt angle and height are parameters, so a reprint with a different angle is one edit.

## Left to the builder

- Exact part split, wall thicknesses, fillets, how the LCD screws in (M3 or M2.5 to match
  the module's holes), screw lengths, cable routing under the LCD.
- Where the deliverables live (suggest `hardware/lcd-hat/` in this repo: script + STLs).

# Open questions (owner)

None.
