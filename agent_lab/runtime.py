"""Own every run task, bound concurrency and connect cancellation to SDK cleanup."""

import asyncio
import secrets
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from claude_agent_sdk import CLINotFoundError

from agent_lab.config import Settings
from agent_lab.curriculum import get_lesson
from agent_lab.exercises import run_exercise, seed_workspace
from agent_lab.models import Event, LessonError, RunRequest, lesson_request


class BusyError(Exception):
    pass


@dataclass
class RunHandle:
    id: str
    token: str
    queue: asyncio.Queue[Event]
    task: asyncio.Task[None] | None = None
    questions: dict[str, asyncio.Future[dict[str, Any]]] = field(default_factory=dict)


class RunService:
    def __init__(self, settings: Settings | None = None) -> None:
        from dotenv import load_dotenv

        from agent_lab.config import ROOT

        load_dotenv(ROOT / ".env", override=False)
        self.settings = settings or Settings()
        self.active: dict[str, RunHandle] = {}

    def start(self, lesson_id: int, request: RunRequest) -> RunHandle:
        lesson = get_lesson(lesson_id)
        request = lesson_request(lesson_id, request)
        if request.mode == "live" and not self.settings.enable_live:
            raise PermissionError("Enable LAB_ENABLE_LIVE=true before making paid SDK calls.")
        if len(self.active) >= self.settings.max_concurrent_runs:
            raise BusyError("All lesson run slots are occupied.")
        handle = RunHandle(uuid.uuid4().hex, secrets.token_urlsafe(24), asyncio.Queue(maxsize=128))
        self.active[handle.id] = handle
        handle.task = asyncio.create_task(self._produce(handle, lesson.id, request))
        return handle

    async def _produce(self, handle: RunHandle, lesson_id: int, request: RunRequest) -> None:
        lesson = get_lesson(lesson_id)
        run_dir = self.settings.data_dir / handle.id
        work = run_dir / "work"
        status = "completed"

        async def emit(event: Event) -> None:
            await handle.queue.put(event)

        async def ask(arguments: dict[str, Any]) -> dict[str, Any]:
            question_id = uuid.uuid4().hex
            future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
            handle.questions[question_id] = future
            await emit(Event(kind="question", data={"question_id": question_id, **arguments}))
            try:
                async with asyncio.timeout(60):
                    return await future
            finally:
                handle.questions.pop(question_id, None)

        try:
            await emit(
                Event(
                    kind="started",
                    data={
                        "run_id": handle.id,
                        "control_token": handle.token,
                        "lesson_id": lesson.id,
                        "mode": request.mode,
                    },
                )
            )
            async with asyncio.timeout(self.settings.timeout_seconds):
                seed_workspace(work, lesson)
                evidence = (
                    {}
                    if 1 <= lesson.id <= 10 and request.mode == "live"
                    else await run_exercise(work, request, lesson, ask=ask)
                    if 2 <= lesson.id <= 10
                    else await run_exercise(work, request, lesson)
                )
                if not (1 <= lesson.id <= 10 and request.mode == "live"):
                    await emit(
                        Event(
                            kind="evidence",
                            data={
                                "source": "local Python host exercise",
                                "lesson_id": lesson.id,
                                "result": evidence,
                            },
                        )
                    )
                if request.mode == "live":
                    from agent_lab.sdk import run_sdk

                    await run_sdk(
                        lesson,
                        request,
                        work,
                        run_dir / "config",
                        self.settings,
                        evidence,
                        emit,
                        ask,
                    )
        except asyncio.CancelledError:
            status = "cancelled"
        except TimeoutError:
            status = "failed"
            await emit(Event(kind="error", data={"message": "Lesson deadline exceeded."}))
        except (PermissionError, LessonError) as exc:
            status = "failed"
            await emit(Event(kind="error", data={"message": str(exc)}))
        except CLINotFoundError:
            status = "failed"
            await emit(
                Event(
                    kind="error",
                    data={
                        "message": "Claude Code executable not found. Install native Claude Code, restart the app, and run 'agent-lab doctor'. Set LAB_CLI_PATH in .env if needed. See https://code.claude.com/docs/en/setup."
                    },
                )
            )
        except Exception as exc:
            status = "failed"
            # Raw SDK errors and request payloads can contain credentials.
            await emit(
                Event(
                    kind="error",
                    data={
                        "message": f"{type(exc).__name__}: lesson failed. Check installation, credentials and the lesson requirements."
                    },
                )
            )
        finally:
            for future in handle.questions.values():
                future.cancel()
            # Do not block cleanup if a disconnected consumer left a full queue.
            terminal = Event(kind="done", data={"status": status, "run_id": handle.id})
            if handle.queue.full():
                handle.queue.get_nowait()
            handle.queue.put_nowait(terminal)
            self.active.pop(handle.id, None)

    async def events(self, handle: RunHandle) -> AsyncIterator[Event]:
        try:
            while True:
                event = await handle.queue.get()
                yield event
                if event.kind == "done":
                    break
        finally:
            await self.cancel(handle)

    async def cancel(self, handle: RunHandle) -> None:
        if handle.task and not handle.task.done():
            handle.task.cancel()
        if handle.task:
            await handle.task

    def answer(self, run_id: str, token: str, question_id: str, answers: dict[str, Any]) -> None:
        handle = self.active.get(run_id)
        if handle is None or not secrets.compare_digest(handle.token, token):
            raise PermissionError("Unknown run or invalid control token.")
        future = handle.questions.get(question_id)
        if future is None or future.done():
            raise ValueError("This question is no longer pending.")
        if len(answers) > 4 or any(
            not isinstance(value, str) or len(value) > 2000 for value in answers.values()
        ):
            raise ValueError("Invalid question answers.")
        future.set_result(answers)

    async def close(self) -> None:
        await asyncio.gather(*(self.cancel(handle) for handle in list(self.active.values())))

    def artifact(self, run_id: str, filename: str) -> Path:
        if len(run_id) != 32 or any(character not in "0123456789abcdef" for character in run_id):
            raise ValueError("Invalid run id.")
        if filename not in {"incident-report.docx", "pixel.png"}:
            raise ValueError("Unknown artifact.")
        return self.settings.data_dir / run_id / "work" / filename
