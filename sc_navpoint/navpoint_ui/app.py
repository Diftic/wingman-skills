"""
navpoint_ui/app.py — NavPoint HUD FastAPI server
Author: Mallachi
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

if TYPE_CHECKING:
    from database import NavPoint, NavPointDatabase


logger = logging.getLogger(__name__)
_STATIC_DIR = Path(__file__).parent / "static"


class NavPointServer:
    """FastAPI server for the NavPoint HUD."""

    def __init__(self, db: "NavPointDatabase", port: int = 7869) -> None:
        self._db = db
        self._port = port
        self._thread: threading.Thread | None = None
        self._server: uvicorn.Server | None = None
        self._active_target: "NavPoint | None" = None
        self._current_position: dict | None = None
        self._update_token: int = 0
        self._app = self._create_app()

    # ------------------------------------------------------------------ #
    # State updates (called from main skill)
    # ------------------------------------------------------------------ #

    def set_active_target(self, navpoint: "NavPoint | None") -> None:
        self._active_target = navpoint
        self._update_token += 1

    def set_position(self, pos_data: dict) -> None:
        self._current_position = pos_data
        self._update_token += 1

    def notify_update(self) -> None:
        self._update_token += 1

    # ------------------------------------------------------------------ #
    # App
    # ------------------------------------------------------------------ #

    def _create_app(self) -> FastAPI:
        app = FastAPI(title="SC NavPoint HUD", docs_url=None, redoc_url=None)

        # Static files
        @app.get("/", response_class=HTMLResponse)
        async def index():
            return _STATIC_DIR.joinpath("index.html").read_text(encoding="utf-8")

        @app.get("/static/{filename:path}")
        async def static_file(filename: str):
            fp = _STATIC_DIR / filename
            if not fp.exists():
                return JSONResponse({"error": "Not found"}, status_code=404)
            content = fp.read_text(encoding="utf-8")
            media = "text/css" if filename.endswith(".css") else (
                "application/javascript" if filename.endswith(".js") else "text/plain"
            )
            return HTMLResponse(content=content, media_type=media,
                                headers={"Cache-Control": "no-cache"})

        # API: Waypoints
        @app.get("/api/navpoints")
        async def get_navpoints(server_id: str = ""):
            navpoints = self._db.get_navpoints(server_id=server_id or None)
            return {
                "navpoints": [self._db.navpoint_to_dict(n) for n in navpoints],
                "servers": self._db.get_distinct_servers(),
            }

        @app.delete("/api/navpoints/{navpoint_id}")
        async def delete_navpoint(navpoint_id: int):
            self._db.delete_navpoint(navpoint_id)
            if self._active_target and self._active_target.id == navpoint_id:
                self._active_target = None
            self._update_token += 1
            return {"success": True}

        @app.put("/api/navpoints/{navpoint_id}/name")
        async def rename_navpoint(navpoint_id: int, body: dict):
            new_name = body.get("name", "")
            if new_name:
                self._db.rename_navpoint(navpoint_id, new_name)
                self._update_token += 1
            return {"success": bool(new_name)}

        @app.put("/api/navpoints/{navpoint_id}/notes")
        async def update_notes(navpoint_id: int, body: dict):
            notes = body.get("notes", "")
            self._db.update_notes(navpoint_id, notes)
            self._update_token += 1
            return {"success": True}

        # API: Navigation
        @app.get("/api/nav/state")
        async def get_nav_state():
            """Poll endpoint — returns full navigation state and an update token."""
            target = None
            if self._active_target:
                target = self._db.navpoint_to_dict(self._active_target)
            return {
                "active_target": target,
                "current_position": self._current_position,
                "update_token": self._update_token,
            }

        @app.post("/api/nav/target/{navpoint_id}")
        async def set_nav_target(navpoint_id: int):
            """Set active navigation target by ID."""
            navpoint = self._db.find_navpoint_by_id(navpoint_id)
            if not navpoint:
                return JSONResponse({"error": "Not found"}, status_code=404)
            self._active_target = navpoint
            self._update_token += 1
            return {"success": True, "target": self._db.navpoint_to_dict(navpoint)}

        @app.delete("/api/nav/target")
        async def clear_nav_target():
            self._active_target = None
            self._update_token += 1
            return {"success": True}

        return app

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        config = uvicorn.Config(
            self._app,
            host="0.0.0.0",
            port=self._port,
            log_level="warning",
        )
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(
            target=self._server.run,
            name="sc-navpoint-ui",
            daemon=True,
        )
        self._thread.start()
        logger.info("NavPoint HUD started on port %d", self._port)

    def stop(self) -> None:
        if self._server:
            self._server.should_exit = True
            self._server = None
        self._thread = None
        logger.info("NavPoint HUD stopped")

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._port}"

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()
