"""Scoped lesson 36 process observations and dry plans."""

import secrets
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query
from pydantic import Field

from agent_lab.foundation_models import Inputs, SpawnInputs
from agent_lab.foundations import source_sections
from agent_lab.models import LessonError, RunRequest
from agent_lab.runtime import BusyError, RunService


class SpawnRun(Inputs):
    mode: Literal["offline", "live"] = "offline"
    lesson_options: SpawnInputs = Field(default_factory=SpawnInputs)
    scenario: Literal["success", "missing-evidence", "wrong-identity", "wrong-frame", "wrong-answer"] = "success"
    max_turns: int = Field(default=4, ge=1, le=6)
    max_budget_usd: float = Field(default=0.10, gt=0, le=0.2)
    consent: bool = False


class SpawnKey(Inputs):
    run_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    control_token: str = Field(min_length=16, max_length=100)


def install_spawn_routes(app: FastAPI, runner: RunService) -> None:
    records: dict[str, tuple[str, dict[str, Any]]] = {}

    def record(run_id: str, control_token: str) -> dict[str, Any]:
        item = records.get(run_id)
        if item is None or not secrets.compare_digest(item[0], control_token):
            raise HTTPException(403, "Unknown lesson run or invalid control token.")
        return item[1]

    @app.get("/api/c36/state")
    async def state(run_id: str = Query(pattern=r"^[0-9a-f]{32}$"),
                    control_token: str = Query(min_length=16, max_length=100)) -> dict[str, Any]:
        item = record(run_id, control_token)
        return {key: item.get(key) for key in ("selected", "sdk_success", "host_success",
                                              "connection_closed", "experiment_passed", "check_scope")}

    @app.post("/api/c36/dry")
    async def dry(body: SpawnInputs) -> dict[str, Any]:
        return {"dry_run": True, "launched": False, "sdk_called": False,
                "planned_argv": ["<owned Python>", "-I", "process_probe.py", "--case",
                                 body.action if body.action in {"stderr", "timeout", "cancel"} else "success"],
                "planned_location": body.location, "shell": False,
                "note": "Options inspection only; no process or SDK session was started."}

    @app.post("/api/c36/run")
    async def run(body: SpawnRun) -> dict[str, Any]:
        if body.mode == "live" and not body.consent:
            raise HTTPException(403, "Confirm the bounded paid lesson run explicitly.")
        try:
            handle = runner.start(36, RunRequest(
                mode=body.mode, lesson_options=body.lesson_options.model_dump(),
                scenario=body.scenario, max_turns=body.max_turns,
                max_budget_usd=body.max_budget_usd,
            ))
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc
        except BusyError as exc:
            raise HTTPException(429, str(exc)) from exc
        except LessonError as exc:
            raise HTTPException(422, str(exc)) from exc
        report: dict[str, Any] = {}
        status = "failed"
        error: str | None = None
        async for event in runner.events(handle):
            if event.kind == "evidence" and isinstance(event.data.get("result"), dict):
                report = event.data["result"].get("experiment", {})
            elif event.kind == "error":
                error = event.data.get("message")
            elif event.kind == "done":
                status = event.data["status"]
        if status == "completed":
            records[handle.id] = (handle.token, report)
        return {"run_id": handle.id, "control_token": handle.token,
                "status": status, "error": error, "experiment": report}

    @app.get("/api/c36/alias")
    async def alias(run_id: str = Query(pattern=r"^[0-9a-f]{32}$"),
                    control_token: str = Query(min_length=16, max_length=100)) -> dict[str, Any]:
        item = record(run_id, control_token)
        return {"location": item["selected"]["location"], "cwd": item["child"]["cwd"],
                "remote": False, "note": "Both aliases are local directories on this host."}

    @app.get("/api/c36/debug")
    async def debug(run_id: str = Query(pattern=r"^[0-9a-f]{32}$"),
                    control_token: str = Query(min_length=16, max_length=100)) -> dict[str, Any]:
        item = record(run_id, control_token)
        child = item["child"]
        return {key: child[key] for key in ("frames", "partial_chunks", "bytes_forwarded_unchanged",
                                           "stderr_marker", "exit_code", "shell")}

    @app.post("/api/c36/failures")
    async def failures(body: SpawnKey) -> dict[str, Any]:
        item = record(body.run_id, body.control_token)
        child = item["child"]
        return {key: child[key] for key in ("launch_error", "interrupted", "child_cleaned", "exit_code")}

    @app.post("/api/c36/reset")
    async def reset(body: SpawnKey) -> dict[str, bool]:
        record(body.run_id, body.control_token)
        records.pop(body.run_id)
        return {"reset": True}

    @app.get("/api/c36/code")
    async def code() -> dict[str, Any]:
        return {"sections": source_sections(36)}
