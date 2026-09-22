# Pins & power

In bitbang mode the Bus Pirate is a small bench instrument: five I/O pins,
two supplies, a voltmeter, a frequency counter and a PWM output.

## The supplies

`configure_peripherals(power=True)` — the **Power the target** tick in the
dashboard — switches on the 3.3V **and** 5V regulators together. There is no
command to choose one: **you pick the voltage by which probe wire you
connect.** Never connect both to the same target.

Each is good for about **150 mA**. A hungry target should use its own supply,
with only the grounds tied together.

The probe cable's supply wires are **+5V orange (pin 8)** and **+3.3V red
(pin 9)**.

## The four LEDs

Along the top edge, left to right, the silkscreen names them **PWR**, **USB**,
**MODE** and **VREG** on both variants. Which ones are under software control
differs — a v3 has one, a v4 has two, because the v4 has no FT232RL and does
USB itself off the PIC:

| LED | v3 | v4 |
|-----|----|----|
| **PWR** | Hardware — `VCC → R2 1K1 → LED → GND`. The board has power. Nothing can turn it off. Dark means a dead cable, a dead port or a dead board — check this before anything else. | Hardware. Same rule. |
| **USB** | Hardware — the FT232RL's **RXLED#** pin, through R3. Data is arriving from the host. It **pulses**; at idle it is dark. A permanently dark USB LED with PWR lit is a driver or cable problem — see [macOS setup](macos-setup.md). | **Firmware** — `BP_LEDUSB` = PIC GPIO **RB10** (`hardwarev4a.h:65`). `main.c:76` lights it while the board enumerates over USB; `main.c:95` turns it **off** once enumeration is configured. **This inverts the v3 rule: on a v4, steady dark means it enumerated correctly**, not a fault. There is no FT232RL on a v4 at all — that is why this LED moved into firmware. |
| **MODE** | Firmware — PIC GPIO **RA1** (`BP_LEDMODE`, `hardwarev3.h:51`). Binary mode has been entered. See below. | Firmware — PIC GPIO **RB8** (`BP_LEDMODE`, `hardwarev4a.h:59`). Same behaviour as a v3, a different GPIO underneath. See below. |
| **VREG** | Hardware — the switched 3.3V regulator VR2's own output (`SWV33 → R6 1K1 → LED → GND`). The on-board supplies are on. `configure_peripherals(power=True)` drives **VREGEN** (RA0), which enables VR2 (3.3V) and VR3 (5V) together; the LED simply runs off VR2's output. | Hardware. Same rule. |

### MODE does not mean "in a protocol"

This trips people up, on either variant. The firmware sets `BP_LEDMODE = 1`
in `binBB()` — the moment **binary mode** is entered — and it stays lit for
the whole binary session, HiZ included. The "on when a protocol is active"
behaviour belongs to `procMenu.c`, the **terminal** UI. Anything speaking the
binary protocol, this library and dashboard included, sees MODE lit from the
moment it connects, and dark again the moment you leave binary mode — which
now includes opening the board's own terminal from the dashboard. See
[Dashboard](dashboard.md#the-boards-terminal) for what that costs.

The firmware also turns it **off** for a second, unrelated reason: to signal
trouble mid-session, while you are still in binary mode. These are the
fault cases worth knowing:

- an SPI sniff that cannot keep up (`SPI.c`) — see [SPI](spi.md)
- a UART overrun (`UART.c`)
- the input buffer filling and a byte being dropped (`baseIO.c`)

So **MODE going dark mid-session means one of two things: you (or the
dashboard) deliberately left binary mode for the board's own terminal, or
the firmware just dropped something.** The first is expected and harmless;
the second is a fault. Check which one actually happened before assuming
the worse case.

### The dashboard draws them

The hook-up diagram lights the same LEDs on the board photograph, and the
status bar carries a compact copy visible on every panel. On a v3, USB is
flashed from the traffic feed, matching the RXLED# pulse. On a v4 it is not
flashed at all — it is shown dark once connected, matching the firmware's
own behaviour once enumeration completes.

**They are inferred, not measured.** No command reads LED state back, so the
dashboard shows what the board *ought* to be doing. It is wrong in exactly the
cases you most want to catch — the overruns above turn MODE off and the
dashboard would still show it lit. **Trust the board over the picture.**

## The pull-up rail (VPU)

The built-in pull-ups pull up to whatever voltage is on the **VPU** pin, so
VPU must be tied to the bus's logic rail or the pull-ups do nothing.

On a **Bus Pirate v4** you can connect VPU to an internal rail in software:

```python
i2c.set_pullup_voltage(i2c.PULLUP_3V3)   # or PULLUP_5V, PULLUP_OFF
```

It refuses, raising `ExternalVoltageError`, if a voltage is already present on
VPU. That is deliberate protection — connecting an internal rail to a target's
live supply would be a short. Older v4 firmware may ignore the command
entirely; if the pull-ups do not change, wire VPU to the target's supply and
leave the rail off. On a **v3** there is no software option: wire VPU.

## Driving pins by hand

```python
bp.set_pin_directions(aux=False, mosi=False, clk=False, miso=True, cs=False)
state = bp.set_pins(power=True, pullups=True, cs=True)
print(bp.decode_pins(state))
```

Directions are `True` for input (high impedance), `False` for output. Every
pin command returns the current state of all pins, whatever their direction —
handy for reading an open-collector bus.

## Measuring

```python
bp.read_voltage()        # volts on the ADC pin, 0 to 6 V
bp.measure_frequency()   # Hz on the AUX pin
```

The ADC is 10-bit behind a divide-by-two, so it reads up to about 6 V with
roughly 6 mV resolution. It needs a shared ground with whatever you are
measuring. It is fine for checking a rail; it is not a multimeter.

**Watch a voltage** streams readings continuously rather than one at a time,
which is what you want for watching a rail come up or sag under load.

## PWM

```python
bp.pwm(1000, duty_cycle=0.25)   # 1 kHz, 25%, on AUX
bp.pwm_clear()
```

The range is about 0.24 Hz to 8 MHz; the driver picks a prescaler for you.

**PWM keeps running after you leave bitbang mode**, and after the program
exits. Stop it explicitly when you are done.

## Self-test

`bp.self_test()` returns an error count. **Bus Pirate v3 hardware only** —
the driver refuses it on a v4 rather than sending a command that means
something else. Disconnect the probe cable from any target first; the test
drives every pin.
