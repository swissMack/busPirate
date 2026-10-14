"""The Bus Pirate 6's programmable supply and pull-ups, in one-click controls."""

from __future__ import annotations

from ... import device as device_module
from ..registry import Action, Panel, Param, keyvalue, text

#: Above this, or with no current limit, a mistake can damage a 3.3 V part.
HIGH_MV = 3600
_TICK = ("Tick 'I have checked the target takes this' first: above 3.6 V, or with "
         "no current limit, a mistake can damage a 3.3 V part.")


def _limit_text(milliamps: int) -> str:
    return f"{milliamps} mA" if milliamps else "none"


def _report(ctx, message: str):
    status = ctx.bp.status()
    if status.psu_tripped:
        return text(
            "Current limit tripped — power cut. The target drew more than "
            f"{ctx.bp.psu_ma} mA. Check the wiring for a short, then press Re-enable.",
            tone="warn",
        )
    return text(message, tone="good")


def _supplies(ctx, on):
    ctx.bp.set_power(on)
    if not on:
        return text("The supply is off.", tone="info")
    return _report(ctx, f"The supply is on: {ctx.bp.psu_mv / 1000:.2f} V, limit "
                        f"{_limit_text(ctx.bp.psu_ma)}.")


def _quick(millivolts):
    def handler(ctx):
        ctx.bp.set_power(True, millivolts=millivolts)
        return _report(ctx, f"The supply is on at {millivolts / 1000:.1f} V, limit "
                            f"{_limit_text(ctx.bp.psu_ma)}.")
    return handler


def _set_supply(ctx, millivolts, limit_ma, confirm_high):
    if (millivolts > HIGH_MV or limit_ma == 0) and not confirm_high:
        return text(_TICK, tone="warn")
    ctx.bp.set_power(True, millivolts=millivolts, milliamps=limit_ma)
    return _report(ctx, f"The supply is on at {millivolts / 1000:.2f} V, limit "
                        f"{_limit_text(limit_ma)}.")


def _reenable(ctx):
    ctx.bp.set_power(False)
    ctx.bp.set_power(True)
    return _report(ctx, "The supply is back on.")


def _pullups(ctx, on):
    ctx.bp.set_pullups(on)
    return text("Pull-ups on: 10 kΩ from every IO pin to the supply." if on
                else "Pull-ups off.", tone="info")


def _readings(ctx):
    status = ctx.bp.status()
    rows = [
        ["Supply", "on" if status.psu_enabled else "off"],
        ["Set to", f"{status.psu_set_mv / 1000:.2f} V, limit {_limit_text(status.psu_set_ma)}"],
        ["Measured", f"{status.psu_mv / 1000:.2f} V, {status.psu_ma} mA"],
        ["Pull-ups", "on" if status.pullups else "off"],
    ]
    # The firmware labels VOUT, IO0..IO7 and GND for the current mode.
    labels = list(status.pin_labels[1:9])
    for index, millivolts in enumerate(status.adc_mv):
        label = labels[index] if index < len(labels) else ""
        name = f"IO{index}" + (f" ({label})" if label else "")
        rows.append([name, f"{millivolts / 1000:.2f} V"])
    caption = ("Current limit tripped — power cut. Press Re-enable once the fault is fixed."
               if status.psu_tripped else "Read from the board just now.")
    return keyvalue(rows, caption=caption)


PANEL = Panel(
    id="power6",
    requires=device_module.CAP_PSU_PROGRAMMABLE,
    doc="bus-pirate-6",
    title="Power & pull-ups",
    blurb="The Bus Pirate 6's adjustable supply on VOUT, its current limit, and the pull-ups.",
    mode=None,
    order=60,
    notes=[
        "VOUT powers the target: 0.8 to 5.0 V, up to 500 mA, cut off at the "
        "current limit you set (300 mA unless you change it).",
        "The pull-ups are 10 kΩ from each IO pin to the supply, so they need the "
        "supply on (or an external voltage on VOUT) to do anything.",
        "The status bar shows the measured voltage and current while you work.",
    ],
    actions=[
        Action(name="supplies", label="Supply on VOUT", switch="supplies",
               params=[Param("on", "bool", "On", default=False)], handler=_supplies,
               help="On at the voltage and limit set below (3.3 V, 300 mA to start)."),
        Action(name="pullups", label="Pull-ups", switch="pullups",
               params=[Param("on", "bool", "On", default=False)], handler=_pullups),
        Action(name="quick_1v8", label="1.8 V", button="1.8 V", handler=_quick(1800)),
        Action(name="quick_3v3", label="3.3 V", button="3.3 V", primary=True, handler=_quick(3300)),
        Action(name="quick_5v0", label="5.0 V", button="5.0 V", handler=_quick(5000),
               confirm="5 V can damage a 3.3 V part. Is the target a 5 V device?"),
        Action(
            name="set_supply", label="Set voltage and current limit", button="Switch on",
            params=[
                Param("millivolts", "int", "Voltage (mV)", default=3300, minimum=800, maximum=5000),
                Param("limit_ma", "int", "Current limit (mA, 0 = none)", default=300,
                      minimum=0, maximum=500),
                Param("confirm_high", "bool", "I have checked the target takes this", default=False,
                      help="Needed above 3.6 V, or with no current limit."),
            ],
            handler=_set_supply,
        ),
        Action(name="reenable", label="Re-enable after a trip", button="Re-enable",
               handler=_reenable, help="Switches the supply back on after the limit cut it."),
        Action(name="readings", label="Read voltages and current", recipe=True, handler=_readings),
    ],
)
