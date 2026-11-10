# Bus Pirate 6 use-case catalogue (for a BP6-only MCP "recipe" server)

Researched 2026-11-10 from https://docs.buspirate.com/docs/ (device demos, adapters, command reference,
scope, logic analyzer, tutorials, binmode-reference/protocol-bpio2, hardware/bp6rev2) and the repo
(`buspirate/mcp/server.py`, `jobs.py`, `wiring.py`, `devices/`, `bp6/`, `boards/bp6.py`, `spiflash.py`).
dangerousprototypes.com returned 403 and was not used. Pin-to-mode assignments below come from the
docs' device demos and `boards/bp6.py`; confirm against `mode_pin_labels` in the BPIO2 status when a
recipe runs. Where the docs show Bus Pirate 5 output, BP6 behaviour is assumed identical unless noted.

Legend. Coverage: **covered** / **partial** / **gap**. Transport: **BPIO2** = drivable over the binary
interface; **terminal** = needs the text terminal (second CDC port) or another binmode; **either**.
Effort: S / M / L.

## 0. Reading guide: what BPIO2 can and cannot do

Facts from `protocol-bpio2` and `bp6/`:

- BPIO2 is one of several mutually exclusive **binmodes** (SUMP, BPIO2, CH32V003 SWIO, Follow-along LA, Legacy
  flashrom/avrdude, IRMAN, aIR, v3 unbrick). The `binmode` command picks one, on the *second* CDC port.
  So BPIO2 recipes can not run at the same time as PulseView/SUMP, FALA, flashrom/avrdude or AnalysIR.
  The terminal is the *first* port; the repo uses it only to select BPIO2 (`bp6/terminal.py`) and has a
  `release_to_terminal()` hand-over, so a hybrid recipe runner is feasible but must serialise the two.
- BPIO2 has three request types only: **Status** (version, mode, pull-ups, PSU, ADC mV per pin, IO
  dir/value, disk size, LED count), **Configuration** (mode + settings + peripherals) and **Data**
  (`start_main`, `start_alt`, `data_write[]`, `bytes_read`, `stop_main`, `stop_alt`; the bus syntax
  `[ { data r ] }`). Max write/read per request is reported by status (example: 512 bytes, packet 640).
- Configuration fields: `speed`, `data_bits`, `parity`, `stop_bits`, `flow_control`, `signal_inversion`,
  `clock_stretch`, `clock_polarity`, `clock_phase`, `chip_select_idle`, `submode`, `tx_modulation`,
  `rx_sensor`; plus `mode_bitorder_msb/lsb`, `psu_enable/disable`, `psu_set_mv`, `psu_set_ma`,
  `pullup_enable/disable`, `io_direction[_mask]`, `io_value[_mask]`, `led_color[]`, `led_resume`,
  `print_string`, `hardware_bootloader`, `hardware_reset`, `hardware_selftest`.
- `modes_available` in the doc's example: HiZ, 1WIRE, UART, HDUART, I2C, SPI, 2WIRE, 3WIRE, DIO, LED,
  INFRARED, JTAG. The Python client ships classes only for I2C, SPI, 1-Wire, UART and LED; 2WIRE/3WIRE/
  DIO/HDUART/INFRARED are selectable and use the generic Data request, but the docs give no data
  semantics for them (**unverified**). PS2 and USB sniffers are not listed (terminal only).
- **Not in BPIO2:** PWM / frequency generator (`g/G`), frequency measure (`f/F`), the `eeprom`, `flash`,
  `ddr4`, `ddr5`, `sle4442`, `usbpd`, `tcs3472`, `sht3x/4x`, `si7021`, `ms5611`, `tsl2561`, `i2c dump`,
  `scan` helpers, all sniffers (`sniff`), `bridge`, `gps`, `glitch`, `bluetag`, `tvbgone/irtx/irrx`,
  `logic`, scope, `macro`/`script`/`button`, disk commands, `ovrclk`, `otpdump`, self-test *result text*
  (BPIO2 can trigger `hardware_selftest` but the report is terminal output). Those terminal "device
  commands" are only convenience wrappers over raw bus bytes, so any that are plain I2C/SPI/1-Wire/UART
  transactions can be re-implemented host-side over BPIO2 (as `spiflash.py` already does).
- Existing driver (`bp6/modes.py`, `boards/bp6.py`): BPIO2 for **I2C, SPI (all 4 modes), UART (with async
  receive), 1-Wire (reset/read/write/ROM search), PSU, pull-ups, ADC readout**. Board capabilities:
  SUPPLIES, ONEWIRE, SPI_MODES, UART_BUFFERED, SPI_FLASH_PROGRAM, PSU_PROGRAMMABLE, PSU_READOUT. It has
  **no** raw-wire/bitbang, PWM, frequency count, sniffers or bridge, so `pwm`, `pwm_off`, `frequency`,
  `pins_read_voltage` exist in `BOARD_TOOLS` but are gated off on a BP6 (they need CAP_PWM / CAP_FREQUENCY /
  CAP_ADC). `measure_voltages` works because it also accepts `psu_current_readout`.

### Existing MCP tools (BOARD_TOOLS), as they apply to a BP6
`find_boards`, `connect`, `disconnect`, `board_status`, `wiring` (jobs: i2c, spi, uart, onewire, rawwire,
pins), `measure_voltages`, `power_plan` (extra confirmation above 3600 mV or with no current limit),
`power_apply`, `power_off`, `hiz`, `i2c_scan`, `i2c_read` (register read), `i2c_sensor` (catalogue:
AHT20, BMP280/BME280, LCD backpack; names list for ~15 more), `i2c_write`, `lcd_write` (HD44780 over
PCF8574, 0x27/0x3F), `spi_identify` (JEDEC 9F), `spi_transfer` (raw), `spi_sensor_read` (MAX31855),
`uart_send`, `uart_listen`, `onewire_scan` (+ DS18x20 via `devices`), `knowledge_*`.
`spiflash.py` has read/erase/program/verify but **no MCP tool** exposes them.

### BP6 hardware limits (hardware/bp6rev2)
- RP2350B, 133 MHz, 12 PIO state machines; 128 Mbit program flash; 1 Gbit NAND (about 100 MB usable) shown as USB disk.
- 8 buffered IO (74LVC1T45, production parts 1.2-5 V; some doc text says 1.65-5 V), 3-state, voltage
  measurement on every pin (CD4067 mux + op-amp buffers, ADC reads up to ~6.6 V but not beyond USB supply),
  toggleable **10 kohm pull-ups on every pin**, powered from VOUT/VREF (warn if no voltage there).
- "Look-behind" logic analyzer taps the pins *behind* the buffers (new in BP6), 62.5 MSPS, 131K samples, 8 ch.
- PSU: 0.8-5.0 V programmable (docs: working range 1-5 V), **300 mA rated**, current limit 0-500 mA digital
  fuse (0 = none), under-voltage limit (default 10 %, `-u`), current sense, backflow protection.
  Trip behaviour: supply cuts, terminal colours invert, bell. VOUT is an input too: an external voltage on
  VOUT/VREF powers the IO side (never fight it with the PSU on).
