"""Strict lesson 43 routes for owned remote MCP scenarios."""

import asyncio
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from pydantic import ValidationError

from agent_lab.foundation_models import Inputs
from agent_lab.foundations import source_sections
from agent_lab.remote_mcp_lab import facts, run, state
from agent_lab.runtime import RunService


class BaseAction(Inputs):
    mode: Literal["local", "live"] = "local"
    consent: bool = False
    scenario: Literal["normal", "missing", "foreign", "failed"] = "normal"


class ResourceAction(BaseAction):
    resource: Literal["runbook", "order", "logo", "widget"] = "runbook"
    transport: Literal["http", "sse"] = "http"


class AgentAction(ResourceAction):
    step: Literal["tool", "resource", "rotate"] = "tool"


def install_remote_mcp_routes(app: FastAPI, runner: RunService) -> None:
    storage = runner.settings.data_dir / "c43-remote-mcp"
    slot = asyncio.Lock()

    def validate(raw: dict[str, Any], shape: type[BaseAction]) -> BaseAction:
        try:
            return shape.model_validate(raw)
        except ValidationError as exc:
            raise HTTPException(400, exc.errors(include_context=False, include_input=False)) from exc

    async def execute(action: str, body: BaseAction, *, transport: str = "http",
                      resource: str = "runbook") -> dict[str, Any]:
        if action not in {"live-tool", "live-resource", "rotation"} and body.mode != "local":
            raise HTTPException(403, "This action is a local host probe.")
        if body.mode == "live" and not body.consent:
            raise HTTPException(403, "Confirm this fresh bounded paid remote MCP action explicitly.")
        if body.mode == "live" and body.scenario != "normal":
            raise HTTPException(400, "Fault scenarios are local only.")
        if slot.locked():
            raise HTTPException(409, "Another lesson 43 operation is active.")
        async with slot:
            try:
                async with asyncio.timeout(120):
                    return await run(storage, runner.settings, action,
                                     "live" if body.mode == "live" else "prepared",
                                     transport, resource, body.scenario)
            except TimeoutError as exc:
                raise HTTPException(409, "The lesson 43 operation expired.") from exc
            except PermissionError as exc:
                raise HTTPException(403, str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from exc

    @app.get("/api/c43/facts")
    async def get_facts() -> dict[str, Any]:
        return facts()

    @app.get("/api/c43/state")
    async def get_state() -> dict[str, Any]:
        if slot.locked():
            raise HTTPException(409, "A lesson 43 action is active.")
        try:
            return state(storage)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc

    def make_base_handler(selected: str) -> Any:
        async def handler(raw: dict[str, Any]) -> dict[str, Any]:
            return await execute(selected, validate(raw, BaseAction))
        return handler

    def make_resource_handler(selected: str) -> Any:
        async def handler(raw: dict[str, Any]) -> dict[str, Any]:
            body = validate(raw, ResourceAction)
            assert isinstance(body, ResourceAction)
            return await execute(selected, body, transport=body.transport, resource=body.resource)
        return handler

    for path in ("auth", "cache", "transports", "toolsets"):
        app.post("/api/c43/" + path)(make_base_handler(path))
    for path in ("resources", "host-read"):
        app.post("/api/c43/" + path)(make_resource_handler(path))

    @app.post("/api/c43/live")
    async def live(raw: dict[str, Any]) -> dict[str, Any]:
        body = validate(raw, AgentAction)
        assert isinstance(body, AgentAction)
        action = {"tool": "live-tool", "resource": "live-resource", "rotate": "rotation"}[body.step]
        return await execute(action, body, transport=body.transport, resource=body.resource)

    @app.get("/api/c43/code")
    async def get_code() -> dict[str, Any]:
        return {"sections": source_sections(43)}
