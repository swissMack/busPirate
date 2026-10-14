"""The one device the dashboard talks to, and the plumbing around it.

A serial port tolerates exactly one caller, and the driver is blocking. So
there is a single session object holding the port, an asyncio lock around
every use of it, and a thread executor to keep the event loop free. Handlers
are ordinary synchronous functions; they never see any of this.
"""

from __future__ import annotations

import asyncio
import os
import queue
import sys
import threading
import time
from collections import deque
from typing import Any, Dict, List, Optional, Set

from .. import device as device_module
from ..connect import open_device
from ..exceptions import BusPirateError, ConnectionError, ModeError
from ..ports import discover, resolve
from .decoders import make_decoder
from .registry import Action, Panel, live, load_panels
from .wiring import BOARDS, DEFAULT_VARIANT, LED_RULES

TRAFFIC_HISTORY = 500
STREAM_EVENT_CAP = 200  # events per websocket message
STREAM_FLUSH_SECONDS = 0.1  # at most ten updates a second, however busy the bus

#: How long to watch after leaving binary mode. Both boards reset here. A v3
#: stays on USB and needs this long to boot (0.5 s was verified on hardware);
#: a v4 drops off USB and re-enumerates — measured on firmware 6.0-a3, gone at
#: 188 ms and back at 463 ms — so the window has to outlast its departure.
#: It is the watch passed to BusPirate.reopen_if_reenumerated().
TERMINAL_SETTLE_SECONDS = 0.8

#: How long stop_stream_blocking() waits for the reader thread to let go of
#: the port. Leaving the board's terminal on a v3 means a hardware reset, so
#: enter_binary_mode()'s 25 retries against a 0.2s serial timeout can run for
#: seconds on their own. A generous wait is still only a wait, though: if it
#: expires we say the stream did not stop rather than pretending it did.
STREAM_STOP_TIMEOUT_SECONDS = 15.0

#: Port names that mean "a simulated board", offered in every port list so
#: the dashboard can be tried without hardware, whatever it was launched with.
SIMULATED_PREFIX = "simulated-"
SIMULATED_VARIANTS = ("v3", "v4", "bitpirate", "bp6")

#: How each simulated board is named in the port list.
SIMULATED_NAMES = {
    "v3": "simulated Bus Pirate v3",
    "v4": "simulated Bus Pirate v4",
    "bitpirate": "simulated ESP32 Bit Pirate",
    "bp6": "simulated Bus Pirate 6",
}


def simulated_variant(port: Optional[str]) -> Optional[str]:
    """The variant a simulated port name stands for, or None for real ports."""
    if port and port.startswith(SIMULATED_PREFIX):
        variant = port[len(SIMULATED_PREFIX):]
        if variant in SIMULATED_VARIANTS:
            return variant
    return None


#: Where captures go when the app is frozen into a ``.app`` bundle.
#:
#: Finder launches an app with a current directory of ``/``, so the relative
#: ``captures/`` used from a checkout would try to create ``/captures`` and
#: fail. The home folder is the one place that is writable, obvious in Finder
#: and *not* covered by macOS TCC — ``~/Documents``, ``~/Desktop`` and
#: ``~/Downloads`` all pop a consent dialog for an unsigned app, and this one
#: is unsigned by design.
FROZEN_CAPTURES_DIR = os.path.join("~", "BusPirate", "captures")


def captures_root() -> str:
    """The directory dumps and logs are written to.

    From a checkout this stays ``<cwd>/captures``, exactly as before: the
    tests and the usual ``bin/dashboard.command`` workflow both depend on it.
    Only a frozen bundle takes the other branch.
    """
    if getattr(sys, "frozen", False):
        return os.path.expanduser(FROZEN_CAPTURES_DIR)
    return os.path.join(os.getcwd(), "captures")


class StreamState:
    """A sniffer or bridge currently holding the port."""

    def __init__(self, kind: str, panel_id: str, action: str, decoder, result):
        self.kind = kind
        self.panel_id = panel_id
        self.action = action
        self.decoder = decoder
        self.result = result
        self.stop_event = threading.Event()
        self.thread: Optional[threading.Thread] = None
        self.started_at = time.time()
        self.events = 0
        self.note = ""
        #: Set by _finish_stream so it can never run twice for one stream,
        #: whichever path gets there first.
        self.finished = False

    def describe(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "panel": self.panel_id,
            "action": self.action,
            "events": self.events,
            "seconds": round(time.time() - self.started_at, 1),
            # False here, True on TerminalState. This is the signal the
            # frontend uses to decide whether a running stream is a console
            # it should re-render with an input line — never ``kind``, which
            # is only a display label. See TerminalState.describe().
            "input": False,
        }


