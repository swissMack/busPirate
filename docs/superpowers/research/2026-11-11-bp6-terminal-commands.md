# Bus Pirate 6 text terminal: commands and exact output (from firmware source)

Source: github.com/DangerousPrototypes/BusPirate5-firmware, branch main.
Commit read: **e2429e0c1412ea0c6315827aafdc8cf054d19d87** (committer date 2026-11-01T08:33:08Z,
"Merge pull request #313 from DangerousPrototypes/bp3unbrick-binmode").
Language strings are from `src/translation/en-us.h`. Nothing here was run on hardware, so every
"observed" claim is source-derived. Anything not settled by source is marked UNCONFIRMED.

BP6 build facts (`src/pirate.h`, `BP_VER == 6`): RP2350, `BP_HW_FALA_BUFFER`, `BP_HW_PSU_PWM`,
`BP_HW_IOEXP_NONE`. **`BP_HW_PULLX` is commented out** (only BP7 has programmable pull-x), and
**`BP_HW_PSU_PWM_IO_BUG` is NOT defined** (that is BP5 rev8 only). So on BP6: `P`/`p` are plain on/off,
and IO0/IO1 ARE usable for PWM and frequency measure.

## 0. Cross-cutting facts that matter for a scripted session

* End-of-prompt marker: every main prompt and every sub-prompt ends with a literal byte `\x03` (ETX)
  after the visible text. `src/pirate.c` BP_SM_COMMAND_PROMPT does `printf("\x03")`; sub-prompts print
  `" >%s \x03"` (`bp_cmd.c: val_prompt_loop`, `ui_prompt.c: ui_prompt_float_units`,
  `bp_cmd_confirm`, `bp_cmd_yes_no_exit`). It is invisible and is the reliable "ready for input" sync.
* A failed command makes the main loop print a BEL (`\x07`) (`pirate.c`: `if (system_config.error) { printf("\x07"); ...`).
  `ui_help_error()` also prints `"\x07\r\n%sError:%s %s\r\n"`.
* Command chaining on one line: `;` always next, `&&` next only if previous succeeded, `||` next only if previous failed
  (`ui_process.c`, `ui_cmdln.c`). A line starting with `[ ] { } >` is bytecode syntax, not a command.
* Unknown command: `"Invalid command: %s. Type ? for help."` (`T_CMDLN_INVALID_COMMAND`), via `ui_process.c`.
* Global commands with `allow_hiz=false` print `"Command has no effect in HiZ mode, press 'm' to choose a mode"`
  (`T_MODE_ERROR_NO_EFFECT_HIZ`, `hiz_error()`) when run in HiZ. From `src/commands.c`:
  `W w P p a A G g` are NOT allowed in HiZ. `f F v V ~ m binmode c @` ARE allowed in HiZ.
* `-h` after any command shows its help (`bp_cmd_help_check`).
* In every interactive sub-prompt: `x` (case-insensitive) or Ctrl-C/Ctrl-D exits (returns `BP_CMD_EXIT`, command ends with error),
  empty Enter accepts the default shown in parentheses (`bp_cmd.c: val_prompt_loop`, `ui_parse_get_*`).
  Sub-prompts use linenoise "simple mode" (`ui_term_linenoise.c: ui_prompt_linenoise_init` sets
  `linenoiseSetSimpleMode(..., true)`): typed characters are echoed straight, no redraw escapes.
* Argument parsing for positional/flag numbers goes through `bp_cmd_positional()`/`bp_cmd_flag()`. Out of range prints
  (`bp_cmd.c: val_print_range_error`):
  FLOAT: `"%s out of range: %1.2f, expected %1.2f%s to %1.2f%s"`; UINT32: `"%s out of range: %lu, expected %lu%s to %lu%s"`
  (label = positional name, e.g. `pin`, `volts`, or option long name) and the command returns error.

## 1. The prompt, VT100 colour, escape codes

**Prompt line** (`src/pirate.c`, `BP_SM_COMMAND_PROMPT`):
```
snprintf(prompt_buf, ..., "%s%s>%s ", ui_term_color_prompt(), modes[system_config.mode].protocol_name, ui_term_color_reset());
/* if system_config.subprotocol_name:  "%s%s-(%s)>%s "  */
```
followed by `\x03`. With colour off the visible text is `HiZ> ` (name, `>`, one space). `protocol_name` strings
(`src/modes.c`): `HiZ`, `1WIRE`, `UART`, `HDUART`, `I2C`, `SPI`, `2WIRE`, `3WIRE`, `DIO`, `LED`, `INFRARED`, `JTAG`, `PS2`,
`USB`, `I2S`, `LCDI2C`, `LCDSPI`, `USBPD`, `DUMMY1` (some are conditional on compile flags; UNCONFIRMED which are in the BP6 build).
Sub-protocol form only for `LED` (`LED-(<device>)>`, device from `led_device_type`) and `INFRARED` (`INFRARED-(<display_name>)>`).
Colour (platform `bpi6-rev2.h`): `BP_COLOR_PROMPT_TEXT "150;203;89"`, info/notice/warning `"191;165;48"`, error `"191;48;48"`,
num_float `"83;166;230"`, grey `"94;94;94"`.

