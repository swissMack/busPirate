# MCP server

`buspirate mcp` lets an AI assistant that speaks the Model Context Protocol
(Claude Code, Claude Desktop) drive a Bus Pirate or ESP32 Bit Pirate. It
reports results in real units (°C, hPa, volts), says which wire goes where
with its colour, and never switches the target's power on without your yes.

It needs **Python 3.10+** and the optional `mcp` extra. The rest of the
package stays on Python 3.8 and does not need it.

## Setup

```bash
make setup                                # .venv with everything (3.10+)
.venv/bin/pip install -e '.[mcp]'
claude mcp add buspirate -- "$PWD/.venv/bin/python" -m buspirate mcp
```

If `.venv` is older than 3.10, let `uv` supply the Python instead. This leaves
`.venv` alone, and `--scope user` makes the server available in every folder:

```bash
claude mcp add --scope user buspirate -- \
  uv run --isolated --python 3.13 --with-editable "${PWD}[mcp]" python -m buspirate mcp
```

Use the absolute path, as `${PWD}` gives you. Claude Code starts the server in
whatever folder you are working in, so a relative `.` points somewhere else.
In zsh, write `"${PWD}[mcp]"`, not `"$PWD[mcp]"`: zsh reads the second form as
an array subscript and drops the path.

With one board plugged in, the server opens it at start-up. With several, or
none, the assistant calls `find_boards` and then `connect`. If new tools do not
appear after connecting, run `/mcp` and reconnect `buspirate`.

Try it with no hardware: `make mcp-demo VARIANT=bp6` (or `v3`, `v4`,
`bitpirate`) serves a simulated board. Add it with
`claude mcp add --scope user buspirate-demo -- uv run --isolated --python 3.13 --with-editable "${PWD}[mcp]" python -m buspirate mcp --demo --variant bp6`.

## Tools

The tool list is **gated by the board**: before a connection only the first
group exists; after it, only tools the connected board can do are listed (a
board without an ADC gets no `pins_read_voltage`, for instance).

| Tool | What it does |
|---|---|
| `find_boards`, `connect` | list serial ports with the likely boards; open one |
| `knowledge_topics`, `knowledge_read`, `knowledge_search` | short distilled notes (boards, I2C, SPI, UART, power, errors, ...) and search over the bundled manuals |
| `disconnect`, `board_status` | close the board safely; mode, firmware, supply state |
| `wiring` | for a job (`i2c`, `spi`, `uart`, `onewire`, ...): every step with pin label and wire colour, plus the panel's notes |
| `measure_voltages` | read the target's voltage, for when you do not know it |
| `power_plan`, `power_apply`, `power_off` | the two-step power switch, below |
| `hiz` | all pins to high-impedance (the safe state) |
| `i2c_scan`, `i2c_read`, `i2c_sensor` | scan with chip labels; read a register; read a known sensor in real units |
| `i2c_write`, `lcd_write` | write raw bytes (a register is the first byte); show text on an HD44780 LCD behind a PCF8574 backpack. On a v3/v4 the supply drops when the tool returns, so an LCD powered from the Bus Pirate loses its text |
| `spi_identify`, `spi_transfer`, `spi_sensor_read` | flash JEDEC ID with the part named; raw transfer; known SPI sensors |
| `uart_send`, `uart_listen` | send text; capture what the target says |
| `onewire_scan` | list 1-Wire devices (DS18B20 temperatures in °C) |
| `pins_read_voltage`, `pwm`, `pwm_off`, `frequency` | ADC, PWM and frequency counter, where the board has them |

## The power flow

1. The assistant asks you whether you know the target's voltage.
2. If you do not, it calls `measure_voltages`, suggests a level, and you confirm it.
3. `power_plan {millivolts, voltage_source}` shows the plan (`"owner"` or `"measured"`) and returns a token. Nothing has changed on the board yet.
4. You say yes to that plan; only then does the assistant call `power_apply {token}`.

