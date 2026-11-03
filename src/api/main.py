"""CarePath API: REST endpoints and the /api/stream WebSocket the console listens to (spec/SPEC.md §10).

The API runs the demo (engine.tick, step 2.1). At start-up it replays the six runs to day 23 in the
background, about 30–70 s, and the data endpoints answer 503 until then; while paused, the clock lets the
lever run catch up (step 2.28). A clock task advances the scenario
on screen at the chosen speed and pushes each day's messages to every connected console. Maria's story
(demo step 1) comes from the file recorded in demo/story/ (D35).
"""

import asyncio
import json
import logging
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

import uvicorn
from fastapi import APIRouter, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from agents import llm

from engine import pathway as pathway_model
from engine import queries, story, whatif
from engine.reports import MANIFEST  # the GET /reports endpoint below shadows a module named reports
from engine.tick import PATHWAY_ID, Demo

UI_DIST = Path(__file__).resolve().parents[1] / "ui" / "dist"
log = logging.getLogger("carepath.api")


class StreamMessage(BaseModel):
    """Envelope for every message on /api/stream."""

    type: Literal["tick", "alert", "action", "investigation", "report"]
    scenario: int
    day: int
    payload: dict[str, Any] = {}


class Speed(BaseModel):
    factor: int


class Ask(BaseModel):
    question: str = Field(min_length=3, max_length=500)


class Autonomy(BaseModel):
    type: str
    level: int


class Admission(BaseModel):
    """POST /admissions (C42). Without `diagnosis` and `facility_id`, the patient's ADMISSION of `day` in the run."""
    patient_id: str = Field(pattern=r"^[A-Za-z0-9_]{1,32}$")
    run: str | None = None
    day: int | None = None
    diagnosis: str | None = Field(None, pattern=r"^[0-9A-Z][0-9A-Z.]{1,9}$")
    facility_id: str | None = Field(None, pattern=r"^[A-Za-z0-9_]{1,32}$")
    choice: int = Field(0, ge=0)


class WhatIf(BaseModel):
    levers: whatif.Levers = whatif.Levers()
    months: int = whatif.MONTHS


class Cache(BaseModel):
    """The demo bar's switch (C37): cache_only, the demo's default (D14), or cache_first, which may ask a model
    for what the cache lacks; live, which asks again for everything, is for warm-ups only."""
    mode: Literal["cache_only", "cache_first"]


class Live:
    """The demo clock and the consoles it pushes to. `tick_seconds` is one simulated day at ×1 (SPEC §9)."""

    def __init__(self, demo: Demo, tick_seconds: float):
        self.demo, self.tick_seconds = demo, tick_seconds
        self.consoles: set[asyncio.Queue] = set()
        self.resume = asyncio.Event()

    def publish(self, messages: list[dict]) -> None:
        for m in messages:
            msg = StreamMessage.model_validate(m).model_dump()
            for q in self.consoles:
                q.put_nowait(msg)

    def need_ready(self) -> None:
        if not self.demo.ready:
            raise HTTPException(503, "the demo runs are being prepared (about 30–70 s after start-up)")

    def set_speed(self, factor: int) -> None:
        try:
            self.demo.set_speed(factor)
        except ValueError as e:
            raise HTTPException(422, str(e)) from None
        if factor:
            self.resume.set()

    async def status(self, messages: list[dict] | None = None) -> dict[str, int]:
        """Publishes `messages`, then returns what the console shows in its top bar."""
        self.publish(messages or [])
        return {"scenario": self.demo.scenario, "day": await asyncio.to_thread(lambda: self.demo.day),
                "speed": self.demo.speed}

    async def control(self, method, *args):
        """A Demo method that rebuilds or advances runs, off the event loop; a bad argument is a 422."""
        self.need_ready()
        try:
            return await asyncio.to_thread(method, *args)
        except ValueError as e:
            raise HTTPException(422, str(e)) from None

    def read(self, run: str | None, query):
        self.need_ready()
        try:
            return self.demo.read(run or self.demo.default_run(), query)
        except KeyError:
            raise HTTPException(404, f"no run {run}") from None

    async def tick_message(self) -> dict:
        return await asyncio.to_thread(self.demo.tick_message)

    async def run(self) -> None:
        await asyncio.to_thread(self.demo.start)
        self.publish([await self.tick_message()])
        loop = asyncio.get_running_loop()
        while True:
            if self.demo.speed == 0:
                if self.demo.ready and await asyncio.to_thread(self.demo.catch_up):  # one day of the lever run
                    continue
                self.resume.clear()
                await self.resume.wait()
                continue
            started = loop.time()
            try:
                self.publish(await asyncio.to_thread(self.demo.advance))
            except Exception:
                log.exception("tick failed; the demo is paused")
                self.demo.set_speed(0)
                continue
            seconds = self.tick_seconds / max(self.demo.speed, 1)
            await asyncio.sleep(max(0.0, seconds - (loop.time() - started)))

    async def serve(self, ws: WebSocket) -> None:
        await ws.accept()
        q: asyncio.Queue = asyncio.Queue()
        self.consoles.add(q)
        try:
            if self.demo.ready:  # a console that connects late starts from the current day
                await ws.send_json(StreamMessage.model_validate(await self.tick_message()).model_dump())
            while True:
                await ws.send_json(await q.get())
        except WebSocketDisconnect:
            pass
        finally:
            self.consoles.discard(q)


