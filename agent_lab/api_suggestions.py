"""Interactive, token-owned prompt suggestion chats for lesson 38."""

import secrets
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from pydantic import Field

from agent_lab.foundation_models import Inputs
from agent_lab.foundations import source_sections
from agent_lab.models import LessonError, RunRequest
from agent_lab.runtime import BusyError, RunService
from agent_lab.suggestions_lab import SuggestionSession, evaluate, suggestion_options

Variant = Literal["enabled", "omitted", "disabled", "env-off", "setting-off",
                  "env-on", "plan", "small", "cached", "uncached", "queued"]


class ChatStart(Inputs):
    mode: Literal["offline", "live"] = "offline"
    variant: Variant = "enabled"
    consent: bool = False


class ChatKey(Inputs):
    run_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    control_token: str = Field(min_length=16, max_length=100)


class ChatSend(ChatKey):
    text: str = Field(min_length=1, max_length=2000)


class Comparison(Inputs):
    mode: Literal["offline", "live"] | None = None
    variant: Variant | None = None
    consent: bool = False


def install_suggestion_routes(app: FastAPI, runner: RunService) -> None:
    active: SuggestionSession | None = None
    history: dict[str, tuple[str, dict[str, Any]]] = {}

    async def close() -> None:
        if active is not None and active.task is not None and not active.task.done():
            active.end()
            try:
                await active.wait()
            except (TimeoutError, RuntimeError):
                pass

    app.state.suggestions_close = close

    def owned(key: ChatKey) -> SuggestionSession:
        if active is None or active.run_id != key.run_id or not secrets.compare_digest(active.token, key.control_token):
            raise HTTPException(403, "Unknown chat or invalid control token.")
        return active

    @app.post("/api/c38/dry")
    async def dry(body: ChatStart) -> dict[str, Any]:
        try:
            opts = suggestion_options(runner.settings.data_dir / "c38-preview",
                                      runner.settings.data_dir / "c38-config-preview",
                                      runner.settings, body.variant, body.mode)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return {"variant": body.variant, "mode": body.mode, "options_only": True,
                "tools": opts.tools, "setting_sources": opts.setting_sources,
                "extra_args": opts.extra_args, "permission_mode": opts.permission_mode,
                "max_turns": opts.max_turns, "max_budget_usd": opts.max_budget_usd}

    @app.post("/api/c38/chat")
    async def chat(body: ChatStart) -> dict[str, Any]:
        nonlocal active
        if active is not None:
            raise HTTPException(409, "A lesson 38 chat is already active.")
        if body.mode == "live" and not body.consent:
            raise HTTPException(403, "Confirm the bounded live chat explicitly.")
        if body.mode == "live" and body.variant in {"setting-off", "cached", "uncached"}:
            raise HTTPException(422, "This variant is comparison-only in the installed Python CLI build.")
        if body.mode == "live":
            from agent_lab.sdk import require_live_access

            try:
                require_live_access(runner.settings)
            except PermissionError as exc:
                raise HTTPException(403, str(exc)) from exc
        base = runner.settings.data_dir / "c38-chats"
        owned_root = base / secrets.token_hex(16)
        session = SuggestionSession(owned_root / "work",
                                    owned_root / "config",
                                    runner.settings, body.mode, body.variant)
        session.start()
        active = session
        return {"run_id": session.run_id, "control_token": session.token,
                "mode": session.mode, "variant": session.variant, "max_inputs": 3,
                "deadline_seconds": 60}

    @app.post("/api/c38/send")
    async def send(body: ChatSend) -> dict[str, Any]:
        session = owned(body)
        try:
            return {"submitted": session.send(body.text), "snapshot": session.snapshot()}
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post("/api/c38/end")
    async def end(body: ChatKey) -> dict[str, Any]:
        nonlocal active
        session = owned(body)
        session.end()
        try:
            await session.wait()
        except TimeoutError:
            pass
        except RuntimeError as exc:
            raise HTTPException(409, str(exc)) from exc
        report = evaluate(session)
        history[session.run_id] = (session.token, report)
        active = None
        return report

    @app.post("/api/c38/status")
    async def status(body: ChatKey) -> dict[str, Any]:
        if active is not None and active.run_id == body.run_id:
            return owned(body).snapshot()
        previous = history.get(body.run_id)
        if previous is None or not secrets.compare_digest(previous[0], body.control_token):
            raise HTTPException(403, "Unknown chat or invalid control token.")
        return previous[1]

    async def comparison(kind: str, body: Comparison) -> dict[str, Any]:
        matrix = {"when": ["enabled", "omitted", "disabled", "queued"],
                  "switches": ["enabled", "env-off", "env-on", "setting-off", "plan", "small"],
                  "cache": ["cached", "uncached"]}[kind]
        if body.mode is None or body.variant is None:
            return {"comparison": kind, "variants": matrix, "metadata_only": True,
                    "note": "Select one variant and mode to start a bounded chat; no background runs occur."}
        if body.variant not in matrix:
            raise HTTPException(422, "Variant is not in this comparison.")
        if body.variant in {"setting-off", "cached", "uncached"}:
            raise HTTPException(422, "This variant is comparison-only in the installed Python CLI build.")
        if body.mode == "live" and not body.consent:
            raise HTTPException(403, "Confirm the bounded live probe explicitly.")
        if body.mode == "live" and body.variant in {"setting-off", "cached", "uncached"}:
            raise HTTPException(422, "This variant is comparison-only in the installed Python CLI build.")
        try:
            handle = runner.start(38, RunRequest(mode=body.mode,
                lesson_options={"variant": body.variant}, max_turns=4, max_budget_usd=0.10))
        except (BusyError, LessonError, ValueError) as exc:
            raise HTTPException(409, str(exc)) from exc
        report: dict[str, Any] | None = None
        error: str | None = None
        async for event in runner.events(handle):
            if event.kind == "evidence":
                report = event.data["result"].get("experiment")
            elif event.kind == "error":
                error = event.data.get("message")
        if report is None:
            raise HTTPException(409, error or "No experiment evidence was produced.")
        return {"comparison": kind, "selected": body.variant, "experiment": report}

    @app.post("/api/c38/when")
    async def when(body: Comparison) -> dict[str, Any]:
        return await comparison("when", body)

    @app.post("/api/c38/switches")
    async def switches(body: Comparison) -> dict[str, Any]:
        return await comparison("switches", body)

    @app.post("/api/c38/cache")
    async def cache(body: Comparison) -> dict[str, Any]:
        return await comparison("cache", body)

    @app.get("/api/c38/code")
    async def code() -> dict[str, Any]:
        return {"sections": source_sections(38)}