Tokens are single-use and expire after 300 s. On the **Bus Pirate 6/5** the
supply is 800-5000 mV with a current limit of 1-500 mA (the server defaults to
100 mA). A plan **above 3600 mV, or with no current limit (0 mA)**, is flagged
`needs_extra_confirmation`: the assistant must ask you a **second** time,
naming the voltage and the limit.

What "powered" means differs by board:

- **v3 / v4:** only 3.3 V or 5 V, picked by which wire you use. The supply is
  asserted for each bus job and **drops when the job's mode exits**, so
  `"power": true` means *approved and applied for this job*, not "stays on".
- **BP6 / BP5:** the supply stays on until `power_off`, a trip, or disconnect.
- **ESP32 Bit Pirate:** the supply is the **dock switch** (1.8, 3.3 or 5 V),
  set by you. Software cannot turn it off; `hiz` says so.

## The Bus Pirate 6 server (`bp6`)

`buspirate mcp-bp6` is a second server for the **Bus Pirate 6 only**. It works
from recipes: name a device ("lcd", "bme280", "ds18b20", "spi flash") and the
assistant finds its recipe, shows you the wiring and the power plan in one
message, and runs it after your yes. Register it at user scope through uv,
from the repo folder:

```bash
R="$PWD"
claude mcp add --scope user bp6 -- \
  uv run --isolated --python 3.13 --with-editable "${R}[mcp]" python -m buspirate mcp-bp6
claude mcp add --scope user bp6-demo -- \
  uv run --isolated --python 3.13 --with-editable "${R}[mcp]" python -m buspirate mcp-bp6 --demo
```

As above, in zsh write `"${R}[mcp]"`, not `"$R[mcp]"`. `bp6-demo` serves a
simulated Bus Pirate 6, with no hardware.

How it differs from `buspirate`:

- **Every tool is listed from the start**, and there is no `find_boards`. The
  board opens on first use, not at start-up, so `bp6` can be registered next to
  `buspirate` without fighting over the port. If the port is busy, the tool
  says which program to close. With two BP6s plugged in it uses the first and
  names the others; `connect(port)` picks another. Any other board is refused
  with a pointer to the `buspirate` server.
- **Recipes:** `recipes(query)` finds one; `recipe_plan(name, options)`
  measures the target and returns the wiring, the power plan and a token
  without switching anything; `recipe_run(token)` applies the plan, runs a
  check, then the action. A target that already has its own voltage is
  *target-powered*: the supply stays off. If the check fails, power stays as
  planned so you can fix the wiring and re-run with `recipe_run(token=None)`
  within 5 minutes.
- **Primitive tools:** `board_status`, `connect`, `hiz`, `power_off`,
  `measure_voltages`, `power_plan`, `power_apply`, `i2c_scan`, `i2c_read`,
  `i2c_write`, `spi_transfer`, `uart_send`, `uart_listen`, `onewire_scan`,
  `pins` (drive IO pins with 1, 0 or `"in"` and read every pin's level and
  voltage) and `bp6_notes` (limits, pin map with colours, the pull-up rule and
  the risks).
- **The supply is capped at 5 V, and goes off when the session ends:** on exit
  the board goes to HiZ, supply and pull-ups off, so an LCD loses its text.

## Stage roadmap

Stage 1 (this server): connect, gating, power flow, wiring, knowledge, I2C,
SPI read/identify, UART, 1-Wire, pins, PWM.

- Stage 2: ESP flashing
- Stage 3: AVR
- Stage 4: SPI flash write
- Stage 5: the remaining modes (sniffers, SUMP, JTAG, raw wire, LCD, extra
  Bit Pirate modes) plus a terminal escape hatch
- Stage 6: low-voltage PIC programming
- Knowledge layer 2: the Dangerous Prototypes and Espressif pages

The hardware checklist is in
[Troubleshooting](troubleshooting.md#mcp-server-stage-1).
