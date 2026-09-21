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

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from ..exceptions import BusPirateError
from . import docs as docs_module
from .params import ParamError, coerce_all
from .session import DeviceSession
from .wiring import (
    BOARD_CAVEAT,
    BOARD_V3,
    CABLE_CARD,
    CABLE_CAVEAT,
    LED_NOTE,
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
        panels = []
        for panel in session.panels:
            data = panel.to_json()
            if capabilities is not None:
                data["actions"] = [
                    action
                    for action in data["actions"]
                    if not action["requires"] or action["requires"] in capabilities
                ]
            panels.append(data)
        return panels

    @app.get("/api/state")
    async def state() -> Dict[str, Any]:
        return {
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
            "board": BOARD_V3,
            "board_caveat": BOARD_CAVEAT,
            "led_note": LED_NOTE,
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
        try:
            while True:
                event = await queue.get()
                await socket.send_json(event)
        except (WebSocketDisconnect, RuntimeError, asyncio.CancelledError):
            pass
        finally:
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
        raise ValueError(
            f"refusing to serve on {host}: the dashboard drives hardware and "
            "has no authentication, so it binds the loopback address only"
        )

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
