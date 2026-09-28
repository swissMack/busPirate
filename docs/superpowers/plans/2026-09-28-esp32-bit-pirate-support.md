# Plan: add ESP32 Bit Pirate (ESP32-S3 DevKit) as a third board

## Context
The dashboard supports Bus Pirate v3 and v4, both through `BusPirate` (`buspirate/base.py`), which speaks the binary BBIO protocol. The user wants to add ESP32 Bit Pirate (geo-tp, firmware v1.7) running on an **ESP32-S3 DevKit**.

That firmware has **no bitbang mode**. It is a text CLI:
- native USB CDC at 115200, Espressif VID 0x303A
- prompt `<MODE>> `, modes chosen by name (`m i2c`)
- word commands (`scan`, `read`) and partial `[ ] r:N` bus syntax
- 3.3 V only, no switchable supply, internal pull-ups via `P`/`p`

So it needs a new driver, not just a new variant.

**Agreed scope for v1:**
- detect the board
- the raw terminal works
- the existing I2C, SPI and UART panels drive it through its CLI
- unsupported controls are hidden

The UI stays simple and one-click, as the user prefers.

## Approach
**Device-level duck typing.** A new `BitPirate` class offers the same surface that `DeviceSession` and the panels already call, so the panels need no board checks.

### 1. Detection and driver factory
- **New `buspirate/connect.py: open_device()`.** It sends nothing until the board type is decided:
  1. VID 0x303A → `BitPirate`.
  2. FTDI (0x0403) or Microchip (0x04D8) → the existing `BusPirate.open()`, unchanged.
  3. Unknown VID: listen for 300 ms, looking for the "Bit Pirate" banner, "Press any key" or an ANSI-redrawn prompt.
  4. Still unsure: send one `\r` and inspect the prompt.
  5. Otherwise, fall back to the existing BP probe.
- **Bit Pirate open:**
  - Open with DTR and RTS low, because ESP32-S3 USB can reset on them.
  - Drain the port until it goes quiet.
  - Answer the boot prompts: the serial-vs-web question and "Press any key".
  - Send `\r` until a prompt appears.
  - Parse the banner if one was captured.
- **`ports.py`:** add Espressif `303A` to `KNOWN_ADAPTERS`.

### 2. Text-CLI driver, new package `buspirate/bitpirate/`
- **`transport.py`, `CliTransport.command(cmd, timeout)`:**
  - Write `cmd\r` and read until the prompt appears, followed by a brief quiet period.
  - Strip ANSI codes and `\r` redraws.
  - Drop the echoed command and the trailing prompt.
  - Track the current mode from the prompt.
  - Timeouts are per command. Unexpected questions raise `CliPromptError`, so it never hangs.
  - `run_dialog()` handles the interactive `config` prompts.
- **`parsers.py`:** pure functions (`parse_banner`, `parse_prompt`, `parse_scan`, `parse_bus_result`, `parse_error`), table-tested against the canonical strings in `samples.py`. The simulator uses the same strings.
  - **The samples should come from the firmware source's own print statements** (`src/Controllers/I2c*`, `Spi*`, `Uart*` and `src/Views/*` on the `pioarduino` branch), not guesses. They will be replaced with real captures after the hardware session.
- **`modes.py`:** `CliI2C`, `CliSPI` and `CliUART`, duck-typed to what the panels call.
  - **I2C:** `scan` runs the `scan` command. `read`, `write` and `read_register` use bus syntax such as `[0xD0 0x00 [0xD1 r:8]`.
  - **SPI:** `write_then_read` becomes `[0x9F r:3]`, read in chunks of 256 or less. Because of that, `SPIFlash` JEDEC ID, read and dump work unchanged.
  - **UART:** send and monitor.
  - `configure_peripherals` sends `P`/`p` and ignores `power`.
  - Speed, mode and baud accept only the defaults until the `config` dialog has been captured.
- **`device.py`, class `BitPirate`:** `profile`, `serial`, `is_open`, `open`/`close`, `write`, `flush_input`, `stop_stream`, `i2c()`/`spi()`/`uart()`, `resync()` and `release_to_terminal()` (flush only, never 0x0F), plus `protocol_label = "text CLI"`.

### 3. Small refactors to existing code, behaviour unchanged for v3/v4
- **`web/session.py`:**
  - Use `open_device()`.
  - `ensure_mode` falls back to `bp.resync()` (on BP, an alias of `enter_binary_mode`).
  - `enter_terminal` calls `bp.release_to_terminal()`, which on BP runs today's reset, reopen and flush.
  - Add `"bitpirate"` to `SIMULATED_VARIANTS`.
