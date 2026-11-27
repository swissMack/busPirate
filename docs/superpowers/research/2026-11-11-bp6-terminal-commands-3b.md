# Bus Pirate 6 text terminal, phase 3b: sniffers, gps, IR, logic (from firmware source)

Source: github.com/DangerousPrototypes/BusPirate5-firmware, commit **e2429e0c1412ea0c6315827aafdc8cf054d19d87**
(same as the companion doc `2026-11-11-bp6-terminal-commands.md`, referred to below as **[C]**). BP6 build only.
Strings from `src/translation/en-us.h`. Nothing was run on hardware. Anything not settled by source is marked UNCONFIRMED.
Cross-cutting facts (ETX `\x03` prompt marker, BEL on error, `x` in sub-prompts, `m <name> -flag` non-interactive rule,
`W` power, Ctrl-C behaviour, ANSI stripping) are in [C] §0, §1, §6, §7 and are not repeated.

## 0. Facts common to this set

* **BP6 mode list** (`src/pirate.h` `BP_USE_*`, order of the enum in `src/modes.h` = numbering of the `m` menu):
  `1 HiZ, 2 1WIRE, 3 UART, 4 HDUART, 5 I2C, 6 SPI, 7 2WIRE, 8 3WIRE, 9 DIO, 10 LED, 11 INFRARED, 12 JTAG, 13 PS2, 14 USB`.
  I2S, LCDSPI, LCDI2C, USBPD, DUMMY1, BINLOOPBACK are compiled out. (Resolves the [C] §1/§9 UNCONFIRMED on mode numbering.)
  Prefer `m <name>` over numbers.
* **Pin map** (`src/platform/bpi6-rev2.h`): IOn = `BIOn` = MCU GPIO `8+n` (`BUFIO0..7` = 8..15); buffer direction pins
  `BUFDIR0..7` = GPIO 0..7; follow-along LA inputs `LA_BPIO0..7` = GPIO 20..27.
* **Mode-command dispatch** (`src/ui/ui_process.c`): before running any mode command (`sniff`, `gps`, `irrx`, ...)
  the mode's `protocol_preflight_sanity_check()` runs. For 2WIRE, UART, INFRARED, PS2, USB it is
  `ui_help_sanity_check(true, ...)`, which, if VOUT/VREF < 0.79 V, prints (non-blocking)
  `"\x07\r\nError: No voltage detected on VOUT/VREF pin\r\n"` + `"Hint: Use W to enable power, or attach an external supply\r\n"`
  and then runs the command anyway. I2C's preflight is a no-op (`hwi2c.c: hwi2c_preflight_sanity_check` returns true).
* FALA capture is suppressed (`supress_fala_capture=true`) for i2c `sniff`, ps2 `sniff`, usb `sniff`, `tvbgone`;
  it runs around `gps`, 2WIRE `sniff`, `irtx`, `irrx`, IR `test` when `logic start` is active (see §7).
* **None of the sniff/listen loops print an ETX** while running; only the main prompt after exit does. The stop key
  is read with `rx_fifo_try_get()` (raw byte, no Enter needed; any trailing `\r` is consumed as "some other key").
* All output in this set is **text** (ASCII, `\r\n` line ends). No binary output on CDC 0.

---

## 1. I2C sniffer: `sniff` in I2C mode

File: `src/commands/i2c/sniff.c` (`i2c_sniff`, `sniff_i2c_def`), registered in `hwi2c_commands[]` (`src/mode/hwi2c.c`).
PIO: `src/lib/pico-i2c-sniff/i2c_sniffer.pio` (pico-i2c-sniff by jjsch-dev). **There is no separate "I2C sniffer" mode**
(not in `modes.c`) and no I2C-sniff binmode; `sniff` is a mode command of I2C (and a different `sniff` exists in 2WIRE, PS2, USB, SPI).

* **Reach:** `m i2c -s 400` (non-interactive, [C] §6). Speed/clock-stretch settings do not affect the sniffer
  (it runs PIO at clkdiv 1; help text "Max speed: 500kHz"). Not allowed in other modes (`Invalid command: sniff...` in HiZ).
* **Syntax:** `sniff [-q] [-7] [-r]` (`i2c_sniff_help`). `-q` quiet (no `+` ACK marks), `-r` raw (no `[` `]`, no `R`/`W`),
  `-7` print the address byte as 7-bit address + direction. Flags combine.
* **Pins (BP6):** IO0 = SDA input, IO1 = SCL input (`M_I2C_SDA/SCL`), **IO2 = EV0 and IO3 = EV1 are driven OUTPUTS**
  (`bio_output(BIO2)`, `bio_output(BIO3)`; PIO `set pins` on GPIO 10/11 to pass the bus-event code between state machines).
  Labels `SDA SCL EV0 EV1`. The I2C mode PIO is torn down (`hwi2c_cleanup()`) for the duration and restored on exit (`hwi2c_setup_exc()`).
  Does not touch the PSU or pull-ups (sniffing is passive; the bus being sniffed provides its own pull-ups).
