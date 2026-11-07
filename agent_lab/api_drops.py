"""Strict owned lesson 40 build, state, comparison and undo actions."""

import asyncio
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query
from pydantic import Field

from agent_lab.drops_lab import (
    build_live,
    build_prepared,
    cases_live,
    cases_prepared,
    dry,
    state,
    undo,
)
from agent_lab.foundation_models import Inputs
from agent_lab.foundations import source_sections
from agent_lab.runtime import RunService


class Build(Inputs):
    mode: Literal["prepared", "live"] = "prepared"
    scenario: Literal["normal", "missing", "foreign"] = "normal"
    consent: bool = False


class Cases(Inputs):
    build_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    mode: Literal["prepared", "live"] = "prepared"
    recover: bool = False
    scenario: Literal["normal", "missing", "foreign", "duplicate", "interrupted", "tampered"] = "normal"
    consent: bool = False


class Undo(Inputs):
    build_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    mode: Literal["prepared", "live"] = "prepared"
    turn: Literal[3, 4] = 4
    boundary: Literal["last", "assistant", "tool-use"] = "last"
    consent: bool = False


def install_drops_routes(app: FastAPI, runner: RunService) -> None:
    storage = runner.settings.data_dir / "c40-builds"
    slot = asyncio.Lock()

    async def exclusive(operation: Any, deadline: float = 90) -> Any:
        if slot.locked():
            raise HTTPException(409, "Another lesson 40 operation is active.")
        async with slot:
            try:
                async with asyncio.timeout(deadline):
                    return await operation()
            except TimeoutError as exc:
                raise HTTPException(409, "The lesson 40 operation expired.") from exc
            except (ValueError, PermissionError) as exc:
                raise HTTPException(409 if isinstance(exc, ValueError) else 403, str(exc)) from exc

    @app.post("/api/c40/dry")
    async def dry_route(body: Inputs) -> dict[str, Any]:
        return dry(runner.settings)

    @app.post("/api/c40/build")
    async def build_route(body: Build) -> dict[str, Any]:
        if body.mode == "live" and not body.consent:
            raise HTTPException(403, "Confirm this fresh bounded paid build explicitly.")
        if body.mode == "live" and body.scenario != "normal":
            raise HTTPException(422, "Fault scenarios are prepared-only.")

        async def run() -> dict[str, Any]:
            return await (build_live(storage, runner.settings) if body.mode == "live"
                          else build_prepared(storage, body.scenario))

        return await exclusive(run)

    @app.get("/api/c40/state")
    async def state_route(build_id: str | None = Query(default=None, pattern=r"^[0-9a-f]{32}$")) -> dict[str, Any]:
        try:
            return state(storage, build_id)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.post("/api/c40/cases")
    async def cases_route(body: Cases) -> dict[str, Any]:
        if body.mode == "live" and not body.consent:
            raise HTTPException(403, "Confirm this fresh bounded paid comparison explicitly.")
        if body.mode == "live" and body.scenario != "normal":
            raise HTTPException(422, "Fault scenarios are prepared-only.")

        async def run() -> dict[str, Any]:
            if body.mode == "live":
                return await cases_live(storage, body.build_id, runner.settings, body.recover)
            source = state(storage, body.build_id)
            if source["manifest"]["mode"] != "prepared":
                raise ValueError("Prepared comparisons require an owned prepared build.")
            return await cases_prepared(storage, body.build_id, body.recover, body.scenario)

        return await exclusive(run)

    @app.post("/api/c40/undo")
    async def undo_route(body: Undo) -> dict[str, Any]:
        if body.mode == "live" and not body.consent:
            raise HTTPException(403, "Confirm this fresh bounded paid undo explicitly.")

        async def run() -> dict[str, Any]:
            return await undo(storage, body.build_id, body.mode, body.turn,
                              body.boundary, runner.settings)

        return await exclusive(run)

    @app.get("/api/c40/code")
    async def code() -> dict[str, Any]:
        return {"sections": source_sections(40)}
