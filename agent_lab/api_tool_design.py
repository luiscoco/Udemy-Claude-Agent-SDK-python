"""Strict Lesson 54 catalog inspection, direct calls and bounded run routes."""

import asyncio
import json
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, ValidationError

from agent_lab.config import ROOT
from agent_lab.runtime import RunService
from agent_lab.tool_design_catalog import EXPECTED, PROFILE_TOOLS, SCHEMAS, Catalog
from agent_lab.tool_design_lab import DesignInput, DirectInput, grade, prepared
from agent_lab.tool_design_native import admission, native


class StopInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    runId: uuid.UUID


async def _body(request: Request, model: type[BaseModel]) -> BaseModel:
    try:
        return model.model_validate_json(json.dumps(await request.json()))
    except (ValueError, ValidationError) as exc:
        raise HTTPException(400, "Invalid fixed catalog request") from exc


def code_excerpts() -> list[dict[str, Any]]:
    anchors = (("agent_lab/tool_design_catalog.py", "    def invoke(", 35,
                "Which inputs fail before the business handler and how is the actual envelope measured?"),
               ("agent_lab/tool_design_lab.py", "async def prepared(", 43,
                "How does the scripted consumer follow the returned cursor?"),
               ("agent_lab/tool_design_lab.py", "def grade(", 44,
                "Which call and result identities must match before the check passes?"))
    result = []
    for path, marker, length, question in anchors:
        lines = (ROOT / path).read_text(encoding="utf-8").splitlines()
        start = next(index for index, line in enumerate(lines, 1) if line.startswith(marker))
        end = min(len(lines), start + length - 1)
        result.append({"file": path, "start_line": start, "end_line": end,
                       "code": "\n".join(lines[start - 1:end]), "question": question})
    return result


def _frame(frame: dict[str, Any]) -> str:
    return "data: " + json.dumps(frame, ensure_ascii=False, default=str) + "\n\n"


def install_tool_design_routes(app: FastAPI, runner: RunService) -> None:
    active: dict[str, Any] = {}
    catalog = Catalog()

    @app.get("/api/c54/facts")
    async def facts() -> dict[str, Any]:
        return {"lesson": 54, "profiles": {name: list(tools) for name, tools in PROFILE_TOOLS.items()},
                "schemas": {name: model.model_json_schema() for name, model in SCHEMAS.items()},
                "descriptions": {"lookup": "Look things up. Pass q.",
                                 "catalog_search": "Exact category, integer EUR cents, stock filter, stable IDs and nextCursor.",
                                 "catalog_get": "Exact stable SKU ID; search first if missing."},
                "snapshotSha256": catalog.snapshot_sha256, "expectedIds": list(EXPECTED),
                "liveEnabled": runner.settings.enable_live,
                "bytesLabel": "UTF-8 serialized handler-envelope bytes; not tokens, network traffic or model-context cost",
                "timingLabel": "Handler milliseconds exclude model and transport time",
                "scope": "Synthetic immutable read-only classroom catalog"}

    @app.get("/api/c54/code")
    async def code() -> list[dict[str, Any]]:
        return code_excerpts()

    @app.post("/api/c54/call")
    async def call(request: Request) -> dict[str, Any]:
        selected = await _body(request, DirectInput)
        assert isinstance(selected, DirectInput)
        if selected.tool not in PROFILE_TOOLS[selected.profile]:
            raise HTTPException(400, "Tool does not belong to selected profile")
        row = catalog.invoke(selected.profile, selected.tool, selected.input)
        return {"source": "direct-host-call", "modelCalls": 0, "reportedSdkUsd": 0,
                "snapshotSha256": catalog.snapshot_sha256, "afterSha256": catalog.current_hash(),
                "receipt": row, "lessonCheck": "not-awarded"}

    @app.get("/api/c54/active")
    async def active_run() -> dict[str, str]:
        if not active:
            raise HTTPException(404, "No active tool-design run")
        return {"runId": str(active["id"])}

    @app.post("/api/c54/run")
    async def run(request: Request) -> StreamingResponse:
        selected = await _body(request, DesignInput)
        assert isinstance(selected, DesignInput)
        if selected.mode == "live":
            try:
                admission(runner.settings, selected)
            except PermissionError as exc:
                raise HTTPException(403, str(exc)) from exc
        if active:
            raise HTTPException(409, "A tool-design run is already active")
        run_id = uuid.uuid4()
        abort = asyncio.Event()
        active.update({"id": run_id, "abort": abort, "task": None})

        async def events() -> Any:
            queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

            async def on_frame(frame: dict[str, Any]) -> None:
                await queue.put({"kind": "trace", "frame": frame})

            async def produce() -> dict[str, Any]:
                if selected.mode == "prepared":
                    return await prepared(selected, run_id, abort, on_frame, catalog)
                return await native(selected, run_id, runner.settings,
                                    runner.settings.data_dir / "lesson-54", abort, on_frame, catalog)

            task = asyncio.create_task(produce())
            active["task"] = task
            try:
                yield _frame({"kind": "start", "runId": str(run_id),
                              "mode": selected.mode, "profile": selected.profile, "format": selected.format})
                while not task.done() or not queue.empty():
                    try:
                        yield _frame(await asyncio.wait_for(queue.get(), timeout=0.05))
                    except TimeoutError:
                        pass
                report = await task
                yield _frame({"kind": "result", "runId": str(run_id), "report": report,
                              "check": "passed" if grade(selected, report) else "needs-review"})
                yield _frame({"kind": "done", "runId": str(run_id), "closed": report["closed"]})
            except asyncio.CancelledError:
                abort.set()
                task.cancel()
                try:
                    await asyncio.shield(task)
                except (asyncio.CancelledError, Exception):
                    pass
                raise
            except Exception as exc:
                yield _frame({"kind": "done", "runId": str(run_id), "error": type(exc).__name__})
            finally:
                active.clear()

        return StreamingResponse(events(), media_type="text/event-stream")

    @app.post("/api/c54/stop")
    async def stop(request: Request) -> dict[str, Any]:
        selected = await _body(request, StopInput)
        assert isinstance(selected, StopInput)
        if active.get("id") != selected.runId:
            raise HTTPException(409, "Active run does not match")
        active["abort"].set()
        task = active.get("task")
        if task:
            task.cancel()
        return {"stopping": True, "runId": str(selected.runId)}