* **Start output:** `"I2C Sniffer\r\n"`, `"Press x to exit\r\n"`, with `-q` also `"Quiet mode enabled, ACKs will not be displayed\r\n"`.
* **Running output** (one `printf` per PIO event, no line buffering; a transaction becomes one line):

  | event | default | `-q` | `-r` (raw) |
  |---|---|---|---|
  | START | `[` | `[` | (nothing) |
  | data byte | ` [0x%02X]%c` (`%c` = `+` ACK / `-` NACK) | ` 0x[%02X]` ACK, ` 0x[%02X-]` NACK | ` 0x%02X%c` (`-q -r`: ` 0x%02X` / ` 0x%02X-`) |
  | 1st byte after START with `-7` | ` %c[0x%02X]%c` (`R`/`W`, addr>>1, `+`/`-`) | ` %c[0x%02X]` then `-` if NACK | ` 0x%02X%c` (7-bit addr) |
  | STOP | `]\r\n` | `]\r\n` | `\r\n` |
  | unknown event code | `U\r\n` | `U\r\n` | `U\r\n` |

  Example default: `[ [0xA0]+ [0x00]+ [0x12]-]\r\n`. A repeated START prints another `[` inside the same line.
  Event codes (`i2c_sniffer.pio`): `EV_DATA 0`, `EV_START 1`, `EV_STOP 3`; word: ev = bits 12..11, data = bits 8..1, ACK = bit0 == 0.
  NOTE: `src/commands/i2c/sniff.md` documents `[ 0x00- 0x01-]`; the code prints `[0x00]-` (brackets per byte). Trust the code.
  NOTE the inconsistent `-q` format `0x[%02X]` (bracket after `0x`), source as written.
* **Stop:** lowercase **`x`** only (`if(c == 'x')`); every other received byte is consumed and ignored. No timeout, no count.
  On exit it prints nothing; returns to `I2C> `.
* **Traps:** never wire IO2/IO3 to anything (they are driven). Output is unbuffered `printf` inside the poll loop: on a busy
  bus at high speed the PIO FIFO can overflow and bytes are lost silently (no overflow indicator; the RAM-FIFO/core1 path is `#if 0`).
  A transaction without STOP leaves the line unterminated.

## 2. 2WIRE sniffer: `sniff` in 2WIRE mode

File: `src/commands/2wire/hw2w_sniff.c` (`hw2w_sniff`, `hw2w_sniff_def`), in `hw2wire_commands[]` (`src/mode/hw2wire.c`).
PIO `src/lib/pico-i2c-sniff/hw2w_sniffer.pio`.

* **Reach:** `m 2wire -s 400` (only flag; range 1-1000 kHz, default 400, saved to `bp2wire.bp`). Speed does not affect the sniffer.
* **Syntax:** `sniff` only. No flags (`opts = NULL`; usage shows `[-q]` but quiet is commented out).
  Help: "Sniffs SLE4442 style 8bit I2C-like protocols (no NAK/ACK)", "Max speed: 500kHz".
* **Pins:** IO0 = SDA in, IO1 = SCL in, **IO2 = EV0, IO3 = EV1 driven outputs** (same as §1). Note IO2 is the 2WIRE `RST` pin
  (`M_2WIRE_RST`): while sniffing it is re-purposed as a driven EV0 output, so do not have a target RST on IO2.
  2WIRE PIO torn down (`hw2wire_cleanup`) and restored (`hw2wire_setup_exc`) on exit. PSU untouched.
* **Output:** `"2Wire Sniffer\r\n"`, `"Press x to exit\r\n"`, then START `[`, each byte ` 0x%02X` (8 bits, **no ACK mark**),
  STOP `]\r\n`, unknown `U\r\n`. Bytes pass through `ui_format_bitorder_manual(&data, 8, system_config.bit_order)`, so the
  global `l`/`L` (LSB/MSB) setting reverses them. Word: ev = bits 11..10, data = bits 7..0.
* **Stop:** lowercase `x` only. **Traps:** as §1.

## 3. PS/2: `sniff` in PS2 mode

File: `src/mode/ps2.c` (`ps2_handler`, `ps2_sniff_def`, setup `ps2_setup`/`ps2_setup_exc`), PIO `src/mode/pico_ps2_sniffer.pio`
(pico-ps2-sniffer by Dreg). It is **sniff only** (passive, both directions); there is no PS/2 host/keyboard read/write command
and the mode's bus syntax functions are not used for PS/2 I/O (UNCONFIRMED: not read beyond the command table).

* **Reach:** `m ps2` (mode 13). `ps2_setup()` returns 1 with no prompts; `ps2_setup_exc()` allocates an 800-entry ring buffer.
* **Syntax:** `sniff` (no flags, no `-h` handling in the handler; `T_PS2_DESCRIPTION`="sniff PS2 protocol").
* **Side effects on start (no confirmation!):** `psu_enable(5.0f, 400.0f, false, 100)` -> prints `"\r\nPSU 5v Enabled\r\n"`
  (or `"\r\nPSU ERROR CODE %d\r\n"`), **VOUT = 5.0 V, 400 mA limit**, then `pullups_enable()` (10K to VOUT = 5 V).
  It also wipes **all state machines and instruction memory of pio0 and pio1** (`pio_destroy()`), which includes the
  logic-analyzer PIO (pio0) and the mode PIO. The PSU stays on after `q`; it is switched off only by leaving the mode (`ps2_cleanup` -> `psu_disable()`).
* **Pins:** IO4 = DAT input, IO5 = CLK input; **IO6 and IO7 are driven outputs** (internal PIO jump/handshake lines,
  `BIO_AUX_H2D_JMP_GPIO`, `BIO_AUX_D2H_JMP_GPIO`), must stay unconnected. Labels (all 8 claimed):
  `TRIG D+ D- RESV DAT CLK RESV RESV` (copied from USB; only DAT/CLK are used). PS/2 lines are 5 V: the pull-ups go to 5 V.
