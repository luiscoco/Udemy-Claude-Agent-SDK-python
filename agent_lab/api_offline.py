"""Strict streaming Lesson 51 routes; no provider or network producer."""

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from agent_lab.config import ROOT
from agent_lab.offline_lab import (
    CASES,
    PUBLIC_SCENARIOS,
    ReplayInput,
    StrictInput,
    SuiteInput,
    replay,
    run_suite,
)
from agent_lab.runtime import RunService


class StopInput(StrictInput):
    runId: uuid.UUID


async def parsed_body(request: Request, model: type[StrictInput]) -> Any:
    try:
        return model.model_validate_json(json.dumps(await request.json()))
    except (ValueError, ValidationError) as exc:
        raise HTTPException(400, "Invalid fixed offline lab request") from exc


def offline_code() -> list[dict[str, Any]]:
    lines = (ROOT / "agent_lab/offline_lab.py").read_text(encoding="utf-8").splitlines()
    markers = (("async def run_suite(", 24, "Why does the host execute every case sequentially?"),
               ("async def run_offline_host(", 27, "Which synthetic envelopes can cause a real host handler call?"),
               ("def evaluate_suite(", 27, "Why can only the unmodified complete suite earn credit?"))
    result = []
    for marker, length, question in markers:
        start = next(index for index, line in enumerate(lines, 1) if line.startswith(marker))
        end = min(len(lines), start + length - 1)
        result.append({"file": "agent_lab/offline_lab.py", "start_line": start,
                       "end_line": end, "code": "\n".join(lines[start - 1:end]),
                       "question": question})
    return result


def install_offline_routes(app: FastAPI, runner: RunService) -> None:
    root = runner.settings.data_dir / "lesson-51"
    active: dict[str, Any] = {}

    @app.get("/api/c51/facts")
    async def facts() -> dict[str, Any]:
        return {"lesson": 51, "command": "uv run python scripts/offline_host.py",
                "cases": [{"id": case, "group": group} for case, group in CASES],
                "group_counts": {"all": 16, "contracts": 6, "store": 2, "replay": 8},
                "public_scenarios": list(PUBLIC_SCENARIOS),
                "scope": "synthetic SDK-style normalized envelopes with real host components; not native SDK wire compatibility or model choice",
                "modelCalls": 0, "actualBilledUsd": 0, "live_enabled": False}

    @app.get("/api/c51/code")
    async def code() -> list[dict[str, Any]]:
        return offline_code()

    @app.get("/api/c51/active")
    async def active_run() -> dict[str, Any]:
        if not active:
            raise HTTPException(404, "No active offline operation")
        return {"runId": str(active["run"]), "action": active["action"]}

    async def start(action: str, selected: SuiteInput | ReplayInput) -> StreamingResponse:
        if active:
            raise HTTPException(409, "Offline lab operation active")
        run = uuid.uuid4()
        abort = asyncio.Event()
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=500)
        active.update({"run": run, "action": action, "abort": abort})

        async def send(frame: dict[str, Any]) -> None:
            if queue.full() or len(json.dumps(frame)) > 100_000:
                raise ValueError("Offline stream evidence limit")
            await queue.put({"run": str(run), **frame})

        async def execute() -> None:
            try:
                async with asyncio.timeout(15):
                    if isinstance(selected, SuiteInput):
                        report = await run_suite(root, group=selected.group,
                                                 mutation=selected.mutation,
                                                 abort=abort, emit=send, run_id=run)
                    else:
                        report = await replay(root, selected.scenario,
                                              abort=abort, emit=send, run_id=run)
                await send({"kind": "complete", "report": report})
            except asyncio.CancelledError:
                await send({"kind": "complete", "report": {"lesson": 51, "run": str(run),
                             "action": action, "status": "cancelled", "experiment_passed": False}})
            except Exception:
                await send({"kind": "complete", "report": {"lesson": 51, "run": str(run),
                             "action": action, "status": "failed", "experiment_passed": False}})
            finally:
                if active.get("run") == run:
                    active.clear()

        task = asyncio.create_task(execute())
        active["task"] = task

        async def stream() -> AsyncIterator[str]:
            try:
                yield "data: " + json.dumps({"run": str(run), "kind": "started",
                                             "action": action, "synthetic": True}) + "\n\n"
                while not task.done() or not queue.empty():
                    try:
                        frame = await asyncio.wait_for(queue.get(), 0.05)
                    except TimeoutError:
                        continue
                    yield "data: " + json.dumps(frame, ensure_ascii=False) + "\n\n"
            finally:
                if not task.done():
                    abort.set()
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)

        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-store"})

    @app.post("/api/c51/run")
    async def run(request: Request) -> StreamingResponse:
        selected: SuiteInput = await parsed_body(request, SuiteInput)
        return await start("run", selected)

    @app.post("/api/c51/replay")
    async def replay_route(request: Request) -> StreamingResponse:
        selected: ReplayInput = await parsed_body(request, ReplayInput)
        return await start("replay", selected)

    @app.post("/api/c51/stop")
    async def stop(request: Request) -> dict[str, Any]:
        selected: StopInput = await parsed_body(request, StopInput)
        if active.get("run") != selected.runId:
            raise HTTPException(409, "Active offline run does not match")
        active["abort"].set()
        return {"stopping": True, "runId": str(selected.runId)}