**Start-of-session flow** (`pirate.c`, `BP_SM_DISPLAY_MODE` / `_WAIT`): after USB connect nothing is shown until you send a line.
1. First line sent (Enter): the first char, lower-cased, is checked: `n` -> ASCII (`terminal_ansi_color = UI_TERM_NO_COLOR`,
   `terminal_ansi_statusbar = false`, prints `"\r\n"`), `y` -> full colour + status bar then `ui_term_init()`.
2. Anything else (e.g. bare Enter): prints the question `"\r\n\r\nVT100 compatible color mode? (Y/n)> "` and waits again
   (only `y`/`n` accepted).
3. If a saved config already has colour enabled (`system_config.terminal_ansi_color` non-zero), no question is asked: it goes straight to
   `ui_term_detect()`, which sends `"\0337\033[999;999H\033[6n\0338"` and waits for a `ESC [ rows ; cols R` reply.
   No reply: prints `"VT100 terminal not detected!\r\nDefaulting to ASCII mode.\r\n"` and falls back to no colour. Scripts
   that never answer the cursor query therefore end up in ASCII mode with that message.
4. Comment in source: "this has the side effect of always prompting if the saved mode is ASCII". So an ASCII-saved unit asks the
   Y/n question on every new connection; sending `n\r` as the very first line answers it.

**Turning colour off with a command** (`src/ui/ui_config.c`, command `c`, allowed in HiZ):
`c` -> prompt list "Configuration options" (` 1. Language / Jezik / Lingua / ...`, ` 2. ANSI color mode`, ` 3. ANSI toolbar mode`,
 ` 4.` screensaver, LED items; ` x. Exit`), type `2` -> list `1. Disable`, `2. ANSI Full-Color (16M colors)` (+ `ANSI-256 color` only if built with
`ANSI_COLOR_256`), type `1`. It prints `"ANSI color mode set to Disable"` (format `"\r\n%s %sset to%s %s\r\n"`) and loops back to the
main list; send `x` to leave, which saves the config file to storage (`"Configuration file: Saved"` if a TF/NAND config store exists).
Choosing Disable also tears down the toolbar (`terminal_ansi_statusbar = 0`). There is NO one-line `c <args>` form: `ui_config_def` has no
positionals, the menu is interactive only.

**How ANSI colour is emitted** (`src/ui/ui_term.c`): colour escapes come only from `ui_term_color(id)`/`ui_term_color_{reset,prompt,info,notice,warning,error,num_float,grey,pacman}()`
which index `ui_term_color_full_table[]` (`"\033[0m"` for reset, `UI_TERM_FULL_COLOR_CONCAT_TEXT(BP_COLOR_*_TEXT)` for the rest, i.e. `ESC[38;2;R;G;Bm`)
or the 256-colour table, and **return `""` when `terminal_ansi_color == UI_TERM_NO_COLOR`**. `ui_term_color_text()/_background()` print nothing in
NO_COLOR. Cursor hide/show return `""`, `ui_term_erase_line()` (`"\033[K"`) and `ui_term_screen_flash()` are gated on colour.
So format strings like `"%sFrequency%s ..."` become plain text.

**But colour-off does not guarantee zero escape bytes** (important for a parser):
* The *main* command line uses full linenoise with a hints callback (`ui_term_linenoise.c`: `bp_cmd_linenoise_init()` sets
  `linenoiseSetHintsCallback(bp_cmd_ln_hints)`), and `linenoiseEditInsert` only skips the full redraw when no hints callback is set.
  So each keystroke at the main prompt re-draws: `"\r"` + prompt + buffer + (ghost hint, wrapped in `"\033[%d;%d;49m"` ... `"\033[0m"`)
  + `"\x1b[0K"` + `"\r\x1b[%dC"` (`bp_linenoise/linenoise.c: refreshSingleLine`, `refreshShowHints`). These are not gated on
  `terminal_ansi_color` (UNCONFIRMED on hardware, derived from source). Strip CSI sequences (`\x1b\[[0-9;?]*[A-Za-z]`) and `\r` from echo.
* BEL `\x07` on errors, `\x03` markers (see section 0).
* Sub-prompts (anything with `x to exit >`) use simple mode: no redraw escapes.
* In VT100 mode a status bar/toolbar scroll region is drawn; it is off after the `n` answer / `c`->Disable.

## 2. PWM / frequency generator: `G` and `g`

Files: `src/commands/global/pwm.c` (`pwm_configure_enable`, `pwm_configure_disable`, `pwm_get_settings`, `pwm_freq_find`), registered in `src/commands.c`
(`G`, `g`, `allow_hiz=false`, so **must be out of HiZ**, e.g. `m dio`).

Syntax (`pwm_enable_usage`): `G [pin]`, `g [pin]`. Only the pin is a positional (range 0..7, default 0).
**Frequency and duty cannot be given as arguments.** `G 1 1khz 50%` is NOT supported: after `G 1` the command always prompts for
frequency and duty. Script it as separate lines: `G 1`, `1khz`, `50%`.

Flow of `G 2`:
1. (pin omitted -> prints `"Generate frequency"` (`T_MODE_PWM_GENERATE_FREQUENCY`) then one line `" %d. IO%d"` per available pin, then
   `"Choose available pin:"` and the prompt `"\r\nx to exit (0) >\x03"`. Out-of-range prints `pin out of range: 9, expected 0 to 7`.)
