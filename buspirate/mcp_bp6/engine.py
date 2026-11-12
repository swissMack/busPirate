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

from ..bp6.console import TerminalError
from ..exceptions import BusPirateError, NackError
from ..mcp import power
from ..mcp.confirm import ConfirmError, ConfirmStore
from ..mcp.session import NotConnected
from ..mcp.wiring import WiringStep, cable_colour
from . import console_power, state
from .recipes import REGISTRY, Recipe

ACTION = "recipe_run"  #: the ConfirmStore action recipe tokens are issued for
WINDOW_S = 300.0       #: how long a token, and a re-run after a run, stays valid
LOCKED = ("millivolts", "address")  #: options a re-run may not change
LOCKED_DESTRUCTIVE = ("backup",)  #: more options a destructive recipe fixes at the plan

# How a recipe's target is powered.
SUPPLY_BP6 = "bp6"        # our supply, from the plan
SUPPLY_TARGET = "target"  # the target's own supply; ours stays off
SUPPLY_NONE = "none"      # the recipe needs no supply (max_mv 0)

COMMIT_ACTION = "recipe_commit"  #: the ConfirmStore action commit tokens are issued for
PREPARE_NOTE = ("this recipe changes the chip: after the power yes it reads what it will "
                "change, saves a backup, and stops; the change needs its own yes")
CHANGE_NOTE = ("this recipe makes a change: after the power yes it shows exactly what will "
               "change and stops; the change needs its own yes")
NO_BACKUP_NOTE = "the owner declined the backup: nothing is saved before the change"
ASK_VOLTAGE = "ask the owner for the target's voltage (3.3 V is usual)"
CHECK_HINT = ("check the wiring and the address; the power is left as it is, so fix it "
              "and re-run with token=None")
VOUT_TOLERANCE = 0.10  #: how far the terminal's VOUT reading may be from the plan
TRIPPED = "power supply disabled"  #: in every firmware error that switched the supply off


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


TERMINAL_STEP_MV = 10  #: the terminal takes volts with two decimals


def _step_error(recipe: Recipe, mv: int) -> Optional[str]:
    """Why ``mv`` cannot be typed into the terminal, or None if it can."""
    if recipe.transport != "terminal" or mv % TERMINAL_STEP_MV == 0:
        return None
    step = TERMINAL_STEP_MV
    below, above = mv - mv % step, mv - mv % step + step
    candidates = [c for c in (below, above) if recipe.min_mv <= c <= recipe.max_mv]
    nearest = min(candidates, key=lambda c: (abs(c - mv), c)) if candidates else below
    return ("%d mV cannot be set through the terminal, which takes the voltage in steps "
            "of %d mV (0.01 V); plan again with %d mV. Nothing was planned"
            % (mv, step, nearest))


def _wiring(recipe: Recipe, target_powered: bool,
            options: Optional[Dict[str, Any]] = None) -> List[Dict[str, str]]:
    channels = (options or {}).get("channels")
    steps = []
    wiring = recipe.wiring_for(options or {}) if recipe.wiring_for else recipe.wiring
    for target_pin, pin in wiring:
        # A recipe with a ``channels`` option wires IO0..IO(channels-1) only.
        if (isinstance(channels, int) and pin.startswith("IO") and pin[2:].isdigit()
                and int(pin[2:]) >= channels):
            continue
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
    if recipe.risk == "destructive":
        warnings.append(PREPARE_NOTE if "backup" in recipe.options else CHANGE_NOTE)
        if merged.get("backup") is False:
            warnings.append(NO_BACKUP_NOTE)

    target_mv = None  # type: Optional[int]
    plan = None  # type: Optional[power.PowerPlan]
    if recipe.max_mv == 0:
        supply, extra = SUPPLY_NONE, False
    else:
        target_mv = session.run(_target_mv)
        if target_mv is not None:
            if not recipe.target_powered_ok and recipe.target_powered_error:
                return {"error": "the target already has its own supply (%d mV measured): "
                        "%s; nothing was planned" % (target_mv, recipe.target_powered_error)}
            if not recipe.target_powered_ok:
                return {"error": "the target already has its own supply (%d mV measured), "
                        "but %s must power it from the Bus Pirate: disconnect the target's "
                        "supply and plan again; nothing was planned" % (target_mv, recipe.name)}
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
            error = _range_error(recipe, mv, "the voltage") or _step_error(recipe, mv)
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
        "wiring": _wiring(recipe, supply == SUPPLY_TARGET, merged),
        "power": plan.to_dict() if plan else None,
        "target_powered": supply == SUPPLY_TARGET,
        "target_mv": target_mv,
        "action": _describe(recipe),
        "warnings": warnings,
        "needs_extra_confirmation": extra,
        "token": confirm.issue(ACTION, payload),
    }


