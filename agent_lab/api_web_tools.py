"""Strict lesson 42 web-tool actions with fresh live consent."""

import asyncio
from typing import Any, Literal

from fastapi import FastAPI, HTTPException

from agent_lab.foundation_models import Inputs
from agent_lab.foundations import source_sections
from agent_lab.runtime import RunService
from agent_lab.web_tools_lab import facts, run, state


class Action(Inputs):
    mode: Literal["prepared", "live"] = "prepared"
    scenario: Literal["normal", "missing", "foreign", "failed"] = "normal"
    consent: bool = False


class FetchAction(Action):
    page: Literal["page", "json", "redirect", "missing"] = "page"


def install_web_tool_routes(app: FastAPI, runner: RunService) -> None:
    storage = runner.settings.data_dir / "c42-web"
    slot = asyncio.Lock()

    async def exclusive(operation: Any) -> Any:
        if slot.locked():
            raise HTTPException(409, "Another lesson 42 operation is active.")
        async with slot:
            try:
                async with asyncio.timeout(120):
                    return await operation()
            except TimeoutError as exc:
                raise HTTPException(409, "The lesson 42 operation expired.") from exc
            except (ValueError, PermissionError) as exc:
                raise HTTPException(409 if isinstance(exc, ValueError) else 403, str(exc)) from exc

    def allowed(body: Action) -> None:
        if body.mode == "live" and not body.consent:
            raise HTTPException(403, "Confirm this fresh bounded paid web action explicitly.")
        if body.mode == "live" and body.scenario != "normal":
            raise HTTPException(422, "Fault scenarios are prepared only.")

    @app.get("/api/c42/facts")
    async def facts_route() -> dict[str, Any]:
        return facts()

    @app.get("/api/c42/state")
    async def state_route() -> dict[str, Any]:
        if slot.locked():
            raise HTTPException(409, "A lesson 42 action is active.")
        try:
            return state(storage)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.post("/api/c42/basics")
    async def basics(body: Action) -> dict[str, Any]:
        allowed(body)
        return await exclusive(lambda: run(storage, runner.settings, "basics", body.mode,
                                           scenario=body.scenario))

    @app.post("/api/c42/fetch-lab")
    async def fetch_lab(body: FetchAction) -> dict[str, Any]:
        allowed(body)
        return await exclusive(lambda: run(storage, runner.settings, "fetch-lab", body.mode,
                                           body.page, body.scenario))

    @app.post("/api/c42/injection")
    async def injection(body: Action) -> dict[str, Any]:
        allowed(body)
        return await exclusive(lambda: run(storage, runner.settings, "injection", body.mode,
                                           scenario=body.scenario))

    @app.post("/api/c42/guard")
    async def guard(body: Action) -> dict[str, Any]:
        allowed(body)
        return await exclusive(lambda: run(storage, runner.settings, "guard", body.mode,
                                           scenario=body.scenario))

    @app.post("/api/c42/research")
    async def research(body: Action) -> dict[str, Any]:
        allowed(body)
        return await exclusive(lambda: run(storage, runner.settings, "research", body.mode,
                                           scenario=body.scenario))

    @app.get("/api/c42/code")
    async def code() -> dict[str, Any]:
        return {"sections": source_sections(42)}
