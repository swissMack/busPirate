"""Power rules: ask, never guess, per board.

Power is only ever switched on from a PowerPlan that the owner has confirmed.
The plan records where the voltage came from: the owner, or a measurement the
owner then confirmed.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

from ..web.wiring import colour_name

SOURCE_OWNER = "owner"
SOURCE_MEASURED = "measured"
_SOURCES = (SOURCE_OWNER, SOURCE_MEASURED)

DEFAULT_MILLIAMPS = 100
BP6_MV_RANGE = (800, 5000)
BP6_MA_RANGE = (1, 500)
EXTRA_CONFIRM_ABOVE_MV = 3600
DOCK_LEVELS = {1800: "1V8", 3300: "3V3", 5000: "5V"}
SUGGEST_MIN_MV = 1000


class PowerRefused(ValueError):
    """A power plan the rules do not allow. The message names an alternative."""


@dataclass(frozen=True)
class PowerPlan:
    variant: str
    millivolts: int
    milliamps: Optional[int]
    pullups: bool
    source: str
    instructions: List[str]
    needs_extra_confirmation: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _v3_v4(variant: str, mv: int, pullups: bool) -> List[str]:
    if mv not in (3300, 5000):
        raise PowerRefused(
            "the Bus Pirate %s supplies only 3.3 V or 5 V, picked by wire; for %d mV "
            "use the target's own supply, or a Bus Pirate 6 (800-5000 mV)"
            % (variant, mv))
    if mv == 3300:
        use, avoid, level = "+3.3V", "+5V", "3.3 V"
    else:
        use, avoid, level = "+5V", "+3.3V", "5 V"
    lines = [
        "connect the %s wire (%s) to the target's VCC for %s"
        % (colour_name(use), use, level),
        "do not connect %s (%s) as well" % (avoid, colour_name(avoid)),
    ]
    if pullups:
        if variant == "v4":
            lines.append(
                "pull-ups: the v4 can feed VPU in software (set_pullup_voltage); "
                "wire VPU (%s) to the target's VCC" % colour_name("VPU"))
        else:
            lines.append("pull-ups: wire VPU (%s) to the target's VCC"
                         % colour_name("VPU"))
    return lines


def _bp6(mv: int, ma: Optional[int]) -> List[str]:
    lo, hi = BP6_MV_RANGE
    if not lo <= mv <= hi:
        raise PowerRefused(
            "the Bus Pirate 6 supplies %d-%d mV, not %d mV; for other levels use "
            "the target's own supply" % (lo, hi, mv))
    if ma is not None and ma != 0 and not BP6_MA_RANGE[0] <= ma <= BP6_MA_RANGE[1]:
        raise PowerRefused(
            "current limit must be %d-%d mA, or 0 for none (needs extra "
            "confirmation); got %d mA" % (BP6_MA_RANGE + (ma,)))
    return ["connect VOUT (red) to the target's VCC, and GND (black) to its ground"]


def _dock(mv: int) -> List[str]:
    if mv not in DOCK_LEVELS:
        raise PowerRefused(
            "the Bit Pirate dock switch is 1.8 V, 3.3 V or 5 V, not %d mV; "
            "use the target's own supply for other levels" % mv)
    return [
        "set the dock's voltage switch to %s; software cannot set it" % DOCK_LEVELS[mv],
        "connect VIO (red) to the target's VCC, and GND (black) to its ground",
    ]


def plan_power(variant: str, millivolts: int, source: str, pullups: bool = True,
               milliamps: Optional[int] = None) -> PowerPlan:
    if source not in _SOURCES:
        raise ValueError("source must be 'owner' or 'measured', not %r" % (source,))
    extra = False
    if variant in ("v3", "v4"):
        lines = _v3_v4(variant, millivolts, pullups)
        milliamps = None
    elif variant in ("bp6", "bp5"):
        lines = _bp6(millivolts, milliamps)
        if milliamps is None:
            milliamps = DEFAULT_MILLIAMPS
        extra = millivolts > EXTRA_CONFIRM_ABOVE_MV or milliamps == 0
    elif variant == "bitpirate":
        lines = _dock(millivolts)
        milliamps = None
    else:
        raise PowerRefused("unknown board %r; supply the target from its own supply"
                           % (variant,))
    return PowerPlan(variant, millivolts, milliamps, pullups, source, lines, extra)


@dataclass(frozen=True)
class Measurement:
    pins_mv: Dict[str, int]
    note: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def measure(bp: Any) -> Measurement:
    """Read what the target is already putting on the pins."""
    if hasattr(bp, "status"):
        st = bp.status()
        # adc_mv holds IO0..IO7; pin_labels has 10 entries (VOUT, IO0..IO7, GND)
        # that follow the current mode, so key by the IO name, not the label.
        pins = {"IO%d" % i: int(v) for i, v in enumerate(st.adc_mv)}
        return Measurement(pins, "voltages on the IO pins, in mV")
    if hasattr(bp, "read_voltage"):
        return Measurement(
            {"ADC": int(round(bp.read_voltage() * 1000))},
            "probe the target's rail with the ADC wire (yellow)")
    return Measurement({}, "cannot measure; read the part number or use a meter")


def suggest_level(m: Measurement) -> Optional[int]:
    """Nearest of 1800/3300/5000 mV to the highest reading; None if unpowered."""
    live = [v for v in m.pins_mv.values() if v >= SUGGEST_MIN_MV]
    if not live:
        return None
    top = max(live)
    return min(DOCK_LEVELS, key=lambda lvl: abs(lvl - top))
