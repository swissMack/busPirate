"""The one device the dashboard talks to, and the plumbing around it.

A serial port tolerates exactly one caller, and the driver is blocking. So
there is a single session object holding the port, an asyncio lock around
every use of it, and a thread executor to keep the event loop free. Handlers
are ordinary synchronous functions; they never see any of this.
"""

from __future__ import annotations

import asyncio
import os
import threading
import time
from collections import deque
from typing import Any, Dict, List, Optional, Set

from ..base import BusPirate
from ..exceptions import BusPirateError, ModeError
from ..ports import discover, resolve
from .decoders import make_decoder
from .registry import Action, Panel, load_panels
from .wiring import BOARDS, DEFAULT_VARIANT

TRAFFIC_HISTORY = 500
STREAM_EVENT_CAP = 200  # events per websocket message
STREAM_FLUSH_SECONDS = 0.1  # at most ten updates a second, however busy the bus


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

    def describe(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "panel": self.panel_id,
            "action": self.action,
            "events": self.events,
            "seconds": round(time.time() - self.started_at, 1),
        }


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
        root = os.path.join(os.getcwd(), "captures")
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
        self.bp: Optional[BusPirate] = None
        self.port: Optional[str] = None
        #: What discovery knew about the port we connected to.
        self.port_info: Optional[Dict[str, Any]] = None
        self.mode_name: Optional[str] = None
        self._mode = None
        self.lock = asyncio.Lock()
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
        #: Manual override of the variant the UI presents. None = follow
        #: whatever the banner said.
        self.display_variant: Optional[str] = None

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
        self.traffic.append(entry)
        self.emit(entry)

    # -- connection --------------------------------------------------------

    def _make_device(self, port: str) -> BusPirate:
        if self.use_fake:
            from tests.fake_serial import FakeSerial, fake_factory

            fake = FakeSerial(variant=self.fake_variant)
            return BusPirate(
                port,
                serial_factory=fake_factory(fake),
                on_traffic=self._on_traffic,
                identify_timeout=0.05,
            )
        return BusPirate(port, on_traffic=self._on_traffic)

    def connect_blocking(self, port: Optional[str]) -> Dict[str, Any]:
        self.disconnect_blocking()
        resolved = "fake" if self.use_fake else resolve(port)
        self.port_info = self._describe_port(resolved)
        device = self._make_device(resolved)
        device.open()
        self.bp = device
        self.port = resolved
        self.mode_name = None
        self._mode = None
        return self.status()

    def disconnect_blocking(self) -> None:
        if self.stream is not None:
            self.stop_stream_blocking()
        if self.bp is not None:
            try:
                self.bp.close()
            except BusPirateError:
                pass
        self.bp = None
        self.port = None
        self.port_info = None
        self.mode_name = None
        self._mode = None
        # Whatever we drove the pins to is no longer true of the board, and
        # keeping it would light VREG on the next connect.
        self.last_pins = dict.fromkeys(self.last_pins, False)

    def _describe_port(self, device: str) -> Dict[str, Any]:
        """What USB discovery can tell us about one device path."""
        if self.use_fake:
            return {
                "device": device,
                "usb_id": None,
                "description": f"simulated Bus Pirate {self.fake_variant}",
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
        if self.use_fake:
            return dict(self.port_info or {}, attached=True, simulated=True)
        attached = any(
            candidate.device == self.port
            for candidate in discover(include_unlikely=True)
        )
        return dict(self.port_info or {"device": self.port}, attached=attached)

    def _supplies_on(self) -> bool:
        """Whether the last thing we told the board was 'supplies on'.

        A protocol mode switches them through ``configure_peripherals``; the
        pins panel goes round it with a bitbang ``set_pins``. Whichever spoke
        last is the one to believe, and entering a mode resets the board's
        peripheral bits, so an active mode wins.
        """
        if self._mode is not None:
            return bool(self._mode.peripherals.get("power"))
        return bool(self.last_pins.get("power"))

    def leds(self) -> Dict[str, bool]:
        """What the four indicator LEDs should be showing.

        Inferred, never read: the binary protocol has no command that reports
        LED state, so this is what the board ought to be doing given what we
        have asked of it. The firmware can disagree — see ``LED_NOTE``.
        """
        live = self.bp is not None and self.bp.is_open
        return {
            # LED1 is wired VCC -> R2 -> LED -> GND, so it is lit whenever the
            # board has power. An open port is the closest we can get.
            "PWR": live,
            # LED4 hangs off the FT232RL's RXLED# pin, which pulses on traffic
            # and is dark at idle — never a steady state we could report. The
            # dashboard flashes it from the traffic feed instead.
            "USB": False,
            # LED2 is GPIO RA1, and binBB() sets it as soon as binary mode is
            # entered — which is what connecting does. It is *not* gated on a
            # protocol mode: that logic lives in procMenu.c, the terminal UI
            # the dashboard never uses. The firmware clears it on an overrun,
            # which we cannot see.
            "MODE": live,
            # The on-board 3.3V and 5V supplies, switched together. Either a
            # protocol mode or the pins panel can have been the one to do it.
            "VREG": live and self._supplies_on(),
        }

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
                "simulated": self.use_fake,
                "usb": {"attached": False},
                "stream": None,
                "leds": self.leds(),
            }
        profile = self.bp.profile
        return {
            "connected": True,
            "leds": self.leds(),
            "simulated": self.use_fake,
            "port": self.port,
            "usb": self.usb_status(),
            "mode": self.mode_name,
            "stream": self.stream.describe() if self.stream else None,
            "variant": profile.variant,
            "firmware": profile.firmware,
            "bootloader": profile.bootloader,
            "devid": profile.devid,
            "description": profile.describe(),
            "capabilities": sorted(profile.capabilities),
            "banner": profile.banner,
        }

    def ports(self) -> List[Dict[str, Any]]:
        if self.use_fake:
            return [
                {
                    "device": "fake",
                    "note": f"simulated Bus Pirate {self.fake_variant}",
                    "likely": True,
                    "usb_id": None,
                }
            ]
        return [
            {
                "device": c.device,
                "note": c.note,
                "likely": c.likely_bus_pirate,
                "usb_id": c.usb_id,
                "description": c.description,
            }
            for c in discover(include_unlikely=True)
        ]

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
                self.bp.enter_binary_mode()
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
        if action.requires and self.bp is not None:
            self.bp.profile.require(action.requires)
        mode = self.ensure_mode(panel.mode)
        context = ActionContext(self, mode)
        result = action.handler(context, **params)
        if action.stream:
            self._begin_stream(panel, action, result)
        return result

    # -- streaming ---------------------------------------------------------

    def _begin_stream(self, panel: Panel, action: Action, result: Dict[str, Any]) -> None:
        """Hand the port to a reader thread until someone stops it."""
        stream = StreamState(
            kind=result.get("kind", action.name),
            panel_id=panel.id,
            action=action.name,
            decoder=make_decoder(result.get("decoder", "text")),
            result=result,
        )
        result["legend"] = stream.decoder.legend
        self.stream = stream
        stream.thread = threading.Thread(
            target=self._read_stream, args=(stream,), daemon=True
        )
        stream.thread.start()
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

        while not stream.stop_event.is_set() and device is not None:
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
        flush()
        self._finish_stream(stream)

    def _finish_stream(self, stream: StreamState) -> None:
        note = ""
        try:
            if self.bp is not None:
                self.bp.stop_stream()
        except (BusPirateError, OSError) as exc:
            note = str(exc)
        self.mode_name = None
        self._mode = None
        self.stream = None
        self.emit({"type": "stream_stopped", **stream.describe(), "note": note})

    def stop_stream_blocking(self) -> Dict[str, Any]:
        stream = self.stream
        if stream is None:
            return {"stopped": False, "reason": "nothing is streaming"}
        stream.stop_event.set()
        if stream.thread is not None:
            stream.thread.join(timeout=5)
        return {"stopped": True, **stream.describe()}

    async def run(self, panel: Panel, action: Action, params: Dict[str, Any]):
        async with self.lock:
            return await asyncio.get_running_loop().run_in_executor(
                None, self.run_blocking, panel, action, params
            )

    async def call(self, fn, *args):
        async with self.lock:
            return await asyncio.get_running_loop().run_in_executor(None, fn, *args)