* **Banner:** `"\r\npico-ps2-sniffer started! for Bus Pirate\r\nhttps://github.com/therealdreg/pico-ps2-sniffer\r\nMIT License David Reguera Garcia aka Dreg\r\n---------------------------------------------------------------\r\n\r\n"`,
  then it **drains (discards) any pending input bytes**, then `"\r\nPress 'q' to exit\r\n\r\nSniffing...\r\n\r\n"`.
* **Per byte** (`ps2_process_packets`):
  `"[0x%04X] t:0x%08X %c:0x%02X\r\n"` = running packet index, timestamp in **ms since boot** (hex, `us_to_ms(time_us_64())`),
  `D` (device->host) or `H` (host->device), byte. For D bytes completing a known scan-code sequence (set 2 table `keytable[]`):
  the entry name (C identifier, e.g. `MAKE_A`, `BREAK_A`, `MAKE_LEFT_ARROW`), then if it has an ASCII value `" --> %c"`;
  for BREAK entries with ASCII also
  `"\r\n**********\r\nkey break tracker (limit 0x%02X bytes): %s\r\n**********"` (accumulated typed chars, limit 0x13F);
  then `"\r\n-----------\r\n"`. Overflow: `"\r\n!! ring buffer full, %u packet(s) dropped !!\r\n"`.
* **Stop:** `q` or `Q` -> `"\r\n\r\nexit...\r\n"`, back to `PS2> `. Other keys ignored. No timeout.
* **Traps:** a `q` sent before `"Sniffing..."` is eaten by the drain loop; send it after that line. 5 V on VOUT with
  pull-ups: if the sniffed keyboard is already powered by a host PC, VOUT backfeeds/fights it (possible
  `Backflow prevention` / current-limit error, [C] §7). After `sniff`, pio0/pio1 programs belonging to other features are
  gone until those features re-init (UNCONFIRMED whether `logic`/FALA recovers without a mode change).
  `stop_device_to_host_sm()` busy-waits on a GPIO inside the PIO IRQ (`while (!gpio_get(...))`): a hang there would freeze the
  board (UNCONFIRMED in practice). `ps2_pins()` prints a stale JTAG label row.

## 4. USB sniffer: `sniff` in USB mode

File: `src/mode/usb.c` (`usb_handler`, `cap`, `process_buffer`, `display_buffer`, `keylog_run`), PIO
`src/mode/pico_usb_sniffer_lite.pio` (pico-usb-sniffer-lite by Alex Taradov / Dreg). USB 1.1 **low speed and full speed only**.

* **Reach:** `m usb` (mode 14), no prompts; setup allocates a 128 KiB capture buffer.
* **Syntax:** `sniff` (no flags). It is an **interactive single-key menu**, not a one-shot command.
* **Side effects on start:** `set_sys_clock_khz(120000, true)` and `stdio_init_all()`, `sleep_ms(500)` -> **the system clock
  is changed to 120 MHz and nothing in usb.c restores it** (not on `x`, not in `usb_cleanup`). Anything clock-derived
  afterwards (PWM `G` actual values, `logic` sample rates, UART baud) is computed from the new `clk_sys` (UNCONFIRMED whether
  any other code restores it; a reset certainly does). Then `psu_enable(3.33f, 400.0f, false, 100)` -> `"\r\nPSU 3V3 Enabled\r\n"`
  (or `"\r\nPSU ERROR CODE %d\r\n"`), then `"Clock successfully set to 120 MHz\r\n"` / `"Failed to set the clock\r\n"`, then the help.
  PSU stays on until the mode is left. Also wipes pio0+pio1 on each capture (`pio_destroy()`).
* **Pins:** IO0 = TRIG input (active LOW, only if trigger enabled), IO1 = D+ input, IO2 = D- input, **IO3 = driven output**
  (PIO "start" sync line, keep unconnected). Labels `TRIG D+ D- RESV DAT CLK RESV RESV`.
* **Help text** (`print_help`, printed on start, on `h`/`?` and on any unknown key):
```
\r\n-------------------------------------------------------------------\r\n
pico-usb-sniffer-lite for Bus Pirate\r\n ... \r\n
Settings:\r\n
  e - Capture speed       : Low|Full\r\n                       (default Low)
  g - Capture trigger     : Enabled|Disabled\r\n               (default Disabled)
  l - Capture limit       : 100|200|500|1000|2000|5000 packets\r\n   (default 5000)
  t - Time display format : Relative to the first packet|...previous packet|...the SOF|...the bus reset\r\n (default SOF)
  a - Data display format : Full|Limit to 16 bytes|Limit to 64 bytes|Do not display data\r\n (default Full)
  f - Fold empty frames   : Enabled|Disabled\r\n               (default Enabled)
\r\nCommands:\r\n  h - Print this help message\r\n  b - Display buffer\r\n  s - Start capture\r\n  p - Stop capture\r\n
  k - Keylogger low speed infinite ('q' to exit)\r\n  x - Exit\r\n\r\n
```
* **Menu loop:** drains pending input, prints `"\r\nCommand: "` (no ETX), waits for ONE byte, echoes `" %c\r\n"`, upper-case folded.
  Settings keys **cycle** to the next value: `"%s changed to %s\r\n"` (e.g. `Capture speed changed to Full`). Settings are
  static globals: they persist across `sniff` runs until reboot. To set e.g. Full speed + 100 packets from defaults: `e`, then `l` (5000 -> 100 wraps).