class TerminalState(StreamState):
    """The Bus Pirate's own terminal, held open as a stream.

    Typed input does not go to the port directly. ``send_terminal_keys`` puts
    it here and the reader thread writes it, so that thread stays the only
    thing touching the port.
    """

    def __init__(self, decoder, result) -> None:
        super().__init__(
            "Board terminal", "terminal", "open_terminal", decoder, result
        )
        self.inbox: "queue.Queue[bytes]" = queue.Queue()

    def describe(self) -> Dict[str, Any]:
        data = super().describe()
        data["input"] = True
        return data


class ActionContext:
    """What a handler is given: the device, its mode, and a way to report back."""

    def __init__(self, session: "DeviceSession", mode) -> None:
        self.session = session
        self.bp = session.bp
        self.mode = mode
        self.profile = session.bp.profile if session.bp else None

    def progress(self, done: int, total: int, message: str = "") -> None:
        """Report progress on a long job. Safe to call from the worker thread."""
        self.session.emit(
            {
                "type": "progress",
                "done": done,
                "total": total,
                "message": message,
            }
        )

    def note(self, message: str) -> None:
        self.session.emit({"type": "note", "message": message})

    def capture_path(self, filename: str) -> str:
        """A writable path under ``captures/`` for dumps and logs."""
        root = captures_root()
        os.makedirs(root, exist_ok=True)
        safe = os.path.basename(filename) or "capture.bin"
        return os.path.join(root, safe)

    def read_capture(self, filename: str) -> bytes:
        """Load a file from ``captures/``, or say what is actually there."""
        path = self.capture_path(filename)
        try:
            with open(path, "rb") as handle:
                return handle.read()
        except OSError:
            root = os.path.dirname(path)
            existing = sorted(
                name for name in os.listdir(root) if not name.startswith(".")
            ) if os.path.isdir(root) else []
            listing = ", ".join(existing) if existing else "nothing"
            raise BusPirateError(
                f"there is no {filename!r} in captures/. It currently holds: "
                f"{listing}."
            ) from None