2. Pin unavailable -> `"IO%d is not available for PWM generation\r\n"`, returns error. Unavailable means: pin label already in use
   (`system_config.pin_labels[i+1] != 0`), or its slice partner pair is in use by `freq_active` or `pwm_active`:
   mask `0b11 << (i%2 ? i-1 : i)`. So IO0/IO1, IO2/IO3, IO4/IO5, IO6/IO7 each share one PWM slice and the second pin of a pair is simply
   refused (not "same frequency"); also refused while a frequency measurement is active on the pair. If no pin is available at all it
   prints the pin names/labels table and errors (menu case only).
3. Frequency prompt (`ui_prompt_float_units`): `"\r\nPeriod or frequency (ns, us, ms, Hz, kHz or Mhz) >\x03"`. Input like `1khz`, `500 hz`, `2.5MHz`, `10ms`.
   Units are matched case-insensitively on the leading chars; empty/unknown units loop with:
   `"\x07\r\nError: Invalid option\r\n"` then `"Error: Unknown units '%s'\r\nValid units: ns, us, ms, Hz, kHz, MHz, %%"`. `x` exits (error).
4. Echo (all values are plain numbers once colour is off):
```
\r\nFrequency: %.3f<units> = %.0fHz (%.2f<f-units>)\r\nPeriod: %.0fns (%.2f<t-units>)\r\n
```
   (real format: `"\r\n%sFrequency:%s %s%.3f%s%s = %s%.0f%sHz (%s%.2f%s%s)\r\n%sPeriod:%s %s%.0f%sns (%s%.2f%s%s)\r\n"`).
   Out of range: `"\r\nFrequency invalid: 7.46Hz-62.5MHz (134.1ms-16us period)\r\n"` (hard-coded text), then it **re-prompts for frequency**.
5. Actual (quantised) values, printed on success of the search:
```
\r\nActual frequency: %.0fHz (%.2f<unit>)\r\nActual period: %.0fns (%.2f<unit>)\r\n
```
   (format `"\r\n%sActual frequency:%s %s%.0f%sHz (%s%.2f%s%s)\r\n%sActual period:%s %s%.0f%sns (%s%.2f%s%s)\r\n"`, prefixes in warning colour.)
6. Duty prompt: `"\r\nDuty cycle (%) >\x03"` (value must carry `%`; `ns/us/ms` give `"\r\nSupport for ns, us or ms duty cycle not yet implemented\r\n"` and re-prompt).
   Duty > period: `"\r\nDuty cycle cannot be longer than the period:\r\n%fns > %fns\r\n"` and re-prompt.
   Echo: `"\r\nDuty cycle: %.2f%% = %.0fns (%.2f<unit>)\r\n"`
   (real: `"\r\n%sDuty cycle:%s %s%.2f%s%s = %s%.0f%sns (%s%.2f%s%s)\r\n"` with the `%` label from `ui_const_freq_labels`),
   then `"Actual duty cycle: %.0fns (%.2f<unit>)\r\n"`, then the debug line `"Divider: %d, Period: %d, Duty: %d\r\n"`.
7. Success line: `"\r\nGenerate frequency: Enabled on IO%d\r\n"` (format `"\r\n%s%s:%s %s on IO%s%d%s\r\n"` with `T_MODE_PWM_GENERATE_FREQUENCY`, `T_MODE_ENABLED`="Enabled").
   The command then ends back at the prompt (no key needed). The PWM keeps running until `g`.

Reported actual frequency is quantised: `pwm_freq_find`, divider 8.4 fixed point, `TOP_MAX 65534`; `actual = (clk_sys<<4)/div/(top+1)`.
Duty actually set: `pwm_duty = top * (duty/100) + 1`.

`g [pin]` (`pwm_configure_disable`):
* No PWM active: `"Frequency generation not active on any IO pins!"` (no `\r\n`, error).
* `g 2` pin given: invalid pin `"Pin IO%d is invalid!"`; not active `"Error: frequency generator not active on IO%d"`.
* `g` with exactly one active -> disables it silently choosing that pin; with several -> menu `"Disable frequency generation"` + `" %d. IO%d"` lines + pin prompt (script danger: waits for input; send `g <pin>`).
* Success: `"Generate frequency: Disabled on IO%d"` (`T_MODE_DISABLED`="Disabled"; no trailing newline from the handler, the dispatcher adds `reset + "\r\n"`).

## 3. Frequency measure: `f` and `F`

File: `src/commands/global/freq.c` (`freq_single`, `freq_cont`, `freq_measure`, `freq_print`, `freq_configure_enable/disable`).
Allowed in HiZ.

**Semantics are not the obvious one-shot vs continuous when the pin is omitted:**
* `f <pin>` -> one measurement (`freq_measure(pin,false)`), prints one line, returns to prompt.
* `F <pin>` -> continuous (`freq_measure(pin,true)`): `ui_prompt_any_key_continue(250ms refresh)` prints `"Press any key to exit"` (`T_PRESS_ANY_KEY_TO_EXIT`,
  `ui_prompt.c`), hides the cursor (only in colour), and repaints the same line every 250 ms with `\r` and (in colour mode only) `ESC[K`. **Any received key stops it**
  (it consumes the byte with `rx_fifo_try_get`; Ctrl-C is just "any key"), then a final one-shot line is printed with a newline.
  Not stopping it = it runs forever and the prompt never returns. A script must send one byte (e.g. space) to end it.
* `F` with no pin -> `freq_configure_enable()`: menu `"Frequency measurement"` + `" %d. IO%d"` lines of free pins, `"Choose available pin:"`, prompt `x to exit (1) >`; then
  `"\r\nFrequency measurement: Enabled on IO%d\r\n"` followed by one measurement line. It labels the pin as a frequency input and keeps measuring in the background (status bar/toolbar), no key needed.