* **`s` capture:** `"capture start!\r\n"`; if trigger enabled `"Waiting for a trigger (waiting for a LOW)\r\n"` ... `"Triggered!\r\n"`;
  **then blocks in `pio_sm_get_blocking()` until `limit` packets are captured or the buffer is full. No key is polled.**
  Then `process_buffer()` (may print `"Synchronization error. Check your speed setting.\r\n"`), then `"capture end!, press 'b' to show the buffer\r\n"`.
  `p` only prints `"capture stop is not implemented yet!\r\n"`.
* **`b` display** (`display_buffer`/`print_packet`): `"\r\nCapture buffer is empty\r\n"` or `"\r\nCapture buffer:\r\n"` then per packet
  `"%d : "` (time in **µs** relative per `t` setting, from the 1 MHz `timer_hw->timelr`) followed by one of:
  `"--- RESET ---\r\n"`, `"LS SOF\r\n"`, `"SOF #%d\r\n"`, `"%s\r\n"` (handshake PID name e.g. ACK/NAK/STALL), `"%s: 0x%02X/%X\r\n"`
  (IN/OUT/SETUP/PING: addr/endpoint), `"SPLIT: HubAddr=0x%02X, SC=%X, Port=%02X, S=%X, E=%X, ET=%X\r\n"`, data packets
  `<PID>` + `": ZLP\r\n"` or `" (%d): "` + `"%02X "`... (+ `"..."` if limited) + `"\r\n"`,
  errors `"ERROR [STUFF, CRC, PID, SYNC, NBIT, SIZE]: SYNC = 0x%02X, PID = 0x%02X, DATA: 0x%02X ...\r\n"`;
  folded frames `"   ... : Folded 1 frame\r\n"` / `"%d frames"`; corruption guard `"Time delta between packets is too large, possible buffer corruption.\r\n"` (stops display).
  Footer: `"\r\nTotal: error: %d, bus reset: %d, %s packet: %d, frame: %d, empty frame: %d\r\n\r\n"` (`%s` = `FS`/`LS`).
* **`k` keylogger** (low-speed boot keyboards only): `"\r\nUSB low speed keylogger started, press 'q' to exit\r\nonly USB 1.1 low speed boot protocol keyboards are decoded\r\n\r\n"`,
  per report `"[0x%04X] IN: 0x%02X 0x%02X 0x%02X 0x%02X 0x%02X 0x%02X 0x%02X 0x%02X\r\n"`, new keys as `" --> %c"` +
  `"\r\n**********\r\nusb key tracker (limit 0x%02X bytes): %s\r\n**********\r\n"`, or a key name, or `"<%02X>"`, `"<CAPS>"`, then `"-----------\r\n"`.
  `q`/`Q` ends: `"\r\n\r\nkeys captured: %s\r\n"`, optional `"words dropped while decoding: %u\r\n"`, `"keylogger stopped\r\n"`, back to `Command: `.
* **Stop:** `x` at `Command: ` returns to `USB> `. During `s` there is **no way out except traffic, the limit, or reset/replug**.
* **Traps:** (1) `s` with no USB traffic (wrong pins, wrong speed, idle bus without SOF on LS) **hangs the board**; use a small
  `l` limit and confirm wiring first. Trigger mode also busy-waits forever for IO0 LOW. (2) Clock left at 120 MHz. (3) 3.3 V on
  VOUT with 400 mA limit. (4) Keys sent before `Command: ` are drained; send one key per `Command: ` prompt.

## 5. `gps`: NMEA decoder in UART mode

Files: `src/commands/uart/nmea.c` (`nmea_decode_handler`, `nmea_decode_def`), `src/lib/minmea/gps.c` (`process_gps`),
`src/lib/minmea/minmea.c`. Registered only in `hwuart_commands[]` (`src/mode/hwuart.c`) -> **UART mode only** (not HDUART).

* **Reach:** `m uart -b 9600` (typical GPS default 9600 8N1; `-d -p -s -f -i` default to 8, none, 1, off, normal; [C] §6). Saved to `bpuart.bp`.
* **Syntax:** `gps` (only `-h`). Help: "Decode GPS NMEA packets: gps", "Exit: press any key".
* **Pins:** IO4 = UART TX (idle output, unused by gps), IO5 = UART RX input (`M_UART_TX/RX`, `uart0`). IO6/IO7 CTS/RTS only if `-f rts`.
* **Precondition:** `ui_help_check_vout_vref()`: if VOUT/VREF < 0.79 V, **`gps` returns silently** (no message from gps, no
  error flag/BEL); only the preflight "No voltage detected" lines (§0) appear. Power the module (`W 3.3`) or feed VREF first.
  PSU is not changed by `gps`.
