"""
SC_LogReader DevKit - Web Server

FastAPI server with SSE endpoint for real-time debug dashboard.

Author: Mallachi
"""

import asyncio
import json
import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse

from bridge import DebugBridge


logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


def create_app(bridge: DebugBridge) -> FastAPI:
    """Create the FastAPI application."""
    app = FastAPI(title="SC_LogReader DevKit")

    @app.get("/", response_class=HTMLResponse)
    async def index() -> HTMLResponse:
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        return HTMLResponse(content=html)

    @app.get("/static/{filename:path}")
    async def static_file(filename: str) -> HTMLResponse:
        file_path = STATIC_DIR / filename
        if not file_path.is_file():
            return HTMLResponse(content="Not found", status_code=404)

        content = file_path.read_text(encoding="utf-8")
        media_type = "text/css" if filename.endswith(".css") else "application/javascript"
        return HTMLResponse(content=content, media_type=media_type)

    @app.get("/api/states")
    async def get_states() -> dict:
        """Get current state snapshot for initial load."""
        return {"states": bridge.get_current_states()}

    @app.get("/api/events")
    async def event_stream(request: Request) -> StreamingResponse:
        """SSE endpoint — streams debug events to the browser."""
        queue = bridge.subscribe()

        async def generate():
            try:
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        packet = await asyncio.wait_for(queue.get(), timeout=1.0)
                        yield f"data: {json.dumps(packet)}\n\n"
                    except asyncio.TimeoutError:
                        # Send keepalive comment to prevent connection timeout
                        yield ": keepalive\n\n"
            finally:
                bridge.unsubscribe(queue)

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    return app
