"""Token-scoped lesson 12 session routes. Context inspection never calls a model."""

import asyncio
import secrets
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from agent_lab.curriculum import LESSONS
from agent_lab.foundation_models import StreamingInputs
from agent_lab.models import LessonError, RunRequest, lesson_request
from agent_lab.runtime import BusyError

if TYPE_CHECKING:
    from agent_lab.runtime import RunHandle, RunService


class StartStream(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    mode: Literal["offline", "live"] = "offline"
    prompt: str = Field(default=LESSONS[12].prompt, min_length=1, max_length=10000)
    follow_up: str = Field(default=RunRequest().follow_up, min_length=1, max_length=2000)
    max_turns: int = Field(default=4, ge=1, le=12)
    max_budget_usd: float = Field(default=0.10, gt=0, le=1, allow_inf_nan=False)
    scenario: Literal["success", "missing-evidence", "wrong-identity", "interrupted"] = "success"
    lesson_options: StreamingInputs = Field(default_factory=StreamingInputs)
    consent: bool = False

    @field_validator("prompt", "follow_up", mode="before")
    @classmethod
    def trim(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    def request(self, interactive: bool) -> RunRequest:
        if self.mode == "live" and not self.consent:
            raise PermissionError("Authorize this bounded paid session with consent=true.")
        data = self.model_dump(exclude={"consent"})
        selected = StreamingInputs.model_validate(data["lesson_options"]).model_dump()
        data["lesson_options"] = dict(selected, interactive=interactive)
        return lesson_request(12, data)


class StreamKey(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    application_handle: str = Field(pattern=r"^[0-9a-f]{32}$")
    control_token: str = Field(min_length=16, max_length=100)


class SendInput(StreamKey):
    text: str = Field(min_length=1, max_length=10000)

    @field_validator("text", mode="before")
    @classmethod
    def trim(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value


class ModelInput(StreamKey):
    model: Literal["haiku", "sonnet"]


class PermissionInput(StreamKey):
    permission_mode: Literal["default", "plan"]


class OpenedStream(BaseModel):
    application_handle: str
    control_token: str
    mode: Literal["offline", "live"]
    message_limit: int


class StreamContext(BaseModel):
    status: str
    state: dict[str, Any]
    evidence: dict[str, Any] | None
    error: str


@dataclass
class ManagedStream:
    handle: "RunHandle"
    task: asyncio.Task[None] | None = None
    status: str = "running"
    evidence: dict[str, Any] | None = None
    error: str = ""


class StreamRegistry:
    def __init__(self, runner: "RunService") -> None:
        self.runner = runner
        self.sessions: dict[str, ManagedStream] = {}

    def lookup(self, key: StreamKey) -> ManagedStream:
        item = self.sessions.get(key.application_handle)
        if item is None or not secrets.compare_digest(item.handle.token, key.control_token):
            raise PermissionError("Unknown session or invalid control token.")
        return item

    async def start(self, body: StartStream, interactive: bool) -> OpenedStream:
        request = body.request(interactive)
        if len(self.sessions) >= 32:
            for identity, item in list(self.sessions.items()):
                if item.status != "running":
                    del self.sessions[identity]
                    break
            else:
                raise LessonError("The session archive is full.")
        handle = self.runner.start(12, request)
        item = ManagedStream(handle)
        self.sessions[handle.id] = item

        async def drain() -> None:
            async for event in self.runner.events(handle):
                if event.kind == "evidence":
                    item.evidence = event.data["result"]
                elif event.kind == "error":
                    item.error = event.data["message"]
                elif event.kind == "done":
                    item.status = event.data["status"]

        item.task = asyncio.create_task(drain())
        return OpenedStream(
            application_handle=handle.id,
            control_token=handle.token,
            mode=request.mode,
            message_limit=request.lesson_options["max_messages"],
        )

    async def close(self) -> None:
        for item in list(self.sessions.values()):
            await self.runner.cancel(item.handle)
        await asyncio.gather(
            *(item.task for item in self.sessions.values() if item.task), return_exceptions=True
        )


def install_stream_routes(app: FastAPI, registry: StreamRegistry) -> None:
    def failure(exc: Exception) -> HTTPException:
        if isinstance(exc, PermissionError):
            return HTTPException(403, str(exc))
        if isinstance(exc, BusyError):
            return HTTPException(429, str(exc))
        if isinstance(exc, ValidationError):
            return HTTPException(422, exc.errors(include_context=False, include_input=False))
        return HTTPException(409, str(exc))

    @app.post("/api/c12/session", response_model=OpenedStream)
    async def open_session(body: StartStream) -> OpenedStream:
        try:
            return await registry.start(body, True)
        except (PermissionError, LessonError, ValidationError, BusyError) as exc:
            if isinstance(exc, LessonError):
                raise HTTPException(422, str(exc)) from exc
            raise failure(exc) from exc

    @app.post("/api/c12/script", response_model=OpenedStream)
    async def script(body: StartStream) -> OpenedStream:
        try:
            return await registry.start(body, False)
        except (PermissionError, LessonError, ValidationError, BusyError) as exc:
            if isinstance(exc, LessonError):
                raise HTTPException(422, str(exc)) from exc
            raise failure(exc) from exc

    @app.post("/api/c12/context", response_model=StreamContext)
    async def context(body: StreamKey) -> StreamContext:
        try:
            item = registry.lookup(body)
            assert item.handle.input_stream is not None
            return StreamContext(
                status=item.status,
                state=item.handle.input_stream.snapshot(),
                evidence=item.evidence,
                error=item.error,
            )
        except PermissionError as exc:
            raise failure(exc) from exc

    async def action(body: StreamKey, name: str, value: str | None = None) -> StreamContext:
        try:
            item = registry.lookup(body)
            session = item.handle.input_stream
            assert session is not None
            if (
                item.status != "running"
                or not session.ready
                or session.input_closed
                or not session.manual_mode
            ):
                raise LessonError("This session is no longer open for input or controls.")
            if name == "send":
                session.push(value or "")
            elif name == "end":
                session.end()
            else:
                await session.command(name, value)
            await session.publish()
            return await context(body)
        except (PermissionError, LessonError) as exc:
            raise failure(exc) from exc

    @app.post("/api/c12/send", response_model=StreamContext)
    async def send(body: SendInput) -> StreamContext:
        return await action(body, "send", body.text)

    @app.post("/api/c12/model", response_model=StreamContext)
    async def model(body: ModelInput) -> StreamContext:
        return await action(body, "model", body.model)

    @app.post("/api/c12/permission-mode", response_model=StreamContext)
    async def permission(body: PermissionInput) -> StreamContext:
        return await action(body, "permission", body.permission_mode)

    @app.post("/api/c12/end", response_model=StreamContext)
    async def end(body: StreamKey) -> StreamContext:
        return await action(body, "end")
