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
    from agent_lab.api_mcp import install_mcp_routes
    from agent_lab.mcp_lab import McpWorkshops

    mcp_workshops = McpWorkshops(runner.settings)
    from agent_lab.api_thinking import ThinkingSessions, install_thinking_routes

    thinking_sessions = ThinkingSessions(runner)
    from agent_lab.api_cache import install_cache_routes
    from agent_lab.api_client_lifecycle import install_client_lifecycle_routes
    from agent_lab.api_cloud import install_cloud_routes
    from agent_lab.api_config_root import install_config_root_routes
    from agent_lab.api_debugging import install_debugging_routes
    from agent_lab.api_desk import install_desk_routes
    from agent_lab.api_drops import install_drops_routes
    from agent_lab.api_evals import install_evals_routes
    from agent_lab.api_gate import install_gate_routes
    from agent_lab.api_hardening import install_hardening_routes
    from agent_lab.api_headless import install_headless_routes
    from agent_lab.api_offline import install_offline_routes
    from agent_lab.api_orchestra import install_orchestra_routes
    from agent_lab.api_remote_mcp import install_remote_mcp_routes
    from agent_lab.api_spawn import install_spawn_routes
    from agent_lab.api_store import install_store_routes
    from agent_lab.api_suggestions import install_suggestion_routes
    from agent_lab.api_teams import install_team_routes
    from agent_lab.api_telemetry import install_telemetry_routes
    from agent_lab.api_tool_design import install_tool_design_routes
    from agent_lab.api_upgrading import install_upgrading_routes
    from agent_lab.api_usage import install_usage_routes
    from agent_lab.api_web_tools import install_web_tool_routes
    from agent_lab.api_worktrees import install_worktree_routes
    from agent_lab.usage_sessions import UsageSessions

    usage_sessions = UsageSessions(runner.settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        await streams.close()
        await runner.close()
        await mcp_workshops.close()
        await thinking_sessions.close()
        await usage_sessions.close()
        await app.state.suggestions_close()

    app = FastAPI(title="Python Claude Agent SDK Lab", lifespan=lifespan)
    app.state.runner = runner
    app.state.input_streams = streams
    install_stream_routes(app, streams)
    app.state.mcp_workshops = mcp_workshops
    install_mcp_routes(app, runner, mcp_workshops)
    app.state.thinking_sessions = thinking_sessions
    install_thinking_routes(app, thinking_sessions)
    app.state.usage_sessions = usage_sessions
    install_usage_routes(app, runner, usage_sessions)
    install_store_routes(app, runner)
    install_spawn_routes(app, runner)
    install_gate_routes(app, runner)
    install_config_root_routes(app, runner)
    install_client_lifecycle_routes(app, runner)
    install_web_tool_routes(app, runner)
    install_remote_mcp_routes(app, runner)
    install_telemetry_routes(app, runner)
    install_cloud_routes(app, runner)
    install_cache_routes(app, runner)
    install_orchestra_routes(app, runner)
    install_hardening_routes(app, runner)
    install_headless_routes(app, runner)
    install_desk_routes(app, runner)
    install_evals_routes(app, runner)
    install_debugging_routes(app, runner)
    install_tool_design_routes(app, runner)
    install_upgrading_routes(app)
    install_team_routes(app, runner)
    install_worktree_routes(app, runner)
    install_offline_routes(app, runner)
    install_drops_routes(app, runner)
    install_suggestion_routes(app, runner)
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