* `f` with no pin -> `freq_configure_disable()` (it DISABLES a background measurement!): none active -> `"Error: Frequency measurement not active on any IO pins"`; one active -> disables
  it; several -> menu `"Disable frequency measurement"`. Success: `"\r\nFrequency measurement: Disabled on IO%d"`.
  So never send bare `f` expecting a reading.

**Measurement line** (`freq_print`), exact format:
```
"%sFrequency%s IO%s%d%s: %s%.2f%s%s %s%.2f%s%s (%s%.0f%sHz), %s%s:%s %s%.1f%s%%\r%s"   (last %s = refresh ? "" : "\n")
```
Colourless result for e.g. 1 kHz 50 %: `Frequency IO1: 1.00kHz 1.00ms (1000Hz), Duty cycle: 50.0%` + `\r` + `\n` (one-shot). Units text from `ui_const_freq_labels` = `"ns","us","ms","Hz","kHz","MHz","%"`.
Words: `T_MODE_FREQ_FREQUENCY`="Frequency", `T_MODE_FREQ_DUTY_CYCLE`="Duty cycle". Output has three numbers: frequency in friendly units, period in friendly units (ns/us/ms) and raw Hz (`%.0f`), plus duty cycle in percent. (Note: unit label directly follows the number with no space in `%.2f%s`.)

Pins/errors in `freq_measure` (pin range arg 0..7; out of range from parser: `pin out of range: N, expected 0 to 7`):
* `"Pin IO%d is invalid!"` (>= pin count)
* `"IO%d has no frequency measurement hardware!\r\nFreq. measure is currently only possible on odd pins (1,3,5,7).\r\nIn the future we will fix this using the RP2040 PIO.\r\n"` (needs PWM channel B; BP6 `BUFIO0..7` = GPIO8..15 so odd IOs; UNCONFIRMED for BP6 mapping, source assumption)
* `"IO%d is unavailable because IO%d or IO%d is in use as a frequency generator (PWM)!\r\nIn the future we will fix this using the RP2040 PIO\r\n"`
* `"IO%d is in use by %s!\r\n"` (pin label owner)
Timing: one measurement takes a 1 ms probe plus gate up to 100 ms (`freq_measure_period`), plus 100 ms for duty (`freq_measure_duty_cycle`), so roughly 0.1-0.25 s each.

## 4. Self-test `~`

File: `src/commands/global/cmd_selftest.c` (`cmd_selftest`, `cmd_selftest_handler`). Registered `~`, `allow_hiz=true`.

Preconditions / early outs:
* scope running: `"Can't self test when the scope is using the analog subsystem - use the 'd 1' command to switch to the default display\r\n"`.
* `system_config.mode != 0`: `"Selftest only available in HiZ mode\r\n"` (nothing else happens).
* No prompt asks you to remove devices: the "Disconnect any devices before running self-test" warning exists only in the `-h` usage text.
* Only prompts: (a) if NAND has no file system: `"No file system!\r\nFormat the Bus Pirate NAND flash?\r\nALL DATA WILL BE DESTROYED."` + `"\r\ny/n >\x03"` (answer `n`),
  then `"FORMAT NAND FLASH: OK\r\n\r\n"` or `"FORMAT NAND FLASH: ERROR! <chinese chars>\r\n\r\n"`; (b) **the push-button test at the end blocks until you press the physical button twice or send SPACE** (see below).

Printed lines in order (BP6: `BP_HW_FALA_BUFFER` and RP2350 both true):
```
SELF TEST STARTING\r\nDISABLE IRQ: OK\r\n          (500 ms delay)
ADC SUBSYSTEM: VUSB  4.xxV OK        | ADC SUBSYSTEM: VUSB NOT DETECTED (x.xxV). ERROR!     (format "ADC SUBSYSTEM: VUSB " then " %1.2fV OK\r\n")
FLASH STORAGE: OK | FLASH STORAGE: NOT DETECTED. ERROR!
PSU ENABLE: OK | PSU ENABLE: PSU ERROR CODE %d
VREG==VOUT:  %d = %d OK | " %d > %d ERROR!!" | " %d < %d ERROR!!"        (mV values)
BIO FLOAT TEST (SHOULD BE 0/<0.30V)         then per pin 0..7:  "BIO%d FLOAT: %d/%1.2fV OK|ERROR!"
BIO HIGH TEST (SHOULD BE >3.00V)            "BIO%d HIGH: %1.2fV OK|ERROR!" and "BIO%d SHORT->BIO%d (%d/%1.2fV): ERROR!"
BIO LOW TEST (SHOULD BE <0.30V)             "BIO%d LOW: %1.2fV OK|ERROR!" and "BIO%d SHORT->BIO%d (%1.2fV): ERROR!"
LA_BPIO TEST (SHOULD BE 1)                  "LA_BPIO%d HIGH: %d OK|ERROR!", "LA_BPIO: 0:%d 1:%d ... 7:%d", "LA_BBIO%d SHORT->BIO%d (%d): ERROR!"
TEST RP2350 E9 BUG FIX                      (errors: "ERROR: BIO%d shows E9 behavior", then 'RP2350 E9 silicon bug detected, try "bug e9 -a" to confirm')
BIO PULL-UP HIGH TEST (SHOULD BE 1/>3.00V)  "BIO%d PU-HIGH: %d/%1.2fV OK|ERROR!" / short lines
BIO PULL-UP LOW TEST (SHOULD BE <0.30V)     "BIO%d PU-LOW: %1.2fV OK|ERROR!" / short lines
CURRENT OVERRIDE: OK | CURRENT OVERRIDE: PPSU CODE %d, ERROR!
CURRENT LIMIT TEST: OK | "PPSU CODE %d, ADC: %d, ERROR!" printed 5 times 200 ms apart
PUSH BUTTON (SPACE TO SKIP): <press> \r\nPUSH BUTTON (SPACE TO SKIP): <release> OK\r\n     | "SKIPPED\r\n"
```
Final summary (exact):
* all good: `"\r\nPASS :)\r\n"`
* any failure: `"\r\nERRORS: %d\r\nFAIL! :(\r\n"` (count of failing sections).
**Skipping the button with SPACE returns "true" (failure), so a script that sends SPACE always ends with `ERRORS: 1` + `FAIL! :(` even if everything else is OK.** A self-test that must give
PASS needs a human to press and release the board button. The command otherwise needs no key. Duration ~ a few seconds before the button stage (UNCONFIRMED, summed delays: 0.5 s + several 1-5 ms per pin).
Any wire/device on the IO pins causes `BIO...ERROR!`/`SHORT` lines. Side effects: PSU enabled at 3.3 V with 0 limit override, pull-ups toggled; PSU and pull-ups are disabled at the end (`pullup_disable(); psu_disable();`).
LCD updates are disabled during the test (`BP_ICM_DISABLE_LCD_UPDATES`) and re-enabled at the end.

