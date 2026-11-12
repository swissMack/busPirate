# Bit Pirate Status LCD + LCD Hat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A 16×2 I²C LCD on the owner's Bit Pirate dock that shows how to connect at boot/HiZ and the mode's wiring once in a mode, held above the printed dock case by a printed, tilted "hat".

**Architecture:** A local firmware patch (`firmware/bitpirate-1.8-lcd.patch`) on geo-tp ESP32-Bit-Pirate v1.8 + the three existing patches. Pure text layout lives in a host-testable transformer; a bit-banged PCF8574/HD44780 driver on GPIO 8/9 sits behind an `LcdView`; a `CompositeDeviceView` lets the board keep its RGB LED view and add the LCD. The hat is a parametric FreeCAD script that checks itself against the case STEP and writes STLs.

**Tech Stack:** C++17 / Arduino-ESP32 / PlatformIO (`s3-devkit-n16-r8`, Unity `native-tests`), FreeCAD 1.x `freecadcmd` Python, Bambu Studio.

**Spec:** `docs/superpowers/specs/2026-11-11-bitpirate-lcd-design.md`

## Global Constraints

- Local only; never pushed upstream or to the owner's fork. Deliverable is `firmware/bitpirate-1.8-lcd.patch` in this repo, applied **after** mode-led, dock-pins and webui-start (only that order).
- Build env `s3-devkit-n16-r8`; flash app-only `firmware.bin` @ `0x10000` over the **UART port** (CP2102, `/dev/cu.usbserial-0001`, 460800) — keeps NVS (Wi-Fi) at 0x9000.
- LCD on **GPIO 8 = SDA, GPIO 9 = SCL**, bit-banged; must not touch `Wire` or `Wire1`. Add 8 and 9 to the s3-devkit `PROTECTED_PINS`.
- Probe addresses **0x27 then 0x3F**; no ACK at either → firmware behaves exactly as today.
- RGB mode LED behaviour unchanged.
- Screen text: 16 chars × 2 lines, always padded/truncated to exactly 16. Pins shown as `IO<n>` (dock silkscreen style), never `GPIO <n>`. Frequency/baud/other non-pin mappings never shown.
- Connection screen: Wi-Fi (`WiFiClient`/`WiFiAp`) → `Bit Pirate WiFi` / `<ip>`; serial → `Bit Pirate USB` / blank.
- Boot splash `Bit Pirate` / `1.8` (from `GlobalState::version`) for ~2 s. Backlight always on.
- Adapter boot modes → adapter name on line 1, line 2 blank.
- Wiring: backpack VCC→DevKit **5V**, GND→**G**, SDA→**8**, SCL→**9**; backpack 5 V pull-ups removed, 4.7 kΩ pull-ups to **3V3**. Direct first; diode in the 5 V lead is the fallback.
- Hat: on the four corner holes (70.9 × 64.6 mm), nothing above the POWER header, LCD tilted ~55–60° toward the probe-connector edge, prints flat without supports, owner's preset `0.20mm Raft Easy-Release @BBL X1C`.

## Review Focus

1. **Mode names longer than the field** (`INFRARED`, `ETHERNET`, `EXPANDER`) — the expected behaviour is a cut-off name, never a shifted or overflowing line. Test in Task 1.
2. **Modes whose mappings are all non-pin, or with >4 pins** (e.g. `LED` with `LED COUNT 16`, JTAG) — non-pin lines are dropped; more than four pins page through, nothing is silently lost. Tests in Task 1.
3. **Wi-Fi requested but the IP falls back to `0.0.0.0` → serial** — the screen must say USB, not show `0.0.0.0`. Test in Task 1.
4. **Mode change while a paging timer is mid-write** — no torn or mixed screen. Covered by the mutex in Task 3 and the hardware check in Task 5.
5. **`initialize()` called twice** (board init and dispatcher setup) — the splash shows once, no second 2 s stall. Check in Task 3 and Task 5.

---

## File Structure

Firmware work tree: `/Users/mackmood/Documents/GitHub/ESP32-Bit-Pirate-lcd` (new clone, never pushed).