- Main header J301: 1 VOUT/VREF, 2-9 IO0-IO7, 10 GND (repo cable colours: VOUT red, IO0 orange, IO1 yellow,
  IO2 green, IO3 blue, IO4 purple, IO5 brown, IO6 grey, IO7 white, GND black). Aux 1 mm header J302:
  IO0-IO7 + GND for a probe.
- 18 SK6812 LEDs, 320x240 LCD, one button (scriptable), USB-C, ROM bootloader (drag UF2).
- Frequency measure only on odd pins (1,3,5,7); PWM pairs share a slice (adjacent pins share frequency).
- Docs for scope say "RP2040 0.5 Msps"; BP6 ADC path is the same mux design, so expect ~0.5 Msps audio-class.

---

# Part A. Capabilities (one entry per mode / global feature)

### A1. HiZ (safe mode)
- Doc: command-reference #HiZ. All outputs off, no pull-ups, max 5 V. Default at boot.
- Steps: `m hiz` (BPIO2: configuration request to HiZ / `hiz()`); PSU stays as is unless `w`.
- Risks: none; the recipe runner should always end here.
- Coverage: **covered** (`hiz`, `power_off`). Transport: BPIO2.

### A2. Power supply `w/W` (PPSU)
- Doc: command-reference `w/W`, tutorial-basics/power-supply. `W <V> <mA> [-u pct]`, e.g. `W 3.3 100`, `W 5 50`,
  `W 3.3 0` (no limit), `w` off. Reply: `Vreg output: 3.3V, Vref/Vout pin: 3.3V, Current: 3.0mA`.
- Settings: 0.8-5.0 V (1-5 V usable), 0-500 mA limit (0 = off), default 300 mA, under-voltage 10 %.
- Wiring: VOUT (red) to target VCC, GND (black) to target GND. LEDs/loads over ~300 mA need an external supply.
- BPIO2: `psu_enable`, `psu_set_mv`, `psu_set_ma`; status reports measured mV/mA and over-current flag.
- Risks: wrong voltage destroys parts (SHT4x is 3.6 V max, TSL2561/TCS3472x 3.6 V max, WS2812 wants 5 V);
  repo already gates >3.6 V and no-limit behind a second confirmation.
- Coverage: **covered** (`power_plan`, `power_apply`, `power_off`, `measure_voltages`). Transport: BPIO2.

### A3. Pull-up resistors `p/P`
- 10 kohm per pin, all pins switched together, powered from VOUT/VREF. Required for I2C, 1-Wire, HDUART, 2WIRE
  (open drain). Not wanted on push-pull SPI/UART or when the target has its own pull-ups (AT24C256 board has 10k).
- BPIO2: `pullup_enable/disable`. Risk: pull-ups to a target not powered can back-feed it.
- Coverage: **covered** (inside `power_plan`: `pullups` flag). Transport: BPIO2.

### A4. Frequency generator / PWM `g/G`
- `G` menu: pick pin, then e.g. `12.4khz`, duty `35%`; `g <pin>` off. Adjacent pin pairs share frequency.
  Used for SIM card clock (IO1), IR transmit (IO4), clocking smart cards, servo/audio tests.
- Wiring: output on the chosen IOn, GND common. Risk: low. Not in BPIO2.
- Coverage: **gap** (`pwm` tool exists but gated off for BP6). Transport: **terminal** (or a new BPIO2 extension upstream).

### A5. Frequency / duty measure `f/F`
- `f <pin>` once, `F <pin>` continuous: `Frequency IO7: 12.40KHz 80.65us (12400Hz), Duty cycle: 35.0%`.
  Odd pins only (IO1, IO3, IO5, IO7). Not in BPIO2.
- Coverage: **gap** (`frequency` gated off for BP6). Transport: **terminal**.

### A6. Voltage / ADC measurement `v/V`, bus syntax `v.<pin>`
- `v` voltage report: VOUT, current, every IO pin mV. In BPIO2 this is `status.adc_mv[8]` plus PSU mV/mA.
  Use to find target voltage before powering (the server instructions already require this).
- Coverage: **covered** (`measure_voltages`, `board_status`). Transport: BPIO2.

### A7. Auxiliary pins `a/A/@`, DIO mode
- `a 1` low, `A 1` high, `@ 1` input + read; unassigned pins only. In DIO mode `>0xff`, `>r`.
  BPIO2: `io_direction`/`io_value` with masks, status `io_value`.
- Use: reset lines, enable pins, bootstrap pins, relay-like toggling (5 V max, tens of mA only).
- Risk: driving a pin against a target output. Coverage: **gap** (no GPIO tool; `pins` wiring job exists).
  Transport: BPIO2 (set `io_direction/io_value`). Effort S.

### A8. Bus syntax: delays, repeat, bit count, bitwise
- `d`/`D` delay 1 us/1 ms (`D:10`), `:n` repeat, `.n` partial bits (`0x5a.4`), `r:n`; bitwise `^ / \ - _ .` (2WIRE,
  3WIRE, DIO only); `=` convert, `|` reverse bits; line limit 255 chars.
- BPIO2 has no delay or bitwise primitives; a recipe must sequence requests host-side.
- Coverage: partial (host-side timing only). Transport: BPIO2 for data; **terminal** for bitwise/partial-bit.

### A9. Bit order `l/L`, output format `o`, display `d`
- `L` LSB first; BPIO2 `mode_bitorder_msb/lsb`. `o`/`d` are display only. Coverage: **gap** (no tool), effort S.

### A10. Scripting: `macro`, `script`, `button`, `pause`
- `.mcr` macro files (`1:W 3.3 100`, `2:[0xa0 0][0xa1 r:5]`), `.scr` scripts (one command per line, cannot answer
  menu prompts), button short/long scripts (`button.scr`, `buttlong.scr`, do not persist after reboot), `pause -b`
  waits for the button. Files live on the NAND disk.
- Value for the MCP: a recipe could be *exported* as a `.scr` so the BP6 can run it standalone (button press).
- Risk: scripts run unattended with power commands. Coverage: **gap**. Transport: **terminal** + disk. Effort L.

### A11. Storage / USB disk `ls cd mkdir rm cat hex format label dump image`
- 1 Gbit NAND as FAT16 USB drive (about 100 MB), holds `BPCONFIG.BP`, macros, scripts, dumps (`flash read -f x.bin`,
  `eeprom read -f`), bitmap for `image`. Read-only vs read/write USB mode (tutorial usb-disk). Status shows disk
  size/used via BPIO2. Risk: `format` erases it. Coverage: **gap**. Transport: **terminal** / USB mass storage.

### A12. Configuration menu `c`
- Language, ANSI colour, toolbar, LCD screensaver, LED effect/colour/brightness; saved to `BPCONFIG.BP`
  (also `bpio_debug_enable:1` for BPIO2 debug). Coverage: **gap**, low value. Transport: terminal.

