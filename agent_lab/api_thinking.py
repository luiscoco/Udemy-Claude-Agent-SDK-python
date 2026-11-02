"""Lesson 14 comparison runs and token-scoped drafts; edits do not call a model."""

import asyncio
import secrets
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from pydantic import Field, ValidationError, field_validator

from agent_lab.curriculum import LESSONS
from agent_lab.foundation_models import Inputs, ThinkingInputs
from agent_lab.models import Event, LessonError, lesson_request
from agent_lab.runtime import BusyError, RunHandle, RunService
from agent_lab.thinking import plan_lanes
from agent_lab.thinking_models import ModelMetadata


class ThinkingQuery(Inputs):
    mode: Literal["offline", "live"] = "offline"
    prompt: str = Field(default=LESSONS[14].prompt, min_length=1, max_length=10000)
    max_turns: int = Field(default=4, ge=1, le=12)
    max_budget_usd: float = Field(default=0.1, gt=0, le=1, allow_inf_nan=False)
    lesson_options: ThinkingInputs = Field(default_factory=ThinkingInputs)
    scenario: Literal[
        "success",
        "missing-evidence",
        "wrong-identity",
        "missing-effort",
        "unsupported",
        "model-error",
        "interrupted",
    ] = "success"
    consent: bool = False

    @field_validator("prompt", mode="before")
    @classmethod
    def trim(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    def request(self):
        if self.mode == "live" and not self.consent:
            raise PermissionError("Authorize this paid run with consent=true.")
        return lesson_request(14, self.model_dump(exclude={"consent"}))


class DraftKey(Inputs):
    application_handle: str = Field(pattern=r"^[0-9a-f]{32}$")
    control_token: str = Field(min_length=16, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")


class SendDraft(DraftKey):
    consent: bool = False
    authorize_comparison: bool = False


class ChangeModel(DraftKey):
    model: str | None = Field(
        default=None, min_length=1, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$"
    )


class ChangeEffort(DraftKey):
    effort: Literal["low", "medium", "high", "xhigh", "max"] | None


class ChangeThinking(DraftKey):
    thinking: Literal["disabled", "adaptive", "enabled"]
    budget_tokens: int = Field(default=4000, ge=1024, le=16384)
    display: Literal["default", "summarized", "omitted"] = "default"


class RunResult(Inputs):
    run_id: str
    events: list[Event]


@dataclass
class ComparisonDraft:
    id: str
    token: str
    query: ThinkingQuery
    closed: bool = False
    revision: int = 0
    sends: int = 0
    handle: RunHandle | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    created: float = field(default_factory=time.monotonic)

    def snapshot(self) -> dict:
        return {
            "application_handle": self.id,
            "closed": self.closed,
            "revision": self.revision,
            "sends": self.sends,
            "prompt": self.query.prompt,
            "mode": self.query.mode,
            "lesson_options": self.query.lesson_options.model_dump(),
            "scope": "Configuration draft. Edits affect the next fresh run; no persistent live CLI or runtime effort/thinking mutation is claimed.",
        }


class ThinkingSessions:
    def __init__(self, runner: RunService) -> None:
        self.runner = runner
        self.drafts: dict[str, ComparisonDraft] = {}
        self.metadata = ModelMetadata(runner.settings)

    def open(self, query: ThinkingQuery) -> ComparisonDraft:
        plan_lanes(query.lesson_options.model_dump(), self.runner.settings.model)
        for draft in self.drafts.values():
            if time.monotonic() - draft.created > 600 and not draft.handle:
                draft.closed = True
        if sum(not d.closed for d in self.drafts.values()) >= 4:
            raise BusyError("All comparison draft slots are occupied.")
        if len(self.drafts) >= 32:
            oldest = next((key for key, value in self.drafts.items() if value.closed), None)
            if oldest is None:
                raise BusyError("The comparison draft archive is full.")
            del self.drafts[oldest]
        identity = uuid.uuid4().hex
        draft = ComparisonDraft(identity, secrets.token_urlsafe(24), query.model_copy(deep=True))
        self.drafts[identity] = draft
        return draft

    def lookup(self, key: DraftKey) -> ComparisonDraft:
        draft = self.drafts.get(key.application_handle)
        if draft is None or not secrets.compare_digest(
            draft.token.encode(), key.control_token.encode()
        ):
            raise PermissionError("Unknown comparison draft or invalid control token.")
        if time.monotonic() - draft.created > 600 and not draft.handle:
            draft.closed = True
        return draft

    async def edit(self, key: DraftKey, values: dict) -> dict:
        draft = self.lookup(key)
        async with draft.lock:
            if draft.closed or draft.handle:
                raise LessonError(
                    "The draft is closed or a run is active. No settings were changed."
                )
            selected = ThinkingInputs.model_validate(
                draft.query.lesson_options.model_dump() | values
            )
            plan_lanes(selected.model_dump(), self.runner.settings.model)
            draft.query.lesson_options = selected
            draft.revision += 1
            draft.created = time.monotonic()
            return draft.snapshot()

    async def send(self, body: SendDraft) -> dict:
        draft = self.lookup(body)
        async with draft.lock:
            if draft.closed or draft.handle or draft.sends >= 4:
                raise LessonError("This draft is closed, busy or has reached its four-run limit.")
            query = draft.query.model_copy(deep=True)
            query.consent = body.consent
            query.lesson_options.authorize_comparison = body.authorize_comparison
            handle = self.runner.start(14, query.request())
            draft.handle = handle
            draft.sends += 1
        try:
            return {
                "run_id": handle.id,
                "events": [event.model_dump() async for event in self.runner.events(handle)],
            }
        finally:
            async with draft.lock:
                draft.handle = None
                draft.created = time.monotonic()

    async def end(self, key: DraftKey) -> dict:
        draft = self.lookup(key)
        async with draft.lock:
            draft.closed = True
            handle = draft.handle
        if handle:
            await self.runner.cancel(handle)
        return draft.snapshot()

    async def close(self) -> None:
        for draft in self.drafts.values():
            draft.closed = True
            if draft.handle:
                await self.runner.cancel(draft.handle)


def install_thinking_routes(app: FastAPI, sessions: ThinkingSessions) -> None:
    def failure(exc: Exception) -> HTTPException:
        if isinstance(exc, PermissionError):
            return HTTPException(403, str(exc))
        if isinstance(exc, BusyError):
            return HTTPException(429, str(exc))
        if isinstance(exc, ValidationError):
            return HTTPException(422, exc.errors(include_context=False, include_input=False))
        return HTTPException(409, str(exc))

    @app.get("/api/c14/models")
    async def models() -> dict:
        return await sessions.metadata.inspect()

    @app.post("/api/c14/run", response_model=RunResult)
    async def run(body: ThinkingQuery) -> dict:
        try:
            handle = sessions.runner.start(14, body.request())
        except (PermissionError, BusyError, LessonError, ValidationError) as exc:
            raise failure(exc) from exc
        return {
            "run_id": handle.id,
            "events": [event.model_dump() async for event in sessions.runner.events(handle)],
        }

    @app.post("/api/c14/session")
    async def session(body: ThinkingQuery) -> dict:
        try:
            draft = sessions.open(body)
            return draft.snapshot() | {"control_token": draft.token}
        except (BusyError, LessonError, ValidationError) as exc:
            raise failure(exc) from exc

    @app.post("/api/c14/send", response_model=RunResult)
    async def send(body: SendDraft) -> dict:
        try:
            return await sessions.send(body)
        except (PermissionError, BusyError, LessonError, ValidationError) as exc:
            raise failure(exc) from exc

    @app.post("/api/c14/model")
    async def model(body: ChangeModel) -> dict:
        try:
            return await sessions.edit(body, {"model": body.model})
        except (PermissionError, LessonError, ValidationError) as exc:
            raise failure(exc) from exc

    @app.post("/api/c14/effort")
    async def effort(body: ChangeEffort) -> dict:
        try:
            return await sessions.edit(body, {"effort": body.effort})
        except (PermissionError, LessonError, ValidationError) as exc:
            raise failure(exc) from exc

    @app.post("/api/c14/thinking")
    async def thinking(body: ChangeThinking) -> dict:
        try:
            return await sessions.edit(
                body,
                {
                    "thinking": body.thinking,
                    "budget_tokens": body.budget_tokens,
                    "display": body.display,
                },
            )
        except (PermissionError, LessonError, ValidationError) as exc:
            raise failure(exc) from exc

    @app.post("/api/c14/end")
    async def end(body: DraftKey) -> dict:
        try:
            return await sessions.end(body)
        except (PermissionError, LessonError) as exc:
            raise failure(exc) from exc
