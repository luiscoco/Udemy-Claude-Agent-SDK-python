"""Lesson 58 bounded tool-search routes."""

import asyncio
import json
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, ValidationError

from agent_lab.headless_native import bundled_cli, private_key
from agent_lab.tool_search_lab import (
    MeasureInput,
    PlanInput,
    RunInput,
    SearchInput,
    plan,
    prepared,
    search,
)
from agent_lab.tool_search_native import live, measure


class StopInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    runId: uuid.UUID


async def parsed[T: BaseModel](request: Request, cls: type[T]) -> T:
    try:
        return cls.model_validate_json(json.dumps(await request.json()))
    except (ValueError, ValidationError) as exc:
        raise HTTPException(400, "Invalid bounded tool-search request") from exc


def install_tool_search_routes(app: FastAPI, runner) -> None:
    lock = asyncio.Lock()
    active: dict[str, Any] = {}
    root = runner.settings.data_dir

    @app.get("/api/c58/facts")
    async def facts():
        return {"lesson": 58, "catalogCount": 64, "liveEnabled": runner.settings.enable_live}

    @app.get("/api/c58/active")
    async def active_run():
        if not active:
            raise HTTPException(404, "No active Lesson 58 operation")
        return {"runId": active["id"]}

    @app.get("/api/c58/code")
    async def code():
        from agent_lab.config import ROOT
        anchors = (("agent_lab/tool_search_lab.py", "def search(", 32,
                    "Which score is a local explanation rather than native ranking?"),
                   ("agent_lab/tool_search_lab.py", "def refund(", 25,
                    "Which exact arguments may change the owned ledger?"),
                   ("agent_lab/tool_search_native.py", "async def live(", 42,
                    "Where is the admitted native refund call correlated?"))
        rows = []
        for path, marker, length, question in anchors:
            lines = (ROOT / path).read_text(encoding="utf-8").splitlines()
            start = next(i for i, line in enumerate(lines, 1) if line.startswith(marker))
            rows.append({"file": path, "start_line": start, "end_line": start + length - 1,
                         "code": "\n".join(lines[start - 1:start + length - 1]),
                         "question": question})
        return rows

    @app.post("/api/c58/search")
    async def search_route(request: Request):
        return search(await parsed(request, SearchInput))

    @app.post("/api/c58/plan")
    async def plan_route(request: Request):
        return plan(await parsed(request, PlanInput))

    def admit(consent: bool):
        if not consent or not runner.settings.enable_live:
            raise HTTPException(403, "Fresh live consent and enabled backend required")
        try:
            bundled_cli()
            private_key()
        except (PermissionError, FileNotFoundError) as exc:
            raise HTTPException(403, str(exc)) from exc

    @app.post("/api/c58/run")
    async def run_route(request: Request):
        selected = await parsed(request, RunInput)
        assert isinstance(selected, RunInput)
        if selected.mode == "live":
            admit(selected.consent)
        if lock.locked():
            raise HTTPException(409, "Lesson 58 operation already active")
        async with lock:
            run_id = str(uuid.uuid4())
            if selected.mode == "prepared":
                return prepared(selected, root, run_id)
            task = asyncio.create_task(live(selected, root, run_id))
            active.update({"id": run_id, "task": task})
            try:
                await asyncio.sleep(0)
                return await task
            finally:
                active.clear()

    @app.post("/api/c58/measure")
    async def measure_route(request: Request):
        selected = await parsed(request, MeasureInput)
        assert isinstance(selected, MeasureInput)
        admit(selected.consent)
        if lock.locked():
            raise HTTPException(409, "Lesson 58 operation already active")
        async with lock:
            run_id = str(uuid.uuid4())
            task = asyncio.create_task(measure(selected, root, run_id))
            active.update({"id": run_id, "task": task})
            try:
                return await task
            finally:
                active.clear()

    @app.post("/api/c58/stop", status_code=202)
    async def stop_route(request: Request):
        selected = await parsed(request, StopInput)
        assert isinstance(selected, StopInput)
        if not active or active["id"] != str(selected.runId):
            raise HTTPException(404, "No matching run")
        active["task"].cancel()
        return {"runId": str(selected.runId), "stopRequested": True}