### A13. Self-test `~` (HiZ only)
- Remove everything from the pins first. Checks NAND, ADC subsystem (VUSB about 5 V), PSU enable (3.3 V, 50 mA),
  BIO float/short tests, LEDs; prints PASS/FAIL per block. BPIO2 can start it (`hardware_selftest`) but the
  report is terminal text. Risk: external devices can be damaged by test voltages. Coverage: **gap**. Transport:
  **terminal** (BPIO2 trigger only). Effort S-M.

### A14. Firmware update / bootloader `$`
- `$` (or BPIO2 `hardware_bootloader`) reboots to the RP2350 ROM drive; copy UF2. `reboot`, BPIO2 `hardware_reset`.
  Risk: a bad image; ROM bootloader cannot be erased. Coverage: **gap** (and arguably should stay a human step).

### A15. LCD display and scope `d`, `sr/ss/x/y/t`
- `d` then `2` selects Scope on the LCD; `sr {pin} {o|n|a}` runs it, `x`/`y`/`t` set timebase, volts, trigger.
  Any IO pin; about 0.5 Msps, so audio and slow analog, not fast digital. Output is on the 320x240 LCD, **not**
  in the terminal, so it is of little use to an AI client. Coverage: **gap**. Transport: **terminal**. Effort L, low value.

### A16. Logic analyzer: `logic` command, SUMP/PulseView, Follow-along (FALA)
- 62.5 MSPS (more if overclocked), 131K samples, 8 channels, single-pin trigger. `logic start|stop|hide|show|nav`,
  `logic -f 1000000 -o 8`. FALA triggers on every bus command; BP6 has a *second* buffer (look-behind) so it
  sees the pins, not just the bus. PulseView/SUMP and FALA are separate binmodes on the second CDC port
  (docs/binmode-reference/protocol-sump, protocol-faladata), conflicting with BPIO2.
- Use: "show me what actually went on the wires" after a failed transaction. Coverage: **gap**. Transport: **terminal**
  (`logic`) or **other binmode** (SUMP/FALA). A decoder over SUMP could return decoded I2C/SPI, effort L.