* **Output:** `"Press any key to exit\r\n"` (+ cursor-hide escape in colour mode only). Then for every sentence
  (bytes from `$` up to and including `\n`, max 80 chars `MINMEA_MAX_SENTENCE_LENGTH`, longer ones restart):
  the raw sentence echoed verbatim (`printf(line)`, so it carries the GPS's own `\r\n`), then the decode:
```
RMC: "$xxRMC: raw coordinates and speed: (%d/%d,%d/%d) %d/%d\r\n"
     "$xxRMC fixed-point coordinates and speed scaled to three decimal places: (%d,%d) %d\r\n"
     "$xxRMC floating point degree coordinates and speed: (%f,%f) %f\r\n"        | "$xxRMC sentence is not parsed\r\n"
GGA: "$xxGGA: fix quality: %d\r\n"                                                 | "$xxGGA sentence is not parsed\r\n"
GST: "$xxGST: raw latitude,longitude and altitude error deviation: (%d/%d,%d/%d,%d/%d)\r\n"
     "$xxGST fixed point latitude,longitude and altitude error deviation scaled to one decimal place: (%d,%d,%d)\r\n"
     "$xxGST floating point degree latitude, longitude and altitude error deviation: (%f,%f,%f)"   <- NO line end
GSV: "$xxGSV: message %d of %d\r\n" "$xxGSV: satellites in view: %d\r\n"
     4x "$xxGSV: sat nr %d, elevation: %d, azimuth: %d, snr: %d dbm\r\n"           (always 4 lines, zeros for empty slots)
VTG: "$xxVTG: true track degrees = %f\r\n" "        magnetic track degrees = %f\r\n" "        speed knots = %f\r\n" "        speed kph = %f\r\n"
ZDA: "$xxZDA: %d:%d:%d %02d.%02d.%d UTC%+03d:%02d\r\n"
bad checksum/format: "$xxxxx sentence is not valid\r\n"; other IDs (GLL, GSA, TXT...): "$xxxxx sentence is not parsed\r\n"
```
  Floats use `%f` (6 decimals); RMC lat/lon in signed decimal degrees, speed in knots. Only RMC carries position; there is no time/date output except ZDA.
* **Stop:** **any key** (`rx_fifo_try_get` -> `return`). Checked only while waiting for bytes, i.e. between sentences; nothing printed on exit.
* **Traps:** silent return without VOUT/VREF; the raw line is used as a printf format string (a `%` in garbage input would
  misprint); GST float line lacks `\r\n`; if UART async print was enabled with `{` it competes for RX bytes (UNCONFIRMED in practice).

## 6. Infrared: INFRARED mode, `irrx`, `irtx`, async decode, `tvbgone`, `test`

Files: `src/mode/infrared.c` (setup, `ir_protocol[]`, `infrared_periodic`, `infrared_write`), `src/commands/infrared/irtxrx.c`
(`irtx_handler`, `irrx_handler`, `irtx_transmit`), `src/pirate/irio_pio.c` (RAW/aIR PIO), `src/lib/pico_ir_nec/*` (NEC),
`src/pirate/rc5_pio.c` (RC5), `src/commands/infrared/tvbgone.c`. Hardware model is the IR Toy v3 plank.

* **Reach:** `m infrared -p raw|nec|rc5 [-f 20-60] [-r barrier|38k_demod|56k_demod]`. `-p` is the primary flag.
  Defaults: protocol `raw`, `-f 38` kHz (only used for RAW; NEC fixed 38 kHz, RC5 fixed 36 kHz), `-r 38k_demod`. Saved to `bpirrxtx.bp`.
  Interactive (no `-p`): optional `Use previous settings?` y/n; `Protocol` list (`RAW (aIR format)`, `NEC`, `RC5`; default 1);
  for RAW `TX modulation` / hint `20kHz to 60kHz` / `x to exit (38) >`; for NEC/RC5 it prints `"\r\n\r\nNEC TX modulation: 38kHz\r\n"`;
  `RX sensor` list (`38kHz barrier`, `36-40kHz demodulator`, `56kHz demodulator`; default 2). Enter accepts each default.
  Prompt becomes `INFRARED-(RAW)> ` / `INFRARED-(NEC)> ` / `INFRARED-(RC5)> ` ([C] §1).
* **Pins (BP6):** IO4 = IR TX output (`IRTX`); RX inputs IO3 = 38 kHz barrier (`BARR`), IO5 = 36-40 kHz demodulator (`38k`),
  IO7 = 56 kHz demodulator (`56k`); IO1 = 20-60 kHz learner (`LERN`, used for carrier-frequency measurement via a pio0 SM2).
  **IO0's MCU pin (GPIO8) is driven by the RAW receiver PIO as an internal PIO-to-PIO link** (`ir_in_low_counter_program_init`,
  side-set pindir) though it is not labelled: keep IO0 unconnected (electrical effect UNCONFIRMED). No PSU change by the mode;
  the IR Toy plank needs VOUT (preflight warns).
* **Async receive at the prompt** (`infrared_periodic` -> `irrx_read`, runs every main-loop pass, even mid-typing):
  * RAW: aIR text streamed as edges arrive: `"$%u:%u,"` (carrier kHz, first MARK µs), then `"%u,"` per SPACE/MARK, ending
    `"%u,;\r\n"` (final SPACE = 65535 timeout) or `",;\r\n"`. Units µs (PIO at 1 µs/count). Carrier measured on IO1 (learner); 0 if none.
  * NEC: `"\r\n(0x%08x) Address: %d (0x%02x) Command: %d (0x%02x)"` (no trailing newline; invalid frames silent).
  * RC5: `"\r\n(0x%04x) SB1:%d SB2:%d Toggle:%d Address: %d (0x%02x) Command: %d (0x%02x)"` (no trailing newline; source bug:
    the hex field after Address repeats the address correctly, both are `(frame>>6)&0x1f`).
  A script must expect these lines interleaved with the prompt/echo.