def _changed_locked(recipe: Recipe, before: Dict[str, Any],
                    options: Dict[str, Any]) -> Optional[str]:
    keys = LOCKED + (LOCKED_DESTRUCTIVE if recipe.risk == "destructive" else ())
    for key in keys:
        if key in options and options[key] != before.get(key):
            return key
    return None


def _check_then_act(bp: Any, recipe: Recipe, options: Dict[str, Any],
                    power_out: Optional[Dict[str, Any]], confirm: ConfirmStore,
                    port: Any, mv: int, supply: str) -> Dict[str, Any]:
    out = {"recipe": recipe.name, "power": power_out}  # type: Dict[str, Any]
    try:
        check = recipe.check(bp, options)
    except NackError as exc:
        check = {"ok": False, "error": str(exc)}
    if (recipe.risk == "destructive" and check.get("ok", False)
            and not (isinstance(check.get("identity"), str) and check["identity"])):
        check = {"ok": False, "error": "the check returned no identity for the chip, so "
                 "a change could not be tied to it"}
    out["check"] = check
    if not check.get("ok", False):
        out.update(stopped="check failed", hint=check.get("hint") or CHECK_HINT)
        return out
    result = recipe.action(bp, options)
    if recipe.risk != "destructive":
        out["result"] = result
        return out
    # The action only prepared. Keep the private keys here, with the check's
    # identity, and hand the caller the public ones and a commit token.
    prepared = dict(result)
    prepared["_identity"] = check.get("identity")
    public = {k: v for k, v in result.items() if not k.startswith("_")}
    out["result"] = public
    payload = {"name": recipe.name, "options": options, "prepared": prepared,
               "port": port, "mv": mv, "supply": supply,
               "expires": time.monotonic() + WINDOW_S}
    out["commit"] = dict(public, token=confirm.issue(COMMIT_ACTION, payload))
    out["stopped"] = "the change needs its own yes"
    return out


def _power_error(bp: Any, session: Any, recipe: Recipe, mv: int,
                 supply: str) -> Optional[str]:
    """Why the power is no longer as a run left it, or None if it is."""
    if supply == SUPPLY_BP6:
        plan = session.power
        if plan is None or plan.millivolts != mv:
            return "plan again: the supply is no longer on at %d mV" % mv
        st = bp.status()
        if not st.psu_enabled or st.psu_tripped:
            return "plan again: the supply is off (it may have tripped)"
    elif supply == SUPPLY_TARGET:
        target_mv = _target_mv(bp)
        if target_mv is None or _range_error(recipe, target_mv, "the target"):
            return ("plan again: the target's own voltage is gone or out of range "
                    "(now %s mV)" % target_mv)
    return None


def _remember(session: Any, recipe: Recipe, options: Dict[str, Any], mv: int,
              supply: str) -> None:
    session.last_recipe = {"name": recipe.name, "options": options, "mv": mv,
                           "supply": supply, "until": time.monotonic() + WINDOW_S}