| File (firmware tree) | Responsibility |
|---|---|
| `src/Transformers/LcdScreenTransformer.{h,cpp}` | Pure: config/terminal info → 16×2 screens. No Arduino. |
| `test/Transformers/test_LcdScreenTransformer.cpp` | Unity tests for the above. |
| `src/Boards/Common/Views/Lcd1602.{h,cpp}` | Bit-banged I²C + PCF8574 + HD44780 4-bit driver. |
| `src/Boards/Common/Views/LcdView.{h,cpp}` | `NoScreenDeviceView` subclass: splash, connection, pin pages, paging timer. |
| `src/Boards/Common/Views/CompositeDeviceView.h` | Forwards every `IDeviceView` call to two views. |
| `test/Views/test_CompositeDeviceView.cpp` | Unity test with two fake views. |
| `src/Boards/S3DevKit/S3DevKitBoard.h` | Hold `RgbLedView` + `LcdView` + composite. |
| `platformio.ini` | `PROTECTED_PINS` += 8, 9 for both s3-devkit envs; `LCD_SDA_PIN=8`, `LCD_SCL_PIN=9`. |

| File (this repo) | Responsibility |
|---|---|
| `firmware/bitpirate-1.8-lcd.patch` | The exported patch. |
| `docs/bitpirate.md` | New "Status LCD" section: wiring, resistor mod, diode fallback, apply order. |
| `hardware/lcd-hat/lcd_hat.py` | Parametric hat model, self-checks, STL + render export. |
| `hardware/lcd-hat/README.md` | Measurements used, screw list, print settings, assembly. |
| `hardware/lcd-hat/*.stl`, `render.png` | Generated outputs, committed. |

---

### Task 1: Firmware work tree + `LcdScreenTransformer`

**Files:**
- Create: `src/Transformers/LcdScreenTransformer.h`, `.cpp`; `test/Transformers/test_LcdScreenTransformer.cpp`
- Modify: `test/test_main.cpp` (include the `.cpp` and test file, call `runLcdScreenTransformerTests()`)

**Interfaces:**
- Produces:
  ```cpp
  using LcdScreen = std::array<std::string, 2>;   // each exactly 16 chars
  class LcdScreenTransformer {
  public:
      static LcdScreen splash(const std::string& version);
      static LcdScreen connection(TerminalTypeEnum type, const std::string& ip);
      static LcdScreen adapter(const std::string& name);
      // empty vector = mode has no pins → caller shows connection()
      static std::vector<LcdScreen> pinPages(const PinoutConfig& config);
  };
  ```
- Layout rules (the tests pin them):
  - Pins parsed from mappings matching `<NAME> GPIO <n>`; everything else dropped.
  - 1–2 pins: line 1 = mode (cut to 5, padded to 6) + name (cut to 4, padded to 5) + `IO<n>`; line 2 = `GND` padded to 6 + second pin the same way (blank if only one).
  - 3+ pins: four per page, two per line, each slot `<ab> IO<n>` padded to 8, where `<ab>` is a 2-letter abbreviation: MOSI→MO, MISO→MI, CLK/SCK/SCLK/CLOCK→CK, CS/CSN→CS, SDA→DA, SCL→CL, DATA/DI→DI, DO→DO, else first 2 letters.

- [ ] **Step 1: Create the work tree and prove the baseline**

```bash
cd /Users/mackmood/Documents/GitHub
git clone --branch v1.8 https://github.com/geo-tp/ESP32-Bit-Pirate.git ESP32-Bit-Pirate-lcd
cd ESP32-Bit-Pirate-lcd && git switch -c lcd
for p in mode-led dock-pins webui-start; do git apply /Users/mackmood/Documents/GitHub/busPirate/firmware/bitpirate-1.8-$p.patch; done
git add -A && git commit -qm "base: v1.8 + mode-led + dock-pins + webui-start"
pio test -e native-tests && pio run -e s3-devkit-n16-r8
```
Expected: tests pass, build SUCCESS. (If `webui-start` needs `git am`, use it — docs/bitpirate.md says `git am` keeps its message.)

- [ ] **Step 2: Write the failing tests** in `test/Transformers/test_LcdScreenTransformer.cpp`

