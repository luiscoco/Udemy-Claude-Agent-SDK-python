"""Strict lesson 39 routes for owned project configuration probes."""

import asyncio
from typing import Any, Literal

from fastapi import FastAPI, HTTPException

from agent_lab.config_root_lab import dry_flags, fixture, startup
from agent_lab.foundation_models import Inputs
from agent_lab.foundations import source_sections
from agent_lab.models import LessonError, RunRequest
from agent_lab.runtime import BusyError, RunService


class Origin(Inputs):
    mode: Literal["prepared", "live"] = "prepared"
    cwd: Literal["trusted", "branch", "docs"] = "branch"
    root: Literal["trusted", "branch", "omitted"] = "trusted"
    sources: Literal["project-local", "none"] = "project-local"
    scenario: Literal["success", "missing-evidence", "wrong-identity", "failed", "interrupted",
                      "wrong-hook", "duplicate-hook", "duplicate-result", "missing-command", "changed-fixture"] = "success"
    consent: bool = False


class Takeover(Inputs):
    mode: Literal["prepared", "live"] = "prepared"
    root: Literal["trusted", "omitted"] = "trusted"
    scenario: Literal["success", "missing-evidence", "wrong-identity", "failed", "interrupted",
                      "wrong-hook", "duplicate-hook", "duplicate-result", "changed-fixture", "wrong-effect"] = "success"
    consent: bool = False


class Try(Inputs):
    mode: Literal["prepared", "live", "startup"] = "prepared"
    cwd: Literal["trusted", "branch", "docs"] = "branch"
    root: Literal["trusted", "branch", "omitted", "relative", "missing", "file"] = "trusted"
    sources: Literal["project-local", "none"] = "project-local"
    scenario: Literal["success", "missing-evidence", "wrong-identity", "failed", "interrupted",
                      "wrong-hook", "duplicate-hook", "duplicate-result", "missing-command", "changed-fixture"] = "success"
    consent: bool = False


def install_config_root_routes(app: FastAPI, runner: RunService) -> None:
    lock = asyncio.Lock()

    async def run(mode: str, choices: dict[str, str], scenario: str, consent: bool) -> dict[str, Any]:
        if mode == "live" and not consent:
            raise HTTPException(403, "Confirm the bounded paid origin probe explicitly.")
        if mode == "live" and scenario != "success":
            raise HTTPException(422, "Synthetic negative cases use prepared mode only.")
        if lock.locked():
            raise HTTPException(409, "Another lesson 39 operation is active.")
        async with lock:
            handle = None
            try:
                async with asyncio.timeout(60):
                    handle = runner.start(39, RunRequest(mode="live" if mode == "live" else "offline",
                        lesson_options=choices, scenario=scenario, max_turns=3, max_budget_usd=0.10))
                    report: dict[str, Any] | None = None
                    status = "unknown"
                    error = None
                    async for event in runner.events(handle):
                        if event.kind == "evidence":
                            report = event.data["result"].get("experiment")
                        elif event.kind == "error":
                            error = event.data.get("message")
                        elif event.kind == "done":
                            status = event.data.get("status", "unknown")
                    if report is None:
                        raise HTTPException(409, error or "The probe produced no evidence.")
                    return {"status": status, "experiment": report}
            except (BusyError, LessonError, ValueError) as exc:
                raise HTTPException(409, str(exc)) from exc
            except TimeoutError as exc:
                if handle is not None:
                    await runner.cancel(handle)
                raise HTTPException(409, "The bounded lesson 39 operation expired.") from exc

    @app.post("/api/c39/dry")
    async def dry(body: Inputs) -> dict[str, Any]:
        if lock.locked():
            raise HTTPException(409, "Another lesson 39 operation is active.")
        async with lock:
            import uuid
            try:
                async with asyncio.timeout(60):
                    paths = await fixture(runner.settings.data_dir / "c39-dry" / uuid.uuid4().hex)
                    return dry_flags(paths, runner.settings)
            except TimeoutError as exc:
                raise HTTPException(409, "The dry inspection expired.") from exc

    @app.post("/api/c39/where")
    async def where(body: Origin) -> dict[str, Any]:
        return await run(body.mode, {"action": "where", "cwd": body.cwd,
            "root": body.root, "sources": body.sources}, body.scenario, body.consent)

    @app.post("/api/c39/takeover")
    async def takeover(body: Takeover) -> dict[str, Any]:
        return await run(body.mode, {"action": "takeover", "cwd": "branch",
            "root": body.root, "sources": "project-local"}, body.scenario, body.consent)

    @app.post("/api/c39/try")
    async def try_probe(body: Try) -> dict[str, Any]:
        if body.mode == "startup":
            if body.root not in {"relative", "missing", "file"} or body.scenario != "success":
                raise HTTPException(422, "Startup accepts only fixed invalid roots and the normal scenario.")
            if lock.locked():
                raise HTTPException(409, "Another lesson 39 operation is active.")
            async with lock:
                import uuid

                try:
                    async with asyncio.timeout(60):
                        return {"startup": await startup(runner.settings.data_dir / "c39-startup" / uuid.uuid4().hex,
                                                          body.root, runner.settings)}
                except TimeoutError as exc:
                    raise HTTPException(409, "The startup probe expired.") from exc
        if body.root in {"relative", "missing", "file"}:
            raise HTTPException(422, "Invalid roots require the credential-free startup mode.")
        return await run(body.mode, {"action": "where", "cwd": body.cwd,
            "root": body.root, "sources": body.sources}, body.scenario, body.consent)

    @app.get("/api/c39/code")
    async def code() -> dict[str, Any]:
        return {"sections": source_sections(39)}
