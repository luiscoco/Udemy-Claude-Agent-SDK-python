"""FastAPI transport; the lesson implementation is shared with CLI and NiceGUI."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agent_lab.config import ROOT
from agent_lab.curriculum import LESSONS, get_lesson
from agent_lab.exercises import exercise_context
from agent_lab.learning import course, guide
from agent_lab.models import LessonError, lesson_request
from agent_lab.runtime import BusyError, RunService
from agent_lab.tutor import TutorAnswer, TutorRequest, TutorService


class AnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    control_token: str = Field(min_length=1, max_length=100)
    question_id: str = Field(min_length=1, max_length=40)
    answers: dict[str, str]


def create_app(service: RunService | None = None, with_ui: bool = True) -> FastAPI:
    # Per-request INFO lines from in-process MCP servers and HTTP clients bury the app's own
    # log; warnings and errors from them still appear.
    for name in ("mcp", "httpx"):
        logging.getLogger(name).setLevel(logging.WARNING)
    runner = service or RunService()
    from agent_lab.api_streaming import StreamRegistry, install_stream_routes

    streams = StreamRegistry(runner)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        await streams.close()
        await runner.close()

    app = FastAPI(title="Python Claude Agent SDK Lab", lifespan=lifespan)
    app.state.runner = runner
    app.state.input_streams = streams
    install_stream_routes(app, streams)
    tutor = app.state.tutor = TutorService(runner.settings)

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "lessons": len(LESSONS),
            "live_enabled": runner.settings.enable_live,
            "active_runs": len(runner.active),
        }

    @app.get("/api/lessons")
    async def lessons() -> list[dict[str, Any]]:
        return [lesson.model_dump() for lesson in LESSONS.values()]

    @app.get("/agent_lab/{source_path:path}", response_class=PlainTextResponse)
    async def source(source_path: str) -> str:
        package = (ROOT / "agent_lab").resolve()
        target = (package / source_path).resolve()
        if not target.is_relative_to(package) or target.suffix != ".py" or not target.is_file():
            raise HTTPException(404, "Unknown course source file.")
        return target.read_text(encoding="utf-8")

    @app.get("/README.md", response_class=PlainTextResponse)
    async def readme() -> str:
        return (ROOT / "README.md").read_text(encoding="utf-8")

    @app.get("/api/lessons/{lesson_id}")
    async def lesson(lesson_id: int) -> dict[str, Any]:
        try:
            return get_lesson(lesson_id).model_dump()
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc

    def start(lesson_id: int, body: dict[str, Any]):
        try:
            return runner.start(lesson_id, lesson_request(lesson_id, body))
        except ValidationError as exc:
            raise HTTPException(422, exc.errors(include_context=False, include_input=False)) from exc
        except LessonError as exc:
            raise HTTPException(422, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc
        except BusyError as exc:
            raise HTTPException(429, str(exc)) from exc

    @app.post("/api/lessons/{lesson_id}/run")
    async def run(lesson_id: int, body: dict[str, Any]) -> dict[str, Any]:
        handle = start(lesson_id, body)
        events = [event.model_dump() async for event in runner.events(handle)]
        return {"run_id": handle.id, "events": events}

    @app.post("/api/lessons/{lesson_id}/stream")
    async def stream(lesson_id: int, body: dict[str, Any]) -> StreamingResponse:
        handle = start(lesson_id, body)

        async def output():
            async for event in runner.events(handle):
                yield f"event: {event.kind}\ndata: {event.model_dump_json()}\n\n"

        return StreamingResponse(
            output(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/course")
    async def course_data() -> dict[str, Any]:
        return course().model_dump()

    @app.get("/api/lessons/{lesson_id}/guide")
    async def lesson_guide(lesson_id: int) -> dict[str, Any]:
        try:
            return guide(lesson_id).model_dump()
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.get("/api/tutor/models")
    async def tutor_models() -> dict[str, Any]:
        return {"live_enabled": runner.settings.enable_live, "models": await tutor.models()}

    @app.post("/api/lessons/{lesson_id}/tutor")
    async def ask_tutor(lesson_id: int, body: TutorRequest) -> TutorAnswer:
        try:
            lesson = get_lesson(lesson_id)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc
        try:
            return await tutor.answer(lesson_id, body, exercise_context(lesson.exercise))
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except LessonError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post("/api/runs/{run_id}/answer")
    async def answer(run_id: str, body: AnswerRequest) -> dict[str, str]:
        try:
            runner.answer(run_id, body.control_token, body.question_id, body.answers)
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"status": "answered"}

    @app.get("/api/runs/{run_id}/artifacts/{filename}")
    async def artifact(run_id: str, filename: str) -> FileResponse:
        try:
            path = runner.artifact(run_id, filename)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc
        if not path.is_file():
            raise HTTPException(404, "Artifact not found.")
        return FileResponse(path, filename=filename)

    @app.websocket("/api/lessons/{lesson_id}/ws")
    async def websocket(websocket: WebSocket, lesson_id: int) -> None:
        await websocket.accept()
        handle = None
        tasks: list[asyncio.Task[Any]] = []
        try:
            body = await websocket.receive_json()
            handle = start(lesson_id, body)

            async def send():
                async for event in runner.events(handle):
                    await websocket.send_json(event.model_dump())

            async def receive():
                while True:
                    message = await websocket.receive_json()
                    if message == {"action": "cancel"}:
                        await runner.cancel(handle)
                        return
                    response = AnswerRequest.model_validate(message)
                    runner.answer(
                        handle.id, response.control_token, response.question_id, response.answers
                    )

            tasks = [asyncio.create_task(send()), asyncio.create_task(receive())]
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        except WebSocketDisconnect:
            pass
        except (ValidationError, HTTPException, PermissionError, ValueError):
            await websocket.close(code=1008)
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if handle:
                await runner.cancel(handle)

    if with_ui:
        from agent_lab.ui import install_ui

        install_ui(app, runner, tutor)
    return app
