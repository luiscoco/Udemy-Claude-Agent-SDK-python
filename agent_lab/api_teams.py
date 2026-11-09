"""Strict Lesson 56 replay and optional native named-subagent observation routes."""

import asyncio
import json
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, ValidationError

from agent_lab.config import ROOT
from agent_lab.headless_native import bundled_cli
from agent_lab.runtime import RunService
from agent_lab.teams_lab import (
    CRITERION,
    MAX_COMMANDS,
    MAX_MESSAGES,
    LiveInput,
    ReplayInput,
    fixture,
    grade,
    run_replay,
    walkthrough,
)
from agent_lab.teams_native import admission, evaluate_native, native_run


class StopInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    runId: uuid.UUID


async def _body(request: Request, model: type[BaseModel]) -> BaseModel:
    try:
        return model.model_validate_json(json.dumps(await request.json()))
    except (ValueError, ValidationError) as exc:
        raise HTTPException(400, "Invalid bounded team command or native request") from exc


def code_excerpts() -> list[dict[str, Any]]:
    anchors = (("agent_lab/teams_lab.py", "def replay_team(", 44,
                "Which ownership, dependency and message transitions can the reducer refuse?"),
               ("agent_lab/teams_lab.py", "def grade(", 38,
                "Which current-history, exact evidence and cleanup facts earn the offline check?"),
               ("agent_lab/teams_native.py", "async def native_run(", 42,
                "How is the named SDK subagent observation bounded and kept separate?"))
    result = []
    for path, marker, length, question in anchors:
        lines = (ROOT / path).read_text(encoding="utf-8").splitlines()
        start = next(index for index, line in enumerate(lines, 1) if line.startswith(marker))
        end = min(len(lines), start + length - 1)
        result.append({"file": path, "start_line": start, "end_line": end,
                       "code": "\n".join(lines[start - 1:end]), "question": question})
    return result


def _frame(value: dict[str, Any]) -> str:
    return "data: " + json.dumps(value, ensure_ascii=False, default=str) + "\n\n"


def install_team_routes(app: FastAPI, runner: RunService) -> None:
    active: dict[str, Any] = {}

    @app.get("/api/c56/facts")
    async def facts() -> dict[str, Any]:
        try:
            executable = bundled_cli()
            available = executable.is_file()
        except FileNotFoundError:
            available = False
        return {"lesson": 56, "walkthrough": walkthrough(), "fixture": fixture(),
                "maxCommands": MAX_COMMANDS, "maxMessages": MAX_MESSAGES,
                "criterion": CRITERION, "executableAvailable": available,
                "liveEnabled": runner.settings.enable_live,
                "freeCommand": "python scripts/teams_check.py",
                "nativeCommand": "python scripts/live_teams_check.py --live --budget 1",
                "scope": "Application reducer is a simulation. Native SDK named subagents are not interactive native teams; an attempted SendMessage or answer 37 does not prove delivery or worker completion."}

    @app.get("/api/c56/code")
    async def code() -> list[dict[str, Any]]:
        return code_excerpts()

    @app.post("/api/c56/replay")
    async def replay(request: Request) -> dict[str, Any]:
        selected = await _body(request, ReplayInput)
        assert isinstance(selected, ReplayInput)
        report = run_replay(selected)
        return {"report": report, "check": "passed" if grade(selected, report) else "needs-review",
                "criterion": CRITERION}

    @app.get("/api/c56/active")
    async def active_run() -> dict[str, str]:
        if not active:
            raise HTTPException(404, "No active native team observation")
        return {"runId": str(active["id"])}

    @app.post("/api/c56/live")
    async def live(request: Request) -> StreamingResponse:
        selected = await _body(request, LiveInput)
        assert isinstance(selected, LiveInput)
        try:
            admission(runner.settings, selected)
        except (PermissionError, FileNotFoundError) as exc:
            raise HTTPException(403, str(exc)) from exc
        if active:
            raise HTTPException(409, "A native team observation is already active")
        run_id = uuid.uuid4()
        abort = asyncio.Event()
        active.update({"id": run_id, "abort": abort, "task": None})

        async def events() -> Any:
            queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

            async def on_frame(frame: dict[str, Any]) -> None:
                await queue.put({"kind": "frame", "frame": frame})

            async def work() -> None:
                try:
                    report = await native_run(selected, runner.settings,
                                              runner.settings.data_dir / "lesson-56", abort, on_frame,
                                              run_id=run_id)
                    await queue.put({"kind": "result", "report": report,
                                     "check": "passed" if evaluate_native(report) else "needs-review"})
                except Exception as exc:
                    await queue.put({"kind": "error", "error": type(exc).__name__})
                finally:
                    await queue.put({"kind": "done"})

            task = asyncio.create_task(work())
            active["task"] = task
            try:
                yield _frame({"kind": "start", "runId": str(run_id), "mode": "live"})
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

        return StreamingResponse(events(), media_type="text/event-stream")

    @app.post("/api/c56/stop")
    async def stop(request: Request) -> dict[str, Any]:
        selected = await _body(request, StopInput)
        assert isinstance(selected, StopInput)
        if not active or active["id"] != selected.runId:
            raise HTTPException(404, "No matching active native team observation")
        active["abort"].set()
        task = active.get("task")
        if task is not None:
            task.cancel()
        return {"runId": str(selected.runId), "stopRequested": True}