### A17. Mode: 1-Wire
- Pins: OWD (IO0 on the repo's BP6 wiring) + GND; open drain, pull-ups always (2k-10k; 10k onboard). `m 1wire`.
  Syntax: `{`/`[` reset + presence, `r`, bytes. Commands: `scan`, `ds18b20`, `eeprom list|dump|read|write|verify|erase|test|protect`.
- BPIO2: data requests with `start_main` = reset; repo has reset/read/write/search_rom.
- Coverage: **covered** for scan/ROM and DS18x20 (`onewire_scan`, `devices.ds18x20`); `eeprom` family **gap**.

### A18. Mode: UART
- `m uart`: baud (default 115200), 5-8 data bits, parity None/Even/Odd, 1/2 stop, flow control None/RTS-CTS,
  invert. Push-pull, 1.65-5 V. Pins: IO4 = Bus Pirate TX (to target RX), IO5 = RX (from target TX), GND.
  Syntax: `[` open + read with `r`, `{` open with async display, `]` close. Commands: `bridge` (USB-serial pass-through,
  exit with button), `gps`, `glitch`. 5 V max; RS-232 levels (+-13 V) are NOT allowed, use the Dual RS-232 plank.
- BPIO2: UART config and data, async receive (`is_async` responses); repo `uart_send`, `uart_listen`.
- Coverage: **covered** for send/listen; `bridge`, `gps`, `glitch` are terminal-only (**gap**). Wiring cross-over is the common failure.

### A19. Mode: HDUART (half-duplex UART)
- `m hduart`: one RXTX wire (IO0), RST on IO2 (`{` high, `}` low), open drain, pull-ups required. Same baud/parity/stop
  menu. Used for SIM and bank cards (needs a clock on IO1 from the frequency generator).
- BPIO2: listed in `modes_available`; no Python data class (**unverified**). Coverage: **gap**. Transport: terminal.

### A20. Mode: I2C
- `m i2c`: speed 1-1000 kHz (default 400), clock stretching on/off. Pins IO0 = SDA, IO1 = SCL. Open drain: pull-ups always.
  Syntax `[0xA0 0x00 [0xA1 r:4]`. 7-bit address shifted: `0x50` = `0xA0` write / `0xA1` read. Commands: `scan [-v]`,
  `sniff` (up to 500 kHz), `i2c dump|read -a 0x50 -w 1 -r 0 -b 64 -f file`, `eeprom ...`, `ddr4`, `ddr5`, `usbpd`,
  `tcs3472`, `sht3x`, `sht4x`, `si7021`, `ms5611`, `tsl2561`.
- BPIO2: complete (write, read, transfer with auto-restart, scan). Repo speeds: `I2C_SPEEDS_MODERN`.
- Coverage: **covered** for scan/read/write/sensor; vendor helper commands are terminal wrappers (see Part B).

### A21. Mode: SPI
- `m spi`: speed 1-62500 kHz (default 100), 4-8 data bits, polarity idle low/high, phase leading/trailing, CS active
  low (default)/high. Push-pull 1.65-5 V. Pins: IO4 MISO, IO5 CS, IO6 CLK, IO7 MOSI. Syntax `[0x9F r:3]`, `{` full-duplex
  mode. Commands: `flash probe|dump|read|write|verify|erase|test` (SFDP aware, `-e` erase first, `-v` verify, `-y` skip
  confirm), `eeprom` (25xx/95xx/93xx Microwire).
- BPIO2: all four SPI modes, `chip_select_idle`, transfer and full-duplex transfer. Repo has `spi_transfer`, `spi_identify`, `spiflash.py`.
- Coverage: **partial** (identify + raw; flash read/erase/write/verify exist in the library but no tool).

### A22. Mode: 2WIRE
- `m 2wire`: speed 1-1000 kHz (default 400). Open drain, pull-ups required. IO0 SDA, IO1 SCL, IO2 RST (`{`/`}`),
  I2C-style start/stop but no ACK bit, bitwise commands. Commands: `sniff` (no-ACK protocols, 500 kHz max), `sle4442`.
- BPIO2: listed; data semantics undocumented (**unverified**). Coverage: **gap**. Transport: terminal.

### A23. Mode: 3WIRE
- `m 3wire`: speed 1-3900 kHz, CS polarity. SPI-like pins (MOSI/MISO/CLK/CS) with bitwise `^ / \ - _ .`. Used for
  Microwire-style chips and odd bit-banged protocols. BPIO2: listed (**unverified**). Coverage: **gap**.

### A24. Mode: DIO
- No protocol; all 8 pins free; push-pull tri-state. `>0xff`, `>r`, `>@.0`; combine with `g/G`, `f/F`. BPIO2 `io_*` fields.
  Coverage: **gap** (see A7). Effort S.

### A25. Mode: LED
- `m led`: type 1 WS2812/SK6812/NeoPixel (one wire, IO0 SDO), 2 APA102/SK9822 (SDO + SCL), 3 onboard 18 SK6812.
  Syntax: `[` reset, then colours as 24-bit values with bit count: `0xFF0000.24 0x00FF00.24 0x0000FF.24` (**note order: GRB**
  for WS2812). APA102: `[` start frame, `]` end frame, frame = `111` + 5-bit brightness + B,G,R.
- BPIO2: LED class (`set_rgb`, `set_rgbw`, `set_multiple_rgb`, `clear`) and `led_color[]` for the onboard LEDs.
- Power: up to 60 mA per LED at full white; PSU is 300 mA, so over about 5 LEDs use an external 5 V supply (share GND).
- Coverage: **gap**. See B-LED entries.

### A26. Mode: INFRARED (RAW aIR, NEC, RC5)
- `m infrared`: protocol, TX modulation 20-60 kHz (38 default), RX sensor (38 kHz barrier, 36-40 kHz demod, 56 kHz demod).
  Pins: IO1 LERN (learner 20-60 kHz), IO3 BARR (38 kHz barrier), IO4 IRTX, IO5 38K demod, IO7 56K demod. Commands (RAW):
  `tvbgone`, `irtx`, `irrx`. BPIO2 config has `submode`, `tx_modulation`, `rx_sensor` (**unverified for data**).
- The docs' "IR Remote Control" device demo is an empty placeholder. Needs the IR Toy plank (B-IR). Coverage: **gap**.

### A27. Mode: JTAG (blueTag pin finder only)
- `m jtag`: not a JTAG master. `bluetag jtag -c 8`, `bluetag swd -c 8`, `-d` no pulsing. Output example
  `TDI=IO0 TDO=IO3 TCK=IO4 TMS=IO2` + IDCODE (`0x59602093 mfg Xilinx`). Set PSU/VREF to the target IO voltage. See B-JTAG. Terminal only.

### A28. Mode: PS2 and USB sniffers
- Need the PS/2 & USB Keyboard Sniffer plank. `sniff` powers the bus itself (5 V for PS/2, 3.3 V for USB), decodes keys.
  Terminal only; interactive single-key UI for USB. See B-SNIFF.

### A29. Binmodes for host software: Legacy (flashrom / avrdude), aIR (AnalysIR), IRMAN, SWIO, v3 unbrick
- `binmode` then `5` (Legacy): terminal locks and the power supply voltage/limit is asked (use 3.30 V, 150 mA); exit by
  re-plugging. `flashrom -p buspirate_spi:dev=COMxx,serialspeed=115200,spispeed=1M`, AVRDUDE >= 8.3 for ICSP (RESET on CS).
  These take over the same port BPIO2 uses. See B-FLASHROM, B-AVR.

---

# Part B. Device and adapter use cases, grouped by bus

Common recipe skeleton: (1) `wiring` card; (2) ask target voltage / `measure_voltages`; (3) `power_plan`; (4) owner
confirms; (5) `power_apply`; (6) mode config; (7) transaction; (8) `hiz`, `power_off`.

## B1. I2C

### B1.1 24C02 smart IC card (I2C)
- Doc: /docs/devices/24c02/. I2C, 100 kHz (up to 400), address 0x50. 5 V, pull-ups needed (10k onboard, `P`).
- Wiring (card contacts): IO0 to C7 I/O (SDA), IO1 to C3 CLK (SCL), VOUT to C1 VCC, GND to C5. Use the IC card plank.
- Steps: `W 5` ; `P` ; `m i2c` 100 ; `scan` (expect 0x50, 0xA0/0xA1) ; `[0xA0 0x00 [0xA1 r:16]` ; or `i2c dump -a 0x50 -w 1 -b 256`.
  Success: 256 bytes (page size 8). Write: `[0xA0 addr data...]` then wait 5 ms.
- Risks: 5 V only; write overwrites card data.
- Coverage: **covered** for read (`i2c_scan`, `i2c_read`), writes via `i2c_write`; no 256-byte dump helper (partial). BPIO2: yes. Effort S.

### B1.2 Generic I2C EEPROM 24xx (24C01 to 24xM02, AT24C256 board)
- Docs: /docs/devices/at24c256/, command `eeprom`, identify-serial-memory-chips. I2C 100-400 kHz (1 MHz for 24FC at 5 V),
  address 0x50-0x57 (A0-A2; 24C04-16 use block-select bits in the address), voltage 1.7-5.5 V by family (AT24C/24C 2.7+, 24LC 2.5+,
  24AA 1.7+, 24FC 1.8+); AT24C256 board has its own 10k pull-ups.
- Wiring: IO0 SDA, IO1 SCL, VOUT to VCC (5 V in the demo, 3.3 V is fine), GND; WP low.
- Steps (terminal): `eeprom list`; `eeprom dump -d 24x256 -s 0 -b 64`; `eeprom read -d 24x256 -f e.bin -v`; `eeprom write -d 24x256 -f e.bin -v`;
  `eeprom erase -d ... -v` (writes 0xFF); `eeprom test -d ...` (erase + 0xAA/0x55 patterns). Address bytes: 1 for up to 24C16, 2 above.
  No non-destructive autodetect; size must be named (a wrong size silently wraps). BPIO2 equivalent: `write_then_read` with 1-2 address bytes, 64-byte page writes + 5 ms.
- Risks: erase/write destroy data; read the whole chip to a file first.
- Coverage: **partial** (`i2c_read`/`i2c_write` do single transfers; no dump/restore/verify). Transport: either (BPIO2 host-side). Effort M.

### B1.3 MB85RC256V FRAM (I2C)
- Doc: /docs/devices/mb85rc256v/. 2.7-5.5 V (3.3 V), 400 kHz (1 MHz max), address 0x50 + A0-A2, WP high = protected; 2-byte address.
- Wiring: IO0 SDA (pin 5), IO1 SCL (pin 6), VOUT to VDD (8), GND, WP low.
- Steps: `W 3.3` ; `P` ; `m i2c` 400 ; `scan` ; `[0xA0 0x00 0x00 0x48 0x65 0x6C 0x6C 0x6F]` ; `[0xA0 0x00 0x00 [0xA1 r:5]`. No write delay (FRAM).
- Coverage: **partial** (generic tools work; no named recipe). BPIO2 yes. Effort S.

### B1.4 SHT30 / SHT31 / SHT35 humidity + temperature
- Doc: /docs/devices/sht30-sht31-sht35/. I2C 400 kHz, address 0x44 (ADDR low) or 0x45, 2.15-5.5 V (3.3 V), pull-ups on.
- Wiring: IO0 SDA, IO1 SCL, VOUT to VDD, GND.
- Steps: `scan` (shows 0x44; ignore 0x00 general call) ; `sht3x` ; raw: `[0x88 0x24 0x00]` wait 16 ms `[0x89 r:6]`
  (T msb,lsb,crc,H msb,lsb,crc). Convert: T = -45 + 175*raw/65535 C; RH = 100*raw/65535 %. Success: `Temperature: 25.07 C, Humidity: 78.37 %`.
- Coverage: **gap** (`i2c_sensor` catalogue has AHT20, BMP280/BME280; no SHT3x). BPIO2 yes. Effort S.

### B1.5 SHT40 / SHT41 / SHT43 / SHT45
- Doc: /docs/devices/sht40-sht41-sht43-sht45/. 400 kHz, 0x44, **1.08-3.6 V only, not 5 V tolerant**. Does not ACK its read address in a scan.
- Steps: `sht4x` ; raw: `[0x88 0xFD]` wait 8.3 ms `[0x89 r:6]`. T = -45 + 175*raw/65535, RH = -6 + 125*raw/65535 (clamp 0-100).
- Risk: setting 5 V kills it; the recipe must cap at 3.6 V. Coverage: **gap**. Effort S.

### B1.6 SI7021 / HTU21 / SHT21
- Doc: /docs/devices/si7021/. 400 kHz, 0x40, 1.9-3.6 V. Raw: `[0x80 0xF5]` (humidity no-hold), `[0x80 0xF3]` (temperature), then `[0x81 r:3]`;
  serial number reads possible. `si7021` prints `Humidity 71.05%, Temperature 18.79C, Serial 0x...`. Coverage: **gap**. Effort S.

### B1.7 TCS3472x colour sensor (TCS34725 breakouts)
- Doc: /docs/devices/tcs3472x/. 400 kHz, address 0x29, 2.7-3.3 V (3.3 V), VIN pin on breakouts is 3.3-5 V.
- Steps: `tcs3472 -g 16 -i 256` (shows R/G/B on the 18 LEDs too) ; raw: enable (reg 0x00 |= 0x03), read 0x14-0x1B (clear, red, green, blue,
  16-bit LE with command bit 0x80/auto-increment 0xA0). Coverage: **gap**. Effort S-M.

### B1.8 TSL2561 lux sensor
- Doc: /docs/devices/tsl2561/. 400 kHz, address 0x39 (ADDR floating; 0x29/0x49 by pin), 2.7-3.6 V. Output `ID: 5 REV: 0 Chan0: 13868 Chan1: 13868 LUX: 81`.
  The repo's names list already recognises 0x39 as TSL2561. Coverage: **gap** for reading (name only). Effort S-M (lux formula).

### B1.9 MS5611 pressure + temperature
- Command `ms5611`; only in the command reference (no device page). Address 0x76/0x77, 3.3 V. Needs PROM calibration + second-order
  compensation. Coverage: **gap** (BMP280 is covered by `i2c_sensor`). Effort M.

### B1.10 DDR4 SPD EEPROM (DDR4 plank)
- Docs: /docs/devices/ddr4/, /docs/overview/ddr4-ram-i2c-adapter/. I2C, SPD at 0x50-0x57, plank takes 5 V on VOUT and makes 3.3 V.
- Wiring (plank): VOUT 5 V, IO0 SDA, IO1 SCL, GND on the main header; SA0 and HVFB pins for the **optional external 9 V** (battery) that is
  needed only to lock/unlock write protection.
- Steps: `W 5` ; `m i2c` ; `ddr4 probe` (type, size, vendor, CRC check) ; `ddr4 dump -s 0x149 -b 32` ; `ddr4 read -f ddr4.bin` ; `ddr4 verify -f` ;
  `ddr4 crc -f` / `ddr4 patch -f` (file only). Write: `ddr4 unlock` (9 V on SA0) then `ddr4 write -f ddr4.bin` (512 byte image, 2 pages via page-select 0x36/0x37 commands).
- Risks: **write can brick the module's SPD (it will no longer boot)**; unlock needs 9 V; do not insert a powered/installed module. Read-only recipes are safe.
- Coverage: **gap**. Transport: terminal for write/lock; read/probe could run over BPIO2 (page select by address-only writes). Effort M (read), L (write).

### B1.11 DDR5 SPD hub (DDR5 plank)
- Docs: /docs/devices/ddr5/, /docs/overview/ddr-ram-i2c-adapter/. I2C 3.3 V level (plank level-shifts HSDA/HSCL), module power 5 V BULK_VIN, PWR_EN to 3.3 V,
  HSA to GND (offline mode, address 0x50), PWR_GOOD LED.
- Steps: `ddr5 probe` (SPD type, revision, vendor, CRC of JEDEC blocks 0-7, protection) ; `ddr5 dump -s 0x280 -b 48` ; `ddr5 read -f` / `verify -f` ;
  `ddr5 crc -f` / `patch -f` ; `ddr5 lock|unlock -b 0-15` (64-byte blocks; unlock needs HSA grounded) ; `ddr5 write -f` (file **must be exactly 1024 bytes**).
- Risks: write can brick the SPD; no 9 V needed on DDR5. Coverage: **gap**. Same transport notes as DDR4. Effort M/L.

### B1.12 USB Power Delivery sink (AP33772S plank)
- Doc: /docs/overview/usbpd-adapter/ and command `usbpd`. I2C. Profiles to 21 V (SPR/PPS) and 28 V (AVS/EPR). `usbpd status`,
  `usbpd request -p 2`, `usbpd request -p 7 -v 7500 -c 3000`, `usbpd reset`. Wiring: plank on the main header (I2C + VOUT).
- Risks: **the plank can output up to 28 V on its own pins**; wrong profile on a target = damage. 30 V/500 mA fuse on the plank. Coverage: **gap**. Terminal (AP33772S registers possible over BPIO2). Effort M.

### B1.13 HD44780 LCD with PCF8574 backpack
- Not in the docs; repo recipe. I2C 0x27 or 0x3F, 5 V typical (backpack contrast pot), pull-ups. Coverage: **covered** (`lcd_write`, `devices/hd44780.py`). BPIO2 yes.

### B1.14 Other I2C sensors already in the repo catalogue (not in docs)
- AHT20 (0x38), BMP280/BME280 (0x76/0x77), named only: HMC5883L, ADXL345, ADS1115/LM75, DS1307/DS3231, MPU-6050, INA219, SSD1306, PCF8574/MCP23017, BMP180, MLX90614. Coverage: AHT20/BMP/BME **covered**, rest names only (`i2c_scan` names them). BPIO2 yes.

### B1.15 I2C sniffer
- `sniff` (max 500 kHz, `-q`, `-r`, `-7`); listens to a live I2C bus. Wiring: IO0 SDA, IO1 SCL, GND to the target bus. Terminal only. Coverage: **gap**. Effort M (a terminal bridge) .

### B1.16 Qwiic / Stemma / Grove / Breakout Garden quick-connect plank
- /docs/overview/qwiic-stemma-breakout-garden-grove-adapter/: plank maps Bus Pirate header to the I2C connectors (SDA, SCL, V+, GND). Wiring card only; voltage matters (Qwiic 3.3 V). Coverage: **covered** by `wiring` (add a connector note). Effort S.

## B2. SPI

### B2.1 SPI NOR flash: probe, dump, backup (W25Qxx and similar)
- Docs: /docs/devices/spi-flash-chips/, /docs/devices/w25q64/, adapters. SPI mode 0, 100 kHz to about 10 MHz (clones: stay at 10 MHz or less; long cable), 3.3 V
  (W25Q 2.7-3.6 V; **5 V kills it**), CS active low, **WP and HOLD must be high**.
- Wiring (SPI flash adapter plank, DIP8/SOP8/WSON8): IO2 to HOLD (7), IO3 to WP (3), IO4 to MISO/DO (2), IO5 to CS (1), IO6 to CLK (6), IO7 to MOSI/DI (5),
  VOUT to VCC (8), GND to 4. Bare chip: same pins; for a chip on a board hold its WP/HOLD up with IO2/IO3 or VOUT.
- Steps: `W 3.3 50` ; `m spi` 1 MHz ; `[0x9F r:3]` (e.g. `EF 40 17` Winbond 8 MB) ; `flash probe` (SFDP: capacity, 4/32/64 KB erase) ; `flash read -f dump.bin` ;
  `flash verify -f dump.bin`. Success: JEDEC ID matches, capacity as expected, verify clean.
- Coverage: **partial** (`spi_identify` gives JEDEC + capacity; reads/erase/program/verify exist in `spiflash.py` but are **not exposed**). BPIO2: yes. Effort M (add `spi_flash_dump`, 512-byte chunks).

### B2.2 SPI NOR flash: erase / write / verify / test
- Commands `flash erase`, `flash write -f x.bin -e -v`, `flash test` (full erase, write, verify; confirmation prompt, `-y` skips). Manual: `[0x06]` write enable,
  `[0x20 a2 a1 a0]` 4 KB sector erase, `[0xD8 ...]` 64 KB block, `[0xC7]` chip erase, `[0x02 a2 a1 a0 data<=256]` page program, `[0x05 r]` poll WIP.
- Risks: **destructive**, chip erase takes tens of seconds; dump a backup first; confirm twice. In-circuit flash on a live board needs the host held in reset. Coverage: **partial** (library only; no tool). Effort M.

### B2.3 SPI EEPROM 25xx / 95xx and Microwire 93xx
- Docs: identify-serial-memory-chips, command `eeprom`. SPI EEPROM (25LC040, AT25040, M95...) 1.7/1.8/2.5-5.5 V; commands READ 0x03, WRITE 0x02, WREN 0x06, RDSR 0x05, WRDI 0x04;
  WP and HOLD high. `eeprom dump|read|write|verify|erase|test|protect -d 25x020`; `-t` tests protection, `-p 0b11` sets block protect, `-w` WPEN.
  Microwire 93x uses 3WIRE-like timing (docs say the SPI `eeprom` command handles it; ORG pin selects x8/x16).
- Coverage: **gap**. Transport: terminal for the `eeprom` command; plain 25xx read/write works over BPIO2. Effort M.

### B2.4 SPI FRAM (FM25xx, MB85RSxx)
- identify-serial-memory-chips: same opcodes as 25xx EEPROM but no write delay and no page limits. Coverage: **gap**, effort S on top of B2.3.

### B2.5 In-system AVR programming (avrdude over the Legacy binmode)
- Doc: /docs/software/avrdude/. SPI to the ICSP header: IO7 MOSI, IO4 MISO, IO6 SCK, IO5 CS to RESET, GND (+ VCC if the board is not self-powered; docs say power the target externally).
  Needs AVRDUDE newer than 8.3; target 3.3 V or 5 V to match.
- Steps (terminal): `binmode`, select 5 (Legacy), answer PSU prompts, then `avrdude -c buspirate -p m32u4 -P COMxx -v`. The terminal then locks; **exit by replugging**.
- Risks: wrong fuses brick (can need HV programming). Coverage: **gap**. Transport: **other binmode** (not BPIO2; incompatible with BPIO2 until replug). Effort L (lifecycle) .

### B2.6 Flashrom on a BIOS/SPI flash chip
- Doc: /docs/software/flashrom/. Legacy binmode; `flashrom -p buspirate_spi:dev=COMxx,serialspeed=115200,spispeed=1M -c "W25Q64JV-.Q" -r flash.bin`. Asks PSU: 3.30 V and 150 mA.
  Wiring as B2.1. Risk: board-level flash needs the board off and held in reset; writes can brick. Coverage: **gap**. Transport: **other binmode**. Effort L.

### B2.7 MAX31855 thermocouple (SPI)
- Not in docs. Repo: `spi_sensor_read`. Coverage: **covered**. BPIO2 yes.

### B2.8 JEDEC ID lookup
- Command `jep106 0x00 0x2c` names a vendor; the repo has `JEDEC_MANUFACTURERS` (9 makers) used by `spi_identify`. Coverage: partial (small table). Effort S.

## B3. 1-Wire

### B3.1 DS18B20 temperature sensor
- Doc: /docs/devices/ds18b20/. 3.3 V (3.0-5.5), 100 mA limit, pull-ups on. Wiring: IO0 to DQ, VOUT to VDD, GND (parasite power not covered).
- Steps: `m 1wire` ; `scan` (`28 5c aa ... DS18B20`) ; `ds18b20` (skip ROM, **one device only**: `Temperature: 23.688`) ; raw: `[0xCC 0x44]` wait 750 ms, `[0xCC 0xBE r:9]`;
  addressed read with `0x55 <8 byte ROM>` for several sensors. Config register `0xCC 0x4E th tl cfg` sets 9-12 bit resolution (0x1F/0x3F/0x5F/0x7F).
- Coverage: **covered** (`onewire_scan` returns ROMs and DS18x20 temperature through `devices.ds18x20`). BPIO2: yes. Effort S (done).

### B3.2 1-Wire EEPROM DS2431 / DS24B33
- Command `eeprom` in 1-Wire mode; 2.8-5.25 V; pull-up (add 2k external if writes fail); `eeprom list|dump|read|write|verify|erase|test|protect -d ds2431`. Skip-ROM, one chip.
  DS2431 128 B (8 B pages, 2 address bytes), DS24B33 512 B. Risks: write/erase; **protect** bits can be one-time. Coverage: **gap** (names the family 0x2D only). BPIO2: scratchpad commands doable. Effort M.

### B3.3 Other 1-Wire devices
- Names in repo: DS1990A iButton (0x01), DS2438, DS2408 I/O. Read ROM works via `onewire_scan`. Coverage: names only.

## B4. UART

### B4.1 Serial console / bootloader sniff of an unknown UART
- Mode UART, 115200 8N1 default (try 9600, 38400, 57600). Wiring: IO4 (TX) to target RX, IO5 (RX) to target TX, GND; **target powered by itself; do not use the PSU unless it is a 3.3 V module**. Common ground essential; target levels over 5 V (RS-232) need the Dual RS-232 plank.
- Steps: `m uart`, `[`/`{`, read; `bridge` for interactive console. Success: readable text; garbage means wrong baud (autodetect idea: try each).
- Coverage: **covered** (`uart_listen`, `uart_send`, baud list); `bridge` terminal-only; baud autodetect is a **gap** (a recipe loop). BPIO2: yes. Effort S.

### B4.2 NMEA GPS module
- Doc: /docs/devices/nmea-gps/. UART 9600 8N1 (newer 38400/115200), 3.3 V module powered from VOUT (about 20 mA), IO4 to GPS RX, IO5 to GPS TX, GND.
- Steps: `W 3.3` ; `m uart` 9600 ; `gps` (decoded lat/lon/fix, press a key to stop) or `bridge` (raw `$GNRMC...`).
  BPIO2 equivalent: `uart_listen` for 2-5 s and parse `$..RMC/GGA` host-side (checksum, convert ddmm.mmmm). Success: "A" valid fix, lat/lon, satellites; indoors expect "V" no fix.
- Coverage: **partial** (`uart_listen` returns bytes; no NMEA decoding). Effort S.

### B4.3 UART glitch of a target (fault injection)
- Doc: /docs/devices/uart-glitch-command/ (Arduino Uno password demo). Needs an external glitch FET/crowbar on VCC. Wiring: TX/RX to target, target powers the IO side (**do not enable the PSU**), IO0 = trigger output, IO1 = ready input. `glitch -c`.
- Risks: intentionally damages/crashes targets; security research only. Coverage: **gap**, **terminal**, effort L, low priority.

### B4.4 RS-232 devices (Dual RS-232 plank)
- /docs/overview/dual-rs232-adapter/: MAX3232 level shifter, male DTE and female DCE DB9. Same UART mode; the plank connects to IO4/IO5 (TX/RX) and VOUT 3.3-5 V. F:F cross-over cable for loopback; `monitor`-style loopback test. Coverage: **covered** as UART with an extra wiring card. Effort S.

### B4.5 MIDI
- UART at 31250 8N1, opto-isolated current-loop adapter needed (5 V, 5 mA). Coverage: **gap**, niche. Effort S.

## B5. HDUART / smart cards

### B5.1 SIM card / bank IC card ATR (HDUART, ISO 7816-3)
- Doc: /docs/devices/sim-bank-ic-cards/, plank /docs/overview/sim-iccard-adapter/. HDUART 9600 baud, 8 data bits, **even parity, 2 stop bits**; 3.3 V, pull-ups on.
- Wiring: IO0 to C7 I/O (RXTX), IO1 to C3 CLK (PWM clock, `G` about 3.5-4 MHz, typical 1-5 MHz), IO2 to C2 RST, VOUT to C1 VCC, GND to C5.
- Steps: `W 3.3` ; `P` ; `m hduart` ; `G` (IO1 clock) ; reset: `}` low, `{` high ; `[` then read ATR (starts `3B ...`); `bridge` for APDU exchange (`00 A4 ...`).
- Risks: wrong voltage (cards are class A/B/C 5/3/1.8 V) can kill the card; PIN attempts block cards. Never brute-force a PIN.
- Coverage: **gap**. Needs PWM, so **terminal**. Effort L.

### B5.2 SLE4442 smart card (2WIRE)
- Doc: /docs/devices/sle4442/. `m 2wire` 20 kHz (cards top out near 50 kHz); **5 V**; pull-ups. Wiring: IO0 SDA (C7), IO1 SCL (C3), IO2 RST (C2), VOUT 5 V (C1), GND (C5).
- Steps: `sle4442 init` (ATR `A2 13 10 91`, remaining PSC attempts 3 of 3) ; `sle4442 dump [-s 6 -b 32 | -f f.bin]` (256 B data + 4 B security + 4 B protection) ;
  `unlock -p 0xffffff` ; `write -a 0xff -v 0x88` ; `erase` (0x32-0xFF) ; `psc -p old -n new` ; `protect -v 0xffffffff` (one way).
- Risks: **three wrong PSC attempts permanently lock the card**; protect bits are irreversible. Coverage: **gap**. Terminal. Effort M-L.

### B5.3 2WIRE sniffer
- `sniff` for 8-bit I2C-like protocols with no ACK (SLE4442). Terminal only. Gap, low priority.

## B6. LED

### B6.1 Onboard 18 SK6812 LEDs
- `m led` then type 3, or BPIO2 `led_color[]` (0xRRGGBB list) and `led_resume`; the board LED effects are set with `c`. No wiring, no power. Risk: none.
- Coverage: **gap** but trivially useful for "identify this board" or status. BPIO2 yes. Effort S.

### B6.2 WS2812 / SK6812 / NeoPixel strip
- Doc: /docs/devices/ws2812-sk6812-neopixel/. LED mode type 1. 5 V data compatible (IO buffer must follow 5 V, so `W 5` even if the strip has its own supply).
- Wiring: IO0 (SDO) to DIN, GND to GND; LEDs on external 5 V (more than about 5 LEDs: 60 mA each). Small strips from VOUT with a 300 mA limit.
- Steps: `m led` ; `W 5 300` ; `[` reset ; `0xFF0000.24 0x00FF00.24 0x0000FF.24` (order is **GRB**: first byte green) ; success is the lit LEDs.
- Risks: current (set the limit, tripped supply cuts out), brightness/eye safety, wrong data direction (DIN not DOUT). BPIO2: LED class. Coverage: **gap**. Effort S.

### B6.3 APA102 / SK9822 (DotStar) strip
- Doc: /docs/devices/apa102-sk9822/. LED type 2. Wiring: IO0 SDO to SDI/DI, IO1 SCL to CKI, GND; 5 V external for strips. Frame: start `[` (0x00000000), per LED `111bbbbb BB GG RR`, stop `]` (0xFFFFFFFF). Coverage: **gap**. Effort S.

## B7. Infrared

### B7.1 IR receive / learn / transmit (IR Toy v3 plank, RAW/NEC/RC5)
- Docs: /docs/overview/infrared-toy-v3/, /docs/devices/infrared-remote-control/ (placeholder). Plank: 38 kHz demodulator receiver, 56 kHz receiver, learner (20-60 kHz), barrier receiver, two Vishay TSAL LEDs on a constant-current driver
  (jumper selects about 100/200/300 mA; keep pulsed under 50 % duty). Pins: IO4 IRTX, IO5 38K, IO7 56K, IO3 BARR, IO1 LERN; supply 5 V (`W 5`).
- Steps: `m infrared` ; protocol RAW/NEC/RC5 ; `irrx` (record) / `irtx` (replay), `tvbgone` (sends many TV power-off codes). Also aIR format for AnalysIR (`binmode` 7).
- Risks: `tvbgone` switches off TVs in view; high LED current. Coverage: **gap**. Transport: terminal (BPIO2 config has IR fields, data unverified). Effort L.

## B8. JTAG / SWD

### B8.1 blueTag JTAG/SWD pinout finder
- Doc: /docs/devices/jtag-swd-pin-finder/. `m jtag`; set PSU (or VREF) to the target's IO voltage; connect IO0..IO7 to candidate pads in order, avoid ground pours/power pins; GND common.
  `bluetag jtag -c 8` (add `-d` to stop pin pulsing) -> `TDI=IO0 TDO=IO3 TCK=IO4 TMS=IO2` + `IDCODE 0x59602093 (Xilinx)`; `bluetag swd -c 8` -> `SWDIO=IO5 SWCLK=IO6`, `0x0BC12477 ARM`.
- Risks: pulsing pins can disturb a running target; measure voltage first. Coverage: **gap**. **Terminal** only. Effort M (parse output). Good recipe candidate: output is short and structured.

## B9. Keyboard sniffers

### B9.1 PS/2 keyboard sniffer or host
- Doc: /docs/devices/ps2-usb-keyboard/ and plank /docs/overview/ps2-usb-sniffer-adapter/. `m ps2`; plank inline between keyboard and PC, **PWR SWITCH to EXT** (the PC powers the keyboard). Pins: DAT IO4, CLK IO5, IO6/IO7 reserved.
  `sniff` prints each byte with make/break and keys typed; or as host: `[` hold CLK, `r` read, commands to set LEDs/ID/reset. Press `q` to stop. Privacy/security: this is a keylogger; recipe needs an explicit "this is my own keyboard" confirmation.
- Coverage: **gap**. Terminal. Effort M.

### B9.2 USB keyboard sniffer (low/full speed)
- `m usb`; D+ IO1, D- IO2, TRIG IO0; `sniff` sets 3.3 V; keys `e g l t a f s p b k x` (capture speed, trigger, packet limit, keylogger). Same ethics note. Coverage: **gap**. Terminal. Effort M.

## B10. Other planks

### B10.1 CAN bus adapter
- /docs/overview/can-bus-adapter/ is a stub (no content). Gap, nothing to implement yet.

### B10.2 Programming-voltage (VPP) SMPS plank
- /docs/overview/vpp-smps/ "in development": 5-16 V output (clamped about 18 V), VPP control high/ground, feedback clamped at 4.7 V; for PIC/EEPROM high-voltage programming. Risks: **high voltage**, must not touch IO pins of the BP6 or the target's logic. Coverage: **gap**, do not automate yet.

### B10.3 Identify an unknown 8-pin memory chip
- Doc: /docs/devices/identify-serial-memory-chips/ (marking guide: 25Qnnn flash, 25xnnn/95xnnn SPI EEPROM, 24xnnn I2C EEPROM, 243n 1-Wire, 93xnn Microwire, FM25/MB85 FRAM).
  A discovery recipe could try, in order: I2C `scan`; 1-Wire `scan`; SPI `0x9F`, `0x90`, `0xAB` ID reads. All three are available over BPIO2. Coverage: **partial** (pieces exist as separate tools). Effort M (the best "one-stop shop" recipe).

---

# Summary table

| Use case | Covered / partial / gap | Effort |
|---|---|---|
| A1 HiZ | covered | S |
| A2 Power supply | covered | S |
| A3 Pull-ups | covered | S |
| A4 PWM generator | gap (terminal) | M |
| A5 Frequency measure | gap (terminal) | M |
| A6 Voltage/ADC | covered | S |
| A7 Aux pins / DIO | gap (BPIO2) | S |
| A8 Delays / bitwise syntax | partial | M |
| A9 Bit order / display | gap | S |
| A10 Macros / scripts / button | gap (terminal) | L |
| A11 Disk / USB storage | gap | M |
| A12 Config menu | gap | S |
| A13 Self-test | gap (terminal) | M |
| A14 Bootloader / firmware | gap | S |
| A15 LCD scope | gap (terminal) | L |
| A16 Logic analyzer | gap (terminal / SUMP) | L |
| A17-A24 mode entries (1-Wire, UART, HDUART, I2C, SPI, 2WIRE, 3WIRE, DIO) | I2C/SPI/UART/1-Wire covered or partial; HDUART/2WIRE/3WIRE/DIO gap | S-M |
| A25 LED mode | gap | S |
| A26 INFRARED mode | gap | L |
| A27 JTAG (blueTag) | gap (terminal) | M |
| A28 PS2/USB sniffers | gap (terminal) | M |
| A29 Legacy binmodes | gap (other binmode) | L |
| B1.1 24C02 card | covered/partial | S |
| B1.2 24xx EEPROM dump/restore | partial | M |
| B1.3 MB85RC256V FRAM | partial | S |
| B1.4 SHT3x | gap | S |
| B1.5 SHT4x (3.6 V max) | gap | S |
| B1.6 SI7021/HTU21 | gap | S |
| B1.7 TCS3472x | gap | S-M |
| B1.8 TSL2561 | gap (name only) | S-M |
| B1.9 MS5611 | gap | M |
| B1.10 DDR4 SPD | gap | M (read) / L (write) |
| B1.11 DDR5 SPD | gap | M / L |
| B1.12 USB PD sink | gap | M |
| B1.13 HD44780 LCD | covered | S |
| B1.14 AHT20 / BMP280 / BME280 | covered | S |
| B1.15 I2C sniffer | gap (terminal) | M |
| B1.16 Qwiic/Grove plank | covered (wiring note) | S |
| B2.1 SPI NOR probe/dump | partial | M |
| B2.2 SPI NOR erase/write | partial (library only) | M |
| B2.3 SPI EEPROM / Microwire | gap | M |
| B2.4 SPI FRAM | gap | S |
| B2.5 AVR ISP (avrdude) | gap (other binmode) | L |
| B2.6 flashrom | gap (other binmode) | L |
| B2.7 MAX31855 | covered | S |
| B2.8 JEDEC lookup | partial | S |
| B3.1 DS18B20 | covered | S |
| B3.2 1-Wire EEPROM | gap | M |
| B3.3 other 1-Wire | partial (names) | S |
| B4.1 UART console / baud scan | covered / baud autodetect gap | S |
| B4.2 NMEA GPS | partial | S |
| B4.3 UART glitch | gap (terminal) | L |
| B4.4 RS-232 plank | covered (wiring card) | S |
| B4.5 MIDI | gap | S |
| B5.1 SIM / bank card ATR | gap (terminal, needs PWM) | L |
| B5.2 SLE4442 | gap (terminal) | M-L |
| B5.3 2WIRE sniffer | gap | M |
| B6.1 Onboard LEDs | gap (BPIO2) | S |
| B6.2 WS2812 | gap (BPIO2) | S |
| B6.3 APA102 | gap (BPIO2) | S |
| B7.1 IR RAW/NEC/RC5 | gap | L |
| B8.1 blueTag JTAG/SWD | gap (terminal) | M |
| B9.1 PS/2 sniffer | gap (terminal) | M |
| B9.2 USB sniffer | gap (terminal) | M |
| B10.1 CAN plank | gap (doc is a stub) | n/a |
| B10.2 VPP SMPS | gap (high voltage, do not automate) | L |
| B10.3 Identify unknown memory chip | partial | M |