## 5. blueTag: `bluetag`

Files: `src/commands/jtag/bluetag.c` (`bluetag_handler`, `bluetag_cli`), `src/lib/bluetag/src/blueTag.c` (scan + output, version `"1.0.2"`), `src/mode/jtag.c`.
**`bluetag` is a mode command of `JTAG` mode only** (`jtag_commands[]` in `mode/jtag.c`; it is not in the global table). In any other mode (incl. HiZ) it prints `"Invalid command: bluetag. Type ? for help."`.
Mode entry: `m jtag`. `jtag_setup()` returns 1 with no prompts, so `m jtag` is fully non-interactive and just prints `"\r\nMode: JTAG"` and then the prompt `JTAG> `. Preflight (`jtag_preflight_sanity_check` -> `ui_help_sanity_check(true,0)`) prints (non-blocking):
`"\x07\r\nError: No voltage detected on VOUT/VREF pin\r\n"` + `"Hint: Use W to enable power, or attach an external supply\r\n"` if VOUT/VREF < 0.79 V. The scan still runs.

Usage string: `bluetag [jtag|swd] [-c <channels>] [-v(ersion)] [-d(isable pulsing)]`.
* `bluetag jtag -c 6` / `bluetag swd -c 4` run the scan non-interactively. `-c <count>` counts channels starting at IO0 (IO0..IO(n-1)). Required: without `-c`:
  `"Specify the number of channels with the -c flag, -h for help\r\n"`. JTAG range 4..8: `"Invalid number of JTAG channels (min 4, max 8)\r\n"`. SWD 2..8: `"Invalid number of SWD channels (min 2, max 8)\r\n"`.
* `-d` disables pin pulsing (JTAG only; the SWD path ignores it); prints `"Disabled pin pulsing\r\n"`.
* `-v`: `"Current version: 1.0.2\r\n"`.
* With no verb: `bluetag` alone starts the interactive menu (splash screen, `" > "` prompt, keys `h v p j s x`). It reads raw single keys (`rx_fifo_get_blocking`), `j`/`s` then ask `"Number of connected IO, starting with IO0 (Min %d, Max %d, x to exit): "` and take ONE digit, `x` exits (and `x` at the ` > ` prompt returns to the BP prompt). Avoid it in scripts.
Always printed before a scan: `"Number of channels set to: %d\r\n"` (after `-d` line if any).

Scan output: a progress bar redrawn with `\r` on one line, no trailing newline until the end: `"\r     Progress: [" + '#'*n + ' '*(50-n) + "] %.2f%%"` (`blueTag.c: printProgress`).

On a JTAG hit (`displayPinout`, `displayDeviceDetails`, `BTAG_EOL "\r\n"`), after the progress bar reaches 100%:
```
\r\n\r\n     [  Pinout  ]  TDI=IO%d TDO=IO%d TCK=IO%d TMS=IO%d TRST=IO%d \r\n\r\n      (or " TRST=N/A " when none found)
     [ Device %d ]  0x%08X (mfg: '%s', part: 0x%x, ver: 0x%x)\r\n        (one per device; the "(mfg..." part only if the IDCODE passes the JEDEC sanity check)
\n
```
On an SWD hit (`swdDisplayPinout`): `"     [  Pinout  ]  SWDIO=IO%d SWCLK=IO%d\r\n\r\n"` then `"     [ Device 0 ]  0x%08X (mfg: '%s', part: 0x%x, ver: 0x%x)\r\n"` then `"\n"`.
Nothing found (`bluetag.c`): progress bar finalised to 100%, then `"\r\n\r\n"` and `"\tNo JTAG devices found. Please try again.\r\n"` / `"\tNo SWD devices found. Please try again.\r\n"`.
The command ends by itself, returns to the `JTAG> ` prompt, no key needed. No Ctrl-C/abort inside the scan loops (nothing polls the keyboard), so a long scan cannot be interrupted.
Permutations: JTAG = n*(n-1)*(n-2)*(n-3) (6 ch: 360, 8 ch: 1680) plus extra TRST probes on a hit; SWD = n*(n-1). Per JTAG permutation: a 4 ms pin pulse (2+2 ms, unless `-d`) plus bypass test and ID read, so ~ seconds to a few tens of seconds for 6 channels and well over a minute for 8. UNCONFIRMED real durations (not measured; the loop has `sleep_ms(2)` x2 per pulse and bit-banged shifts).
The scan drives the IO pins; the pin labels are only set in the interactive path (the CLI path leaves them commented out).

