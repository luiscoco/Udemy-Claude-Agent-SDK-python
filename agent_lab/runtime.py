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
from agent_lab.streaming import StreamSession


class BusyError(Exception):
    pass


@dataclass
class RunHandle:
    id: str
    token: str
    queue: asyncio.Queue[Event]
    task: asyncio.Task[None] | None = None
    questions: dict[str, asyncio.Future[dict[str, Any]]] = field(default_factory=dict)
    input_stream: StreamSession | None = None


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
        if lesson_id == 14:
            from agent_lab.thinking import plan_lanes

            plan_lanes(request.lesson_options, self.settings.model)
        if request.mode == "live" and not self.settings.enable_live:
            raise PermissionError("Enable LAB_ENABLE_LIVE=true before making paid SDK calls.")
        if len(self.active) >= self.settings.max_concurrent_runs:
            raise BusyError("All lesson run slots are occupied.")
        handle = RunHandle(uuid.uuid4().hex, secrets.token_urlsafe(24), asyncio.Queue(maxsize=128))
        if lesson_id == 12:
            handle.input_stream = StreamSession(handle.id, request.lesson_options["max_messages"])
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
            deadline = max(self.settings.timeout_seconds, 350) if lesson_id == 48 else max(self.settings.timeout_seconds, 180) if lesson_id in {45, 46, 47, 49, 50, 52} else max(self.settings.timeout_seconds, 100) if lesson_id in {56, 57} else max(self.settings.timeout_seconds, 75) if lesson_id in {53, 54} else self.settings.timeout_seconds
            async with asyncio.timeout(deadline):
                if lesson.id == 57:
                    from agent_lab.headless_native import bundled_cli, private_key
                    from agent_lab.worktrees_lab import RunInput, run_workshop

                    selected_worktrees = RunInput.model_validate(request.lesson_options)
                    if request.mode == "live":
                        if not self.settings.enable_live or not selected_worktrees.consent:
                            raise LessonError("Lesson 57 live mode requires fresh consent and enabled access.")
                        bundled_cli()
                        private_key()
                    worktree_report = await run_workshop(selected_worktrees, self.settings.data_dir,
                                                         allow_live=self.settings.enable_live)
                    await emit(Event(kind="evidence", data={"source": "Lesson 57 owned Git workshop",
                                                            "lesson_id": 57,
                                                            "result": {"report": worktree_report,
                                                                       "experiment_passed": worktree_report["check"] == "passed"}}))
                    return
                if lesson.id == 56:
                    from agent_lab.teams_lab import LiveInput, ReplayInput, grade, run_replay
                    from agent_lab.teams_native import evaluate_native, native_run

                    if request.mode == "offline":
                        team_selected = ReplayInput.model_validate(request.lesson_options)
                        team_report = run_replay(team_selected)
                        passed = grade(team_selected, team_report)
                    else:
                        team_live_selected = LiveInput.model_validate(request.lesson_options)
                        team_report = await native_run(team_live_selected, self.settings,
                                                       self.settings.data_dir / "lesson-56")
                        passed = evaluate_native(team_report)
                    await emit(Event(kind="evidence", data={"source": "Lesson 56 team reducer/native observer",
                                                            "lesson_id": 56,
                                                            "result": {"report": team_report,
                                                                       "experiment_passed": passed}}))
                    return
                if lesson.id == 55:
                    from agent_lab.upgrading_lab import RunInput, criterion, run_upgrade

                    selected_upgrade = RunInput.model_validate(request.lesson_options)
                    upgrade_report = run_upgrade(selected_upgrade)
                    await emit(Event(kind="evidence", data={"source": "Lesson 55 offline fixture contracts",
                                                            "lesson_id": 55,
                                                            "result": {"report": upgrade_report,
                                                                       "experiment_passed": criterion(selected_upgrade, upgrade_report)}}))
                    return
                if lesson.id == 54:
                    from agent_lab.tool_design_lab import DesignInput, grade, prepared
                    from agent_lab.tool_design_native import native

                    design_selected = DesignInput.model_validate(request.lesson_options)
                    design_id = uuid.uuid4()
                    design_report = (await prepared(design_selected, design_id) if request.mode == "offline" else
                                     await native(design_selected, design_id, self.settings,
                                                  self.settings.data_dir / "lesson-54"))
                    await emit(Event(kind="evidence", data={"source": "Lesson 54 catalog handler receipts",
                                                            "lesson_id": 54,
                                                            "result": {"report": design_report,
                                                                       "experiment_passed": grade(design_selected, design_report)}}))
                    return
                if lesson.id == 53:
                    from agent_lab.debug_lab import DebugInput, criterion, prepared_run
                    from agent_lab.debug_native import native_run
                    from agent_lab.debug_store import DebugStore

                    debug_selected = DebugInput.model_validate(request.lesson_options)
                    debug_store = DebugStore(self.settings.data_dir / "lesson-53")
                    identifier = uuid.uuid4()
                    bundle = (await prepared_run(debug_selected, debug_store.root, identifier)
                              if request.mode == "offline" else
                              await native_run(debug_selected, debug_store.root, identifier, self.settings))
                    loaded = debug_store.save(bundle)
                    result = {"start": {"runId": str(identifier)}, "loaded": loaded,
                              "selected": debug_selected.model_dump(mode="json"),
                              "experiment_passed": criterion(str(identifier), debug_selected, bundle, loaded)}
                    await emit(Event(kind="evidence", data={"source": "Lesson 53 persisted diagnostic bundle",
                                                            "lesson_id": 53, "result": result}))
                    return
                if lesson.id == 52:
                    from agent_lab.evals_core import compare, synthetic_criterion, synthetic_report
                    from agent_lab.evals_live import native_eval
                    from agent_lab.evals_store import EvalStore

                    options = request.lesson_options
                    store = EvalStore(self.settings.data_dir / "lesson-52")
                    if request.mode == "live":
                        candidate = await native_eval(store.root, self.settings,
                                                      variant=options["variant"], trials=options["trials"],
                                                      judge=options["judge"], budget=options["budget"],
                                                      consent=options["consent"])
                    else:
                        candidate = synthetic_report(options["variant"], options["trials"])
                    store.save(candidate)
                    baseline = store.baseline(options["mode"], options["judge"])
                    comparison = compare(baseline, candidate)
                    report = {"baseline": baseline, "candidate": candidate,
                              "comparison": comparison,
                              "experiment_passed": (baseline is not None and
                                                    synthetic_criterion(baseline, candidate, comparison)
                                                    if request.mode == "offline" else False)}
                    await emit(Event(kind="evidence", data={"source": "Lesson 52 evaluation reports",
                                                            "lesson_id": 52, "result": report}))
                    return
                if lesson.id == 51:
                    from agent_lab.offline_lab import run_suite

                    report = await run_suite(self.settings.data_dir / "lesson-51",
                                             group=request.lesson_options["group"],
                                             mutation=request.lesson_options["mutation"])
                    await emit(Event(kind="evidence", data={"source": "actual offline host assertions",
                                                            "lesson_id": 51, "result": report}))
                    return
                if lesson.id == 50:
                    from agent_lab.desk_approver import DeskApprover, Pending
                    from agent_lab.desk_lab import local_chat
                    from agent_lab.desk_native import native_chat
                    from agent_lab.desk_store import DeskStore

                    options = request.lesson_options
                    desk = DeskStore(self.settings.data_dir / "lesson-50")
                    approver = DeskApprover()

                    async def decide(entry: Pending) -> None:
                        approver.answer(entry.run, entry.conversation, entry.call,
                                        entry.token, options["approval"])

                    selected = uuid.UUID(options["conversation_id"]) if options["conversation_id"] else None
                    intent = options["intent"]
                    if request.mode == "live":
                        result = await native_chat(desk, approver, customer=options["customer"],
                                                   conversation=selected, intent=intent,
                                                   message=request.prompt, on_approval=decide)
                    else:
                        result = await local_chat(desk, approver, customer=options["customer"],
                                                  conversation=selected, intent=intent,
                                                  message=request.prompt,
                                                  scenario="normal" if request.scenario == "success" else request.scenario,
                                                  on_approval=decide)
                    await emit(Event(kind="evidence", data={"source": result["source"],
                                                            "lesson_id": 50, "result": result}))
                    return
                seed_workspace(work, lesson)
                if lesson.id == 12:
                    from agent_lab.streaming import execute_stream

                    assert handle.input_stream is not None
                    await execute_stream(handle.input_stream, request, work, run_dir / "config", self.settings, emit)
                    return
                evidence = (
                    {}
                    if 1 <= lesson.id <= 49 and request.mode == "live"
                    else await run_exercise(work, request, lesson, ask=ask)
                    if 2 <= lesson.id <= 49
                    else await run_exercise(work, request, lesson)
                )
                if not (1 <= lesson.id <= 49 and request.mode == "live"):
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
