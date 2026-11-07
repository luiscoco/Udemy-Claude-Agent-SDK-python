"""Strict Lesson 44 telemetry action routes."""

import asyncio
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agent_lab.foundation_models import Inputs
from agent_lab.foundations import source_sections
from agent_lab.runtime import RunService
from agent_lab.telemetry_lab import ACTIONS, facts, run, state


class TelemetryAction(Inputs):
    mode: Literal["local", "live"] = "local"
    consent: bool = False
    scenario: Literal["normal", "missing", "foreign", "failed"] = "normal"


class ReceiptResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: str
    status: int
    signal: Literal["metrics", "logs", "traces"]
    sender: Literal["fixture", "host", "subprocess"]
    lane: str
    bytes: int = Field(ge=0)
    sha256: str
    count: int = Field(ge=0)


class LaneResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    name: str
    signals: list[str] = Field(default_factory=list)
    receipts: list[ReceiptResponse] = Field(default_factory=list)
    records: list[dict[str, Any]] = Field(default_factory=list)
    series: list[dict[str, Any]] = Field(default_factory=list)
    content_seen: bool = False
    raw_body_retained: bool = False
    unauthorized_status: int | None = None
    host_linked: bool = False
    protobuf_probe_status: int | None = None
    protobuf_decoded: bool = False
    auth_attempts: list[dict[str, Any]] = Field(default_factory=list)
    pre: list[dict[str, Any]] = Field(default_factory=list)
    post: list[dict[str, Any]] = Field(default_factory=list)
    calls: list[dict[str, Any]] = Field(default_factory=list)
    results: list[dict[str, Any]] = Field(default_factory=list)
    initialization: list[dict[str, Any]] = Field(default_factory=list)
    terminals: list[dict[str, Any]] = Field(default_factory=list)
    truncated: bool = False


class TelemetryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    action: Literal["signals", "privacy", "tracing", "rich", "exporters", "collector"]
    mode: Literal["local", "live"]
    source_label: str
    scenario: Literal["normal", "missing", "foreign", "failed"]
    run_id: str
    lanes: list[LaneResponse]
    closed: bool
    experiment_passed: bool
    evidence_bound_hit: bool = False


class StateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    run_id: str
    action: str
    mode: Literal["local", "live"]
    check: Literal["passed"]
    created_at: str


def install_telemetry_routes(app: FastAPI, runner: RunService) -> None:
    storage = runner.settings.data_dir / "c44-telemetry"
    slot = asyncio.Lock()

    async def execute(action: str, raw: dict[str, Any]) -> dict[str, Any]:
        try:
            body = TelemetryAction.model_validate(raw)
        except ValidationError as exc:
            raise HTTPException(400, exc.errors(include_context=False, include_input=False)) from exc
        if body.mode == "live" and not body.consent:
            raise HTTPException(403, "Confirm this fresh bounded paid telemetry action.")
        if body.mode == "live" and body.scenario != "normal":
            raise HTTPException(400, "Fault scenarios are local only.")
        if slot.locked():
            raise HTTPException(409, "Another Lesson 44 action is active.")
        async with slot:
            try:
                async with asyncio.timeout(120):
                    return await run(storage, runner.settings, action, body.mode, body.scenario)
            except TimeoutError as exc:
                raise HTTPException(409, "The telemetry action expired.") from exc
            except PermissionError as exc:
                raise HTTPException(403, str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from exc

    @app.get("/api/c44/facts")
    async def get_facts() -> dict[str, Any]:
        return facts()

    @app.get("/api/c44/state", response_model=StateResponse)
    async def get_state() -> dict[str, Any]:
        if slot.locked():
            raise HTTPException(409, "A telemetry action is active.")
        try:
            return state(storage)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.get("/api/c44/code")
    async def get_code() -> dict[str, Any]:
        return {"sections": source_sections(44)}

    for action in ACTIONS:
        async def handler(raw: dict[str, Any], selected: str = action) -> dict[str, Any]:
            return await execute(selected, raw)
        app.post("/api/c44/" + action, response_model=TelemetryResponse)(handler)