## 6. Mode change `m <name>`

File: `src/ui/ui_mode.c` (`ui_mode_enable_args`, `mode_interactive_prompt`). Command `m` allowed in HiZ.
* `m` alone: `"Mode selection"`, then ` %lu. <protocol_name>` lines (1-based in `modes[]` order), then `"\r\nx to exit >\x03"`; type the number.
  Invalid -> `"\x07\r\nError: Invalid option\r\n"` and returns.
* `m <name> [flags]`: name matches `protocol_name` case-insensitively (`m jtag`, `m i2c`, `m HiZ`). It prints `"\r\nMode: <PROTOCOL_NAME>"` (no trailing newline) BEFORE running the mode's setup, then the setup's own prompts (if any).
* **Non-interactive rule:** every mode that has options defines one "primary" flag; if that flag is present the mode takes CLI flags and silently defaults everything else, otherwise it runs the wizard.
  I2C: `-s <1-1000 kHz>` (default 400), `-c off|on` clock stretch. UART: `-b <baud>`, `-d 5-8`, `-p none|even|odd`, `-s 1|2`, `-f off|rts`, `-i normal|invert`. SPI: `-s <1-625000 kHz>`, `-d 4-8`, `-o idle_low|idle_high`, `-a leading|trailing`, `-c low|high`.
  2WIRE: `-s 1-1000`. LED: `-d ws2812|apa102|onboard`. (Primary flags are I2C `s`, UART `b`, SPI `s`, 2WIRE `s`, LED `d`.) 1WIRE, JTAG, DIO and HiZ have no setup prompts. Usage text in source: "*If speed flag is provided, other values will use defaults."
  Example: `m i2c -s 400` -> `Mode: I2C` and done. `m uart -b 115200 -p even`.
* Interactive wizard for I2C (`hwi2c_setup`, when no `-s`): if a saved `bpi2c.bp` exists it first prints `"\r\n\r\nUse previous settings?\r\n"`, the saved settings and `"\r\ny/n, x to exit (Y) >\x03"` (Enter or `y` = reuse, `n` = continue, `x` = abort). Then the speed prompt: description `"I2C speed"` (`T_HWI2C_SPEED_MENU`), hint `"1kHz to 1000kHz"`, then `"\r\n\r\n x to exit (400) >\x03"`-style line (`"x to exit (%lu) >"`); then clock stretching as a numbered choice (`1. Off*`, `2. On`, `x to exit (1) >`). **Accept defaults by sending an empty line (Enter) at each prompt.** The wizard saves the choice for next time (`storage_save_mode`), and the CLI path also saves (`storage_save_mode` after success).
  UART wizard prompts in the order baud, data bits, parity, stop bits, flow control, invert, same style.
* Abort mid-wizard (`x`/Ctrl-C): setup returns 0 and the mode does not change (nothing printed after `Mode: X`).
* Invalid flag value: `"... out of range ..."` error from the section 0 format and mode does not change.
* Changing mode runs `protocol_cleanup()` of the old mode, switches to HiZ, then sets up the new one; the PSU is disabled by the HiZ setup (`hiz_setup_exec` "disables power supply etc."), so re-run `W` after `m`.
* `m foo` (unknown name): UNCONFIRMED, `bp_cmd_get_action` did not match so it falls to the interactive list (likely, not verified).

## 7. Power `W`/`w`, pull-ups `P`/`p`

