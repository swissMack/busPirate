"""Pins, power and measurement — the Bus Pirate as a bench instrument."""

from __future__ import annotations

from ... import device as device_module
from ..registry import Action, Panel, Param, Wire, keyvalue, pins, text
from ..wiring import CABLE_CAVEAT, POWER_NOTE, colour


def _set_pins(ctx, power, pullups, aux, mosi, clk, miso, cs):
    wanted = {
        "power": power,
        "pullups": pullups,
        "aux": aux,
        "mosi": mosi,
        "clk": clk,
        "miso": miso,
        "cs": cs,
    }
    ctx.session.last_pins = wanted
    return pins(ctx.bp.decode_pins(ctx.bp.set_pins(**wanted)))


def _directions(ctx, aux, mosi, clk, miso, cs):
    state = ctx.bp.set_pin_directions(aux=aux, mosi=mosi, clk=clk, miso=miso, cs=cs)
    return pins(ctx.bp.decode_pins(state))


def _voltage(ctx):
    volts = ctx.bp.read_voltage()
    return keyvalue(
        [["ADC probe", f"{volts:.2f} V"]],
        caption="Measured on the ADC wire. The input tolerates up to 6 V.",
    )


def _frequency(ctx):
    hertz = ctx.bp.measure_frequency()
    if hertz == 0:
        return text("No edges seen on AUX in the sample window.")
    return keyvalue(
        [
            ["AUX frequency", f"{hertz:,} Hz"],
            ["Period", f"{1e6 / hertz:.2f} µs"],
        ]
    )


def _pwm(ctx, frequency, duty_cycle):
    ctx.bp.pwm(frequency, duty_cycle / 100.0)
    return text(
        f"PWM running on AUX at {frequency} Hz, {duty_cycle:.0f}% duty. "
        "It keeps running until you stop it, even after leaving this mode.",
        tone="good",
    )


def _pwm_clear(ctx):
    ctx.bp.pwm_clear()
    return text("PWM stopped.")


PANEL = Panel(
    id="pins",
    refcard_rows=['AUX', 'ADC', 'supplies', 'GND'],
    doc="pins-and-power",
    title="Pins & power",
    blurb="Drive the pins by hand, switch the supplies, measure a voltage.",
    mode=None,
    order=60,
    wiring=[
        Wire("ADC", colour("ADC"), "point to measure", "0 to 6 V, high impedance"),
        Wire("AUX", colour("AUX"), "PWM out / frequency in", ""),
        Wire("GND", colour("GND"), "GND", "the measurement needs a shared ground"),
    ],
    notes=[
        "These controls work in bitbang mode, so selecting this panel leaves "
        "whatever protocol mode you were in.",
        "The on-board supplies are modest — a few tens of milliamps. Power a "
        "hungry target from its own supply and connect only the grounds.",
        POWER_NOTE,
        CABLE_CAVEAT,
    ],
    actions=[
        Action(
            name="set_pins",
            label="Set the pins",
            primary=True,
            params=[
                Param("power", "bool", "3.3V and 5V supplies (both, together)", default=False),
                Param("pullups", "bool", "Pull-ups", default=False),
                Param("aux", "bool", "AUX high", default=False),
                Param("mosi", "bool", "MOSI high", default=False),
                Param("clk", "bool", "CLK high", default=False),
                Param("miso", "bool", "MISO high", default=False),
                Param("cs", "bool", "CS high", default=False),
            ],
            handler=_set_pins,
        ),
        Action(
            name="directions",
            label="Set pin directions",
            help="Ticked means input (high impedance); unticked means output.",
            params=[
                Param("aux", "bool", "AUX is an input", default=True),
                Param("mosi", "bool", "MOSI is an input", default=True),
                Param("clk", "bool", "CLK is an input", default=True),
                Param("miso", "bool", "MISO is an input", default=True),
                Param("cs", "bool", "CS is an input", default=True),
            ],
            handler=_directions,
        ),
        Action(
            name="voltage",
            label="Measure a voltage",
            recipe=True,
            requires=device_module.CAP_ADC,
            handler=_voltage,
        ),
        Action(
            name="frequency",
            label="Measure a frequency",
            requires=device_module.CAP_FREQUENCY,
            handler=_frequency,
        ),
        Action(
            name="pwm",
            label="Output PWM on AUX",
            requires=device_module.CAP_PWM,
            params=[
                Param("frequency", "int", "Frequency (Hz)", default=1000, minimum=1, maximum=4_000_000),
                Param("duty_cycle", "int", "Duty cycle (%)", default=50, minimum=0, maximum=100),
            ],
            handler=_pwm,
        ),
        Action(
            name="pwm_clear",
            label="Stop PWM",
            requires=device_module.CAP_PWM,
            handler=_pwm_clear,
        ),
    ],
)
