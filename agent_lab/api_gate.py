"""Scoped inspection of lesson 37 permission-gate runs."""

import asyncio
import secrets
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from pydantic import Field

from agent_lab.foundation_models import GateInputs, Inputs
from agent_lab.foundations import source_sections
from agent_lab.models import LessonError, RunRequest
from agent_lab.permission_gate_lab import ACTIVE_GATES, permission_rule
from agent_lab.runtime import BusyError, RunService


class GateRun(Inputs):
    mode: Literal["offline", "live"] = "offline"
    lesson_options: GateInputs = Field(default_factory=GateInputs)
    scenario: Literal["success", "missing-evidence", "wrong-identity", "rejected-input"] = "success"
    max_turns: int = Field(default=4, ge=1, le=4)
    max_budget_usd: float = Field(default=0.10, gt=0, le=0.10)
    consent: bool = False


class GateKey(Inputs):
    run_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    control_token: str = Field(min_length=16, max_length=100)


class GateAnswer(GateKey):
    gate_id: str = Field(min_length=1, max_length=100)
    capability: Literal["owned-write"] = "owned-write"
    action: Literal["allow", "edit", "remember", "deny", "interrupt", "malformed"]


def install_gate_routes(app: FastAPI, runner: RunService) -> None:
    records: dict[str, tuple[str, dict[str, Any]]] = {}
    active: dict[str, str] = {}

    def record(key: GateKey) -> dict[str, Any]:
        item = records.get(key.run_id)
        if item is None and key.run_id in active and secrets.compare_digest(active[key.run_id], key.control_token):
            raise HTTPException(409, "The gate run is still in progress.")
        if item is None or not secrets.compare_digest(item[0], key.control_token):
            raise HTTPException(403, "Unknown lesson run or invalid control token.")
        return item[1]

    @app.post("/api/c37/run")
    async def run(body: GateRun) -> dict[str, Any]:
        if body.mode == "live" and not body.consent:
            raise HTTPException(403, "Confirm the bounded paid gate run explicitly.")
        try:
            handle = runner.start(37, RunRequest(mode=body.mode,
                lesson_options=body.lesson_options.model_dump(), scenario=body.scenario,
                max_turns=body.max_turns, max_budget_usd=body.max_budget_usd))
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc
        except BusyError as exc:
            raise HTTPException(429, str(exc)) from exc
        except LessonError as exc:
            raise HTTPException(422, str(exc)) from exc
        async def collect() -> dict[str, Any]:
            report: dict[str, Any] = {}
            status = "failed"
            error: str | None = None
            try:
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
            finally:
                active.pop(handle.id, None)

        if body.lesson_options.action == "manual":
            active[handle.id] = handle.token
            asyncio.create_task(collect())
            return {"run_id": handle.id, "control_token": handle.token,
                    "status": "running", "error": None, "experiment": {}}
        return await collect()

    @app.post("/api/c37/dry")
    async def dry(body: GateInputs) -> dict[str, Any]:
        return {"dry_run": True, "launched": False, "sdk_called": False,
                "selected_action": body.action, "gate_tool": "mcp__gate__approve",
                "planned_tool": "Write", "planned_target": "gate-original.txt",
                "bash_rule_preview": permission_rule("Bash", {"command": "git status"}),
                "note": "Options inspection only; no MCP process, gate or SDK session started."}

    @app.post("/api/c37/gate-log")
    async def gate_log(body: GateKey) -> dict[str, Any]:
        if body.run_id in active:
            if not secrets.compare_digest(active[body.run_id], body.control_token):
                raise HTTPException(403, "Invalid control token.")
            gate = ACTIVE_GATES.get(body.run_id)
            return {"gate_calls": [], "gate_decisions": [], "process_receipts": [],
                    "pending": None if gate is None or gate.pending_input is None else {
                        "gate_id": gate.gate_id, "capability": "owned-write",
                        "tool_name": gate.pending_input.get("tool_name"),
                        "tool_input": gate.pending_input.get("tool_input")}}
        item = record(body)
        return {key: item.get(key) for key in ("gate_calls", "gate_decisions", "process_receipts")}

    @app.post("/api/c37/who")
    async def who(body: GateKey) -> dict[str, Any]:
        if body.run_id in active:
            if not secrets.compare_digest(active[body.run_id], body.control_token):
                raise HTTPException(403, "Invalid control token.")
            return {"run_id": body.run_id, "selected": {"action": "manual"}, "scope": "Pending owned Write gate."}
        item = record(body)
        return {"run_id": body.run_id, "selected": item.get("selected"),
                "scope": item.get("check_scope")}

    @app.post("/api/c37/answers")
    async def answers(body: GateKey) -> dict[str, Any]:
        item = record(body)
        return {"decision": item.get("gate_decisions"),
                "file_inventory": item.get("file_inventory"),
                "experiment_passed": item.get("experiment_passed")}

    @app.post("/api/c37/failures")
    async def failures(body: GateKey) -> dict[str, Any]:
        item = record(body)
        return {key: item.get(key) for key in ("gate_correlated", "sdk_write_paired",
                                              "file_effect_verified", "connection_closed")}

    @app.post("/api/c37/decide")
    async def decide(body: GateAnswer) -> dict[str, Any]:
        if body.run_id in active:
            if not secrets.compare_digest(active[body.run_id], body.control_token):
                raise HTTPException(403, "Invalid control token.")
            gate = ACTIVE_GATES.get(body.run_id)
            if gate is None:
                raise HTTPException(409, "The gate has not started or already closed.")
            try:
                gate.submit(body.gate_id, body.capability, body.action)
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from exc
            return {"accepted": True, "run_id": body.run_id, "gate_id": body.gate_id}
        item = record(body)
        decisions = item.get("gate_decisions", [])
        if not decisions or decisions[0].get("gate_id") != body.gate_id:
            raise HTTPException(409, "Unrelated or stale gate decision.")
        raise HTTPException(409, "This gate was already decided; duplicate answers are refused.")

    @app.get("/api/c37/code")
    async def code() -> dict[str, Any]:
        return {"sections": source_sections(37)}
