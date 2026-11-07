"""Validated Lesson 45 cloud-format action routes."""

import asyncio
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agent_lab.cloud_lab import ACTIONS, facts, run, state
from agent_lab.config import ROOT
from agent_lab.runtime import RunService


class CloudAction(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    mode: Literal["local", "live"] = "local"
    consent: bool = False
    scenario: Literal["normal", "missing", "foreign", "failed"] = "normal"
    auth_case: Literal["sigv4", "bearer", "wif", "foundry", "gateway"] = "bearer"
    model_case: Literal["alias", "profile", "region"] = "profile"


class CloudReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: str
    provider: str
    lane: str
    run_id: str
    method: str
    path: str
    body_sha256: str
    auth_kind: str
    auth_verdict: bool
    status: int
    kind: str
    route_reason: str
    wire_model: str | None
    canonical_model: str | None
    streaming: bool
    marker_seen: str | None
    message_id: str | None
    upstream_status: int | None


class LocalLane(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    name: str
    provider: str
    wire_model: str
    catalog_status: int
    catalog_models: list[str]
    response_status: int | None
    response_id: str | None
    marker: str
    rejected_statuses: list[int]
    receipts: list[CloudReceipt]
    forwarded: int = Field(ge=0)
    listener_closed: bool


class NativeLane(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    lesson: Literal[45]
    run_id: str
    provider: str
    mode: Literal["live"]
    inspect_only: bool
    auth_case: str
    model_case: str
    fallback_configured: bool
    auth_probes_required: bool
    auth_probe_statuses: list[int]
    marker: str
    frames: list[dict[str, Any]]
    receipts: list[CloudReceipt]
    forward_diagnostics: list[dict[str, Any]]
    forwarded: int = Field(ge=0)
    closed: bool
    created_at: str
    passed: bool


class CloudResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    action: Literal["catalog", "same", "auth", "models", "failures"]
    mode: Literal["local", "live"]
    scenario: Literal["normal", "missing", "foreign", "failed"]
    auth_case: Literal["sigv4", "bearer", "wif", "foundry", "gateway"]
    model_case: Literal["alias", "profile", "region"]
    run_id: str
    source_label: str
    lanes: list[LocalLane | NativeLane]
    closed: bool
    experiment_passed: bool
    evidence_bound_hit: bool = False


class StateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    run_id: str
    action: str
    mode: Literal["local", "live"]
    check: Literal["passed"]


def source_excerpts() -> list[dict[str, Any]]:
    items = [("agent_lab/cloud_wire.py", "def verify_sigv4(", "How are signed bytes checked?"),
             ("agent_lab/cloud_proxy.py", "    async def _forward(", "Which credentials reach the upstream?"),
             ("agent_lab/cloud_lab.py", "def evaluate_native(", "What proves the SDK used this response?")]
    output: list[dict[str, Any]] = []
    for path, marker, question in items:
        lines = (ROOT / path).read_text(encoding="utf-8").splitlines()
        start = next(index for index, line in enumerate(lines, 1) if line.startswith(marker))
        end = min(len(lines), start + 22)
        output.append({"file": path, "start_line": start, "end_line": end,
                       "code": "\n".join(lines[start - 1:end]), "question": question})
    return output


def install_cloud_routes(app: FastAPI, runner: RunService) -> None:
    storage = runner.settings.data_dir / "c45-cloud"
    slot = asyncio.Lock()

    async def execute(action: str, raw: dict[str, Any]) -> dict[str, Any]:
        try:
            body = CloudAction.model_validate(raw)
        except ValidationError as exc:
            raise HTTPException(400, exc.errors(include_context=False, include_input=False)) from exc
        if body.mode == "live" and (not body.consent or not runner.settings.enable_live or
                                    body.scenario != "normal"):
            raise HTTPException(403, "Confirm this bounded paid cloud action with live access enabled.")
        if slot.locked():
            raise HTTPException(409, "Another Lesson 45 action is active.")
        async with slot:
            try:
                async with asyncio.timeout(180):
                    return await run(storage, runner.settings, action, body.mode,
                                     scenario=body.scenario, auth_case=body.auth_case,
                                     model_case=body.model_case)
            except TimeoutError as exc:
                raise HTTPException(409, "The cloud action expired.") from exc
            except PermissionError as exc:
                raise HTTPException(403, str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from exc

    @app.get("/api/c45/facts")
    async def get_facts() -> dict[str, Any]:
        return facts()

    @app.get("/api/c45/state", response_model=StateResponse)
    async def get_state() -> dict[str, Any]:
        if slot.locked():
            raise HTTPException(409, "A cloud action is active.")
        try:
            return state(storage)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.get("/api/c45/code")
    async def get_code() -> dict[str, Any]:
        return {"sections": source_excerpts()}

    for action in ACTIONS:
        async def handler(raw: dict[str, Any], selected: str = action) -> dict[str, Any]:
            return await execute(selected, raw)
        app.post("/api/c45/" + action, response_model=CloudResponse)(handler)