```cpp
// helper: PinoutConfig cfg(mode, {mappings...})
test_connection_wifi:      connection(WiFiClient,"192.168.1.42") == {"Bit Pirate WiFi ","192.168.1.42    "}
test_connection_ap:        connection(WiFiAp,"192.168.4.1")[0] == "Bit Pirate WiFi "
test_connection_serial:    connection(SerialPort,"") == {"Bit Pirate USB  ","                "}
test_connection_zero_ip:   connection(WiFiClient,"0.0.0.0") == connection(SerialPort,"")
test_splash:               splash("1.8") == {"Bit Pirate      ","1.8             "}
test_adapter:              adapter("flashrom serprog") == {"flashrom serprog","                "}
test_i2c:                  pinPages(cfg("I2C",{"SDA GPIO 15","SCL GPIO 16","FREQ 100000"}))
                             == {{"I2C   SDA  IO15 ","GND   SCL  IO16 "}}
test_onewire:              pinPages(cfg("1WIRE",{"DATA GPIO 6"})) == {{"1WIRE DATA IO6  ","GND             "}}
test_spi_four:             pinPages(cfg("SPI",{"MOSI GPIO 13","MISO GPIO 10","CLK GPIO 12","CS GPIO 11"}))
                             == {{"MO IO13 MI IO10 ","CK IO12 CS IO11 "}}
test_three_pins:           pinPages(cfg("2WIRE",{"IO GPIO 11","CLK GPIO 12","RST GPIO 14"}))
                             == {{"IO IO11 CK IO12 ","RS IO14         "}}
test_five_pins_two_pages:  5 GPIO mappings → size()==2, page 2 line 1 holds the 5th pin
test_long_mode_name:       pinPages(cfg("INFRARED",{"TX GPIO 4"}))[0][0] == "INFRA TX   IO4  "
test_no_pins:              pinPages(cfg("LED",{"LED COUNT 16","apa102"})).empty()
                           pinPages(cfg("HIZ",{})).empty()
test_every_line_16:        for every screen above, each line .size()==16
```
(Write these as real `TEST_ASSERT_EQUAL_STRING` tests in a `lcd_screen_tests` namespace, like `test_PinoutTransformer.cpp`. Check the real mapping names for 1-Wire/2-Wire in `PinoutTransformer.cpp` and use those.)

- [ ] **Step 3: Run to see them fail** — `pio test -e native-tests` → compile error / FAIL on `LcdScreenTransformer`.
- [ ] **Step 4: Implement** `LcdScreenTransformer` per the Interfaces block (std only, no Arduino headers).
- [ ] **Step 5: Run** — `pio test -e native-tests` → all PASS, including existing tests.
- [ ] **Step 6: Commit** (firmware tree) — `git commit -am "lcd: screen text transformer"` (add new files first).

### Task 2: `Lcd1602` bit-banged driver

**Files:** Create `src/Boards/Common/Views/Lcd1602.{h,cpp}`

**Interfaces:**
- Produces:
  ```cpp
  class Lcd1602 {
  public:
      bool begin(uint8_t sdaPin, uint8_t sclPin);      // probes 0x27 then 0x3F; false = absent
      bool present() const;
      bool write(const LcdScreen& screen);             // false on any NACK
      uint32_t selfTest(uint32_t rounds);              // write+read-back PCF8574 port; returns mismatches+NACKs
      uint8_t address() const;
  };
  ```
- Bus: open-drain emulation — high = `pinMode(INPUT)` (external 3V3 pull-ups), low = `OUTPUT` + `LOW`; ~5 µs half-period (≤100 kHz). PCF8574 bit map (FC-113): P0 RS, P1 RW (always 0), P2 E, P3 backlight (always 1), P4–P7 D4–D7. Standard HD44780 4-bit init (0x3,0x3,0x3,0x2, then 0x28, 0x0C, 0x06, 0x01 with datasheet delays). `write()` only rewrites changed characters is **not** needed — whole-line writes are fine.
- `selfTest`: for `rounds` iterations write a pattern byte with E low (no LCD effect, RW=0, backlight on) and read the port back; count mismatches + NACKs. Restore the LCD afterwards.

