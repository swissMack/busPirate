"""The one device the dashboard talks to, and the plumbing around it.

A serial port tolerates exactly one caller, and the driver is blocking. So
there is a single session object holding the port, an asyncio lock around
every use of it, and a thread executor to keep the event loop free. Handlers
are ordinary synchronous functions; they never see any of this.
"""

from __future__ import annotations

import asyncio
import os
import time
from collections import deque
from typing import Any, Dict, List, Optional, Set

from ..base import BusPirate
from ..exceptions import BusPirateError, ModeError
from ..ports import discover, resolve
from .registry import Action, Panel, load_panels

TRAFFIC_HISTORY = 500


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


class DeviceSession:
    """Owns the port, the current mode, and the live traffic log."""

    def __init__(self, use_fake: bool = False, fake_variant: str = "v3") -> None:
        self.use_fake = use_fake
        self.fake_variant = fake_variant
        self.bp: Optional[BusPirate] = None
        self.port: Optional[str] = None
        self.mode_name: Optional[str] = None
        self._mode = None
        self.lock = asyncio.Lock()
        self.traffic: deque = deque(maxlen=TRAFFIC_HISTORY)
        self.subscribers: Set[asyncio.Queue] = set()
        self.panels: List[Panel] = load_panels()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._seq = 0
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
        device = self._make_device(resolved)
        device.open()
        self.bp = device
        self.port = resolved
        self.mode_name = None
        self._mode = None
        return self.status()

    def disconnect_blocking(self) -> None:
        if self.bp is not None:
            try:
                self.bp.close()
            except BusPirateError:
                pass
        self.bp = None
        self.port = None
        self.mode_name = None
        self._mode = None

    def status(self) -> Dict[str, Any]:
        if self.bp is None or not self.bp.is_open:
            return {"connected": False, "simulated": self.use_fake}
        profile = self.bp.profile
        return {
            "connected": True,
            "simulated": self.use_fake,
            "port": self.port,
            "mode": self.mode_name,
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
        if action.requires and self.bp is not None:
            self.bp.profile.require(action.requires)
        mode = self.ensure_mode(panel.mode)
        context = ActionContext(self, mode)
        return action.handler(context, **params)

    async def run(self, panel: Panel, action: Action, params: Dict[str, Any]):
        async with self.lock:
            return await asyncio.get_running_loop().run_in_executor(
                None, self.run_blocking, panel, action, params
            )

    async def call(self, fn, *args):
        async with self.lock:
            return await asyncio.get_running_loop().run_in_executor(None, fn, *args)
