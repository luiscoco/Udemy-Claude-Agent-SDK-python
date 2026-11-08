"""Strict Lesson 53 diagnostic routes and one-owner SSE mutation lifecycle."""

import asyncio
import json
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, ValidationError

from agent_lab.config import ROOT
from agent_lab.debug_lab import (
    LIVE_SCENARIOS,
    DebugInput,
    comparison,
    criterion,
    effective,
    prepared_run,
)
from agent_lab.debug_native import admission, native_run
from agent_lab.debug_store import DebugStore, InvalidBundle, MissingBundle
from agent_lab.runtime import RunService


class StopInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    runId: uuid.UUID


async def _body(request: Request, model: type[Any]) -> Any:
    try:
        return model.model_validate_json(json.dumps(await request.json()))
    except (ValueError, ValidationError) as exc:
        raise HTTPException(400, "Invalid fixed diagnostic body") from exc


def debug_code() -> list[dict[str, Any]]:
    markers = (
        ("agent_lab/debug_lab.py", "def bounded_debug_log(", 19, "How does the reader distinguish missing from empty while closing its descriptor?"),
        ("agent_lab/debug_native.py", "    finally:", 31, "Why are the stream and log closed before the bundle is assembled?"),
        ("agent_lab/debug_lab.py", "def diagnose(", 33, "Why is the first causal finding shown before downstream symptoms?"),
    )
    rows = []
    for path, marker, count, question in markers:
        lines = (ROOT / path).read_text(encoding="utf-8").splitlines()
        start = next(index for index, line in enumerate(lines, 1) if line.startswith(marker))
        end = min(len(lines), start + count - 1)
        rows.append({"file": path, "start_line": start, "end_line": end,
                     "code": "\n".join(lines[start - 1:end]), "question": question})
    return rows


def _frame(value: dict[str, Any]) -> str:
    return "data: " + json.dumps(value, ensure_ascii=False) + "\n\n"


def install_debugging_routes(app: FastAPI, runner: RunService) -> None:
    store = DebugStore(runner.settings.data_dir / "lesson-53")
    active: dict[str, Any] = {}

    def reserve(identifier: uuid.UUID) -> asyncio.Event:
        if active:
            raise HTTPException(409, "A diagnostic mutation is already active")
        abort = asyncio.Event()
        active.update({"run": identifier, "abort": abort, "task": None})
        return abort

    def release(identifier: uuid.UUID) -> None:
        if active.get("run") == identifier:
            active.clear()

    @app.get("/api/c53/facts")
    async def facts() -> dict[str, Any]:
        return {"lesson": 53, "scenarios": ["success", "denied", "missing", "max-turns",
                                              "startup", "api-error", "truncated"],
                "liveScenarios": list(LIVE_SCENARIOS), "freeReplay": True,
                "liveEnabled": runner.settings.enable_live,
                "scope": "Owned fixture and causal diagnostics; prepared SDK rows are authored"}

    @app.get("/api/c53/code")
    async def code() -> list[dict[str, Any]]:
        return debug_code()

    @app.get("/api/c53/runs/{identifier}")
    async def saved_run(identifier: str) -> dict[str, Any]:
        try:
            parsed = uuid.UUID(identifier)
        except ValueError as exc:
            raise HTTPException(400, "Invalid diagnostic UUID") from exc
        try:
            return store.load(parsed)
        except MissingBundle as exc:
            raise HTTPException(404, str(exc)) from exc
        except InvalidBundle as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.get("/api/c53/active")
    async def active_run() -> dict[str, Any]:
        if not active:
            raise HTTPException(404, "No active diagnostic")
        return {"runId": str(active["run"])}

    @app.post("/api/c53/run")
    async def run(request: Request) -> StreamingResponse:
        selected: DebugInput = await _body(request, DebugInput)
        if selected.mode == "live":
            try:
                admission(runner.settings, selected)
            except PermissionError as exc:
                raise HTTPException(403, str(exc)) from exc
        identifier = uuid.uuid4()
        abort = reserve(identifier)
        try:
            previous = store.load(selected.compareId)["bundle"] if selected.compareId else None
        except MissingBundle as exc:
            release(identifier)
            raise HTTPException(404, str(exc)) from exc
        except InvalidBundle as exc:
            release(identifier)
            raise HTTPException(409, str(exc)) from exc

        async def events() -> Any:
            queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

            async def on_row(row: dict[str, Any]) -> None:
                await queue.put({"kind": "trace", "row": row})

            async def produce() -> dict[str, Any]:
                bundle = (await prepared_run(selected, store.root, identifier, abort, on_row)
                          if selected.mode == "prepared" else
                          await native_run(selected, store.root, identifier, runner.settings, abort, on_row))
                if previous is not None:
                    bundle["comparison"] = comparison(previous, bundle)
                loaded = store.save(bundle)
                return {"loaded": loaded, "check": "passed" if criterion(str(identifier), selected, bundle, loaded)
                        else "needs-review"}

            worker = asyncio.create_task(produce())
            active["task"] = worker
            try:
                yield _frame({"kind": "start", "runId": str(identifier), "scenario": selected.scenario,
                              "mode": selected.mode, "effectiveConfig": effective(selected)})
                while not worker.done() or not queue.empty():
                    try:
                        frame = await asyncio.wait_for(queue.get(), timeout=0.05)
                        yield _frame(frame)
                    except TimeoutError:
                        pass
                result = await worker
                yield _frame({"kind": "bundle", **result})
                yield _frame({"kind": "done", "runId": str(identifier), "saved": True,
                              "cancelled": result["loaded"]["bundle"]["interrupted"]})
            except asyncio.CancelledError:
                abort.set()
                worker.cancel()
                try:
                    await asyncio.shield(worker)
                except (asyncio.CancelledError, Exception):
                    pass
                raise
            except Exception as exc:
                yield _frame({"kind": "done", "runId": str(identifier), "saved": False,
                              "cancelled": abort.is_set(), "error": type(exc).__name__})
            finally:
                release(identifier)

        return StreamingResponse(events(), media_type="text/event-stream")

    @app.post("/api/c53/stop")
    async def stop(request: Request) -> dict[str, Any]:
        selected: StopInput = await _body(request, StopInput)
        if active.get("run") != selected.runId:
            raise HTTPException(409, "Active diagnostic does not match")
        active["abort"].set()
        task = active.get("task")
        if task is not None:
            task.cancel()
        return {"stopping": True, "runId": str(selected.runId)}
