"""The ``bp6`` MCP server: recipes and primitive tools for a Bus Pirate 6 only.

Every tool is listed from the start. The board is opened on first use, not at
start-up, so this server can sit next to the ``buspirate`` server without
fighting over the port. When the server exits, the board goes to HiZ: the
supply and the pull-ups are off.

This is the only module in ``buspirate.mcp_bp6`` that imports the ``mcp`` SDK
(Python 3.10+).
"""

import weakref
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import anyio
from mcp.server.mcpserver import MCPServer

from ..exceptions import BusPirateError
from ..mcp import jobs
from ..mcp.confirm import ConfirmError, ConfirmStore
from ..mcp.power import (
    SOURCE_MEASURED, SOURCE_OWNER, PowerRefused, apply_plan, measure, plan_power, suggest_level,
)
from ..mcp.server import _BP6_STATUS_FIELDS, BOARD_GONE, POWER_ACTION
from ..mcp.session import BoardGone, BoardSession, NotConnected
from ..mcp.wiring import JOBS, job_notes, wiring_steps
from ..bp6 import signals
from . import console_power, engine, handoff, state
from .recipes import find_recipes
from .recipes import pins as pin_recipe

NOTES = Path(__file__).resolve().parent / "notes" / "bp6.md"
VARIANT = "bp6"
WRONG_BOARD = "this server only drives a Bus Pirate 6; use the buspirate server for %s"

INSTRUCTIONS = """\
Tools for a Bus Pirate 6.

- When the owner names a device, call `recipes`, then `recipe_plan`. Show the wiring \
and the plan in one message.
- Call `recipe_run` only after the owner's yes. Ask a second time when \
`needs_extra_confirmation` is true.
- A recipe that changes a chip stops after its backup and returns `commit`. Read its \
`summary` to the owner, and call `recipe_commit` only after a second yes to that change.
- Never pass backup=False unless the owner asked for no backup.
- A target-powered plan switches nothing on.
- If the check fails, read the `hint` to the owner.
- `hiz` makes everything safe.
- A hand-off (flashrom, avrdude, pulseview) lends the board to that program: give the \
owner the `command` and `how_to_return`. Call `connect` or `hiz` to take it back.
"""

#: Each built server's session, for run_stdio and tests.
_SESSIONS: "weakref.WeakKeyDictionary[MCPServer, BoardSession]" = weakref.WeakKeyDictionary()


def _open(session: BoardSession, port: Optional[str]) -> Dict[str, Any]:
    """Connect; with several boards and no port, take the first and name the others.

    A board that is not a BP6 is closed again and reported as an error.
    """
    others: List[str] = []
    out = session.connect(port)
    if "choose_from" in out:
        first, others = out["choose_from"][0], out["choose_from"][1:]
        out = session.connect(first)
    variant = out.get("variant")
    if variant != VARIANT:
        session.disconnect()
        return {"connected": False, "error": WRONG_BOARD % variant}
    if others:
        out["other_boards"] = others
        out["board_note"] = ("several boards are plugged in; using %s, not %s. "
                             "connect(port) picks another." % (out["port"], ", ".join(others)))
    return out


