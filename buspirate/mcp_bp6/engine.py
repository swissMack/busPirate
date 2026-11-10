"""Plans and runs recipes. This decides when the target supply may switch on.

``plan_recipe`` measures first and never switches anything; it issues a
single-use token naming the voltage and current limit. ``run_recipe`` with
that token applies exactly that plan, then runs the check and the action.
``run_recipe(token=None)`` only re-runs the check and the action while the
power is still as planned: it never switches the supply on and never changes
the voltage or the address.
"""

from __future__ import annotations

import dataclasses
import time
from typing import Any, Dict, List, Optional, Tuple

from ..exceptions import BusPirateError, NackError
from ..mcp import power
from ..mcp.confirm import ConfirmError, ConfirmStore
from ..mcp.session import NotConnected
from ..mcp.wiring import WiringStep, cable_colour
from .recipes import REGISTRY, Recipe

ACTION = "recipe_run"  #: the ConfirmStore action recipe tokens are issued for
WINDOW_S = 300.0       #: how long a token, and a re-run after a run, stays valid
LOCKED = ("millivolts", "address")  #: options a re-run may not change

# How a recipe's target is powered.
SUPPLY_BP6 = "bp6"        # our supply, from the plan
SUPPLY_TARGET = "target"  # the target's own supply; ours stays off
SUPPLY_NONE = "none"      # the recipe needs no supply (max_mv 0)

DESTRUCTIVE = "erase and write recipes arrive in phase 2"
ASK_VOLTAGE = "ask the owner for the target's voltage (3.3 V is usual)"
CHECK_HINT = ("check the wiring and the address; the power is left as it is, so fix it "
              "and re-run with token=None")


def _recipe(name: str) -> Recipe:
    try:
        return REGISTRY[name]
    except KeyError:
        raise ValueError("no recipe named %r; use recipes(query) to find one" % name) from None


def _readings(bp: Any) -> Tuple[Dict[str, int], bool]:
    """The target's voltages, and whether our own supply is on.

    While our supply is on, the readings are our own voltage, not the target's.
    """
    pins = dict(power.measure(bp).pins_mv)
    st = bp.status()
    if not st.psu_enabled:
        # With the supply off, the measured supply voltage is what the target
        # puts on VOUT. Verified only in the simulator, not on a real board.
        pins["VOUT"] = int(st.psu_mv)
    return pins, bool(st.psu_enabled)


def _target_mv(bp: Any) -> Optional[int]:
    """The target's own voltage, or None if it has none (or our supply is on)."""
    pins, ours_on = _readings(bp)
    live = [mv for mv in pins.values() if mv >= power.SUGGEST_MIN_MV]
    if ours_on or not live:
        return None
    return max(live)


def _range_error(recipe: Recipe, mv: int, what: str) -> Optional[str]:
    if recipe.min_mv <= mv <= recipe.max_mv:
        return None
    return ("%s %d mV is outside %s's %d-%d mV range; nothing was planned"
            % (what, mv, recipe.name, recipe.min_mv, recipe.max_mv))


def _wiring(recipe: Recipe, target_powered: bool) -> List[Dict[str, str]]:
    steps = []
    for target_pin, pin in recipe.wiring:
        note = ""
        if pin == "VOUT" and target_powered:
            note = ("the target has its own supply: ours stays off, and VOUT reads its "
                    "voltage and feeds the pull-ups")
        steps.append(WiringStep(pin, cable_colour("bp6", pin), target_pin, note).to_dict())
    return steps


def _describe(recipe: Recipe) -> str:
    doc = (recipe.action.__doc__ or "").strip()
    return doc.splitlines()[0] if doc else recipe.title


