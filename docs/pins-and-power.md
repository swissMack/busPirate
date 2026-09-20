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