def create_app(demo: Demo | None = None, tick_seconds: float = 2.0, ui_dir: Path | None = UI_DIST,
               story_dir: Path = story.STORY_DIR, whatif_dir: Path = whatif.WHATIF_DIR) -> FastAPI:
    demo = demo or Demo()
    live = Live(demo, tick_seconds)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        task = asyncio.create_task(live.run())
        task.add_done_callback(lambda t: t.cancelled() or t.exception() is None or
                               log.error("demo clock stopped", exc_info=t.exception()))
        yield
        task.cancel()
        await asyncio.to_thread(demo.close)

    app = FastAPI(title="CarePath AI", lifespan=lifespan)
    app.state.demo = demo
    api = APIRouter(prefix="/api")

    @api.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @api.websocket("/stream")
    async def stream(ws: WebSocket) -> None:
        await live.serve(ws)

    @api.post("/sim/start")
    async def start() -> dict[str, int]:
        live.need_ready()
        live.set_speed(demo.speed or 1)
        return await live.status()

    @api.post("/sim/pause")
    async def pause() -> dict[str, int]:
        live.need_ready()
        live.set_speed(0)
        return await live.status()

    @api.post("/sim/speed")
    async def speed(body: Speed) -> dict[str, int]:
        live.need_ready()
        live.set_speed(body.factor)
        return await live.status()

    @api.post("/sim/reset")
    async def reset() -> dict[str, int]:
        await live.control(demo.start)
        return await live.status([await live.tick_message()])

    @api.post("/sim/scenario/{n}")
    async def choose_scenario(n: int) -> dict[str, int]:
        await live.control(demo.choose, n)
        return await live.status([await live.tick_message()])

    @api.post("/sim/jump/{day}")
    async def jump(day: int) -> dict[str, int]:
        return await live.status(await live.control(demo.jump, day))

    @api.get("/sim/cache")
    def cache_mode() -> dict[str, str]:
        """C37: the LLM gateway's mode, for the demo bar's indicator (the team only)."""
        return {"mode": llm.mode()}

    @api.put("/sim/cache")
    def set_cache_mode(body: Cache) -> dict[str, str]:
        llm.set_mode(body.mode)
        return {"mode": llm.mode()}

    @api.get("/reveal/{scenario}")
    def reveal(scenario: int) -> dict:
        """Rivelazione (C37): the agents' own alarms next to scenario_truth; nothing else reads it."""
        live.need_ready()
        try:
            return demo.reveal(scenario)
        except ValueError as e:
            raise HTTPException(404, str(e)) from None

    @api.get("/kpi")
    def kpi(run: str | None = None, pathway_id: str | None = None, level: str | None = None,
            key: str | None = None) -> list[dict]:
        return live.read(run, lambda con: queries.kpi(con, pathway_id, level, key))

    @api.get("/capacity")
    def capacity(service: str, run: str | None = None, pathway_id: str | None = None, day: int | None = None) -> list[dict]:
        """C28: slot use and waits per facility of a service; the before/after of a lever run (D45)."""
        return live.read(run, lambda con: queries.capacity(con, pathway_id or demo.population.pathway.pathway_id,
                                                           service, day))

    @api.get("/sankey")
    def sankey(run: str | None = None, pathway_id: str | None = None) -> list[dict]:
        return live.read(run, lambda con: queries.sankey(con, pathway_id))

    @api.get("/map")
    def map_comuni(run: str | None = None, pathway_id: str | None = None) -> list[dict]:
        return live.read(run, lambda con: queries.map_comuni(con, pathway_id))

    @api.get("/worklist")
    def worklist(run: str | None = None, day: int | None = None) -> list[dict]:
        return live.read(run, lambda con: queries.worklist(con, day))

    @api.get("/patients/{patient_id}")
    def patient(patient_id: str, run: str | None = None, day: int | None = None) -> dict:
        if day is None:
            found = live.read(run, lambda con: queries.patient_360(con, patient_id))
        else:  # a recorded story (C17)
            found = story.load(patient_id, run or "", day, story_dir)
        if found is None:
            raise HTTPException(404, f"no patient {patient_id} in run {run}, day {day}")
        return found

    @api.get("/actions")
    def actions(run: str | None = None, status: str | None = None, day: int | None = None) -> list[dict]:
        return live.read(run, lambda con: queries.actions(con, status, day))

    @api.post("/actions/{action_id}/{decision}")
    async def decide(action_id: str, decision: Literal["approve", "reject", "undo"]) -> dict:
        """The manager's decision (SPEC §7.3): approve executes the action at once, reject closes it, undo
        reverses an executed one; the audit log records each, and the feed gets the changed action."""
        try:
            messages = await live.control(demo.decide, action_id, decision)
        except KeyError:
            raise HTTPException(404, f"no action {action_id}") from None
        live.publish(messages)
        return {"action_id": action_id, "status": messages[0]["payload"]["status"]}

    @api.post("/admissions")
    async def admissions(body: Admission) -> dict:
        """Bed Finder (demo step 9c, C42): a doctor has decided to admit; the agent picks ward and bed in the
        run (the agents arm on screen by default) and the action service assigns or proposes it (SPEC §7)."""
        run = body.run or demo.default_run()
        try:
            result, messages = await live.control(demo.admit, run, body.patient_id, body.day, body.diagnosis,
                                                  body.facility_id, body.choice)
        except KeyError:
            raise HTTPException(404, f"no run {run}") from None
        live.publish(messages)
        return result

    @api.get("/settings")
    def settings() -> dict:
        live.need_ready()
        return {"autonomy": demo.autonomy()}

    @api.put("/settings/autonomy")
    async def set_autonomy(body: Autonomy) -> dict:
        await live.control(demo.set_autonomy, body.type, body.level)
        return {"autonomy": demo.autonomy()}

    @api.get("/investigations")
    def investigations(run: str | None = None) -> list[dict]:
        return live.read(run, queries.investigations)

    @api.get("/reports")
    def reports(run: str | None = None) -> list[dict]:
        return live.read(run, queries.reports)

    @api.get("/questions")
    def questions() -> dict:
        """C40: the questions Chiedi suggests for the scenario on screen, the cache manifest's (D17): the ones
        that have an answer in the demo, on their alarm day. The console holds no question of its own (AC17)."""
        scenarios = json.loads(MANIFEST.read_text(encoding="utf-8"))["scenarios"] if MANIFEST.is_file() else []
        s = next((s for s in scenarios if s["scenario"] == demo.scenario), {})
        return {"scenario": demo.scenario, "day": s.get("alarm_day"), "questions": s.get("questions", [])}

    @api.post("/ask")
    async def ask(body: Ask) -> dict:
        """An operator's question (Chiedi): the stored investigation; its steps go on the stream. In the demo
        the answer comes from the cache (D14), so a question nobody warmed has no answer: 503, no template."""
        try:
            row, messages = await live.control(demo.ask, body.question)
        except llm.LLMUnavailable as e:
            raise HTTPException(503, f"no answer to this question: {e}") from None
        live.publish(messages)
        return queries.decode(row)

    @api.post("/whatif")
    def what_if(body: WhatIf) -> dict:
        """The scenario on screen, from its precomputed grid (C27, D48); it does not wait for the runs."""
        try:
            # the pathway from its file, not from the runs: what-if answers before they are ready (D48)
            return whatif.result(demo.scenario, body.levers, body.months, whatif_dir, pathway_model.load(PATHWAY_ID))
        except FileNotFoundError:
            raise HTTPException(503, f"no what-if grid for scenario {demo.scenario}: uv run python -m engine.whatif")
        except ValueError as e:
            raise HTTPException(422, str(e))

    @api.get("/pathways/{pathway_id}")
    def pathway(pathway_id: str) -> dict:
        """The pathway file as it is (C22): the console names steps and drugs from it, not from code (AC17)."""
        path = pathway_model.PATHWAYS_DIR / f"{pathway_id}.json"
        if not re.fullmatch(pathway_model.ID, pathway_id) or not path.is_file():
            raise HTTPException(404, f"no pathway {pathway_id}")
        return json.loads(path.read_text(encoding="utf-8"))

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