- [ ] **Step 1: Implement** the class.
- [ ] **Step 2: Build** — `pio run -e s3-devkit-n16-r8` → SUCCESS (no unit test: it's pin-level; verified on hardware in Task 5).
- [ ] **Step 3: Commit** — `git commit -m "lcd: bit-banged PCF8574/HD44780 driver"`.

### Task 3: `LcdView`, `CompositeDeviceView`, board wiring, protected pins

**Files:**
- Create: `src/Boards/Common/Views/LcdView.{h,cpp}`, `src/Boards/Common/Views/CompositeDeviceView.h`, `test/Views/test_CompositeDeviceView.cpp`
- Modify: `src/Boards/S3DevKit/S3DevKitBoard.h` (and `.cpp` if `getDeviceView` lives there), `platformio.ini` (both `[env:s3-devkit]` and `[env:s3-devkit-n16-r8]`: `PROTECTED_PINS` += `8, 9`; add `-DLCD_SDA_PIN=8 -DLCD_SCL_PIN=9`), `test/test_main.cpp`

**Interfaces:**
- Consumes: `LcdScreenTransformer` (Task 1), `Lcd1602` (Task 2), `GlobalState::getTerminalMode()`, `getTerminalIp()`, `GlobalState::version`.
- Produces:
  ```cpp
  class CompositeDeviceView : public IDeviceView {
  public: CompositeDeviceView(IDeviceView& primary, IDeviceView& secondary);
      // every method forwards to primary then secondary;
      // getScreen/getSharedSpiInstance/getBrightness return primary's
  };
  class LcdView : public NoScreenDeviceView {
  public: LcdView(uint8_t sda, uint8_t scl);
      void initialize() override;   // begin(); splash 2 s only on the first call; no-op if absent
      void welcome(TerminalTypeEnum&, std::string&) override;  // connection screen
      void show(PinoutConfig&) override;   // pages, or connection screen if no pins
      void adapterMode(const std::string&, const std::string&, const std::vector<std::string>&) override;
      void clear() override;        // deliberately a no-op (keep last screen)
  };
  ```
- Paging: one FreeRTOS software timer (3000 ms, auto-reload) advances the page only when >1 page; all `Lcd1602` access under one mutex. If `LcdView` is absent every method returns immediately.

- [ ] **Step 1: Write the failing composite test** — `test_composite_forwards_show_to_both` (two `FakeDeviceView`s recording calls; after `composite.show(cfg)` both saw `cfg.getMode()=="I2C"`), `test_composite_forwards_welcome_to_both`, `test_composite_brightness_from_primary` (primary returns 24, secondary 99 → 24).
- [ ] **Step 2: Run** `pio test -e native-tests` → FAIL (no `CompositeDeviceView`).
- [ ] **Step 3: Implement** `CompositeDeviceView` (header-only), then `LcdView`; in `S3DevKitBoard.h` hold `RgbLedView ledView{LED_PIN}; LcdView lcdView{LCD_SDA_PIN, LCD_SCL_PIN}; CompositeDeviceView deviceView{ledView, lcdView};`.
- [ ] **Step 4: Run** `pio test -e native-tests` → PASS; `pio run -e s3-devkit-n16-r8` → SUCCESS; `grep -n "PROTECTED_PINS" platformio.ini` shows 8 and 9 in both s3-devkit envs.
- [ ] **Step 5: Commit** — `git commit -m "lcd: LcdView + composite view on S3 DevKit, protect GPIO 8/9"`.

### Task 4: Export the patch, document it

**Files:** Create `firmware/bitpirate-1.8-lcd.patch`; Modify `docs/bitpirate.md` (new section "Status LCD" after the webui-start section)

- [ ] **Step 1: Export** — in the firmware tree: `git diff <base-commit> lcd > /Users/mackmood/Documents/GitHub/busPirate/firmware/bitpirate-1.8-lcd.patch` (one patch covering Tasks 1–3; `<base-commit>` is the "base: …" commit from Task 1).
- [ ] **Step 2: Prove it applies** — fresh clone of v1.8 in the scratchpad, apply the four patches in order, `pio test -e native-tests && pio run -e s3-devkit-n16-r8` → PASS / SUCCESS.
- [ ] **Step 3: Write the docs section**: what the screen shows; wiring table (5V/G/8/9 on the DevKit's left header row, 4.7 kΩ to 3V3); the resistor removal; the diode fallback and when to use it; apply order; flashing app-only over UART.
- [ ] **Step 4: Commit** (this repo) — `git add firmware/bitpirate-1.8-lcd.patch docs/bitpirate.md && git commit -m "firmware: status LCD patch and docs"`.

### Task 5: Hardware bring-up (owner + agent)

Owner does the soldering and wiring; the agent flashes and checks over USB/HTTP. Record results in `docs/bitpirate.md`.

- [ ] **Step 1: Backpack mod** — owner photographs the backpack close up; agent identifies the two SDA/SCL pull-ups (confirm by meter: ~4.7–10 kΩ from SDA→VCC and SCL→VCC). Owner removes them, fits 4.7 kΩ from SDA and SCL to the 3V3 lead. Meter check: SDA→VCC and SCL→VCC now open.
- [ ] **Step 2: Wire** — VCC→5V, GND→G, SDA→8, SCL→9 on the DevKit's left row. Flash app-only over UART (Global Constraints).
- [ ] **Step 3: Contrast + splash** — power on; adjust the blue pot until text is crisp; splash `Bit Pirate / 1.8` shows ~2 s, once.
- [ ] **Step 4: Diode decision** — temporary build with `-DLCD_SELFTEST=10000` printing `selfTest()` result on the UART log at boot. **0 errors → direct wiring stays.** Any error, garbage, or no ACK → owner adds the diode in the 5 V lead, re-run until 0. Remove the flag, reflash.
- [ ] **Step 5: Behaviour checks** — USB boot → `Bit Pirate USB`; short-press Wi-Fi boot → `Bit Pirate WiFi` + IP that opens in the browser; `m i2c` → I2C screen IO15/IO16; `m spi`, `m uart`, `m 1wire` → matching pins; mode with >4 pins pages every ~3 s cleanly; back to HiZ → connection screen; mode LED colours unchanged; I²C scan of a target does **not** list 0x27/0x3F; LCD unplugged → boots and works as before.
- [ ] **Step 6: Commit** the results notes — `git commit -am "docs: status LCD verified on hardware"`.

### Task 6: LCD hat model

**Files:** Create `hardware/lcd-hat/lcd_hat.py`, `hardware/lcd-hat/README.md`; generated `hardware/lcd-hat/{side_left,side_right,lcd_frame}.stl`, `render.png`

**Interfaces:**
- Inputs (top of script, all in mm/degrees): `CASE_STEP` (`~/Downloads/dock_case_no_logo.step`), `TILT_DEG = 57`, `LCD_PCB = (80.0, 36.0)`, `LCD_HOLES = (75.0, 31.0)`, `LCD_HOLE_D`, `LCD_DEPTH_BEHIND` (backpack + header), `CLEARANCE_OVER_DEVKIT`, `WALL = 3.0`, `CORNER_HOLES` (read from the STEP: the four Ø3.1 Top Case holes, 70.9 × 64.6), `KEEPOUT_POWER` (box over the POWER header window, full height).
- Run: `/Applications/FreeCAD.app/Contents/Resources/bin/freecadcmd hardware/lcd-hat/lcd_hat.py` → prints `CHECK ... OK` lines and writes the STLs + render.

- [ ] **Step 1: Measure** — owner gives, with calipers: LCD PCB size, hole spacing and hole Ø, bezel thickness, depth from PCB front to the back of the backpack incl. header, and the DevKit's height above the Top Case. Record in `README.md`.
- [ ] **Step 2: Write the self-checks first** (script fails until the geometry exists): `CHECK no_interference_with_case` (hat ∩ Top Case and ∩ Bottom Case volume < 0.01 mm³), `CHECK power_header_clear` (hat ∩ `KEEPOUT_POWER` empty), `CHECK lcd_back_clears_devkit` (LCD+backpack box ∩ DevKit box empty, plus ≥ `CLEARANCE_OVER_DEVKIT`), `CHECK feet_on_corner_holes` (each foot's hole axis within 0.2 mm of a case hole), `CHECK parts_print_flat` (each part has a planar face ≥ 60 % of its footprint on z=0 in print orientation), `CHECK tilt` (LCD face normal at `TILT_DEG` ± 1° from the desk, facing the probe-connector edge).
- [ ] **Step 3: Run** → checks FAIL (no geometry).
- [ ] **Step 4: Build the geometry**: two side supports (one per side, foot on front and back corner hole, arching over the middle; foot hole Ø3.2 with a counterbore for the M3 head), an LCD frame screwed between them holding the module by its four holes; cable gap on the right for the backpack header.
- [ ] **Step 5: Run** → all `CHECK ... OK`; STLs and `render.png` (case + hat + LCD box, view from the probe-connector edge) written. Show the owner the render and iterate on `TILT_DEG`/height if asked.
- [ ] **Step 6: README** — screw list (exact M3 length = foot + Top Case stack + ≥ 4 mm into the Bottom Case pilot; head type; count; plus LCD screws), print settings (preset above, orientation per part, PLA/PETG), assembly order.
- [ ] **Step 7: Commit** — `git add hardware/lcd-hat && git commit -m "hardware: printable LCD hat for the dock case"`.

### Task 7: Print and fit (owner)

- [ ] **Step 1:** Agent opens the STLs in Bambu Studio (`open -a BambuStudio …`); owner selects the raft preset, slices, prints.
- [ ] **Step 2:** Owner assembles with the screws from the README; checks: POWER header usable, probe cable plugs in, SW1 and Wi-Fi button reachable, USB ports free, screen readable from the seat.
- [ ] **Step 3:** Record fit notes (and any parameter change + reprint) in `hardware/lcd-hat/README.md`; commit.
