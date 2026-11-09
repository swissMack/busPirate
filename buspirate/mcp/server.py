"""The MCP server: board-gated tools, two-step power, wiring and knowledge.

This is the only module that imports the ``mcp`` SDK (Python 3.10+). Every
other module in ``buspirate.mcp`` stays importable on Python 3.8.

Power is never switched on without a redeemed confirmation token:
``power_plan`` returns a plan and a token, the owner says yes, and only then
does ``power_apply(token)`` touch the supply.
"""

import importlib
import logging
import weakref
from typing import Any, Callable, Dict, FrozenSet, List, Optional, Tuple

from mcp.server.mcpserver import Context, MCPServer

from .. import boards
from ..exceptions import BusPirateError
from . import knowledge
from .confirm import ConfirmError, ConfirmStore
from .power import SOURCE_MEASURED, SOURCE_OWNER, PowerRefused, measure, plan_power, suggest_level
from .session import BoardGone, BoardSession, NotConnected
from .wiring import JOBS, wiring_steps

log = logging.getLogger(__name__)

ALWAYS = ("find_boards", "connect", "knowledge_topics", "knowledge_read", "knowledge_search")

_ANY_BOARD = (frozenset(),)

#: Tool name -> alternative capability sets; listed when any set is satisfied.
BOARD_TOOLS: Dict[str, Tuple[FrozenSet[str], ...]] = {
    "disconnect": _ANY_BOARD,
    "board_status": _ANY_BOARD,
    "wiring": _ANY_BOARD,
    "measure_voltages": (frozenset({"adc"}), frozenset({"psu_current_readout"})),
    "power_plan": _ANY_BOARD,
    "power_apply": _ANY_BOARD,
    "power_off": _ANY_BOARD,
    "hiz": _ANY_BOARD,
}

RECONNECT_HINT = "If new tools don't appear, run /mcp → reconnect buspirate."
BOARD_GONE = "board disconnected — plug it back in and call connect"
POWER_ACTION = "power_apply"
_BP6_FAMILY = ("bp6", "bp5")
_BP6_STATUS_FIELDS = ("psu_enabled", "psu_mv", "psu_ma", "psu_tripped", "pullups",
                      "adc_mv", "pin_labels")

INSTRUCTIONS = """\
Tools for a Bus Pirate (v3, v4, Bus Pirate 5/6) or an ESP32 Bit Pirate.

- Read the `boards` knowledge topic first (knowledge_read("boards")).
- Call find_boards and connect; the board's own tools appear once it is connected.
- Always call `wiring` for the job and give the owner every step, pin and wire \
colour, before using any bus tool.
- Before `power_plan`, ask the owner whether they know the target's voltage. If \
they do not, call `measure_voltages`, then suggest a level and let them confirm it.
- Never call `power_apply` until the owner has said yes to the plan you showed them.
- When a plan has `needs_extra_confirmation` true, ask a second time, naming the \
voltage and the current limit.
- If a tool reports the board disconnected, ask the owner to plug it back in and \
call connect.
"""

#: Each built server's session and tool registry, for apply_gating.
_SESSIONS: "weakref.WeakKeyDictionary[MCPServer, BoardSession]" = weakref.WeakKeyDictionary()
_TOOLS: "weakref.WeakKeyDictionary[MCPServer, Dict[str, Tuple[Callable, str]]]" = (
    weakref.WeakKeyDictionary())
_LISTED: "weakref.WeakKeyDictionary[MCPServer, set]" = weakref.WeakKeyDictionary()


def apply_gating(server: MCPServer, session: BoardSession) -> List[str]:
    """List ALWAYS plus every board tool whose capabilities the board has."""
    caps = session.capabilities
    connected = session.board is not None
    wanted = set(ALWAYS)
    if connected:
        wanted |= {name for name, alternatives in BOARD_TOOLS.items()
                   if any(need <= caps for need in alternatives)}
    tools = _TOOLS[server]
    listed = _LISTED[server]
    for name in sorted(listed - wanted):
        server.remove_tool(name)
        listed.discard(name)
    for name in sorted(wanted - listed):
        if name in tools:
            fn, description = tools[name]
            server.add_tool(fn, name=name, description=description)
            listed.add(name)
    return sorted(listed)


def _panel_notes(variant: str, job: str) -> List[str]:
    """The notes the dashboard shows under this job's panel on this board."""
    board = boards.get(variant)
    override = board.wiring.get("panels", {}).get(job, {}) if board is not None else {}
    if "notes" in override:
        return list(override["notes"])
    try:
        panel = importlib.import_module("buspirate.web.panels." + job).PANEL
    except ImportError:
        return []
    return list(panel.notes)