def plan_recipe(session: Any, confirm: ConfirmStore, name: str,
                options: Dict[str, Any]) -> Dict[str, Any]:
    try:
        recipe = _recipe(name)
    except ValueError as exc:
        return {"error": str(exc)}
    if recipe.risk == "destructive":
        return {"error": DESTRUCTIVE}
    if session.variant is None:
        raise NotConnected("no board is connected — call connect first")
    if session.variant != "bp6":
        return {"error": "these recipes are for a Bus Pirate 6, not a %s" % session.variant}
    options = {k: v for k, v in options.items() if not (k == "millivolts" and v is None)}
    asked = options.get("millivolts")
    if asked is not None and (isinstance(asked, bool) or not isinstance(asked, int)):
        return {"error": "millivolts must be a whole number of mV, such as 3300, not %r"
                % (asked,)}
    merged = dict(recipe.options)
    merged.update(options)
    warnings = list(recipe.notes)
    if recipe.risk == "owner-only":
        warnings.append("ask the owner to confirm the device is theirs before running this")

    target_mv = None  # type: Optional[int]
    plan = None  # type: Optional[power.PowerPlan]
    if recipe.max_mv == 0:
        supply, extra = SUPPLY_NONE, False
    else:
        target_mv = session.run(_target_mv)
        if target_mv is not None:
            error = _range_error(recipe, target_mv, "the target is already powered at")
            if error:
                return {"error": error}
            supply, extra = SUPPLY_TARGET, False
            warnings.append("the target has its own supply (%d mV measured): the Bus "
                            "Pirate's supply stays off" % target_mv)
            if "millivolts" in options and options["millivolts"] != target_mv:
                warnings.append("the measured %d mV is used, not the %s mV asked for"
                                % (target_mv, options["millivolts"]))
        else:
            if recipe.default_mv == 0 and "millivolts" not in options:
                return {"error": ASK_VOLTAGE}
            mv = int(merged.get("millivolts", recipe.default_mv))
            error = _range_error(recipe, mv, "the voltage")
            if error:
                return {"error": error}
            try:
                plan = power.plan_power("bp6", mv, power.SOURCE_OWNER, recipe.pullups,
                                        recipe.milliamps)
            except power.PowerRefused as exc:
                return {"error": str(exc)}
            if recipe.default_mv:
                extra = mv > recipe.default_mv or recipe.milliamps == 0
            else:
                # No default to go above: the owner's stated voltage takes the
                # stage-1 rule (above 3.6 V, or no current limit, asks twice).
                extra = mv > power.EXTRA_CONFIRM_ABOVE_MV or recipe.milliamps == 0
            plan = dataclasses.replace(plan, needs_extra_confirmation=extra)
            supply = SUPPLY_BP6
            if recipe.milliamps == 0:
                warnings.append("this plan has no current limit")
            elif recipe.default_mv and mv > recipe.default_mv:
                warnings.append("%d mV is above this recipe's default of %d mV"
                                % (mv, recipe.default_mv))

    payload = {
        "name": recipe.name, "options": merged, "plan": plan, "supply": supply,
        "mv": plan.millivolts if plan else (target_mv or 0),
        "port": session.port, "expires": time.monotonic() + WINDOW_S,
    }
    return {
        "recipe": recipe.name,
        "title": recipe.title,
        "wiring": _wiring(recipe, supply == SUPPLY_TARGET),
        "power": plan.to_dict() if plan else None,
        "target_powered": supply == SUPPLY_TARGET,
        "target_mv": target_mv,
        "action": _describe(recipe),
        "warnings": warnings,
        "needs_extra_confirmation": extra,
        "token": confirm.issue(ACTION, payload),
    }


def _changed_locked(before: Dict[str, Any], options: Dict[str, Any]) -> Optional[str]:
    for key in LOCKED:
        if key in options and options[key] != before.get(key):
            return key
    return None


