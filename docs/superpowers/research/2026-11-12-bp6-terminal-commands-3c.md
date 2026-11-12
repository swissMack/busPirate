# Bus Pirate 6 text terminal, phase 3c: smart cards, USB-PD, disk, scripts (from firmware source)

Source: github.com/DangerousPrototypes/BusPirate5-firmware, commit **e2429e0c1412ea0c6315827aafdc8cf054d19d87**
(same as [C] `2026-11-11-bp6-terminal-commands.md` and [3b] `2026-11-11-bp6-terminal-commands-3b.md`). BP6 build only.
Nothing was run on hardware. Partial: SLE4442 and `glitch` are not covered here.

## 1. HDUART and SIM / bank card ATR

* All settings take flags: `m hduart -b 9600 -p even -s 2`. Received parity is not checked.
* No dedicated smart-card command (`sim` is a commented-out stub).
* `r` gives up after 0xfff polls, too short to wait for an ATR. Use async print instead: `}` (reset low), then
  `[ {` (print on, release reset). Bytes arrive as `0x%02x ` after the prompt.
* `bridge` exits only on the board button and drives IO2. Do not automate it.
* UNCONFIRMED: whether HDUART master mode receives from an open-drain card at all.

## 2. USB-PD (`usbpd`)

* Present in the BP6 build as an **I2C-mode command** (`commands/i2c/usbpd.c`, `lib/ap33772s/`; registered in
  `hwi2c_commands[]` with no `#ifdef`). Only the USBPD *mode* is compiled out. Run `m i2c` first.
* Verbs `status | request | reset`; no verb shows help. Flags `-p <index>`, `-v <mV>` (PPS/AVS only), `-i <mA>`
  (current is `-i`, not the `-c` in the docs). `status` only reads the chip.
* Failures never set the error flag, so there is no BEL; parse the text.
* `fusb302 scan` is an interactive single-key command: do not automate.

## 3. Disk

* FAT short names only (8.3, long names off); every file is dated 2020-01-01. No command reports free space.
* `rm` deletes with no prompt. `format` asks y/n twice (`-y` skips both). `dump <bytes> <file>` overwrites with no prompt.
* `hex` pages every 21 rows unless `-c` is given.
* FatFs errors print with no line ending.
* While the terminal is connected the USB disk is read-only to the computer. Each firmware write ejects and
  re-inserts the drive and waits for the host to poll it (UNCONFIRMED: possible hang).
* `edit` and `hexedit` are full-screen interactive editors: do not automate.

## 4. Macros and scripts

* Any byte received while a script runs aborts it (operator-precedence bug in `script.c`: `c|0x20 == 'x'`).
  The same bug makes `script -p` abort on the first Enter.
* Lines are cut at 256 characters. `macro` matches ids by prefix. Macro file and button bindings live in RAM only.
* `pause -b` waits only for the physical button.

## 5. Ended only by the button or a replug

HDUART/UART `bridge`; `glitch` while waiting for a target reply.

## Recommendations for automation

| Item | Verdict | Reason |
|---|---|---|
| SIM / bank card ATR | automate read-only | flags cover the setup; ATR via async print |
| USB-PD | automate (`status`; `request` above 5 V on its own yes) | command exists in I2C mode |
| Disk | automate `ls`, `cat`, `hex -c`; `rm` on its own yes; not `format`, `edit`, `hexedit` | no prompts on delete |
| Macros / scripts | do not automate | any incoming byte aborts a run; button-only pauses |
| `bridge`, `fusb302 scan` | do not automate | button-only exit / interactive |
