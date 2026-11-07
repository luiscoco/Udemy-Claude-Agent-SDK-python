"""Scoped inspection and management routes for the lesson 35 session store."""

import secrets
from typing import Any, Literal

from claude_agent_sdk import project_key_for_directory
from fastapi import FastAPI, HTTPException, Query
from pydantic import Field

from agent_lab.foundation_models import Inputs, StoreInputs
from agent_lab.foundations import source_sections
from agent_lab.models import LessonError, RunRequest
from agent_lab.runtime import BusyError, RunService
from agent_lab.sqlite_session_store import SQLiteSessionStore


class StoreRun(Inputs):
    mode: Literal["offline", "live"] = "offline"
    lesson_options: StoreInputs = Field(default_factory=StoreInputs)
    scenario: Literal["success", "missing-evidence", "wrong-identity", "changed-host", "wrong-answer"] = "success"
    max_turns: int = Field(default=4, ge=1, le=6)
    max_budget_usd: float = Field(default=0.10, gt=0, le=0.2)
    consent: bool = False


class StoreKey(Inputs):
    run_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    control_token: str = Field(min_length=16, max_length=100)


class StoreManage(StoreKey):
    action: Literal["list", "delete"]


def install_store_routes(app: FastAPI, runner: RunService) -> None:
    records: dict[str, tuple[str, dict[str, Any]]] = {}

    def record(run_id: str, control_token: str) -> dict[str, Any]:
        item = records.get(run_id)
        if item is None or not secrets.compare_digest(item[0], control_token):
            raise HTTPException(403, "Unknown lesson run or invalid control token.")
        return item[1]

    def sqlite_store(run_id: str, item: dict[str, Any]) -> SQLiteSessionStore:
        if item["action"] != "durable-resume":
            raise HTTPException(409, "This run selected a process-local store.")
        return SQLiteSessionStore(runner.settings.data_dir / run_id / "session-store.sqlite3")

    @app.post("/api/c35/run")
    async def run(body: StoreRun) -> dict[str, Any]:
        if body.mode == "live" and not body.consent:
            raise HTTPException(403, "Confirm the bounded paid lesson run explicitly.")
        try:
            handle = runner.start(35, RunRequest(
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

    @app.get("/api/c35/db")
    async def db(run_id: str = Query(pattern=r"^[0-9a-f]{32}$"),
                 control_token: str = Query(min_length=16, max_length=100)) -> dict[str, Any]:
        item = record(run_id, control_token)
        return {key: item.get(key) for key in (
            "action", "local_line_count", "stored_line_count", "local_uuid_count",
            "stored_uuid_count", "missing_uuid_count", "mirror_errors",
            "uuid_coverage_verified", "summary_verified", "summary_count",
            "store_reopened", "store_sessions",
            "experiment_passed",
        )}

    @app.get("/api/c35/entries")
    async def entries(run_id: str = Query(pattern=r"^[0-9a-f]{32}$"),
                      control_token: str = Query(min_length=16, max_length=100)) -> dict[str, Any]:
        item = record(run_id, control_token)
        return {"local_uuids": item.get("local_uuids", []),
                "stored_entries": item.get("stored_entries", []),
                "missing_uuids": item.get("missing_uuids", [])}

    @app.post("/api/c35/failures")
    async def failures(body: StoreKey) -> dict[str, Any]:
        item = record(body.run_id, body.control_token)
        return {"mirror_errors": item.get("mirror_errors", 0),
                "missing_uuid_count": item.get("missing_uuid_count", 0),
                "store_observations": item.get("store_observations", []),
                "session_verified": item.get("session_verified", False)}

    @app.post("/api/c35/manage")
    async def manage(body: StoreManage) -> dict[str, Any]:
        item = record(body.run_id, body.control_token)
        store = sqlite_store(body.run_id, item)
        work = (runner.settings.data_dir / body.run_id / "work").resolve()
        project = project_key_for_directory(str(work))
        sessions = await store.list_sessions(project)
        if body.action == "list":
            return {"sessions": sessions}
        terminals = item.get("terminal_results", [])
        session_id = terminals[-1].get("session_id") if terminals else None
        if not isinstance(session_id, str) or session_id not in [s["session_id"] for s in sessions]:
            raise HTTPException(409, "The owned session is not available for deletion.")
        await store.delete({"project_key": project, "session_id": session_id})
        item["store_sessions"] = []
        item["stored_entries"] = []
        item["stored_line_count"] = 0
        item["stored_uuid_count"] = 0
        item["missing_uuids"] = item.get("local_uuids", [])
        item["missing_uuid_count"] = len(item["missing_uuids"])
        item["uuid_coverage_verified"] = False
        item["experiment_passed"] = False
        return {"deleted_session_id": session_id, "sessions": await store.list_sessions(project)}

    @app.post("/api/c35/reset")
    async def reset(body: StoreKey) -> dict[str, Any]:
        item = record(body.run_id, body.control_token)
        if item["action"] == "durable-resume":
            store = sqlite_store(body.run_id, item)
            work = (runner.settings.data_dir / body.run_id / "work").resolve()
            project = project_key_for_directory(str(work))
            for session in await store.list_sessions(project):
                await store.delete({"project_key": project, "session_id": session["session_id"]})
        records.pop(body.run_id)
        return {"reset": True}

    @app.get("/api/c35/code")
    async def code() -> dict[str, Any]:
        return {"sections": source_sections(35)}