def _check_then_act(bp: Any, recipe: Recipe, options: Dict[str, Any],
                    power_out: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    out = {"recipe": recipe.name, "power": power_out}  # type: Dict[str, Any]
    try:
        check = recipe.check(bp, options)
    except NackError as exc:
        check = {"ok": False, "error": str(exc)}
    out["check"] = check
    if not check.get("ok", False):
        out.update(stopped="check failed", hint=check.get("hint") or CHECK_HINT)
        return out
    out["result"] = recipe.action(bp, options)
    return out


def _remember(session: Any, recipe: Recipe, options: Dict[str, Any], mv: int,
              supply: str) -> None:
    session.last_recipe = {"name": recipe.name, "options": options, "mv": mv,
                           "supply": supply, "until": time.monotonic() + WINDOW_S}


def _run_planned(session: Any, recipe: Recipe, payload: Dict[str, Any],
                 options: Dict[str, Any]) -> Dict[str, Any]:
    def go(bp: Any) -> Dict[str, Any]:
        session.last_recipe = None
        if payload["port"] != session.port:
            return {"error": "this plan was made for another board (%s); plan again"
                    % payload["port"]}
        supply = payload["supply"]
        power_out = None
        if supply != SUPPLY_NONE:
            target_mv = _target_mv(bp)
            if supply == SUPPLY_TARGET:
                if target_mv is None or _range_error(recipe, target_mv, "the target"):
                    return {"error": "plan again: the target's own voltage is gone or "
                            "changed since the plan (now %s mV)" % target_mv}
                # Never leave a stale plan behind: every bus tool re-asserts
                # session.power, which would feed our supply into the target.
                session.power = None
                if recipe.pullups:
                    bp.set_pullups(True)  # fed from the target's VOUT
            else:
                plan = payload["plan"]
                if plan is None or plan.millivolts != payload["mv"]:
                    return {"error": "plan again: the plan's voltage does not match"}
                if target_mv is not None:
                    return {"error": "plan again: the target now has its own supply "
                            "(%d mV); ours was not switched on" % target_mv}
                try:
                    power_out = power.apply_plan(bp, session, plan)
                except (BusPirateError, power.PowerRefused) as exc:
                    session.power = None
                    return {"recipe": recipe.name, "power": None, "error": str(exc)}
                if not power_out.get("applied"):
                    return {"recipe": recipe.name, "power": power_out,
                            "error": power_out.get("error", "the supply did not start")}
        _remember(session, recipe, options, payload["mv"], supply)
        return _check_then_act(bp, recipe, options, power_out)
    return session.run(go)


def _rerun(session: Any, options: Dict[str, Any]) -> Dict[str, Any]:
    def go(bp: Any) -> Dict[str, Any]:
        last = session.last_recipe
        if last is None:
            return {"error": "plan again: no recipe has run on this connection"}
        if time.monotonic() > last["until"]:
            return {"error": "plan again: the last run was more than 5 minutes ago"}
        recipe = REGISTRY.get(last["name"])
        if recipe is None:
            return {"error": "plan again: recipe %r is gone" % last["name"]}
        if recipe.risk == "destructive":
            return {"error": DESTRUCTIVE}
        key = _changed_locked(last["options"], options)
        if key:
            return {"error": "plan again: a re-run cannot change %s" % key}
        supply = last["supply"]
        if supply == SUPPLY_BP6:
            plan = session.power
            if plan is None or plan.millivolts != last["mv"]:
                return {"error": "plan again: the supply is no longer on at %d mV"
                        % last["mv"]}
            st = bp.status()
            if not st.psu_enabled or st.psu_tripped:
                return {"error": "plan again: the supply is off (it may have tripped)"}
        elif supply == SUPPLY_TARGET:
            target_mv = _target_mv(bp)
            if target_mv is None or _range_error(recipe, target_mv, "the target"):
                return {"error": "plan again: the target's own voltage is gone or out "
                        "of range (now %s mV)" % target_mv}
        merged = dict(last["options"])
        merged.update(options)
        power_out = session.power.to_dict() if supply == SUPPLY_BP6 else None
        return _check_then_act(bp, recipe, merged, power_out)
    return session.run(go)


def run_recipe(session: Any, confirm: ConfirmStore, token: Optional[str],
               options: Dict[str, Any]) -> Dict[str, Any]:
    if token is None:
        return _rerun(session, options)
    try:
        payload = confirm.redeem(token, ACTION)
    except ConfirmError as exc:
        return {"error": str(exc)}
    if time.monotonic() > payload["expires"]:
        return {"error": "plan again: the plan has expired"}
    recipe = REGISTRY.get(payload["name"])
    if recipe is None:
        return {"error": "plan again: recipe %r is gone" % payload["name"]}
    if recipe.risk == "destructive":
        return {"error": DESTRUCTIVE}
    key = _changed_locked(payload["options"], options)
    if key:
        return {"error": "plan again: %s was fixed by the plan" % key}
    merged = dict(payload["options"])
    merged.update(options)
    return _run_planned(session, recipe, payload, merged)
