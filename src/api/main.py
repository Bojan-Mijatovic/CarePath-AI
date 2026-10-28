"""CarePath API: REST endpoints and the /api/stream WebSocket the console listens to.

Until the real tick (engine.tick, step 2.1) the API runs in fixture mode (step 1.25): the SPEC §10
endpoints the first screens need answer from testing/fixtures/, and the stream replays them one day per
tick. Without fixtures it falls back to the phase 0 counter. The message envelope is the one of
spec/SPEC.md §10, so the console does not change when the tick arrives.
"""

import asyncio
from pathlib import Path
from typing import Any, Literal

import uvicorn
from fastapi import APIRouter, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from api.fixtures import FIXTURES_DIR, Fixtures

UI_DIST = Path(__file__).resolve().parents[1] / "ui" / "dist"
DEFAULT_RUN = "s2_agents"  # SPEC §10: the scenario on screen, agents arm


class StreamMessage(BaseModel):
    """Envelope for every message on /api/stream."""

    type: Literal["tick", "alert", "action", "investigation"]
    scenario: int
    day: int
    payload: dict[str, Any] = {}


def create_app(tick_seconds: float = 2.0, scenario: int = 1, ui_dir: Path | None = UI_DIST,
               fixtures_dir: Path | None = FIXTURES_DIR) -> FastAPI:
    app = FastAPI(title="CarePath AI")
    api = APIRouter(prefix="/api")
    fixtures = Fixtures(fixtures_dir) if fixtures_dir is not None and fixtures_dir.is_dir() else None
    app.state.scenario = scenario

    @api.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @api.websocket("/stream")
    async def stream(ws: WebSocket) -> None:
        await ws.accept()
        try:
            if fixtures is not None:
                messages = fixtures.stream()
                for day in sorted({m["day"] for m in messages}):
                    for m in messages:
                        if m["day"] == day:
                            await ws.send_json(StreamMessage.model_validate(m).model_dump())
                    await asyncio.sleep(tick_seconds)
                await ws.receive_text()  # the replay is over; keep the connection until the console leaves
            else:
                day = 0
                while True:
                    msg = StreamMessage(type="tick", scenario=app.state.scenario, day=day)
                    await ws.send_json(msg.model_dump())
                    day += 1
                    await asyncio.sleep(tick_seconds)
        except WebSocketDisconnect:
            pass

    def need_fixtures() -> Fixtures:
        if fixtures is None:
            raise HTTPException(503, "no data source yet: the tick comes in step 2.1")
        return fixtures

    @api.post("/sim/scenario/{n}")
    def choose_scenario(n: int) -> dict[str, int]:
        if n not in (1, 2, 3):
            raise HTTPException(422, "scenario is 1, 2 or 3")
        app.state.scenario = n
        return {"scenario": n}

    @api.get("/kpi")
    def kpi(run: str = DEFAULT_RUN, pathway_id: str | None = None, level: str | None = None,
            key: str | None = None) -> list[dict]:
        return need_fixtures().kpi(run, pathway_id, level, key)

    @api.get("/patients/{patient_id}")
    def patient(patient_id: str, run: str = DEFAULT_RUN) -> dict:
        found = need_fixtures().patient(patient_id, run)
        if found is None:
            raise HTTPException(404, f"no patient {patient_id} in {run}")
        return found

    @api.get("/actions")
    def actions(run: str = DEFAULT_RUN, status: str | None = None) -> list[dict]:
        return need_fixtures().actions(run, status)

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