def _failed_precheck(bp: Any, recipe: Recipe,
                     options: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The precheck's result if it stopped the run, else None. Runs over BPIO2."""
    if recipe.precheck is None:
        return None
    try:
        pre = recipe.precheck(bp, options)
    except NackError as exc:
        pre = {"ok": False, "error": str(exc)}
    return None if pre.get("ok", False) else pre


def _terminal_power(con: Any, plan: power.PowerPlan) -> Dict[str, Any]:
    """Switch the planned supply on with ``W`` and check what VOUT reads."""
    readings = console_power.power_on(con, plan.millivolts, plan.milliamps)
    if abs(readings["vout_mv"] - plan.millivolts) > plan.millivolts * VOUT_TOLERANCE:
        con.command("w")
        raise TerminalError("VOUT reads %d mV, not the planned %d mV; the supply was "
                            "switched off again" % (readings["vout_mv"], plan.millivolts))
    return dict(plan.to_dict(), applied=True, **readings)


class _TripWatch:
    """A ``Console`` whose replies are watched for the supply cutting out.

    The console carries a trip the board printed on its own into the next
    ``Reply.error`` instead of raising, so a check or an action could return
    normally after one. Any such reply clears ``session.power`` at once, so
    no BPIO2 tool re-asserts the supply into the fault.
    """

    def __init__(self, con: Any, session: Any) -> None:
        self._con = con
        self._session = session
        #: For recipes that keep per-session state (``state.of(con.session)``).
        self.session = session
        self.tripped = None  # type: Optional[str]

    def command(self, *args: Any, **kwargs: Any) -> Any:
        reply = self._con.command(*args, **kwargs)
        if reply.error and TRIPPED in reply.error.lower():
            self._session.power = None
            self.tripped = self.tripped or (
                "%s; the supply is off, so plan again" % reply.error)
        return reply

    def __getattr__(self, name: str) -> Any:
        return getattr(self._con, name)


def _run_terminal(bp: Any, session: Any, confirm: ConfirmStore, recipe: Recipe,
                  options: Dict[str, Any], mv: int, supply: str,
                  plan: Optional[power.PowerPlan], rerun: bool = False) -> Dict[str, Any]:
    """A terminal recipe, once the BPIO2 checks of the power have passed.

    A first run switches to the recipe's mode (which switches the supply and
    pull-ups off), then applies the plan and the pull-ups. A re-run changes
    neither: it refuses unless the terminal is still in the recipe's mode.
    """
    power_out = plan.to_dict() if (rerun and plan is not None) else None
    pre = _failed_precheck(bp, recipe, options)
    if pre is not None:
        return {"recipe": recipe.name, "power": power_out, "check": pre,
                "stopped": "check failed", "hint": pre.get("hint") or CHECK_HINT}
    want = recipe.terminal_mode or "hiz"
    try:
        with bp.console() as raw:
            con = _TripWatch(raw, session)
            if rerun:
                now = con.command("").mode  # Enter: a fresh prompt names the mode
                if con.tripped:
                    return {"recipe": recipe.name, "power": None, "error": con.tripped}
                if now.upper() != want.upper():
                    return {"error": "plan again: the board is in %s mode now" % now}
            else:
                session.power = None  # m switches the supply, the pull-ups and PWM off
                # Recorded first, so hiz cleans up even after a switch that failed.
                state.of(session).terminal_mode = recipe.terminal_mode
                state.of(session).pwm_pins.clear()
                console_power.set_mode(con, want, recipe.terminal_flags)
                if supply == SUPPLY_BP6 and recipe.supply_by == "engine":
                    power_out = _terminal_power(con, plan)
                    session.power = plan
                if recipe.pullups:
                    console_power.pullups(con, True)
                _remember(session, recipe, options, mv, supply)
            out = _check_then_act(con, recipe, options, power_out, confirm, session.port,
                                  mv, supply)
            if con.tripped:
                # The supply cut out while the check or action ran: report it,
                # and never hand a re-run the old power.
                out["power"] = None
                out.setdefault("error", con.tripped)
                session.last_recipe = None
            return out
    except TerminalError as exc:
        if TRIPPED in str(exc).lower():
            session.power = None
        return {"recipe": recipe.name, "power": power_out, "error": str(exc)}


def _run_planned(session: Any, confirm: ConfirmStore, recipe: Recipe,
                 payload: Dict[str, Any], options: Dict[str, Any]) -> Dict[str, Any]:
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
                if recipe.pullups and recipe.transport != "terminal":
                    bp.set_pullups(True)  # fed from the target's VOUT
            else:
                plan = payload["plan"]
                if plan is None or plan.millivolts != payload["mv"]:
                    return {"error": "plan again: the plan's voltage does not match"}
                if target_mv is not None:
                    return {"error": "plan again: the target now has its own supply "
                            "(%d mV); ours was not switched on" % target_mv}
        if recipe.transport == "terminal":
            return _run_terminal(bp, session, confirm, recipe, options, payload["mv"],
                                 supply, payload["plan"])
        if supply == SUPPLY_BP6:
            try:
                power_out = power.apply_plan(bp, session, payload["plan"])
            except (BusPirateError, power.PowerRefused) as exc:
                session.power = None
                return {"recipe": recipe.name, "power": None, "error": str(exc)}
            if not power_out.get("applied"):
                return {"recipe": recipe.name, "power": power_out,
                        "error": power_out.get("error", "the supply did not start")}
        _remember(session, recipe, options, payload["mv"], supply)
        return _check_then_act(bp, recipe, options, power_out, confirm, session.port,
                               payload["mv"], supply)
    return session.run(go)


def _rerun(session: Any, confirm: ConfirmStore, options: Dict[str, Any]) -> Dict[str, Any]:
    def go(bp: Any) -> Dict[str, Any]:
        last = session.last_recipe
        if last is None:
            return {"error": "plan again: no recipe has run on this connection"}
        if time.monotonic() > last["until"]:
            return {"error": "plan again: the last run was more than 5 minutes ago"}
        recipe = REGISTRY.get(last["name"])
        if recipe is None:
            return {"error": "plan again: recipe %r is gone" % last["name"]}
        key = _changed_locked(recipe, last["options"], options)
        if key:
            return {"error": "plan again: a re-run cannot change %s" % key}
        supply = last["supply"]
        error = _power_error(bp, session, recipe, last["mv"], supply)
        if error:
            return {"error": error}
        merged = dict(last["options"])
        merged.update(options)
        if recipe.transport == "terminal":
            return _run_terminal(bp, session, confirm, recipe, merged, last["mv"], supply,
                                 session.power, rerun=True)
        power_out = session.power.to_dict() if supply == SUPPLY_BP6 else None
        return _check_then_act(bp, recipe, merged, power_out, confirm, session.port,
                               last["mv"], supply)
    return session.run(go)


def run_recipe(session: Any, confirm: ConfirmStore, token: Optional[str],
               options: Dict[str, Any]) -> Dict[str, Any]:
    if token is None:
        return _rerun(session, confirm, options)
    try:
        payload = confirm.redeem(token, ACTION)
    except ConfirmError as exc:
        return {"error": str(exc)}
    if time.monotonic() > payload["expires"]:
        return {"error": "plan again: the plan has expired"}
    recipe = REGISTRY.get(payload["name"])
    if recipe is None:
        return {"error": "plan again: recipe %r is gone" % payload["name"]}
    key = _changed_locked(recipe, payload["options"], options)
    if key:
        return {"error": "plan again: %s was fixed by the plan" % key}
    merged = dict(payload["options"])
    merged.update(options)
    return _run_planned(session, confirm, recipe, payload, merged)


def commit_recipe(session: Any, confirm: ConfirmStore, token: str) -> Dict[str, Any]:
    """Make the change a prepare described. Never switches power on or changes it."""
    try:
        payload = confirm.redeem(token, COMMIT_ACTION)
    except ConfirmError as exc:
        return {"error": str(exc)}
    if time.monotonic() > payload["expires"]:
        return {"error": "plan again: the commit token has expired"}
    recipe = REGISTRY.get(payload["name"])
    if recipe is None or recipe.risk != "destructive" or recipe.commit is None:
        return {"error": "plan again: recipe %r is gone or no longer changes the chip"
                % payload["name"]}

    def go(bp: Any) -> Dict[str, Any]:
        if payload["port"] != session.port:
            return {"error": "plan again: this was prepared for another board (%s)"
                    % payload["port"]}
        error = _power_error(bp, session, recipe, payload["mv"], payload["supply"])
        if error:
            return {"error": error}
        if recipe.transport == "terminal":
            return _commit_terminal(bp, session, recipe, payload)
        return _check_then_commit(bp, recipe, payload)
    return session.run(go)


def _check_then_commit(dev: Any, recipe: Recipe, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Re-run the check on ``dev`` (the board, or the ``Console``) and commit if it
    is still the prepared chip."""
    options, prepared = payload["options"], payload["prepared"]
    try:
        check = recipe.check(dev, options)
    except NackError as exc:
        check = {"ok": False, "error": str(exc)}
    if not check.get("ok", False):
        return {"error": "plan again: the chip no longer answers the check (%s)"
                % (check.get("error") or check.get("hint") or "check failed")}
    ident = check.get("identity")
    if not (isinstance(ident, str) and ident) or ident != prepared.get("_identity"):
        return {"error": "plan again: the chip is not the one that was prepared "
                "(%s, was %s)" % (check.get("identity"), prepared.get("_identity"))}
    result = recipe.commit(dev, options, prepared)
    # A change that failed or did not verify (e.g. a write-protected chip) is not a commit.
    committed = "error" not in result and result.get("verified") is not False
    return {"recipe": recipe.name, "committed": committed, "result": result}


def _commit_terminal(bp: Any, session: Any, recipe: Recipe,
                     payload: Dict[str, Any]) -> Dict[str, Any]:
    """Commit a terminal recipe in the terminal, only while it is still in the
    recipe's mode. Never switches the mode, the supply or the pull-ups."""
    want = recipe.terminal_mode or "hiz"
    try:
        with bp.console() as raw:
            con = _TripWatch(raw, session)
            now = con.command("").mode  # Enter: a fresh prompt names the mode
            if con.tripped:
                return {"recipe": recipe.name, "error": con.tripped}
            if now.upper() != want.upper():
                return {"error": "plan again: the board is in %s mode now" % now}
            out = _check_then_commit(con, recipe, payload)
            if con.tripped:
                # The supply cut out during the check or the change: say so,
                # and never hand a re-run the old power.
                out.setdefault("error", con.tripped)
                if "committed" in out:
                    out["committed"] = False
                session.last_recipe = None
            return out
    except TerminalError as exc:
        if TRIPPED in str(exc).lower():
            session.power = None
        return {"recipe": recipe.name, "error": str(exc)}