### W (file `commands/global/w_psu.c`, `psucmd_enable_handler`)
Not allowed in HiZ. Syntax: `W [volts] [mA] [-u <percent>]`. Ranges: volts 0.8..5.0 (default 3.3), mA 0..500 (default 300; **0 = no current limit**), `-u` 1..100 (default 10; **100 disables undervoltage protection**).
* `W 3.3 100` or `W 5 50 -u 20`: fully non-interactive. `W 3.3` uses 300 mA.
* `W` alone: prompts `"Voltage, 0.8-5.0volts"` / `"x to exit (3.30) >"`, then `"Current limit, 0-500mA"` / `"x to exit (300.00) >"`.
* **Trap:** if the volts argument is out of range or unparsable (`W 9`), `bp_cmd_positional` prints `volts out of range: 9.00, expected 0.80 to 5.00` and the handler then FALLS INTO the interactive voltage+current prompts (it only exits on `BP_CMD_EXIT`). A script must be ready to answer `x`. If volts is fine but current is out of range, it errors out cleanly.
Output on success (colourless):
```
%1.2fV requested, closest value: %1.2fV\r\n
%1.1fmA requested, closest value: %3.1fmA\r\n          (or "Current limit: Disabled\r\n" when mA = 0)
Undervoltage limit: %d.%dV (%d%%)\r\n                    (or "Undervoltage limit: Disabled\r\n" when -u 100)
\r\nPower supply:  Enabled\r\n                           (printed even if an error follows)
Vreg output: %d.%dV, Vref/Vout pin: %d.%dV, Current: %d.%dmA\r\n
```
Errors (then `res->error`, BEL, prompt): `"\x07\r\nError: Current over limit, power supply disabled\r\n"` (`PSU_ERROR_FUSE_TRIPPED`), `"\x07\r\nError: Potential short circuit, power supply disabled\r\n"` (`PSU_ERROR_VOUT_LOW`),
`"\r\nError: Vout > on-board power supply. Backflow prevention activated\r\n\tIs an external voltage connected to Vout/Vref pin?\r\n"` (`PSU_ERROR_BACKFLOW`).
Scope running: `"Can't turn the power supply on when the scope is using the analog subsystem - use the 'ss' command to stop the scope\r\n"`.
Asynchronous: if the supply trips later, the main loop prints the BEL and `Error: Current over limit...`/`Potential short circuit...` lines (`psucmd_show_clear_error`) at the next loop, possibly mid-session.
### w
`w` -> `"Power supply: Disabled"` (no newline from the handler; the dispatcher adds `\r\n`). No error if already off.
### P / p (file `commands/global/p_pullups.c`, non-PULLX branch for BP6)
No arguments or flags on BP6 (the `10K`, `-d`, `-p` forms are PULLX/BP7 only; passing extras on BP6 is UNCONFIRMED but they are not parsed). Not allowed in HiZ.
* `P` -> `"Pull-up resistors: Enabled (10K ohms @ %d.%dV)"` (tenths of volts of Vref/Vout; format `"%s%s:%s %s (%s @ %s%d.%d%sV)\r\n"`). If Vref/Vout ADC < 250 raw it adds
  `"\r\nWarning: no/low voltage detected.\r\nEnable power supply (W) or attach external supply to Vout/Vref"` (not an error).
* `p` -> `"Pull-up resistors: Disabled"` (no newline from handler).

## 8. `binmode`

