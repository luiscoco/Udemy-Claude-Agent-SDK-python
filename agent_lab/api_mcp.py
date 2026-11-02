"""Strict lesson 13 routes: no-model transport workshops and explicit agent queries."""

import asyncio
from typing import Any, Literal

from fastapi import FastAPI, Header, HTTPException, Query
from pydantic import Field, ValidationError, field_validator

from agent_lab.curriculum import LESSONS
from agent_lab.foundation_models import Inputs, McpInputs
from agent_lab.mcp_lab import McpWorkshops
from agent_lab.models import Event, LessonError, lesson_request
from agent_lab.runtime import BusyError, RunService


class OpenWorkshop(Inputs):
    transport: Literal["stdio", "http", "sdk"] = "sdk"


class WorkshopKey(Inputs):
    application_handle: str = Field(pattern=r"^[0-9a-f]{32}$")
    control_token: str = Field(min_length=16, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")


class CallTool(WorkshopKey):
    tool: Literal["stock", "reserve"] = "stock"
    sku: Literal["notebook", "pen"] = "notebook"
    quantity: int = Field(default=2, ge=1, le=5)


class ToggleServer(WorkshopKey):
    enabled: bool


class SelectServer(WorkshopKey):
    transport: Literal["stdio", "http", "sdk"]


class AgentQuery(Inputs):
    mode: Literal["offline", "live"] = "offline"
    prompt: str = Field(default=LESSONS[13].prompt, min_length=1, max_length=10000)
    max_turns: int = Field(default=4, ge=1, le=12)
    max_budget_usd: float = Field(default=0.1, gt=0, le=1, allow_inf_nan=False)
    lesson_options: McpInputs = Field(default_factory=McpInputs)
    scenario: Literal["success", "missing-evidence", "wrong-identity", "tool-error"] = "success"
    consent: bool = False

    @field_validator("prompt", mode="before")
    @classmethod
    def trim(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value


class OpenedWorkshop(WorkshopKey):
    scope: str


class WorkshopState(Inputs):
    application_handle: str
    transport: Literal["stdio", "http", "sdk"]
    enabled: bool
    closed: bool
    connection_open: bool
    last_probe_connected: bool
    discovered_tools: list[dict]
    timeline: list[dict]
    scope: str


class InventoryState(Inputs):
    stock: dict[str, int]
    reservations: list[dict]


class WorkshopAction(Inputs):
    result: dict
    state: WorkshopState
    inventory: InventoryState


class QueryResult(Inputs):
    run_id: str
    events: list[Event]


def install_mcp_routes(app: FastAPI, runner: RunService, workshops: McpWorkshops) -> None:
    def failure(exc: Exception) -> HTTPException:
        if isinstance(exc, PermissionError):
            return HTTPException(403, str(exc))
        if isinstance(exc, BusyError):
            return HTTPException(429, str(exc))
        return HTTPException(409, str(exc))

    @app.post("/api/c13/session", response_model=OpenedWorkshop)
    async def open_session(body: OpenWorkshop) -> dict:
        try:
            item = await workshops.start(body.transport)
            return {
                "application_handle": item.id,
                "control_token": item.token,
                "scope": "Direct MCP workshop; no model call.",
            }
        except LessonError as exc:
            raise failure(exc) from exc

    def lookup(body: WorkshopKey):
        try:
            return workshops.lookup(body.application_handle, body.control_token)
        except PermissionError as exc:
            raise failure(exc) from exc

    @app.post("/api/c13/log", response_model=WorkshopState)
    async def log(body: WorkshopKey) -> dict:
        return lookup(body).snapshot()

    @app.post("/api/c13/mcp")
    async def mcp(body: WorkshopKey) -> dict:
        item = lookup(body)
        return {
            "configured": {"inventory": {"type": item.transport}},
            "enabled": item.enabled,
            "scope": "Configuration inspection only; not proof of connection or invocation.",
        }

    @app.get("/api/c13/stock", response_model=InventoryState)
    async def stock(
        application_handle: str = Query(pattern=r"^[0-9a-f]{32}$"),
        x_control_token: str = Header(min_length=16, max_length=100, pattern=r"^[A-Za-z0-9_-]+$"),
    ) -> dict:
        item = lookup(
            WorkshopKey(application_handle=application_handle, control_token=x_control_token)
        )
        async with item.lock:
            return await asyncio.to_thread(item.inventory.read)

    async def operation(body: WorkshopKey, action: str, arguments: dict | None = None) -> dict:
        item = lookup(body)
        try:
            result = await item.operation(action, arguments)
            return {
                "result": result,
                "state": item.snapshot(),
                "inventory": await asyncio.to_thread(item.inventory.read),
            }
        except LessonError as exc:
            raise failure(exc) from exc

    @app.post("/api/c13/stock/reset", response_model=WorkshopAction)
    async def reset(body: WorkshopKey) -> dict:
        return await operation(body, "reset")

    @app.post("/api/c13/status", response_model=WorkshopAction)
    async def status(body: WorkshopKey) -> dict:
        return await operation(body, "status")

    @app.post("/api/c13/reconnect", response_model=WorkshopAction)
    async def reconnect(body: WorkshopKey) -> dict:
        return await operation(body, "reconnect")

    @app.post("/api/c13/end", response_model=WorkshopAction)
    async def end(body: WorkshopKey) -> dict:
        return await operation(body, "end")

    @app.post("/api/c13/toggle", response_model=WorkshopAction)
    async def toggle(body: ToggleServer) -> dict:
        return await operation(body, "toggle", {"enabled": body.enabled})

    @app.post("/api/c13/set-servers", response_model=WorkshopAction)
    async def set_servers(body: SelectServer) -> dict:
        return await operation(body, "set-servers", {"transport": body.transport})

    @app.post("/api/c13/send", response_model=WorkshopAction)
    async def send(body: CallTool) -> dict:
        arguments = {"sku": body.sku, "quantity": body.quantity} if body.tool == "reserve" else {}
        return await operation(body, "call", {"tool": body.tool, "arguments": arguments})

    @app.post("/api/c13/query", response_model=QueryResult)
    async def query(body: AgentQuery) -> dict:
        if body.mode == "live" and not body.consent:
            raise HTTPException(403, "Authorize this bounded paid query with consent=true.")
        try:
            request = lesson_request(13, body.model_dump(exclude={"consent"}))
            handle = runner.start(13, request)
        except ValidationError as exc:
            raise HTTPException(
                422, exc.errors(include_context=False, include_input=False)
            ) from exc
        except LessonError as exc:
            raise HTTPException(422, str(exc)) from exc
        except (PermissionError, BusyError) as exc:
            raise failure(exc) from exc
        return {
            "run_id": handle.id,
            "events": [event.model_dump() async for event in runner.events(handle)],
        }
