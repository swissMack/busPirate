"""The dashboard's HTTP and websocket API.

Everything the browser can do goes through two endpoints: ``/api/state``
describes the device and the panels, and ``/api/run`` executes one declared
action. The frontend has no knowledge of any particular protocol — it renders
whatever the registry describes.
"""

from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import os
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .. import __version__
from ..exceptions import BusPirateError
from . import docs as docs_module
from .params import ParamError, coerce_all
from .session import DeviceSession
from .wiring import (
    BOARDS,
    CABLE_CARD,
    CABLE_CAVEAT,
    LED_NOTES,
    LED_RULES,
    REFCARD,
    SEEED_CABLE,
    SIGNAL_NOTES,
    SIGNAL_ROLES,
)

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


def create_app(
    use_fake: Optional[bool] = None, fake_variant: str = "v3"
) -> FastAPI:
    """Build the application. ``BUSPIRATE_FAKE=1`` simulates a device."""
    if use_fake is None:
        use_fake = os.environ.get("BUSPIRATE_FAKE", "") not in ("", "0", "false")
    fake_variant = os.environ.get("BUSPIRATE_FAKE_VARIANT", fake_variant)

    session = DeviceSession(use_fake=use_fake, fake_variant=fake_variant)

    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI):
        session.bind_loop()
        try:
            yield
        finally:
            # A reader thread that has not let go of the port makes
            # disconnect refuse rather than close the handle under it. The
            # process is going away regardless, so note it and move on.
            with contextlib.suppress(BusPirateError):
                session.disconnect_blocking()

    app = FastAPI(
        title="Bus Pirate dashboard",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.session = session

    # -- state ------------------------------------------------------------

    def _panels_json() -> list:
        capabilities = session.available_capabilities()

        def offered(item: dict) -> bool:
            required = item.get("requires")
            return capabilities is None or not required or required in capabilities

        # A board that is not a Bus Pirate (the ESP32 Bit Pirate) has its own
        # pins and caveats; it replaces a panel's wiring, notes and wording
        # rather than the panel modules learning about every board.
        overrides = BOARDS[session.effective_variant()].get("panels", {})
        panels = []
        for panel in session.panels:
            data = panel.to_json()
            if not offered(data):
                continue
            data["actions"] = [a for a in data["actions"] if offered(a)]
            for action in data["actions"]:
                action["params"] = [p for p in action["params"] if offered(p)]
            override = overrides.get(panel.id, {})
            for key in ("blurb", "wiring", "notes"):
                if key in override:
                    data[key] = override[key]
            for action in data["actions"]:
                action.update(override.get("actions", {}).get(action["name"], {}))
            panels.append(data)
        return panels

    @app.get("/api/state")
    async def state() -> Dict[str, Any]:
        variant = session.effective_variant()
        board = BOARDS[variant]
        # Signals the probe cable already carries a note for elsewhere (the
        # cable legend); board pins outside that set — currently only the v4's
        # AUX1/AUX2 — have nowhere else to surface SIGNAL_NOTES, so pipe those
        # through here instead. Keeps the v3 response unchanged, since every
        # v3 pin is one of the ten cable signals.
        cable_signals = {signal for signal, _, _ in SEEED_CABLE}
        board_pin_notes = {
            signal: SIGNAL_NOTES[signal]
            for signal in board["pins"]
            if signal in SIGNAL_NOTES and signal not in cable_signals
        }
        return {
            "version": __version__,
            "status": session.status(),
            "panels": _panels_json(),
            "traffic": list(session.traffic),
            "cable": [
                {
                    "pin": index,
                    "signal": signal,
                    "colour": hexcode,
                    "colour_name": name,
                    "roles": SIGNAL_ROLES.get(signal, {}),
                    "note": SIGNAL_NOTES.get(signal, ""),
                }
                for index, (signal, hexcode, name) in enumerate(SEEED_CABLE, start=1)
            ],
            "cable_caveat": CABLE_CAVEAT,
            "refcard": REFCARD,
            "cable_card": CABLE_CARD,
            "board": board,
            "board_caveat": board["caveat"],
            "board_pin_notes": board_pin_notes,
            "variant": variant,
            "variant_detected": session.detected_variant(),
            "variant_source": session.variant_source(),
            # Declared order, so the picker reads v3, v4, then the Bit Pirate.
            "variants": list(BOARDS),
            "led_note": LED_NOTES[variant],
            "led_rules": LED_RULES[variant],
        }

    @app.get("/api/ports")
    async def ports() -> Dict[str, Any]:
        return {"ports": await session.call(session.ports)}

    @app.post("/api/stream/stop")
    async def stop_stream() -> JSONResponse:
        result = await asyncio.get_running_loop().run_in_executor(
            None, session.stop_stream_blocking
        )
        return JSONResponse(
            {"ok": True, "result": result, "status": session.status(),
             "panels": _panels_json()}
        )

    @app.get("/api/docs")
    async def doc_index() -> Dict[str, Any]:
        return {"pages": docs_module.available()}

    @app.get("/api/docs/{name}")
    async def doc_page(name: str) -> JSONResponse:
        text = docs_module.read(name)
        if text is None:
            return _error(f"no guide page called {name!r}", status=404)
        return JSONResponse({"ok": True, "name": name, "markdown": text})

    @app.post("/api/run")
    async def run(payload: Dict[str, Any]) -> JSONResponse:
        panel_id = payload.get("panel")
        action_name = payload.get("action")
        try:
            panel, action = session.find(panel_id, action_name)
        except KeyError as exc:
            return _error(str(exc), status=404)

        try:
            params = coerce_all(action.params, payload.get("params") or {})
        except ParamError as exc:
            return _error(str(exc))

        try:
            result = await session.run(panel, action, params)
        except ParamError as exc:
            return _error(str(exc))
        except BusPirateError as exc:
            return _error(str(exc))
        except (ValueError, KeyError) as exc:
            return _error(str(exc))
        except OSError as exc:
            return _error(f"the serial port went away: {exc}")

        return JSONResponse(
            {"ok": True, "result": result, "status": session.status(),
             "panels": _panels_json()}
        )

    # -- live feed --------------------------------------------------------

    @app.websocket("/ws")
    async def feed(socket: WebSocket) -> None:
        await socket.accept()
        queue = session.subscribe()

        async def pump() -> None:
            while True:
                event = await queue.get()
                await socket.send_json(event)

        async def watch() -> None:
            # The page never sends anything, so the only message is the
            # disconnect. Without reading it, a client that leaves during a
            # quiet spell goes unnoticed — the pump sits in queue.get() for
            # good, and uvicorn's graceful shutdown waits on it forever.
            while (await socket.receive())["type"] != "websocket.disconnect":
                pass

        tasks = [asyncio.create_task(pump()), asyncio.create_task(watch())]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in tasks:
                task.cancel()
            # Retrieve each outcome so a pump that died on a closed socket
            # (WebSocketDisconnect, RuntimeError) is not logged as an
            # unretrieved task exception.
            await asyncio.gather(*tasks, return_exceptions=True)
            session.unsubscribe(queue)

    # -- static -----------------------------------------------------------

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))

    @app.middleware("http")
    async def no_cache(request: Request, call_next):
        """The UI is edited in place while it runs; never serve it stale."""
        response = await call_next(request)
        if request.url.path.startswith("/static") or request.url.path == "/":
            response.headers["Cache-Control"] = "no-store, must-revalidate"
        return response

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


def loopback_refusal(host: str) -> str:
    """The one wording of the loopback rule.

    Shared with ``web.window`` so the two guards cannot drift. The callers
    raise different exception types on purpose, so only the words live here.
    """
    return (
        f"refusing to serve on {host}: the dashboard drives hardware and "
        "has no authentication, so it binds the loopback address only"
    )


def _error(message: str, status: int = 400) -> JSONResponse:
    return JSONResponse({"ok": False, "error": message}, status_code=status)


def serve(
    host: str = "127.0.0.1",
    port: int = 8765,
    use_fake: Optional[bool] = None,
    fake_variant: str = "v3",
    open_browser: bool = False,
) -> None:
    """Run the dashboard. Refuses to listen anywhere but the loopback address."""
    import uvicorn

    if not ipaddress.ip_address(host).is_loopback:
        raise ValueError(loopback_refusal(host))

    if open_browser:
        import threading
        import webbrowser

        threading.Timer(1.0, lambda: webbrowser.open(f"http://{host}:{port}/")).start()

    uvicorn.run(
        create_app(use_fake=use_fake, fake_variant=fake_variant),
        host=host,
        port=port,
        log_level="warning",
    )
