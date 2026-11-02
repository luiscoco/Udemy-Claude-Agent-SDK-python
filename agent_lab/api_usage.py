"""Strict lesson 15 run/session commands; usage/context inspection never sends a prompt."""

from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import Field, ValidationError

from agent_lab.api_thinking import DraftKey, RunResult
from agent_lab.foundation_models import Inputs, UsageInputs
from agent_lab.models import LessonError, lesson_request
from agent_lab.runtime import BusyError, RunService
from agent_lab.usage_sessions import UsageSessions


class UsageQuery(Inputs):
    mode: Literal["offline", "live"] = "offline"
    max_turns: int = Field(default=4, ge=1, le=12)
    max_budget_usd: float = Field(default=0.1, gt=0, le=1, allow_inf_nan=False)
    consent: bool = False
    prompt: str = Field(
        default="Answer briefly: what is a token budget?", min_length=1, max_length=10000
    )
    lesson_options: UsageInputs = Field(default_factory=UsageInputs)
    scenario: Literal[
        "success",
        "missing-evidence",
        "wrong-identity",
        "missing-usage",
        "invalid-usage",
        "turn-limit",
        "budget-limit",
        "interrupted",
    ] = "success"

    def request(self):
        if self.mode == "live" and not self.consent:
            raise PermissionError("Authorize this paid run with consent=true.")
        return lesson_request(15, self.model_dump(exclude={"consent"}))


class UsageSend(DraftKey):
    prompt: str = Field(min_length=1, max_length=10000)
    consent: bool = False


class UsageSnapshot(Inputs):
    application_handle: str
    mode: Literal["offline", "live"]
    closed: bool
    connection_closed: bool
    busy: bool
    sends: int
    send_limit: int
    meter: list[dict]
    reports: list[dict]
    error: str | None
    scope: str


class OpenUsage(UsageSnapshot):
    control_token: str


class SendUsageResult(Inputs):
    events: list[dict]
    session: UsageSnapshot


class ContextResult(Inputs):
    context: dict
    prompt_sent: bool
    source: str


def install_usage_routes(app: FastAPI, runner: RunService, sessions: UsageSessions) -> None:
    def failure(exc: Exception) -> HTTPException:
        return HTTPException(
            403
            if isinstance(exc, PermissionError)
            else 429
            if isinstance(exc, BusyError)
            else 422
            if isinstance(exc, ValidationError)
            else 409,
            exc.errors(include_context=False, include_input=False)
            if isinstance(exc, ValidationError)
            else str(exc),
        )

    @app.post("/api/c15/run", response_model=RunResult)
    async def run(body: UsageQuery) -> dict:
        try:
            handle = runner.start(15, body.request())
        except (PermissionError, BusyError, LessonError, ValidationError) as exc:
            raise failure(exc) from exc
        return {
            "run_id": handle.id,
            "events": [e.model_dump() async for e in runner.events(handle)],
        }

    @app.post("/api/c15/session", response_model=OpenUsage)
    async def session(body: UsageQuery) -> dict:
        try:
            value = await sessions.open(body.request())
            return value.snapshot() | {"control_token": value.token}
        except (PermissionError, BusyError, LessonError, ValidationError) as exc:
            raise failure(exc) from exc

    @app.post("/api/c15/send", response_model=SendUsageResult)
    async def send(body: UsageSend) -> dict:
        try:
            value = sessions.lookup(body.application_handle, body.control_token)
            if value.request.mode == "live" and not body.consent:
                raise PermissionError("Authorize this paid message with consent=true.")
            return await sessions.command(value, "send", body.prompt)
        except (PermissionError, BusyError, LessonError, ValidationError) as exc:
            raise failure(exc) from exc

    @app.post("/api/c15/context", response_model=ContextResult)
    async def context(body: DraftKey) -> dict:
        try:
            return await sessions.command(
                sessions.lookup(body.application_handle, body.control_token), "context"
            )
        except (PermissionError, LessonError) as exc:
            raise failure(exc) from exc

    @app.post("/api/c15/usage", response_model=UsageSnapshot)
    async def usage(body: DraftKey) -> dict:
        try:
            return sessions.lookup(body.application_handle, body.control_token).snapshot()
        except PermissionError as exc:
            raise failure(exc) from exc

    @app.post("/api/c15/end", response_model=UsageSnapshot)
    async def end(body: DraftKey) -> dict:
        try:
            return await sessions.end(sessions.lookup(body.application_handle, body.control_token))
        except PermissionError as exc:
            raise failure(exc) from exc
