# Errors: message → cause → fix

Messages are quoted as the tool prints them. The esp and avr notes have the
full esptool and avrdude tables; the main ones are repeated here.

## The port

| Message | Cause | Fix |
|---|---|---|
| `no USB serial ports found` | the Mac cannot see the adapter | another USB cable (many are power-only), plug in directly, not via a hub |
| `cannot open /dev/cu.…: Resource busy` | another program holds the port: a forgotten `screen`, the dashboard, esptool/avrdude | `lsof \| grep cu.usbserial`; `screen -ls`; disconnect the dashboard |
| hangs forever, no error | a `/dev/tty.*` device, which waits for carrier detect | use the `/dev/cu.*` device of the same name |
| `A serial exception error occurred` (esptool) | port in use, missing, unplugged, no permission, or bad driver | free the port; on Linux add the user to `dialout`/`uucp` |

## v3 / v4

| Message | Cause | Fix |
|---|---|---|
| `no BBIO response after 25 attempts` | wrong port; wrong baud (must be 115200 8N1); firmware mid-command from an earlier session; firmware older than v2.6 | check the port; unplug for a few seconds and retry (a power cycle always resolves a stuck board) |
| `expected a BBIO<version> banner, got …` | the device is mid-stream from an earlier command | reconnect; the driver resynchronises after a failed mode entry |
| self-test reports errors | something is attached to the pins (v3 only) | disconnect the probe cable from everything; on a v4 `~` asks for ADC jumpered to +3.3V, else `ADC(0.00)` fails |
| `ExternalVoltageError` on the v4 pull-up rail | a voltage is already on VPU; connecting the internal rail would short it | leave the rail off and use the target's supply on VPU |
| `UnsupportedFeatureError` | the connected variant lacks the feature | it names the board that has it |
| v4 hangs after extended AUX (`0x09`) | firmware 7.0 waits on a UART the host is not on | unplug; drive AUX from the pins page instead |
| UART bridge will not exit | v3/v4 bridge is "reset to exit" | unplug and replug |
| `pirate-loader … ERROR, timeout` | its goodbye after `--hello` or a flash; it restarts the board | harmless |
| `SKIPPED by bootloader` (last page) | the protected configuration page | expected |

## Bus Pirate 6

| Message | Cause | Fix |
|---|---|---|
| `did not answer on its BPIO2 port` | a stuck board, a `screen` on either port, or firmware older than 2026-10-12 | unplug and replug; quit `screen`; update firmware |
| `Current limit tripped`, supply switches itself off | the target drew more than the limit | find the short, then Re-enable; raise the limit only if the target really needs it |
| `The supply would not start` / `Power supply initialization failed` | the target already draws more than the limit at switch-on | no trip to re-enable: find the short or raise the limit |
| terminal hangs at "VT100 compatible color mode?" | Ctrl-C was sent there | replug; answer `n` or `y` only |
| both ports stop answering | a BPIO2 reply was sent to a closed port | replug; always read every reply before closing |
| BPIO2 slow (about 3 s) | normal after selecting it, and after opening the terminal | wait; do not re-send |
| terminal locked after binmode 5 | Legacy binary mode for flashrom/avrdude | replug to leave it |
| "Disk Not Ejected Properly" | the BP6's own storage drive | harmless; eject in Finder first to avoid it |

## Bit Pirate

| Message | Cause | Fix |
|---|---|---|
| connect fails right after plugging in | it spends about 3 s choosing its terminal | wait and connect again |
| no prompt on the port | plugged into UART / USB TTL, not USB / USB OTG | use the USB port |
| Wi-Fi `Connection failed` | the firmware gives no reason | try once more |
| Web CLI page: `Nothing matches the given URI` | the web server starts before its page | wait about 10 s and reload |

## Bus symptoms

| Symptom | Cause | Fix |
|---|---|---|
| I2C scan finds nothing | pull-ups off or VPU floating; target unpowered; SDA/SCL swapped; no common GND | see the i2c note |
| I2C scan: every address answers | VPU floating (SDA low reads as ACK) | pull-ups off, or VPU to a supply |
| SPI all `00` or all `FF` | MISO not connected, WP/HOLD not high, or CLK on the wrong lead | not a blank chip; see the spi note |
| SPI writes do nothing | WP held low | tie WP high |
| UART garbage | wrong baud rate | wiring faults give silence, not nonsense |
| UART: stream of one junk byte (`18` on a v4) | line never set up: 300 baud, TX not driving | set the line up first |
| 1-Wire finds nothing, ROM all `00` | no pull-up | 4.7 kΩ from DQ to VCC |
| DS18B20 reads exactly 85.0 °C | the conversion never completed | wait 750 ms; parasite sensors need VDD |
| worked yesterday, not today | an intermittent DuPont lead | swap the probe cable |

## External tools (short)

| Message | Cause | Fix |
|---|---|---|
| esptool `No serial data received.` | RX/TX not connected, or not in download mode | crossover; redo the boot sequence |
| esptool `Wrong boot mode detected (0xXX)!` | booted normally: boot pin not low at reset | redo the boot sequence |
| esptool `…getting no sync reply: The serial TX path seems to be down.` | host → ESP line broken | Bus Pirate TX to ESP RX |
| esptool `Invalid head of packet (0xXX)` | bad cable, breadboard, brown-out | own supply, shorter leads |
| avrdude `invalid device signature` (`0x000000` / `0xffffff`) | no answer from the chip | wiring, power, RESET on CS, slower `spifreq` |
| avrdude `binary mode not confirmed` | no BBIO answer | right port; BP6 must be in binmode 5 |
| avrdude `reset failed; you may need to powercycle it` | the Bus Pirate did not leave binary mode | replug |

Sources:
- docs/troubleshooting.md
- docs/bus-pirate-6.md
- docs/bus-pirate-v4.md (extended AUX, pirate-loader)
- docs/pins-and-power.md (ExternalVoltageError)
- docs/bitpirate.md (connecting, Web CLI)
- docs/uart.md, docs/i2c.md, docs/spi.md, docs/onewire.md
- docs/official/software/avrdude.md, docs/official/software/flashrom.md (binmode 5)
- https://docs.espressif.com/projects/esptool/en/latest/esp32/troubleshooting.html
- https://github.com/avrdudes/avrdude/blob/main/src/buspirate.c, https://github.com/avrdudes/avrdude/blob/main/src/main.c