* **Transmit via bus syntax:** numbers written in the mode go to `irtx_write` (`infrared_write`): NEC `0xAACC` = address `0xAA`,
  command `0xCC` (16 bits, encoded with inverses); RC5 14-bit value, S1/S2 forced to 1 (`T<<11 | A<<6 | C`); RAW one 32-bit word
  = MARK µs <<16 | SPACE µs. `protocol_wait_done` waits for TX idle after the line. (Syntax/echo format: [C]-style syntax output, UNCONFIRMED here.)
* **`irtx`** `irtx [aIR packet] [-f <file>]`. aIR: `$<carrier kHz>:<MARK1>,<SPACE1>,...,<MARKn>,<SPACEn>,;` (µs, decimal).
  On the command line `;` is the command separator and gets stripped, so type `irtx $38:9000,4500,560,560,560,65535,` (the handler
  re-appends `;`); **every value must be followed by `,`**, an odd count gets SPACE 65535 appended. Max 127 pairs.
  Output: `"\r\nTransmitting from command line\r\n"`, then the parsed packet `"\r\n$%u:" + "%u,%u," ... + ";\r\n\r\n"`,
  `"Parsed AIR packet: modulation frequency %dkHz, %d MARK/SPACE pairs\r\nTransmitting..."`, `"done\r\n"` (or `"PIO TX timeout\r\n"`).
  Errors: `"Unable to find start of data ($) in AIR packet\r\n"`, `"Unable to find modulation frequency (:) in AIR packet\r\n"`,
  `"Unable to find end of MARK/SPACE data (,) in AIR packet\r\n"`, `"Too many MARK/SPACE pairs in AIR packet, max 127\r\n"`, then
  `"Error parsing AIR packet\r\n"` (error flag). No args: `"Nothing to do, showing help\r\n"` + help. `-f file.air` sends every line of
  a file (`"Transmitting from file %s\r\n"`; `"Error opening file %s for reading\r\n"`). Works in any IR protocol (it swaps in the RAW
  PIO temporarily and restores the mode's). Ends by itself. Carrier field is `uint8_t` kHz.
  Source risk: re-appending `;` uses `buffer[strlen(buffer)+1]=0` after overwriting the terminator (reads an uninitialised stack
  buffer, UNCONFIRMED effect); the `-f` path avoids it.
* **`irrx`** `irrx [-f <file>] [-s 38b|38d|56d]` (case-insensitive; unknown value silently = `38d`; learner IO1 is not selectable).
  Output: `"No file specified, packets cannot be saved\r\n"` or `"Saving to file %s\r\n"`; `"RX sensor: <name>\r\n"`;
  `"\r\nListening for IR packets (x to exit)...\r\n"`. Per captured frame: `"\r\n$%u:%u,%u,...,%u,;\r\n\r\n"` (aIR, last SPACE omitted)
  then `"Modulation frequency %dkHz, %d MARK/SPACE pairs\r\n\r\n"`, then the single-key menu (no ETX):
  `"'s' to save, "` (only with `-f`) + `"'r' or 't' to re-transmit, space for next, 'x' to exit > "`; the key is echoed `"%c\r\n"`.
  `s` appends the aIR line to the file (stays in menu), `r`/`t` retransmit (`"\r\nTransmitting..."` `"done\r\n\r\n"`, stays in menu),
  SPACE -> listen again, `x` -> leave, any other -> `"Invalid input\r\n"` + menu.
  **Stop:** while listening, lowercase `x` -> `"Exiting...\r\n"` (others ignored); at the menu, `x`. The file is closed only on `x`.
  Frame end = a SPACE timeout of 65535 µs. `irio_pio_rx_frame_buf` writes into a 128-pair buffer with no bounds check (very long
  frames could overrun the stack, UNCONFIRMED).
* **`tvbgone`**: plays all built-in TV-off codes on IO4 (`"TVBGONE player\r\nPlaying %d TV off codes:\r\n"`, `"\r%d"` counter,
  `"\r\nDone!\r\n"`). **Not interruptible** (no key/button check). **`test`**: IR Toy v3 self-test, prints `OK`/`FAIL` lines, ends with
  `"\r\nOK :)\r\n"` or `"\r\n%d FAILS :(\r\n"`.
* Binary IR protocols (IRMAN, AIR/AnalysIR) are binmodes 6/7, see [C] §8.

## 7. `logic`: follow-along logic analyzer

Files: `src/commands/global/logic.c` (`logic_handler`), `src/toolbars/logic_bar.c` (graph), `src/binmode/fala.c` (`fala_*` hooks,
`fala_print_result`), `src/binmode/logicanalyzer.c`, `src/ui/ui_process.c` (hook calls). Global command, `allow_hiz=true`.

* **What it is:** not a standalone triggered capture. `logic start` registers a hook so that **every subsequent bus-syntax line**
  (`[0xa0 0x00 r:4]` etc.) and every non-suppressed mode command is captured: arm before, stop after, then print a result
  and redraw the graph (`ui_process.c` -> `fala_start_hook`, `fala_stop_hook`, `fala_notify_hook`). Inputs: the follow-along
  buffer `LA_BPIO0..7` (GPIO 20-27 = mirror of IO0-7), i.e. it records what the BP itself drives/sees on IO0-IO7.
  No trigger options and no sample count: the stale string `T_CMDLN_LOGIC` ("logic <frequency in kHz> <samples> <trigger pin>...")
  is NOT the current syntax. Triggered/sized captures are only via the SUMP binmode ([C] §8).
* **Syntax:** `logic [start|stop|hide|show|nav] [-i] [-o <oversample>] [-f <Hz>] [-d 0|1|2] [-0 <lowchar>] [-1 <highchar>] [-b <pin>]`.
  * `logic start` -> may print `"\r\nLogic analyzer setup error, out of memory?\r\n"` / `"Logic analyzer failed to start\r\n"`;
    `"Logic analyzer already active\r\n"`. On success prints 10 `\r\n` and activates a 10-row toolbar (scroll region).
  * `logic stop`, `hide`, `show`: `"Logic analyzer not active\r\n"`, `"Logic analyzer already hidden\r\n"`, `"Logic analyzer already visible\r\n"`.
  * `logic nav`: `"\r\nCommands: <- and -> to scroll, x or q to exit\r\n"`, then reads keys **blocking** (ESC `[D`/`[C` arrows scroll);
    **only `x` or `q` exit**. `s`/`r` are no-ops.
  * Flags (each prints a confirmation): `-f` `"Sample frequency set to: %dHz\r\n"` (base rate, Hz, no range check), `-o`
    `"Oversample rate set to: %d\r\n"` (>=1, else `"Error: oversample rate must be greater than 0, '%d' is invalid\r\n"`), `-d`
    `"Debug level set to: %d\r\n"` (>2 -> `"Error: debug level must be 0, 1, or 2, '%d' is invalid\r\n"`), `-0`/`-1`
    `"Low char set to: %c\r\n"`/`"High char set to: %c\r\n"` (toolbar graph glyphs, defaults low `_`, high `#`; `logic_bar.c`), `-b` `"Base channel set to: %d\r\n"`
    (0=bufdir, 8=bufio, 20=follow along, default 20). With `-f`/`-o` (or `-i` together with another flag) it prints
    `"\r\nLogic Analyzer settings\r\n Oversample rate: %d\r\n Sample frequency: %dHz\r\n"` and, if quantised,
    `"\r\nNote: actual oversample rate is not 1\r\n"` / `"Actual sample frequency: %dHz (%f * %dHz)\r\n"`.
    **`logic -i` alone prints only the help** (`has_ok` false). Bare `logic` prints help.
* **Rates:** defaults `base_frequency 1000000`, `oversample 8` (8 MS/s). On every mode change (`fala_mode_change_hook`) base is
  reset to the mode's speed and oversample to 8, printing (if active) `"\r\nLogic analyzer speed: %dHz (%dx oversampling)\r\n"` +
  `"Use the 'logic' command to change capture settings\r\n"`. Actual rate = `clk_sys / (2*div)` (2 PIO instructions/sample).
  Buffer `LA_BUFFER_SIZE` = 131072 samples (1 byte = 8 channels), ring.
* **Per-capture output** (`fala_print_result`, after each syntax line while active):
  `"\r\nLogic analyzer: %d samples captured\r\n"` or `"\r\nLogic analyzer: invalid sample count\r\n"`.
  **Text export of samples:** with `logic -d 2` it then prints `"[DEBUG] Logic Analyzer Graph\r\n"`, 8 lines (IO0..IO7, in that
  order) of up to the first 80 samples each, `-` = high, `_` = low, then `"[DEBUG] End of Logic Analyzer Graph\r\n"`. This is the
  only ASCII sample dump on the terminal; full sample data is only reachable via the SUMP/FALA binmodes on CDC 1.
* **Graph:** drawn in the toolbar with absolute cursor addressing (`ui_term_cursor_position` emits nothing when colour is off;
  `toolbar_apply_scroll_region` returns early without colour). In ASCII mode the graph glyphs are emitted without positioning,
  i.e. garbage in the stream (UNCONFIRMED appearance). Not drawn on the LCD by this code (UNCONFIRMED).
* **Stop:** `logic stop` (frees the buffer when no hook remains). It never runs on its own; `nav` blocks until `x`/`q`.
* **Traps:** in ASCII sessions use `logic -d 2` + parse the debug graph and treat toolbar output as noise, or keep `logic` off;
  every syntax line gets extra output while active; `nav` swallows input until `x`/`q`; a PS2/USB `sniff` wipes pio0 (the LA PIO);
  USB `sniff` changes `clk_sys`, so later actual sample rates differ.

## 8. Scripting traps (this set)

1. **USB `sniff` -> `s` can hang the board** (blocking PIO read, no key poll) and leaves `clk_sys` at 120 MHz; the trigger wait also never times out.
2. **Sniffers drive pins:** i2c/2wire `sniff` drive IO2/IO3 (2WIRE's RST pin!), PS2 drives IO6/IO7, USB drives IO3, IR RAW receive drives GPIO8 (IO0 side).
3. **PS2 and USB `sniff` switch the PSU on by themselves** (5.0 V / 400 mA + 5 V pull-ups for PS2; 3.33 V / 400 mA for USB), no prompt,
   and it stays on until the mode is left.
4. Stop keys differ: i2c/2wire `sniff` and `irrx` listening: lowercase `x` only; PS2 `sniff`: `q`/`Q`; USB menu: `x` (keylogger `q`);
   `gps`: any key; `logic nav`: `x`/`q`; `tvbgone`: none. None print ETX until back at the main prompt.
5. PS2/USB drain input before their "ready" line; send stop/menu keys only after `Sniffing...` / `Command: `. USB and `irrx` menus are
   single raw keys with no ETX; a trailing `\r` counts as a key (`Invalid input` / help reprint).
6. `gps` returns silently with no VOUT/VREF; GST decode lacks a newline; NEC/RC5/RAW IR decodes print asynchronously at the prompt.
7. `irtx` on the command line: `;` is a command separator; end the packet with `,` and let the handler add `;`.
8. UNCONFIRMED: real-hardware transcripts; whether pio0/LA and `clk_sys` recover after PS2/USB sniff without reset; logic graph in ASCII
   mode; electrical effect of GPIO8 drive in IR RAW; long-IR-frame overflow; syntax-echo format of IR writes.

## 9. Follow-ups

### 9.1 Maximum command-line length
* The main prompt is linenoise in embedded mode: `linenoiseEditStart()` / `linenoiseSetCallbacks()` set
  `l->buflen = BP_LINENOISE_MAX_LINE` (`src/lib/bp_linenoise/linenoise.c`), and `BP_LINENOISE_MAX_LINE` is **256**
  (`src/lib/bp_linenoise/linenoise.h`, `#ifndef` default; it is not overridden in the files read, and CMakeLists.txt does not set it).
  The command is parsed straight from that buffer (`ln_cmdln_init(ln_state.buf, ln_state.len)` in `src/ui/ui_term_linenoise.c`).
  `UI_CMDBUFFSIZE 512` in `pirate.h` is the older ring buffer and does not limit the line.
* Overflow: `linenoiseEditInsert()` only inserts `if (l->len + clen <= l->buflen)`. **Characters past 256 are dropped
  silently**: no echo, no BEL, no error string. Enter then runs the **truncated** line. For `irtx` that usually means
  `Unable to find end of MARK/SPACE data (,) in AIR packet` + `Error parsing AIR packet`, or a shorter packet if the cut
  falls just after a `,`. `ui_term_linenoise_inject_string()` (macros/scripts) truncates to 256 the same way and returns false.
* So a ~350-character `irtx $38:...` cannot be sent on one line. Keep the line at 256 characters or fewer, including `irtx `
  (about 40-45 four/five-digit values), or put the packet in a file on the BP storage and use `irtx -f <8.3 name>`.
  Each file line can be up to 511 characters (`f_gets` into `char buffer[512]`), and each line is one packet of up to 127 pairs.
  How to get the file onto the BP from a script is not covered here (UNCONFIRMED).

### 9.2 Sending one NEC / RC5 code with bus syntax
* A line is treated as bus syntax only if its first character is `[ > { ] }` (`src/ui/ui_process.c: ui_process_commands`).
  A bare `0x00FF` is looked up as a command name and gives `Invalid command: 0x00FF. Type ? for help.`
* **Do not use `[`/`]`/`{`/`}` in INFRARED mode.** Its `protocol_start/stop(_alt)` are `nullfunc1_temp` (`src/modes.c`), which print
  `"ERROR: command has no effect here\r\n"` (`T_MODE_ERROR_NO_EFFECT`) and set the error flag (BEL).
* **Use `>`**: `> 0x00FF` (or `>0x00FF`). The `>` itself compiles to nothing (`syntax_compile.c` skips `c <= ' ' || c == '>'`).
  The number becomes `SYN_WRITE` with `bits = system_config.num_bits`, which INFRARED setup sets to 16 for NEC/RC5 (32 for RAW).
  Several codes can go on one line: `> 0x00FF 0x0010`.
* NEC (`nec_write`): high byte = address, low byte = command, so `> 0x0045` sends address 0x00, command 0x45
  (encoded as addr, ~addr, cmd, ~cmd). The value is not modified.
* RC5 (`rc5_send`): 14-bit `T<<11 | A<<6 | C`. **It ORs S1/S2 (bits 13,12) into `result->out_data` in place**, so the echo
  shows the modified value: `> 0x000C` (address 0, command 12) echoes `0x300C.16`.
* Output sequence (source-derived; colour off):
  1. `"\r\n"` (`ui_process_commands` ends the input line).
  2. Preflight `infrared_preflight_sanity_check` -> `ui_help_sanity_check(true,0)`: if VOUT/VREF < 0.79 V it prints
     `"\x07\r\nError: No voltage detected on VOUT/VREF pin\r\n"` + `"Hint: Use W to enable power, or attach an external supply\r\n"`
     (non-blocking, TX still happens).
  3. Run: `infrared_write` -> protocol TX (prints nothing); then `protocol_wait_done` = `infrared_wait_idle` (NEC: `pio_sm_wait_idle(..., 0xfffff)`).
  4. Post (`syntax_post.c: postprocess_mode_write`, `ui_format.c: ui_format_print_number_3`): `"\r\nTX: "`, then per value
     `0x%04X` + `".16"` + `" "` (hex digits in alternating colours only when colour is on; the `.16` suffix appears because bits != 8), new row
     `"\r\n    "` after 8 values, and finally `"\r\n"`.
     Example: `> 0x00FF` -> `\r\nTX: 0x00FF.16 \r\n`. A value typed in decimal (`> 255`) echoes in decimal (`255.16`) under the default
     `df_auto` display format.
  5. FALA result lines if `logic start` is active (§7). Then the normal prompt `INFRARED-(NEC)> ` + `\x03` (the line succeeded, no BEL).
* If the receiver sees the board's own TX LED, the async decoder (§6) can print `"\r\n(0x%08x) Address: ..."` after the prompt. Expect
  it in the stream (UNCONFIRMED whether the IR Toy plank's geometry causes self-reception).
* `r` (read) is a no-op in INFRARED mode (`infrared_read` body is commented out). Received codes only arrive through the async print.