- **`BusPirate`:** add `resync`, `release_to_terminal` and `protocol_label = "BBIO1"`.
- **`I2C` (`buspirate/i2c.py`):** add `read_after_write(addr, ptr, n)`. The I2C panel's EEPROM read and `read_register` go through it, instead of the byte-level primitives.
- **Connection panel:** the identify card shows `protocol_label` instead of `bitbang_version`.

### 4. Capability gating
- **`device.py`:** new capabilities
  - `CAP_BITBANG_PINS`, `CAP_SUPPLIES`, `CAP_ONEWIRE`, `CAP_RAWWIRE`, `CAP_SNIFFER`
  - `CAP_BUS_CONFIG`, `CAP_UART_BUFFERED`, `CAP_UART_BRIDGE`, `CAP_SPI_FLASH_PROGRAM`

  v3, v4 and unknown get all of them. `bitpirate` gets none. Add `parse_bitpirate_banner` and a `describe()` text.
- **`web/registry.py` and `server._panels_json`:** add `Panel.requires` and `Param.requires` and filter on them, since today only actions are filtered. Tag the relevant panels and params. The pins/supplies panel, 1-Wire, raw-wire and the sniffers disappear on the Bit Pirate.

### 5. Board visuals
- **`web/wiring.py`:**
  - Add `BOARDS["bitpirate"]`: a self-drawn SVG `static/img/board-bitpirate.svg` showing the S3 DevKit pin header, with pins GPIO1/2/12/14/39/40, 3V3 and GND, and `cable: False`.
  - Wiring per panel: I2C GPIO1→SCL and GPIO2→SDA; SPI CS12, CLK40, MISO39 and MOSI14; UART RX1 and TX2.
  - `LED_RULES["bitpirate"] = {"PWR": powered}`.
- **`static/app.js`:**
  - `VARIANT_LABELS` entry.
  - The diagram caption comes from `state.board.label`.
  - Hide the cable-colour legend when `cable` is false.
- **`cli.py`:** `--variant` accepts `bitpirate`.

### 6. Simulator and tests (TDD)
- **`buspirate/simulator_bitpirate.py`, class `FakeBitPirateSerial`:** works a line at a time, with echo and ANSI redraws. It handles the boot prompt, `m`, `scan`, `P`/`p`, bus syntax (reusing `FakeFlash`) and unknown commands.
- **New test files:**
  - `tests/bitpirate/`: `test_parsers`, `test_transport` (chunked reads, split prompts, timeouts), `test_fake`, `test_driver`
  - `tests/test_connect.py`: asserts that no `\x00` or 0x0F ever reaches a Bit Pirate, and that the bytes sent to a BP are unchanged
  - `tests/test_dashboard_bitpirate.py`
- **Existing test files:**
  - `conftest.variant` stays v3/v4. Add an `any_client` fixture over v3/v4/bitpirate for the behaviour-level dashboard tests.
  - Deliberate updates: the exact-set simulator test in `test_dashboard.py`, and `"auto,v3,v4"` in `tests/ui/frontend.mjs`.
- **CI (`.github/workflows/tests.yml`):** also run `frontend.mjs` against `--demo --variant bitpirate`.

### Task order
1. Capabilities and the bitpirate profile in `device.py`.
2. `Panel`/`Param.requires` and tagging, with existing suites green.
3. Parsers and samples, taken from the firmware source.
4. Transport.
5. Simulator.
6. `BitPirate` driver and modes, plus `read_after_write`.
7. `connect.py` and `ports.py`.
8. Session and CLI refactor.
9. Wiring, SVG and `app.js`.
10. Dashboard and UI tests, and CI.
11. Docs: spec and plan in `docs/superpowers/`, `docs/bitpirate.md`, and a note in `docs/extending.md`.

## Verification
- `make test` and `make ui-test` stay green for v3 and v4, and the new bitpirate suites pass.
- `buspirate dashboard --demo --variant bitpirate`:
  - The DevKit diagram shows.
  - The supplies, 1-Wire and pins panels are hidden.
  - I2C scan and read, SPI JEDEC ID and UART send all work against the fake.
- **Real ESP32-S3 DevKit (hardware session)** — record the results in the `docs/troubleshooting.md` checklists, then replace `samples.py` with real captures and re-run the tests:
  - USB PID, and whether opening the port resets the board.
  - The boot question and its answer key.
  - Banner capture.
  - `scan` output with 0 and 1+ devices.
  - ACK, NACK and `r:8` output.
  - Repeated start.
  - Unknown-command error text.
  - The `config` dialogs.
  - UART read/exit.
  - `P`/`p` actually switching the pull-ups.
  - A terminal round trip that stays in sync.