Files: `src/commands/global/cmd_binmode.c`, `src/binmode/binmodes.c` (table + `binmode_setup/service/cleanup`), `src/binmode/*.c`.
`binmode [number]` (`binmode_range` min 1, max `BINMODE_MAXPROTO`=8, default 1), allowed in HiZ, `binmode -h` prints `"Active binmode: <name>"` plus help.
Menu printed when no number is given (`" %d. %s\r\n"`, order = `binmodes[]` table order, NOT the enum order), then prompt `"Select binary mode"` / `"x to exit (1) >\x03"`:
```
 1. SUMP logic analyzer
 2. BPIO2 flatbuffer interface          (the entry is called "dirtyproto" in code; name string dirtyproto_mode_name)
 3. Arduino CH32V003 SWIO
 4. Follow along logic analyzer
 5. Legacy Binary Mode for Flashrom and AVRdude
 6. IRMAN IR decoder (LIRC, etc)
 7. AIR capture (AnalysIR, etc)
 8. Bus Pirate v3 unbrick: bootloader v4.6 (ICSP)
```
Note: `enum` in `binmodes.h` lists LEGACY4THIRD before FALA but the table has FALA (index 3) before Legacy (index 4); the menu follows the table. Use `binmode <n>` with the numbers above, but verify against the printed menu at runtime.
Flow: `binmode 5` -> `binmode_cleanup()` of the old one -> `"\r\nBinmode selected: <name>\r\n"` -> if `can_save_config` (SUMP, BPIO2, FALA only): `"Save setting?"` + `"\r\ny/n >\x03"` (Enter alone is NOT a default, it re-asks; `y` saves `bpbinmod.bp`, `n` keeps it for this power cycle only; nothing is printed on save) -> `binmode_setup()` -> optional setup message (FALA prints a hint).
Second USB serial port (CDC index 1) is what binmodes speak; the terminal is CDC 0.
`system_config.binmode_select` defaults to 0 = **SUMP** (`system_config.c`), then `binmode_load_save_config(false)` at boot overrides it from `bpbinmod.bp` if present. So on a unit with no saved file the second port is SUMP, not BPIO2 (UNCONFIRMED what the user's unit has stored).
* **SUMP** (`sump.c`): terminal stays unlocked, nothing printed. The SUMP state machine arms when the second CDC port gets opened; it keeps speaking SUMP on that port until the binmode is changed again with `binmode <n>` (or the saved/booted selection changes after a reset), it is not tied to replug. Side effect: **when CDC1 connects and (mode is HiZ or no terminal is connected) it enables the PSU at 3.3 V / 100 mA with override (`psu_enable(3.3, 100, true, 100)`) and disables it again on disconnect or button press** (`sump_logic_analyzer_service`). While SUMP is selected, BPIO2 on that port will NOT answer.
* **BPIO2** (`bpio.c`): second port speaks BPIO2 flatbuffers while this binmode is selected; terminal unlocked.
* **Legacy** (`legacy4third.c`; `lock_terminal=true`, `can_save_config=false`, `reset_to_hiz=false`): prints `"\r\nBinmode active. Terminal locked\r\n"` (the main loop stops reading commands), then the legacy
  setup asks on the terminal, in order: `"\r\nSet OUTPUT HOLD(IO2) & WP(IO3) pins? (no=INPUT)"` (+ `"\r\ny/n, x to exit (Y) >\x03"`), if yes `"\r\nSet HOLD HIGH? (no=LOW)"`, `"\r\nSet WP HIGH? (no=LOW)"`,
  `"\r\nClock on IO0 for avrdude -x cpufreq?"`, then `"\r\nPower supply\r\nVolts (0.80V-5.00V)"` + `x to exit (3.30) >`, `"\r\nMaximum current (0mA-500mA)"` + `x to exit (200.00) >`,
  `"\r\nPower supply set to %2.2fV, %3.0fmA\r\n"`, SPI speed note, `"Done! Just execute flashrom or avrdude using the binary com port\r\nTo exit: press the button, or type 'q' here and confirm with 'y'.\r\nEither way the Bus Pirate resets on exit.\r\n"`.
  Enter = default at every prompt; `x` at any of them aborts and resets. The terminal is then a dead console until exit.
  Way out: on the TERMINAL port send `q`, it asks `"\r\nExit legacy binary mode and reset the Bus Pirate? (y/n) "`, answer `y` within 15 s (`n` or timeout stays: `"No answer, staying in legacy binary mode."`), or press the button. It then prints
  `"\r\nExit reason: ...\r\n"`, `"\r\nExiting Legacy Binary Mode...\r\nResetting Bus Pirate...\r\nAfter reconnect press enter to use Bus Pirate in other modes.\r\n"` and calls `cmd_mcu_reset()`: **the unit reboots and the USB ports vanish and re-enumerate**; reconnect and press Enter. A replug also works. Legacy is not saved, so after the reboot the previously saved binmode is active again.
  The legacy protocol runs on CDC 1 (`CDC_SEND_STR(1, ...)`; `\x0F` returns the string `"Bus Pirate v2.5\r\nCommunity Firmware v7.1\r\nHiZ>"` on that port).
* **FALA** (`falaio.c`): terminal unlocked; on non-FALA-buffer boards prints 6 warning lines; BP6 has `BP_HW_FALA_BUFFER` so prints nothing extra.
* **CH32V003 SWIO** (lock + `button_to_exit`), **IRMAN** (lock + `button_to_exit`, PSU 5 V), both print `"Press any key to exit binary mode\r\n"`; **any byte on the terminal** exits, resets `binmode_select` to 0 (SUMP) and sets HiZ (`binmode_service`).
* **AIR** (`irtoy-air.c`): lock, `reset_to_hiz`, PSU 5 V, NO key/button exit in `binmodes.c` (`button_to_exit=false`): UNCONFIRMED how to leave other than replug/reset.
* **BP3 unbrick** (`bp3unbrick.c`): prompts and writes a bootloader over ICSP; contains `"Continue?"` confirm, `"Try again?"`, `"Hold the Bus Pirate v3 in its bootloader ... now?"` and a "press any key or the button" wait. Not to be used in scripts.

## 9. Things that wedge or endanger a scripted session

* **`F <pin>` never ends by itself**; any byte stops it. `~` waits forever for the physical button (SPACE skips but counts as FAIL). Legacy binmode locks the terminal and ends only by `q`,`y` / button / replug (then reboots). CH32V003 and IRMAN binmodes lock the terminal until any key.
* Many commands fall into interactive prompts on bad/missing args (`W 9`, `G`, `F`, `g` with several active, `m` alone, `binmode` alone, `m i2c` without `-s`). Always wait for the `\x03` (ETX) marker, and be ready to send `x`.
* `G` takes pin only; frequency and duty are always separate prompt lines; unit text is mandatory (`1khz`, `50%`). An empty line at the frequency prompt loops with `Error: Unknown units ''`.
* `W`, `P`, `G`, `g`, `a`, `A` are refused in HiZ; `bluetag` exists only in JTAG mode; `~` only in HiZ. `m` resets the PSU, pull-ups-state and pin labels: configure power/pull-ups after the mode change.
* A bare `f` DISABLES a background measurement (or errors) instead of reading; `f <odd pin>` reads. Even pins fail with the "odd pins (1,3,5,7)" message.
* Errors emit BEL and (for `ui_help_error`) a leading `\x07\r\n`; the typed command echo contains `\r`, `ESC[0K`, `ESC[nC` and ghost-hint sequences even with colour off. Parse after stripping them and anchor on the last `\x03`.
* Ctrl-C at the main prompt prints `^C\r\n` and re-prompts (cancels the typed line); at a sub-prompt it aborts that command. It does NOT interrupt a running scan (`bluetag`) or `~`; during `F` it is just "any key".
* PSU faults can print asynchronously (`Error: Current over limit, power supply disabled`, `Potential short circuit, power supply disabled`, each preceded by BEL) at the next idle loop, then the supply is off.
* SUMP selected + CDC1 opened by a client turns on the 3.3 V PSU in HiZ; BPIO clients must make sure binmode 2 is selected (and saved with `y` if it must survive a reboot).
* Saved settings can change prompts: `m i2c`/`m uart` without flags ask `Use previous settings?` when a config file exists; the VT100 Y/n question is asked on connect depending on saved colour state.
* Not read / UNCONFIRMED: real-hardware transcripts, exact scan timings, whether `P` ignores extra args on BP6, mode numbering in the `m` menu for the BP6 build, behaviour of `m <unknown>`, how AIR binmode is left, which binmode a given unit has saved.
