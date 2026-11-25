"""Lesson 59 fixed routing workshop routes."""

import asyncio
import json
import uuid
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agent_lab.headless_native import bundled_cli, private_key
from agent_lab.routing_lab import RoutingInput, facts, prepared
from agent_lab.routing_native import delegate, live, native_models, resolution


class StopInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    runId: uuid.UUID


class SpecialInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    mode: Literal["prepared", "live"] = "prepared"
    consent: bool = False
    budget: float = Field(default=1, ge=.3, le=1)


async def _parse[T: BaseModel](request: Request, schema: type[T]) -> T:
    try:
        return schema.model_validate_json(json.dumps(await request.json()))
    except (ValueError, ValidationError) as exc:
        raise HTTPException(400, "Invalid fixed routing request") from exc


def install_routing_routes(app: FastAPI, runner: Any) -> None:
    lock = asyncio.Lock()
    active: dict[str, Any] = {}
    root = runner.settings.data_dir

    @app.get("/api/c59/facts")
    async def facts_route():
        return {**facts(), "liveEnabled": runner.settings.enable_live}

    @app.get("/api/c59/plan")
    async def plan_route(request: Request):
        if request.query_params:
            raise HTTPException(400, "Plan accepts no parameters")
        return {"first": "Run one strategy, then compare all prepared strategies.",
                "inspect": "Compare cost per correct answer and failed or escalated tasks.",
                "challenge": "Explain why the cheapest token price may not yield the cheapest solution.",
                "hints": ["Count accepted answers, not only tokens.",
                          "Include failed attempts, classifier calls and escalations in the total cost."],
                "reference": "A low token price can still cost more per correct solution when failed tasks require an escalation or another attempt. Include routing overhead and grade each answer independently."}

    @app.get("/api/c59/code")
    async def code_route(request: Request):
        if request.query_params:
            raise HTTPException(400, "Code accepts no parameters")
        from agent_lab.config import ROOT
        anchors = (("agent_lab/routing_lab.py", "def answer_key(", 75,
                    "Which operations compute answer keys independently of the selected tier?"),
                   ("agent_lab/routing_lab.py", "def metrics(", 58,
                    "Why does the final snapshot count once for each query?"),
                   ("agent_lab/routing_native.py", "async def _query(", 95,
                    "Where is a native model switch acknowledged in the same session?"))
        rows = []
        for name, marker, length, question in anchors:
            lines = (ROOT / name).read_text(encoding="utf-8").splitlines()
            start = next(i for i, line in enumerate(lines, 1) if line.startswith(marker))
            rows.append({"file": name, "start_line": start,
                         "end_line": min(len(lines), start + length - 1),
                         "code": "\n".join(lines[start - 1:start + length - 1]),
                         "question": question})
        return rows

    @app.get("/api/c59/models")
    async def models_route(request: Request):
        if not request.query_params:
            return {"source": "configured-local", "models": facts()["models"]}
        if dict(request.query_params) != {"native": "1", "consent": "1"}:
            raise HTTPException(400, "Exact native model-list opt-in required")
        if not runner.settings.enable_live:
            raise HTTPException(403, "Enabled backend required")
        try:
            bundled_cli()
            private_key()
        except (PermissionError, FileNotFoundError) as exc:
            raise HTTPException(403, str(exc)) from exc
        if lock.locked():
            raise HTTPException(409, "Lesson 59 operation already active")
        async with lock:
            run_id = str(uuid.uuid4())
            task = asyncio.create_task(native_models(root, run_id))
            active.update({"id": run_id, "task": task})
            try:
                return await task
            finally:
                active.clear()

    @app.get("/api/c59/active")
    async def active_route():
        if not active:
            raise HTTPException(404, "No active Lesson 59 run")
        return {"runId": active["id"]}

    @app.post("/api/c59/run")
    async def run_route(request: Request):
        selected = await _parse(request, RoutingInput)
        if selected.mode == "live":
            if not selected.consent or not runner.settings.enable_live:
                raise HTTPException(403, "Fresh consent and enabled backend required")
            try:
                bundled_cli()
                private_key()
            except (PermissionError, FileNotFoundError) as exc:
                raise HTTPException(403, str(exc)) from exc
            reservation = len(selected.taskIds) * (2 if selected.strategies[0] == "classifier" else 1) * .1
            if selected.budget + 1e-9 < reservation:
                raise HTTPException(400, "Budget below reserved query thresholds")
        if lock.locked():
            raise HTTPException(409, "Lesson 59 operation already active")
        async with lock:
            run_id = str(uuid.uuid4())
            if selected.mode == "prepared":
                return prepared(selected, run_id)
            task = asyncio.create_task(live(selected, root, run_id))
            active.update({"id": run_id, "task": task})
            try:
                return await task
            finally:
                active.clear()

    @app.post("/api/c59/resolution")
    async def resolution_route(request: Request):
        selected = await _parse(request, SpecialInput)
        if selected.mode == "live":
            if not selected.consent or not runner.settings.enable_live:
                raise HTTPException(403, "Fresh consent and enabled backend required")
            try:
                bundled_cli()
                private_key()
            except (PermissionError, FileNotFoundError) as exc:
                raise HTTPException(403, str(exc)) from exc
        if lock.locked():
            raise HTTPException(409, "Lesson 59 operation already active")
        async with lock:
            run_id = str(uuid.uuid4())
            task = asyncio.create_task(resolution(root, mode=selected.mode,
                                                  consent=selected.consent,
                                                  budget=selected.budget, run_id=run_id))
            active.update({"id": run_id, "task": task})
            try:
                return await task
            finally:
                active.clear()

    @app.post("/api/c59/delegate")
    async def delegate_route(request: Request):
        selected = await _parse(request, SpecialInput)
        if selected.mode == "live":
            if not selected.consent or not runner.settings.enable_live:
                raise HTTPException(403, "Fresh consent and enabled backend required")
            try:
                bundled_cli()
                private_key()
            except (PermissionError, FileNotFoundError) as exc:
                raise HTTPException(403, str(exc)) from exc
        if lock.locked():
            raise HTTPException(409, "Lesson 59 operation already active")
        async with lock:
            run_id = str(uuid.uuid4())
            task = asyncio.create_task(delegate(root, mode=selected.mode,
                                                consent=selected.consent,
                                                budget=selected.budget, run_id=run_id))
            active.update({"id": run_id, "task": task})
            try:
                return await task
            finally:
                active.clear()

    @app.post("/api/c59/stop", status_code=202)
    async def stop_route(request: Request):
        selected = await _parse(request, StopInput)
        if not active or active["id"] != str(selected.runId):
            raise HTTPException(404, "No matching run")
        active["task"].cancel()
        return {"runId": str(selected.runId), "stopRequested": True}
