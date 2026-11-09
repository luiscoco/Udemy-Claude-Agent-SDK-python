"""Lesson 57 strict workshop routes and owned report recovery."""

import asyncio
import json
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, ValidationError

from agent_lab.config import ROOT
from agent_lab.headless_native import bundled_cli, private_key
from agent_lab.runtime import RunService
from agent_lab.worktrees_lab import CRITERION, RunInput, load_report, run_workshop


class StopInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    runId: uuid.UUID


async def _body(request: Request, model: type[BaseModel]) -> BaseModel:
    try:
        return model.model_validate_json(json.dumps(await request.json()))
    except (ValueError, ValidationError) as exc:
        raise HTTPException(400, "Invalid bounded worktree request") from exc


def _frame(value: dict[str, Any]) -> str:
    return "data: " + json.dumps(value, ensure_ascii=False, default=str) + "\n\n"


def code_excerpts() -> list[dict[str, Any]]:
    anchors = (("agent_lab/worktrees_lab.py", "async def run_workshop(", 46,
                "Where do the two workers start before integration?"),
               ("agent_lab/worktrees_lab.py", "def grade(", 49,
                "Which actual commits, tests and cleanup facts earn the check?"),
               ("agent_lab/worktrees_native.py", "def exact_file(", 20,
                "How do both SDK permission gates bind to the assigned file?"))
    rows = []
    for path, marker, length, question in anchors:
        lines = (ROOT / path).read_text(encoding="utf-8").splitlines()
        start = next(index for index, line in enumerate(lines, 1) if line.startswith(marker))
        rows.append({"file": path, "start_line": start, "end_line": min(start + length - 1, len(lines)),
                     "code": "\n".join(lines[start - 1:start + length - 1]), "question": question})
    return rows


def install_worktree_routes(app: FastAPI, runner: RunService) -> None:
    active: dict[str, Any] = {}
    root = runner.settings.data_dir

    @app.get("/api/c57/facts")
    async def facts() -> dict[str, Any]:
        return {"lesson": 57, "criterion": CRITERION, "liveEnabled": runner.settings.enable_live,
                "freeCommand": "python scripts/worktrees_check.py",
                "nativeCommand": "python scripts/live_worktrees_check.py --live --budget 1",
                "scope": "Real local Git and Node are used even in prepared mode; Git worktrees are not OS sandboxes."}

    @app.get("/api/c57/code")
    async def code() -> list[dict[str, Any]]:
        return code_excerpts()

    @app.get("/api/c57/active")
    async def active_run() -> dict[str, str]:
        if not active:
            raise HTTPException(404, "No active worktree workshop")
        return {"runId": active["id"]}

    @app.get("/api/c57/runs/{run_id}")
    async def recovered(run_id: str) -> JSONResponse:
        try:
            uuid.UUID(run_id)
        except ValueError as exc:
            raise HTTPException(400, "Malformed run ID", headers={"Cache-Control": "no-store"}) from exc
        try:
            payload = load_report(root, run_id)
        except (FileNotFoundError, ValueError, KeyError, PermissionError) as exc:
            raise HTTPException(404, "Owned report unavailable", headers={"Cache-Control": "no-store"}) from exc
        return JSONResponse(payload, headers={"Cache-Control": "no-store"})

    @app.post("/api/c57/run")
    async def run(request: Request) -> StreamingResponse:
        selected = await _body(request, RunInput)
        assert isinstance(selected, RunInput)
        if selected.mode == "live":
            if not runner.settings.enable_live or not selected.consent:
                raise HTTPException(403, "Fresh live consent and enabled backend are required")
            try:
                bundled_cli()
                private_key()
            except (PermissionError, FileNotFoundError) as exc:
                raise HTTPException(403, str(exc)) from exc
        if active:
            raise HTTPException(409, "A worktree workshop is already active")
        run_id = str(uuid.uuid4())
        abort = asyncio.Event()
        active.update({"id": run_id, "abort": abort, "task": None})

        async def events() -> Any:
            queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

            async def notify(row: dict[str, Any]) -> None:
                await queue.put({"kind": "progress", "event": row})

            async def work() -> None:
                try:
                    report = await run_workshop(selected, root, abort, notify, run_id=run_id,
                                                allow_live=runner.settings.enable_live)
                    await queue.put({"kind": "result", "report": report,
                                     "check": report["check"], "criterion": CRITERION})
                except Exception as exc:
                    await queue.put({"kind": "error", "error": type(exc).__name__})
                finally:
                    await queue.put({"kind": "done"})

            task = asyncio.create_task(work())
            active["task"] = task
            try:
                yield _frame({"kind": "start", "runId": run_id,
                              "mode": selected.mode, "scenario": selected.scenario})
                while True:
                    frame = await queue.get()
                    yield _frame(frame)
                    if frame["kind"] == "done":
                        break
            finally:
                abort.set()
                if not task.done():
                    task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                active.clear()

        return StreamingResponse(events(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-store"})

    @app.post("/api/c57/stop", status_code=202)
    async def stop(request: Request) -> dict[str, Any]:
        selected = await _body(request, StopInput)
        assert isinstance(selected, StopInput)
        if not active or active["id"] != str(selected.runId):
            raise HTTPException(404, "No matching active workshop")
        active["abort"].set()
        task = active.get("task")
        if task is not None:
            task.cancel()
        return {"runId": str(selected.runId), "stopRequested": True}