def build_server(session: BoardSession) -> MCPServer:
    server = MCPServer("buspirate", instructions=INSTRUCTIONS)
    confirm = ConfirmStore()
    measured: Dict[str, Any] = {"board": None}  # the board measure_voltages last read

    async def guard(ctx: Context, fn: Callable[[], Dict[str, Any]]) -> Dict[str, Any]:
        try:
            return fn()
        except BoardGone:
            apply_gating(server, session)
            await ctx.notify_tools_changed()
            return {"error": BOARD_GONE}
        except NotConnected as exc:
            return {"error": str(exc)}
        except BusPirateError as exc:
            return {"error": str(exc)}

    # -- always listed --------------------------------------------------------

    async def find_boards(ctx: Context) -> Dict[str, Any]:
        return {"ports": session.candidates()}

    async def connect(ctx: Context, port: Optional[str] = None) -> Dict[str, Any]:
        try:
            out = session.connect(port)
        except (NotConnected, OSError, BusPirateError) as exc:
            out = {"connected": False, "error": str(exc)}
        measured["board"] = None
        out["tools"] = apply_gating(server, session)
        out["hint"] = RECONNECT_HINT
        await ctx.notify_tools_changed()
        return out

    async def knowledge_topics(ctx: Context) -> Dict[str, Any]:
        return {"topics": knowledge.topics()}

    async def knowledge_read(ctx: Context, topic: str) -> Dict[str, Any]:
        try:
            return {"topic": topic, "text": knowledge.read(topic)}
        except KeyError as exc:
            return {"error": exc.args[0]}

    async def knowledge_search(ctx: Context, query: str) -> Dict[str, Any]:
        return {"query": query, "results": knowledge.search(query)}

    # -- board tools ------------------------------------------------------------

    async def disconnect(ctx: Context) -> Dict[str, Any]:
        session.disconnect()
        measured["board"] = None
        tools = apply_gating(server, session)
        await ctx.notify_tools_changed()
        return {"connected": False, "tools": tools, "hint": RECONNECT_HINT}

    async def board_status(ctx: Context) -> Dict[str, Any]:
        def read(bp: Any) -> Dict[str, Any]:
            profile = bp.profile
            out = {
                "board": profile.describe(),
                "variant": profile.variant,
                "capabilities": sorted(profile.capabilities),
                "power": session.power.to_dict() if session.power else None,
            }
            if profile.variant in _BP6_FAMILY:
                st = bp.status()
                for key in _BP6_STATUS_FIELDS:
                    value = getattr(st, key)
                    out[key] = list(value) if isinstance(value, tuple) else value
            return out
        return await guard(ctx, lambda: session.run(read))

    async def wiring(ctx: Context, job: str) -> Dict[str, Any]:
        def steps() -> Dict[str, Any]:
            variant = session.variant
            if variant is None:
                raise NotConnected("no board is connected — call connect first")
            try:
                found = wiring_steps(variant, job)
            except KeyError:
                return {"error": "no wiring for %r on this board" % job, "jobs": list(JOBS)}
            return {"job": job, "steps": [s.to_dict() for s in found],
                    "notes": _panel_notes(variant, job)}
        return await guard(ctx, steps)

    async def measure_voltages(ctx: Context) -> Dict[str, Any]:
        def read(bp: Any) -> Dict[str, Any]:
            m = measure(bp)
            measured["board"] = bp
            out = m.to_dict()
            out["suggested_mv"] = suggest_level(m)
            return out
        return await guard(ctx, lambda: session.run(read))

    async def power_plan(ctx: Context, millivolts: int, voltage_source: str,
                         pullups: bool = True,
                         milliamps: Optional[int] = None) -> Dict[str, Any]:
        def plan() -> Dict[str, Any]:
            variant = session.variant
            if variant is None:
                raise NotConnected("no board is connected — call connect first")
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
                p = plan_power(variant, millivolts, voltage_source, pullups, milliamps)
            except PowerRefused as exc:
                return {"refused": str(exc)}
            out = p.to_dict()
            out["token"] = confirm.issue(POWER_ACTION, p)
            return out
        return await guard(ctx, plan)

    async def power_apply(ctx: Context, token: str) -> Dict[str, Any]:
        def apply() -> Dict[str, Any]:
            try:
                p = confirm.redeem(token, POWER_ACTION)
            except ConfirmError as exc:
                return {"error": str(exc)}
            if p.variant != session.variant:
                return {"error": "this plan was made for a %s, but the connected board is "
                                 "%s; nothing was switched — plan again"
                                 % (p.variant, session.variant or "none")}

            def switch(bp: Any) -> Dict[str, Any]:
                out = p.to_dict()
                if p.variant in _BP6_FAMILY:
                    try:
                        bp.set_power(True, millivolts=p.millivolts, milliamps=p.milliamps)
                        st = bp.set_pullups(p.pullups)
                    except BusPirateError:
                        try:
                            bp.set_power(False)  # never leave a half-applied plan on
                        except BusPirateError:
                            log.warning("could not switch the supply back off", exc_info=True)
                        raise
                    out.update(psu_enabled=st.psu_enabled, psu_mv=st.psu_mv,
                               psu_ma=st.psu_ma, psu_tripped=st.psu_tripped,
                               pullups_on=st.pullups)
                elif p.variant in ("v3", "v4"):
                    out["pins"] = bp.decode_pins(bp.set_pins(power=True, pullups=p.pullups))
                else:
                    out["note"] = ("recorded only: software cannot switch this board's "
                                   "supply; the owner sets it")
                session.power = p
                out["applied"] = True
                return out
            return session.run(switch)
        return await guard(ctx, apply)

    def _switch_off(bp: Any) -> Dict[str, Any]:
        variant = bp.profile.variant
        out: Dict[str, Any] = {"power": False}
        if variant in _BP6_FAMILY:
            out["psu_enabled"] = bp.set_power(False).psu_enabled
        elif variant in ("v3", "v4"):
            out["pins"] = bp.decode_pins(bp.set_pins())
        else:
            out["note"] = ("software cannot switch this board's supply; ask the owner "
                           "to disconnect VIO or switch the target off")
        session.power = None
        return out

    async def power_off(ctx: Context) -> Dict[str, Any]:
        return await guard(ctx, lambda: session.run(_switch_off))

    async def hiz(ctx: Context) -> Dict[str, Any]:
        def safe(bp: Any) -> Dict[str, Any]:
            if not hasattr(bp, "hiz"):
                return _switch_off(bp)
            bp.hiz()
            session.power = None
            return {"hiz": True}
        return await guard(ctx, lambda: session.run(safe))

    ask_first = (" Only after the owner has said yes to the plan you showed them; ask "
                 "a second time, naming voltage and limit, when needs_extra_confirmation "
                 "is true.")
    tools: Dict[str, Tuple[Callable, str]] = {
        "find_boards": (find_boards, "List the serial ports that look like a Bus Pirate "
                        "or Bit Pirate. Use before connect when unsure which board is "
                        "plugged in."),
        "connect": (connect, "Open the board (give `port` when find_boards lists several). "
                    "Its own tools appear once it is connected."),
        "knowledge_topics": (knowledge_topics, "List the knowledge notes. Read `boards` "
                             "first, and the note for a job before doing it."),
        "knowledge_read": (knowledge_read, "Read one knowledge note by topic name."),
        "knowledge_search": (knowledge_search, "Search the notes and bundled manuals when "
                             "a question is not covered by one topic."),
        "disconnect": (disconnect, "Close the board (leaves it in HiZ). Use when the owner "
                       "is done or wants to swap boards."),
        "board_status": (board_status, "Board, capabilities, approved power, and on a Bus "
                         "Pirate 6 the live supply readings. Use to check state."),
        "wiring": (wiring, "The wires to connect for a job (%s), each with pin and colour, "
                   "plus notes. Call before any bus tool and give the owner every step."
                   % ", ".join(JOBS)),
        "measure_voltages": (measure_voltages, "Read the voltages the target already puts "
                             "on the pins and suggest a level. Use when the owner does not "
                             "know the target's voltage, before power_plan."),
        "power_plan": (power_plan, "Plan the target supply. Ask the owner the voltage first "
                       "(voltage_source='owner'), or measure_voltages and have them confirm "
                       "(voltage_source='measured'). Returns the plan and a token; show the "
                       "owner the plan. Nothing is switched."),
        "power_apply": (power_apply, "Switch on the supply from a power_plan token." + ask_first),
        "power_off": (power_off, "Switch the target supply off."),
        "hiz": (hiz, "Put every pin in high impedance and the supply off. Use when done or "
                "when anything looks wrong."),
    }
    _SESSIONS[server] = session
    _TOOLS[server] = tools
    _LISTED[server] = set()
    apply_gating(server, session)
    return server


def run_stdio(simulated: Optional[str] = None) -> None:
    """Serve over stdio; auto-connect when exactly one board is plugged in."""
    session = BoardSession(simulated=simulated)
    server = build_server(session)
    try:
        try:
            if len(session.candidates()) == 1:
                session.connect()
        except Exception:
            log.warning("could not open the board at startup", exc_info=True)
        apply_gating(server, session)
        server.run("stdio")
    finally:
        session.disconnect()