class DeviceSession:
    """Owns the port, the current mode, and the live traffic log."""

    def __init__(self, use_fake: bool = False, fake_variant: str = "v3") -> None:
        self.use_fake = use_fake
        self.fake_variant = fake_variant
        #: A BusPirate or a BitPirate — the dashboard only uses what both offer.
        self.bp = None
        self.port: Optional[str] = None
        #: What discovery knew about the port we connected to.
        self.port_info: Optional[Dict[str, Any]] = None
        self.mode_name: Optional[str] = None
        self._mode = None
        # Made on first use, inside the running loop. On Python 3.8 and 3.9 a
        # Lock grabs the thread's event loop when it is created, and building
        # one here — with no loop running — fails once an earlier loop in the
        # thread has been closed.
        self._lock: Optional[asyncio.Lock] = None
        self.traffic: deque = deque(maxlen=TRAFFIC_HISTORY)
        self.subscribers: Set[asyncio.Queue] = set()
        self.panels: List[Panel] = load_panels()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._seq = 0
        #: The sniffer or bridge holding the port, if any.
        self.stream: Optional[StreamState] = None
        #: Last pin state the Pins panel drove, so it can be re-applied.
        self.last_pins = {
            "power": False,
            "pullups": False,
            "aux": False,
            "mosi": False,
            "clk": False,
            "miso": False,
            "cs": False,
        }
        #: PWM on AUX survives a mode change, so it has to be remembered.
        self.pwm_running = False
        #: Manual override of the variant the UI presents. None = follow
        #: whatever the banner said.
        self.display_variant: Optional[str] = None
        #: The board speaks BPIO2 (a Bus Pirate 6): summarise its frames in
        #: the traffic log. Set before connecting, so the status request sent
        #: while opening is summarised too.
        self._bpio2_traffic = False
        #: When the Bus Pirate 6's supply was last read, for the status poll.
        self._power_read_at = 0.0

    @property
    def lock(self) -> asyncio.Lock:
        """The lock around every use of the port. Only touched from the loop."""
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    # -- events ------------------------------------------------------------

    def bind_loop(self) -> None:
        self._loop = asyncio.get_running_loop()

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self.subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self.subscribers.discard(queue)

    def emit(self, event: Dict[str, Any]) -> None:
        """Publish an event. Callable from any thread."""
        if self._loop is None:
            return
        self._loop.call_soon_threadsafe(self._emit_now, event)

    def _emit_now(self, event: Dict[str, Any]) -> None:
        for queue in list(self.subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                self.subscribers.discard(queue)

    def _on_traffic(self, direction: str, data: bytes) -> None:
        self._seq += 1
        entry = {
            "type": "traffic",
            "seq": self._seq,
            "at": time.strftime("%H:%M:%S"),
            "direction": direction,
            "hex": bytes(data).hex(" "),
        }
        if self._bpio2_traffic and not isinstance(self.stream, TerminalState):
            from ..bp6.protocol import describe_frame

            entry["summary"] = describe_frame(direction, data)
        self.traffic.append(entry)
        self.emit(entry)

    # -- connection --------------------------------------------------------

    @property
    def simulated(self) -> bool:
        """Whether the board in use (or, before connecting, the default) is fake.

        Decided per connection rather than per launch: a dashboard started for
        real hardware can still be pointed at a simulated board.
        """
        if self.port is not None:
            return simulated_variant(self.port) is not None
        return self.use_fake

    def _open_device(self, port: str):
        """Open the board on ``port`` with the driver it needs."""
        variant = simulated_variant(port)
        if variant == "bp6":
            from ..bp6 import BusPirate6
            from ..simulator_bp6 import FakeBp6

            fake = FakeBp6()
            return BusPirate6(
                FakeBp6.BINARY,
                terminal_port=FakeBp6.TERMINAL,
                serial_factory=fake.factory(),
                on_traffic=self._on_traffic,
                connect_timeout=0.2,
            ).open()
        if variant == "bitpirate":
            from ..bitpirate import BitPirate
            from ..simulator import fake_factory
            from ..simulator_bitpirate import FakeBitPirateSerial

            return BitPirate(
                port,
                serial_factory=fake_factory(FakeBitPirateSerial(booting=True)),
                on_traffic=self._on_traffic,
                connect_timeout=0.3,
            ).open()
        if variant is not None:
            from ..base import BusPirate
            from ..simulator import FakeSerial, fake_factory

            fake = FakeSerial(variant=variant)
            return BusPirate(
                port,
                serial_factory=fake_factory(fake),
                on_traffic=self._on_traffic,
                identify_timeout=0.05,
            ).open()
        return open_device(
            port,
            usb_id=(self.port_info or {}).get("usb_id"),
            on_traffic=self._on_traffic,
        )

    def _resolve(self, port: Optional[str]) -> str:
        """Turn what the user picked into a port name, real or simulated."""
        if port == "fake" or (self.use_fake and port in (None, "", "auto")):
            # "fake" is the name the simulator had before it could be picked.
            return SIMULATED_PREFIX + self.fake_variant
        if simulated_variant(port) is not None:
            return port
        try:
            return resolve(port)
        except ConnectionError as exc:
            # Automatic detection never picks the simulator — that would pass
            # off a fake board as the real one — but it should be mentioned.
            raise ConnectionError(
                f"{exc} To try the dashboard without hardware, pick a "
                "simulated Bus Pirate from the port list instead."
            ) from None

    def connect_blocking(self, port: Optional[str]) -> Dict[str, Any]:
        self.disconnect_blocking()
        resolved = self._resolve(port)
        self.port_info = self._describe_port(resolved)
        self._bpio2_traffic = (
            simulated_variant(resolved) == "bp6"
            or (self.port_info or {}).get("usb_id") == "1209:7331"
        )
        try:
            self.bp = self._open_device(resolved)
        except BaseException:
            self._bpio2_traffic = False
            raise
        self.port = resolved
        self.mode_name = None
        self._mode = None
        return self.status()

    def disconnect_blocking(self) -> None:
        if self.stream is not None:
            outcome = self.stop_stream_blocking()
            if not outcome.get("stopped") and self.stream is not None:
                # The reader thread still owns the port. Closing it here
                # would put two threads on one serial handle — the exact
                # thing the single-reader design exists to prevent — so
                # refuse instead. The thread clears self.stream on its way
                # out, after which a retry disconnects normally.
                raise BusPirateError(
                    outcome.get("reason", "a stream still holds the port")
                )
        if self.bp is not None:
            try:
                self.bp.close()
            except BusPirateError:
                pass
        self.bp = None
        self.port = None
        self.port_info = None
        self._bpio2_traffic = False
        self.mode_name = None
        self._mode = None
        # Whatever we drove the pins to is no longer true of the board, and
        # keeping it would light VREG on the next connect.
        self.last_pins = dict.fromkeys(self.last_pins, False)
        self.pwm_running = False
        # An override set while inspecting one board must not follow you onto
        # the next one you plug in.
        self.display_variant = None

    def hiz_blocking(self) -> None:
        """Let go of the target: every pin an input, supplies and pull-ups off.

        Disconnect without closing the port. Stops a stream on the same
        terms as :meth:`disconnect_blocking`, leaves the protocol mode, and
        then releases the pins the way the firmware's own ``binReset()``
        does — directions first, then states — because leaving a mode
        resets them but a bare bitbang ``0x00`` does not, and the Pins
        panel works in bitbang. PWM survives a mode change, so it is
        stopped too.
        """
        if self.bp is None:
            raise BusPirateError("not connected — pick a port and connect first")
        if self.stream is not None:
            outcome = self.stop_stream_blocking()
            if not outcome.get("stopped") and self.stream is not None:
                raise BusPirateError(
                    outcome.get("reason", "a stream still holds the port")
                )
        self.ensure_mode(None)
        capabilities = self.bp.profile.capabilities
        if device_module.CAP_BITBANG_PINS in capabilities:
            self.bp.set_pin_directions()
            self.bp.set_pins()
            if device_module.CAP_PWM in capabilities:
                self.bp.pwm_clear()
        elif hasattr(self.bp, "hiz"):
            self.bp.hiz()  # a Bus Pirate 6: one BPIO2 request releases everything
        else:
            # A Bit Pirate has no bitbang: its own HiZ mode releases the pins.
            self.bp.cli.command("m hiz")
        self.last_pins = dict.fromkeys(self.last_pins, False)
        self.pwm_running = False

    def live(self) -> List[str]:
        """What is holding the target, in words; empty means it is in HiZ.

        Built from what this session drove, like the LEDs: a stream, a
        protocol mode (its pins are configured, whatever the supplies),
        the supplies, the pull-ups, pins driven from the Pins panel, PWM.
        The board's own terminal is a stream, so it counts as live too.
        """
        reasons = []
        if self.stream is not None:
            reasons.append(f"{self.stream.kind} running")
        if self.mode_name is not None:
            titles = {p.mode: p.title for p in self.panels if p.mode}
            reasons.append(f"{titles.get(self.mode_name, self.mode_name)} mode")
        if self._supplies_on():
            reasons.append("supplies on")
        if self._pullups_on():
            reasons.append("pull-ups on")
        if self._mode is None and any(
            self.last_pins.get(pin) for pin in ("aux", "mosi", "clk", "miso", "cs")
        ):
            reasons.append("pins driven")
        if self.pwm_running:
            reasons.append("PWM on AUX")
        return reasons

    def _describe_port(self, device: str) -> Dict[str, Any]:
        """What USB discovery can tell us about one device path."""
        variant = simulated_variant(device)
        if variant is not None:
            return {
                "device": device,
                "usb_id": None,
                "description": SIMULATED_NAMES[variant],
                "note": "no hardware involved",
            }
        for candidate in discover(include_unlikely=True):
            if candidate.device == device:
                return {
                    "device": device,
                    "usb_id": candidate.usb_id,
                    "description": candidate.description,
                    "note": candidate.note,
                }
        return {"device": device, "usb_id": None, "description": "", "note": ""}

    def usb_status(self) -> Dict[str, Any]:
        """Is the USB device still there? Checked live, not cached.

        Unplugging the Bus Pirate does not close the file handle on macOS, so
        the only honest way to answer is to re-enumerate.
        """
        if self.port is None:
            return {"attached": False}
        if self.simulated:
            return dict(self.port_info or {}, attached=True, simulated=True)
        attached = any(
            candidate.device == self.port
            for candidate in discover(include_unlikely=True)
        )
        return dict(self.port_info or {"device": self.port}, attached=attached)

    def supplies_on(self) -> bool:
        """Public name for :meth:`_supplies_on`, for panels to read."""
        return self._supplies_on()

    def _supplies_on(self) -> bool:
        """Whether the last thing we told the board was 'supplies on'.

        A protocol mode switches them through ``configure_peripherals``; the
        pins panel goes round it with a bitbang ``set_pins``. Whichever spoke
        last is the one to believe, and entering a mode resets the board's
        peripheral bits, so an active mode wins.
        """
        status = getattr(self.bp, "last_status", None)
        if status is not None:
            return bool(status.psu_enabled)  # a Bus Pirate 6 says, so ask it
        if self._mode is not None:
            return bool(self._mode.peripherals.get("power"))
        return bool(self.last_pins.get("power"))

    def _pullups_on(self) -> bool:
        status = getattr(self.bp, "last_status", None)
        if status is not None:
            return bool(status.pullups)
        if self._mode is not None:
            return bool(self._mode.peripherals.get("pullups"))
        return bool(self.last_pins.get("pullups"))

    def _power(self) -> Optional[Dict[str, Any]]:
        """The Bus Pirate 6's supply as last read, or None for other boards."""
        status = getattr(self.bp, "last_status", None)
        if status is None or isinstance(self.stream, TerminalState):
            return None
        return {"on": status.psu_enabled, "set_mv": self.bp.psu_mv, "set_ma": self.bp.psu_ma,
                "mv": status.psu_mv, "ma": status.psu_ma, "tripped": status.psu_tripped,
                "pullups": status.pullups}

    POWER_REFRESH_SECONDS = 0.8

    def wants_power_refresh(self) -> bool:
        return (
            self.bp is not None and self.bp.is_open and self.stream is None
            and getattr(self.bp, "last_status", None) is not None
            and time.monotonic() - self._power_read_at >= self.POWER_REFRESH_SECONDS
        )

    def refresh_power_blocking(self) -> None:
        """Re-read a Bus Pirate 6's supply for the status bar, at most ~1/s."""
        if not self.wants_power_refresh():
            return
        self._power_read_at = time.monotonic()
        try:
            self.bp.status(quiet=True)
        except (BusPirateError, OSError):
            pass  # the next poll tries again; a dead port shows as USB detached

    def leds(self) -> Dict[str, Optional[bool]]:
        """What the indicator LEDs should be showing, for the shown variant.

        Inferred, never read: no command reports LED state. See LED_NOTES.
        ``None`` means unknown: while the board's own terminal is open, its
        commands drive MODE and VREG (``W`` switches the supplies, the ``~``
        self-test lights both), and this session sees none of it.
        """
        live = self.bp is not None and self.bp.is_open
        in_terminal = isinstance(self.stream, TerminalState)
        rules = LED_RULES[self.effective_variant()]
        state: Dict[str, Optional[bool]] = {}
        for name, rule in rules.items():
            how = rule["inference"]
            if live and in_terminal and how in ("supplies", "connected"):
                state[name] = None
            elif how == "supplies":
                state[name] = live and self._supplies_on()
            elif how == "connected":
                state[name] = live
            elif how == "powered":
                state[name] = live
            else:  # flash_on_traffic, always_dark
                state[name] = False
        return state

    def detected_variant(self) -> Optional[str]:
        """What the banner said, or None if nothing is connected."""
        if self.bp is None or not self.bp.is_open:
            return None
        variant = self.bp.profile.variant
        return variant if variant in BOARDS else None

    def effective_variant(self) -> str:
        """The variant the UI should present: override, else detected, else v3."""
        if self.display_variant is not None:
            return self.display_variant
        return self.detected_variant() or DEFAULT_VARIANT

    def variant_source(self) -> str:
        """Why effective_variant() is what it is: override, detected or default."""
        if self.display_variant is not None:
            return "override"
        if self.detected_variant() is not None:
            return "detected"
        return "default"

    def status(self) -> Dict[str, Any]:
        if self.bp is None or not self.bp.is_open:
            return {
                "connected": False,
                "simulated": self.simulated,
                "usb": {"attached": False},
                "stream": None,
                "leds": self.leds(),
            }
        profile = self.bp.profile
        return {
            "connected": True,
            "leds": self.leds(),
            "simulated": self.simulated,
            "port": self.port,
            "usb": self.usb_status(),
            "mode": self.mode_name,
            "stream": self.stream.describe() if self.stream else None,
            # None while the board's own terminal is open: its commands can
            # switch the supplies out of this session's sight.
            "supplies": None if isinstance(self.stream, TerminalState) else self._supplies_on(),
            "pullups": self._pullups_on(),
            "power": self._power(),
            # Empty means in HiZ: the sidebar button reads HiZ, else Live.
            "live": self.live(),
            "variant": profile.variant,
            "firmware": profile.firmware,
            "bootloader": profile.bootloader,
            "devid": profile.devid,
            "description": profile.describe(),
            "capabilities": sorted(profile.capabilities),
            "banner": profile.banner,
        }

    def ports(self) -> List[Dict[str, Any]]:
        # A demo launch offers its own variant first; a hardware launch lists
        # the simulators after the real ports and never marks them likely.
        variants = sorted(
            SIMULATED_VARIANTS,
            key=lambda v: (not (self.use_fake and v == self.fake_variant), v),
        )
        simulators = [
            {
                "device": SIMULATED_PREFIX + variant,
                "note": f"{SIMULATED_NAMES[variant]}, no hardware",
                "likely": self.use_fake and variant == self.fake_variant,
                "usb_id": None,
                "simulated": True,
            }
            for variant in variants
        ]
        if self.use_fake:
            return simulators
        return [
            {
                "device": c.device,
                "note": c.note,
                "likely": c.likely_bus_pirate,
                "usb_id": c.usb_id,
                "description": c.description,
                "simulated": False,
            }
            for c in discover(include_unlikely=True)
        ] + simulators

    # -- modes -------------------------------------------------------------

    def ensure_mode(self, mode_name: Optional[str]):
        """Put the device in ``mode_name``, leaving whatever it was in."""
        if self.bp is None:
            if mode_name is None:
                return None  # the connection panel works without a device
            raise BusPirateError("not connected — pick a port and connect first")
        if self.mode_name == mode_name:
            return self._mode
        if self._mode is not None:
            try:
                self._mode.close()
            except (BusPirateError, OSError):
                self.bp.resync()
            self._mode = None
            self.mode_name = None
        if mode_name is None:
            return None
        enter = getattr(self.bp, mode_name, None)
        if enter is None:
            raise ModeError(f"this build has no {mode_name!r} mode")
        self._mode = enter()
        self.mode_name = mode_name
        return self._mode

    # -- running actions ---------------------------------------------------

    def find(self, panel_id: str, action_name: str):
        for panel in self.panels:
            if panel.id == panel_id:
                return panel, panel.action(action_name)
        raise KeyError(f"no panel {panel_id!r}")

    def available_capabilities(self) -> Optional[List[str]]:
        if self.bp is None:
            return None
        return sorted(self.bp.profile.capabilities)

    def run_blocking(self, panel: Panel, action: Action, params: Dict[str, Any]):
        if self.stream is not None and not action.allow_while_streaming:
            raise BusPirateError(
                f"{self.stream.kind} is running and has the port. Stop it first."
            )
        if self.bp is not None:
            for required in (panel.requires, action.requires):
                if required:
                    self.bp.profile.require(required)
        mode = self.ensure_mode(panel.mode)
        context = ActionContext(self, mode)
        result = action.handler(context, **params)
        if action.stream:
            self._begin_stream(panel, action, result)
        return result

    # -- streaming ---------------------------------------------------------

    def _begin_stream(self, panel: Panel, action: Action, result: Dict[str, Any]) -> None:
        """Hand the port to a reader thread until someone stops it."""
        decoder = make_decoder(result.get("decoder", "text"))
        if result.get("input"):
            stream = TerminalState(decoder, result)
        else:
            stream = StreamState(
                kind=result.get("kind", action.name),
                panel_id=panel.id,
                action=action.name,
                decoder=decoder,
                result=result,
            )
        result["legend"] = stream.decoder.legend
        self.stream = stream
        stream.thread = threading.Thread(
            target=self._read_stream, args=(stream,), daemon=True
        )
        try:
            stream.thread.start()
        except BaseException:
            # No reader exists, so nothing will ever clear self.stream.
            self.stream = None
            if isinstance(stream, TerminalState):
                # 0x0F has already gone out: the board is in its own
                # terminal and this session cannot speak to it.
                self._drop_connection()
            raise
        self.emit({"type": "stream_started", **stream.describe()})

    def _read_stream(self, stream: StreamState) -> None:
        """The only thing touching the port while a stream runs.

        Events are batched before they go out: a busy bus can produce them far
        faster than a browser can draw them, and a message per read would
        bury the UI. Ten updates a second is plenty to watch by.
        """
        device = self.bp
        pending: List[Dict[str, Any]] = []
        last_flush = time.monotonic()

        def flush() -> None:
            nonlocal pending, last_flush
            if not pending:
                return
            self.emit(
                {
                    "type": "stream",
                    "kind": stream.kind,
                    "events": pending[-STREAM_EVENT_CAP:],
                    "dropped": max(0, len(pending) - STREAM_EVENT_CAP),
                    "total": stream.events,
                }
            )
            pending = []
            last_flush = time.monotonic()

        # Everything below runs under try/finally: whatever ends this loop —
        # a stop request, a dead port, a decoder or _notify raising — the
        # stream has to be finished exactly once. self.stream is only ever
        # cleared in _finish_stream, so an escaping exception here would
        # leave it set for the life of the process and every later action
        # would be refused with "…has the port".
        try:
            while not stream.stop_event.is_set() and device is not None:
                if isinstance(stream, TerminalState) and not self._drain_inbox(
                    stream, device
                ):
                    break
                try:
                    data = device.serial.read(256)
                except (OSError, AttributeError):
                    break
                if not data:
                    flush()
                    time.sleep(0.01)
                    continue
                device._notify("rx", data)
                events = stream.decoder.feed(data)
                if events:
                    stream.events += len(events)
                    pending.extend(events)
                if time.monotonic() - last_flush >= STREAM_FLUSH_SECONDS:
                    flush()
        finally:
            try:
                flush()
            finally:
                self._finish_stream(stream)

    def _drain_inbox(self, stream: "TerminalState", device) -> bool:
        """Write everything the user has typed. False means the port is gone.

        ``BusPirate.write`` raises ConnectionError when the handle has gone
        away and lets serial.SerialException through, so an unguarded write
        here would escape the reader loop entirely. Returning False instead
        ends the stream through the normal path.
        """
        while True:
            try:
                line = stream.inbox.get_nowait()
            except queue.Empty:
                return True
            try:
                device.write(line)
            except (OSError, AttributeError, BusPirateError):
                return False

    def _drop_connection(self) -> None:
        """Forget the device without claiming anything about the board.

        Used whenever the board has been sent out of binary mode and this
        session cannot prove it came back. Reporting "connected" then would
        let the dashboard go on presenting a working binary-mode session that
        does not exist, and every action after it would fail confusingly.
        Dropping the connection outright makes the connection panel the one
        honest way back.
        """
        if self.bp is not None:
            try:
                self.bp.close()
            except BusPirateError:
                pass
        self.bp = None
        self.port = None
        self.port_info = None
        self._bpio2_traffic = False
        self.display_variant = None
        self.mode_name = None
        self._mode = None
        # Whatever we drove the pins to is no longer true of the board.
        self.last_pins = dict.fromkeys(self.last_pins, False)

    def _finish_stream(self, stream: StreamState) -> None:
        if stream.finished:
            return
        stream.finished = True
        note = ""
        try:
            if self.bp is not None:
                self.bp.stop_stream()
        except (BusPirateError, OSError) as exc:
            note = str(exc)
        self.mode_name = None
        self._mode = None
        if isinstance(stream, TerminalState):
            # The board was reset on the way in — a v3 and a v4 alike — so
            # the supplies this session last drove are no longer true of it.
            # Leaving last_pins stale would light VREG over a dark board, the
            # same reasoning disconnect_blocking() already applies.
            self.last_pins = dict.fromkeys(self.last_pins, False)
        self.stream = None
        if note and self.bp is not None:
            # stop_stream() could not knock the board back into binary mode,
            # so the session no longer knows what state the board is in
            # (still sitting in its own terminal, most likely).
            self._drop_connection()
        # Stash the failure reason on the (already-finished) stream object so
        # stop_stream_blocking() — running on a different thread, after
        # join() — can hand it back to the caller. Without this the note
        # only ever reached the websocket "stream_stopped" event: real for a
        # browser watching at that exact moment, invisible to anything that
        # only reads the HTTP response or polls state after the fact.
        stream.note = note
        self.emit({"type": "stream_stopped", **stream.describe(), "note": note})

    def stop_stream_blocking(self) -> Dict[str, Any]:
        stream = self.stream
        if stream is None:
            return {"stopped": False, "reason": "nothing is streaming"}
        stream.stop_event.set()
        thread = stream.thread
        if thread is not None:
            thread.join(timeout=STREAM_STOP_TIMEOUT_SECONDS)
            if thread.is_alive():
                # Do not claim stopped: the reader thread is still inside
                # stop_stream() and still owns the port. Callers use this
                # answer to decide whether it is safe to close the handle.
                return {
                    "stopped": False,
                    "reason": (
                        f"{stream.kind} has not let go of the port after "
                        f"{STREAM_STOP_TIMEOUT_SECONDS:g}s — it is still "
                        "returning the board to binary mode. Nothing else "
                        "may touch the port until it finishes; try again "
                        "in a moment."
                    ),
                    **stream.describe(),
                    "note": stream.note,
                }
        return {
            "stopped": True,
            **stream.describe(),
            "note": stream.note,
        }

    def enter_terminal(self) -> Dict[str, Any]:
        """Leave binary mode and hold the board's own terminal open."""
        if self.bp is None or not self.bp.is_open:
            raise BusPirateError("not connected — pick a port and connect first")
        # Once 0x0F is on the wire the board is in its own terminal whatever
        # happens next, so any failure from here has to tear the connection
        # down the same way a failed return does — otherwise the session
        # reports a live binary-mode connection over a board that is not
        # listening to one. reset_hardware() is inside the guard because it
        # writes 0x0F and then flushes: it can raise with the command
        # already sent.
        try:
            # On a Bus Pirate: reset, and follow a v4 off USB and back. The
            # settle doubles as the v3's boot time; on a board that stays on
            # USB it simply runs out the window. A Bit Pirate has nothing to
            # leave, and is only nudged to show a fresh prompt.
            self.bp.release_to_terminal(TERMINAL_SETTLE_SECONDS)
        except BusPirateError:
            self._drop_connection()
            raise
        except Exception as exc:  # noqa: BLE001 - re-raised as a board error
            self._drop_connection()
            raise BusPirateError(
                "the board was sent out of binary mode but its terminal "
                f"could not be opened: {exc}"
            ) from exc
        variant = self.bp.profile.variant
        if variant == "bitpirate":
            caption = "The Bit Pirate's own command line. Type a command; 'help' lists them."
        elif variant == "bp6":
            caption = ("The Bus Pirate 6's own terminal. Type a command; '?' lists them. "
                       "If it asks 'VT100 compatible color mode?', answer n.")
        else:
            caption = "The Bus Pirate's own terminal. Type a command; '?' lists them."
        return live("Board terminal", decoder="console", caption=caption, input=True)

    def send_terminal_keys(self, keys: str) -> None:
        """Queue keys for the board exactly as typed, the way `screen` does.

        Nothing is appended. The firmware reads raw keys and several of its
        prompts want exactly one ("Space to continue", "Any key to exit"), so
        a line with Enter added answered them before anyone had read them —
        found on a real v3, running the ``~`` self-test.
        """
        stream = self.stream
        if not isinstance(stream, TerminalState):
            raise BusPirateError("the board's terminal is not open")
        stream.inbox.put(keys.encode("ascii", errors="replace"))

    async def run(self, panel: Panel, action: Action, params: Dict[str, Any]):
        async with self.lock:
            return await asyncio.get_running_loop().run_in_executor(
                None, self.run_blocking, panel, action, params
            )

    async def call(self, fn, *args):
        async with self.lock:
            return await asyncio.get_running_loop().run_in_executor(None, fn, *args)
