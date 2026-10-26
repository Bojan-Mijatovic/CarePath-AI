"""CarePath API: REST endpoints and the /api/stream WebSocket the console listens to.

Phase 0 skeleton: /api/health, a fake simulation tick on /api/stream, and the built console.
The real tick comes from engine.tick in Phase 2; the message envelope is already the one
from spec/SPEC.md §10, so the console does not change when it arrives.
"""

import asyncio
from pathlib import Path
from typing import Any, Literal

import uvicorn
from fastapi import APIRouter, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

UI_DIST = Path(__file__).resolve().parents[1] / "ui" / "dist"


class StreamMessage(BaseModel):
    """Envelope for every message on /api/stream."""

    type: Literal["tick", "alert", "action", "investigation"]
    scenario: int
    day: int
    payload: dict[str, Any] = {}


def create_app(tick_seconds: float = 2.0, scenario: int = 1, ui_dir: Path | None = UI_DIST) -> FastAPI:
    app = FastAPI(title="CarePath AI")
    api = APIRouter(prefix="/api")

    @api.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @api.websocket("/stream")
    async def stream(ws: WebSocket) -> None:
        await ws.accept()
        day = 0
        try:
            while True:
                msg = StreamMessage(type="tick", scenario=scenario, day=day)
                await ws.send_json(msg.model_dump())
                day += 1
                await asyncio.sleep(tick_seconds)
        except WebSocketDisconnect:
            pass

    app.include_router(api)

    # The built console (npm run build in src/ui). Mounted last so /api wins.
    # In development the console runs on Vite and this mount is not used.
    if ui_dir is not None and ui_dir.is_dir():
        app.mount("/", StaticFiles(directory=ui_dir, html=True), name="ui")
    return app


app = create_app()


def run() -> None:
    uvicorn.run("api.main:app", host="127.0.0.1", port=8000)


if __name__ == "__main__":
    run()