def build_server(session: BoardSession) -> MCPServer:
    server = MCPServer("bp6", instructions=INSTRUCTIONS)
    confirm = ConfirmStore()  # recipe tokens and power tokens carry different actions
    measured: Dict[str, Any] = {"board": None}  # the board measure_voltages last read

    async def guard(fn: Callable[[], Dict[str, Any]],
                    connect_first: bool = True, lent_ok: bool = False) -> Dict[str, Any]:
        """Open the board if needed, run ``fn`` in a worker thread, turn errors into results.

        While the board is lent to another program, only a ``lent_ok`` tool runs.
        """
        lent = state.of(session).lent
        if lent is not None and not lent_ok:
            return {"error": handoff.lent_error(lent)}
        try:
            opened = None
            if connect_first and session.board is None:
                opened = await anyio.to_thread.run_sync(lambda: _open(session, None))
                measured["board"] = None
                if "error" in opened:
                    return {"error": opened["error"]}
            out = await anyio.to_thread.run_sync(fn)
            if opened and "other_boards" in opened and isinstance(out, dict):
                out["other_boards"] = opened["other_boards"]
                out["board_note"] = opened["board_note"]
            return out
        except BoardGone:
            return {"error": BOARD_GONE}
        except (NotConnected, BusPirateError, ValueError, OSError) as exc:
            return {"error": str(exc)}

    # -- recipes ----------------------------------------------------------------

    async def recipes(query: Optional[str] = None) -> Dict[str, Any]:
        return {"query": query, "recipes": find_recipes(query)}

    async def recipe_plan(name: str, options: Optional[dict] = None) -> Dict[str, Any]:
        return await guard(lambda: engine.plan_recipe(session, confirm, name, options or {}))

    async def recipe_run(token: Optional[str] = None,
                         options: Optional[dict] = None) -> Dict[str, Any]:
        return await guard(lambda: engine.run_recipe(session, confirm, token, options or {}))

    async def recipe_commit(token: str) -> Dict[str, Any]:
        return await guard(lambda: engine.commit_recipe(session, confirm, token))

    # -- the board --------------------------------------------------------------

    def _take_back(port: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Take a lent board back (None if none was lent), connecting again if needed.

        A board that cannot be reached is no longer lent: a board found now is
        connected fresh, and with none found the result is the board-gone error.
        """
        if state.of(session).lent is None:
            return None
        back = handoff.reclaim(session)
        out = {"reclaimed": back["reclaimed"]}  # type: Dict[str, Any]
        if "warning" in back:
            out["warnings"] = [back["warning"]]
        if back["reconnect"]:
            try:
                out.update(_open(session, port))
            except NotConnected:
                out.update(connected=False, error=BOARD_GONE)
        return out

    async def connect(port: Optional[str] = None) -> Dict[str, Any]:
        measured["board"] = None

        def go() -> Dict[str, Any]:
            back = _take_back(port)
            if back is None:
                return _open(session, port)
            if "connected" in back:
                return back
            return dict(back, **_open(session, port))
        out = await guard(go, connect_first=False, lent_ok=True)
        out.setdefault("connected", False)
        return out

    async def board_status() -> Dict[str, Any]:
        def read(bp: Any) -> Dict[str, Any]:
            profile = bp.profile
            out = {
                "board": profile.describe(),
                "variant": profile.variant,
                "port": session.port,
                "power": session.power.to_dict() if session.power else None,
            }
            lent = state.of(session).lent
            if lent is not None:
                # The BPIO2 port is the other program's: nothing is asked on it.
                out["lent"] = dict(lent, how_to_return=handoff.how_to_return(lent["to"]))
                return out
            st = bp.status()
            for key in _BP6_STATUS_FIELDS:
                value = getattr(st, key)
                out[key] = list(value) if isinstance(value, tuple) else value
            return out
        return await guard(lambda: session.run(read), lent_ok=True)

    async def hiz() -> Dict[str, Any]:
        def safe(bp: Any) -> Dict[str, Any]:
            out = {"hiz": True}  # type: Dict[str, Any]
            st = state.of(session)
            if st.terminal_mode is not None or st.pwm_pins:
                # The terminal's PWM and mode outlive BPIO2: stop them there first.
                problems = []
                try:
                    with bp.console() as con:
                        for pin in sorted(st.pwm_pins):
                            reply = con.command("g %d" % pin)
                            if reply.error:
                                problems.append(reply.error)
                        reply = con.command("m hiz")
                        if reply.error:
                            problems.append(reply.error)
                except BusPirateError as exc:
                    problems.append(str(exc))
                st.pwm_pins.clear()
                st.terminal_mode = None
                if problems:
                    out["warnings"] = ["the terminal said: %s" % p for p in problems]
            bp.hiz()
            session.power = None
            return out

        def go() -> Dict[str, Any]:
            back = _take_back()
            if back is not None and "error" in back:
                return dict(back, hiz=False)
            out = session.run(safe)
            if back is not None:
                out.update(back)
            return out
        return await guard(go, lent_ok=True)

    async def power_off() -> Dict[str, Any]:
        def off(bp: Any) -> Dict[str, Any]:
            st = bp.set_power(False)
            session.power = None
            return {"power": False, "psu_enabled": st.psu_enabled}
        return await guard(lambda: session.run(off))

    async def measure_voltages() -> Dict[str, Any]:
        def read(bp: Any) -> Dict[str, Any]:
            m = measure(bp)
            measured["board"] = bp
            out = m.to_dict()
            out["suggested_mv"] = suggest_level(m)
            return out
        return await guard(lambda: session.run(read))

    async def power_plan(millivolts: int, voltage_source: str, pullups: bool = True,
                         milliamps: Optional[int] = None) -> Dict[str, Any]:
        def plan() -> Dict[str, Any]:
            if voltage_source not in (SOURCE_OWNER, SOURCE_MEASURED):
                return {"refused": "voltage_source must be 'owner' (the owner told you) "
                                   "or 'measured' (from measure_voltages, then confirmed "
                                   "by the owner), not %r" % (voltage_source,)}
            if voltage_source == SOURCE_MEASURED and (
                    measured["board"] is None or measured["board"] is not session.board):
                return {"refused": "nothing has been measured on this board; call "
                                   "measure_voltages first, suggest a level and let the "
                                   "owner confirm it"}
            try:
                p = plan_power(VARIANT, millivolts, voltage_source, pullups, milliamps)
            except PowerRefused as exc:
                return {"refused": str(exc)}
            out = p.to_dict()
            out["token"] = confirm.issue(POWER_ACTION, (session.port, p))
            return out
        return await guard(plan)

    async def power_apply(token: str) -> Dict[str, Any]:
        def apply() -> Dict[str, Any]:
            try:
                port, p = confirm.redeem(token, POWER_ACTION)
            except ConfirmError as exc:
                return {"error": str(exc)}

            def switch(bp: Any) -> Dict[str, Any]:
                # Checked under the session lock: the board may have been swapped
                # since the plan.
                if session.port != port:
                    return {"error": "this plan was made for the board on %s, but %s is "
                                     "connected; nothing was switched — plan again"
                                     % (port, session.port)}
                try:
                    return apply_plan(bp, session, p)
                except PowerRefused as exc:
                    return {"error": str(exc)}
            return session.run(switch)
        return await guard(apply)

    # -- bus tools (buspirate.mcp.jobs) -------------------------------------------

    async def wiring(job: str) -> Dict[str, Any]:
        try:
            steps = wiring_steps(VARIANT, job)
        except KeyError:
            return {"error": "no wiring for %r on this board" % (job,), "jobs": list(JOBS)}
        return {"job": job, "steps": [s.to_dict() for s in steps],
                "notes": job_notes(VARIANT, job)}

    SUPPLY_LOST = ("the target supply was found off or tripped, so this ran unpowered; "
                   "make a new power_plan (or recipe_plan) and get the owner's yes to "
                   "switch it on again")

    def _unpowered_if_lost() -> bool:
        """Forget the approved power if the supply is no longer on.

        Primitive bus tools reassert ``session.power``; with the supply tripped or
        switched off on the board that would switch it back on into the fault.
        """
        def check(bp: Any) -> bool:
            if session.power is None:
                return False
            status = bp.status()
            if status.psu_tripped or not status.psu_enabled:
                session.power = None
                return True
            return False
        return session.run(check)

    async def bus(job: Callable[[], Dict[str, Any]]) -> Dict[str, Any]:
        def run() -> Dict[str, Any]:
            lost = _unpowered_if_lost()
            out = job()
            if lost and isinstance(out, dict):
                out["supply_lost"] = SUPPLY_LOST
            return out
        return await guard(run)

    async def i2c_scan(speed_khz: int = 100) -> Dict[str, Any]:
        return await bus(lambda: jobs.i2c_scan(session, speed_khz))

    async def i2c_read(address: int, register: int, count: int = 1) -> Dict[str, Any]:
        return await bus(lambda: jobs.i2c_read(session, address, register, count))

    async def i2c_write(address: int, data_hex: str) -> Dict[str, Any]:
        return await bus(lambda: jobs.i2c_write(session, address, data_hex))

    async def spi_transfer(write_hex: str, read_count: int, mode: int = 0,
                           speed_khz: int = 1000) -> Dict[str, Any]:
        return await bus(lambda: jobs.spi_transfer(session, write_hex, read_count, mode,
                                                     speed_khz))

    async def uart_send(text: str, baud: int = 115200) -> Dict[str, Any]:
        return await bus(lambda: jobs.uart_send(session, text, baud))

    async def uart_listen(seconds: float = 2.0, baud: int = 115200) -> Dict[str, Any]:
        return await bus(lambda: jobs.uart_listen(session, seconds, baud))

    async def onewire_scan() -> Dict[str, Any]:
        return await bus(lambda: jobs.onewire_scan(session))

    async def pins(set: Optional[dict] = None) -> Dict[str, Any]:  # noqa: A002 (tool arg)
        setting = None
        if set:
            if not isinstance(set, dict):
                return {"error": 'set must be a mapping such as {"IO2": 1}, not %r' % (set,)}
            setting = {name: None if level == "in" else level for name, level in set.items()}
            try:
                pin_recipe._masks(setting)  # refuse bad pins before opening the board
            except ValueError as exc:
                return {"error": str(exc)}
        return await bus(lambda: session.run(
            lambda bp: pin_recipe._action(bp, {"set": setting, "read": True})))

    # -- signals (terminal) --------------------------------------------------------

    NEEDS_POWER = "plan power first (power_plan, then power_apply) or power the target"

    def _in_dio(bp: Any, work: Callable[[Any], Dict[str, Any]]) -> Dict[str, Any]:
        """Run ``work(console)`` with the terminal in DIO and the confirmed power on.

        A tool has no plan of its own: it needs the confirmed ``session.power``
        (re-applied after ``m dio``, which switches the supply off) or a target
        that powers itself.
        """
        plan = session.power
        if plan is None and engine._target_mv(bp) is None:
            return {"error": NEEDS_POWER}
        with bp.console() as raw:
            con = engine._TripWatch(raw, session)
            if con.command("").mode.upper() != "DIO":
                state.of(session).terminal_mode = "dio"
                console_power.set_mode(con, "dio")
                if plan is not None:
                    console_power.power_on(con, plan.millivolts, plan.milliamps)
            out = work(con)
            if con.tripped:
                out = dict(out, error=con.tripped)
            return out

    async def pwm(pin: int = 0, hz: float = 1000, duty: float = 50) -> Dict[str, Any]:
        def run() -> Dict[str, Any]:
            signals.check_pwm(pin, hz, duty)  # refuse before touching the board

            def work(con: Any) -> Dict[str, Any]:
                other = next((p for p in sorted(state.of(session).pwm_pins)
                              if p // 2 == pin // 2), None)
                if other is not None:
                    return {"error": "IO%d and IO%d share one PWM, and IO%d already has one "
                            "running; call pwm_off first" % (pin - pin % 2, pin - pin % 2 + 1,
                                                              other)}
                out = signals.pwm_start(con, pin, hz, duty)
                state.of(session).pwm_pins.add(pin)
                return out
            return session.run(lambda bp: _in_dio(bp, work))
        return await guard(run)

    async def pwm_off(pin: int) -> Dict[str, Any]:
        def run() -> Dict[str, Any]:
            def stop(bp: Any) -> Dict[str, Any]:
                with bp.console() as raw:  # g needs no mode change
                    con = engine._TripWatch(raw, session)
                    try:
                        out = signals.pwm_stop(con, pin)
                    finally:
                        state.of(session).pwm_pins.discard(pin)
                    if con.tripped:
                        out = dict(out, error=con.tripped)
                    return out
            return session.run(stop)
        return await guard(run)

    async def frequency(pin: int = 1) -> Dict[str, Any]:
        def run() -> Dict[str, Any]:
            signals.check_frequency_pin(pin)
            return session.run(lambda bp: _in_dio(
                bp, lambda con: signals.measure_frequency(con, pin)))
        return await guard(run)

    async def bp6_notes() -> Dict[str, Any]:
        return {"text": NOTES.read_text(encoding="utf-8")}

    unpowered = (" Never switches the target supply on: it is powered only after "
                 "power_apply or recipe_run.")
    tools: List[Tuple[str, Callable, str]] = [
        ("recipes", recipes, "Find recipes by device or job name (e.g. 'lcd', 'bme280', "
         "'spi flash'); with no query, list them all by bus. Call first when the owner "
         "names a device."),
        ("recipe_plan", recipe_plan, "Plan a recipe: measures the target, then returns the "
         "wiring, the power plan, what the action does, warnings and a token. Switches "
         "nothing. Options may override the voltage (millivolts) or address within range. "
         "Show the owner the wiring and the plan in one message."),
        ("recipe_run", recipe_run, "Run a planned recipe with its token: applies the planned "
         "power, runs the check, then the action. Only after the owner's yes; ask a second "
         "time when needs_extra_confirmation is true. token=None re-runs the last recipe "
         "while its power is still on, within 5 minutes."),
        ("recipe_commit", recipe_commit, "Make the change a recipe_run stopped at, with the "
         "`commit` token it returned. Only after the owner's second yes to that change. "
         "Switches no power and touches no pull-ups. `committed` is true only when the "
         "read-back matches; otherwise the result names the backup."),
        ("board_status", board_status, "The Bus Pirate 6, its port, approved power and live "
         "supply readings."),
        ("connect", connect, "Open the Bus Pirate 6 (give `port` to pick one of several). "
         "Other tools connect on first use, so this is only needed to switch boards."),
        ("hiz", hiz, "Put every pin in high impedance, the supply and pull-ups off. Use when "
         "done or when anything looks wrong."),
        ("power_off", power_off, "Switch the target supply off."),
        ("measure_voltages", measure_voltages, "Read the voltages the target already puts on "
         "the pins and suggest a level, before power_plan."),
        ("power_plan", power_plan, "Plan the target supply outside a recipe (800-5000 mV). "
         "voltage_source is 'owner' or 'measured'. Returns the plan and a token; nothing "
         "is switched."),
        ("power_apply", power_apply, "Switch on the supply from a power_plan token. Only "
         "after the owner's yes; ask a second time when needs_extra_confirmation is true."),
        ("wiring", wiring, "The wires to connect for a job (%s), each with pin and colour, "
         "plus notes. Recipes carry their own wiring; use this for the primitive bus tools "
         "and give the owner every step." % ", ".join(JOBS)),
        ("i2c_scan", i2c_scan, "Find the I2C devices (SDA IO0, SCL IO1), named and read in "
         "real units where known." + unpowered),
        ("i2c_read", i2c_read, "Read `count` bytes from one register of an I2C device "
         "(7-bit address as an integer) and explain them." + unpowered),
        ("i2c_write", i2c_write, "Write hex bytes to an I2C device in one transaction (a "
         "register is the first byte). It changes the chip: say what and why first."
         + unpowered),
        ("spi_transfer", spi_transfer, "Write hex bytes over SPI with CS low, then read "
         "`read_count` bytes." + unpowered),
        ("uart_send", uart_send, "Send text on the UART at `baud` (8N1)." + unpowered),
        ("uart_listen", uart_listen, "Listen on the UART for `seconds` at `baud` and return "
         "what arrived, as text and hex." + unpowered),
        ("onewire_scan", onewire_scan, "Find the 1-Wire device on IO0 and read it if known "
         "(DS18B20 in °C)." + unpowered),
        ("pins", pins, "Drive IO pins and read every pin's direction, level and voltage. "
         "`set` maps pins to 1, 0 or \"in\", e.g. {\"IO2\": 1, \"IO3\": \"in\"}; omit it to "
         "only read." + unpowered),
        ("pwm", pwm, "Generate a square wave on an IO pin (0-7): `hz` 8 to 62500000, `duty` "
         "above 0 to 100 percent. IO0/IO1, IO2/IO3, IO4/IO5 and IO6/IO7 share one PWM, so "
         "only one pin of a pair runs. Needs power: planned and applied, or the target's own. "
         "Runs until pwm_off or hiz. Returns the actual frequency and duty."),
        ("pwm_off", pwm_off, "Stop the PWM on an IO pin."),
        ("frequency", frequency, "Measure the frequency and duty cycle of a signal on IO1, "
         "IO3, IO5 or IO7 (one reading). Needs power like pwm."),
        ("bp6_notes", bp6_notes, "The Bus Pirate 6 notes: limits, pin map with wire colours, "
         "the pull-up rule and the risks. Read when unsure."),
    ]
    for name, fn, description in tools:
        server.add_tool(fn, name=name, description=description)
    _SESSIONS[server] = session
    return server


#: The tool names, in the order they are registered.
TOOL_NAMES = ("recipes", "recipe_plan", "recipe_run", "recipe_commit", "board_status",
              "connect", "hiz", "power_off", "measure_voltages", "power_plan", "power_apply",
              "wiring", "i2c_scan", "i2c_read", "i2c_write", "spi_transfer", "uart_send", "uart_listen",
              "onewire_scan", "pins", "pwm", "pwm_off", "frequency", "bp6_notes")


def shut_down(session: BoardSession) -> None:
    """On exit: take a lent board back (its supply goes off), then HiZ and close."""
    try:
        if state.of(session).lent is not None:
            handoff.reclaim(session)
    finally:
        session.disconnect()


def run_stdio(demo: bool = False) -> None:
    """Serve over stdio. The board opens on first use and goes to HiZ on exit."""
    session = BoardSession(simulated=VARIANT if demo else None)
    server = build_server(session)
    try:
        server.run("stdio")
    finally:
        shut_down(session)
