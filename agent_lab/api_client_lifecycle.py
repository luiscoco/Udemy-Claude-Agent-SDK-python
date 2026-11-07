"""Strict lesson 41 Python client lifecycle actions."""

import asyncio
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query
from pydantic import Field

from agent_lab.client_lifecycle_lab import base, compare, facts, resume, state
from agent_lab.foundation_models import Inputs
from agent_lab.foundations import source_sections
from agent_lab.runtime import RunService


class Action(Inputs):
    mode: Literal["prepared", "live"] = "prepared"
    scenario: Literal["normal", "missing", "foreign", "failed"] = "normal"
    consent: bool = False


class Resume(Action):
    build_id: str = Field(pattern=r"^[0-9a-f]{32}$")


def install_client_lifecycle_routes(app: FastAPI, runner: RunService) -> None:
    storage = runner.settings.data_dir / "c41-builds"
    slot = asyncio.Lock()

    async def exclusive(operation: Any) -> Any:
        if slot.locked():
            raise HTTPException(409, "Another lesson 41 operation is active.")
        async with slot:
            try:
                async with asyncio.timeout(90):
                    return await operation()
            except TimeoutError as exc:
                raise HTTPException(409, "The lesson 41 operation expired.") from exc
            except (ValueError, PermissionError) as exc:
                raise HTTPException(409 if isinstance(exc, ValueError) else 403, str(exc)) from exc

    def allowed(body: Action) -> None:
        if body.mode == "live" and not body.consent:
            raise HTTPException(403, "Confirm this fresh bounded paid action explicitly.")
        if body.mode == "live" and body.scenario != "normal":
            raise HTTPException(422, "Fault scenarios are prepared only.")

    @app.get("/api/c41/facts")
    async def facts_route() -> dict[str, Any]:
        return facts()

    @app.get("/api/c41/state")
    async def state_route(build_id: str | None = Query(default=None, pattern=r"^[0-9a-f]{32}$")) -> dict[str, Any]:
        if slot.locked():
            raise HTTPException(409, "A lesson 41 mutation is active.")
        try:
            return state(storage, build_id)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.post("/api/c41/client")
    async def client_route(body: Action) -> dict[str, Any]:
        allowed(body)
        return await exclusive(lambda: base(storage, runner.settings, body.mode, body.scenario))

    @app.post("/api/c41/resume")
    async def resume_route(body: Resume) -> dict[str, Any]:
        allowed(body)
        return await exclusive(lambda: resume(storage, body.build_id, runner.settings, body.mode, body.scenario))

    @app.post("/api/c41/compare")
    async def compare_route(body: Action) -> dict[str, Any]:
        allowed(body)
        return await exclusive(lambda: compare(storage, runner.settings, body.mode, body.scenario))

    @app.get("/api/c41/code")
    async def code() -> dict[str, Any]:
        return {"sections": source_sections(41)}
