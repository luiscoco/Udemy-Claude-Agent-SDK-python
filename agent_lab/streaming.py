"""One owned SDK connection, a wakeable input queue and acknowledged runtime controls.

Offline mode uses the official client against a scripted transport. Application handles,
input UUIDs and SDK session identities are distinct. No answer-recall claim is made.
"""

import asyncio
import copy
import dataclasses
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, ResultMessage, SystemMessage

from agent_lab.config import Settings
from agent_lab.foundation_models import StreamingInputs
from agent_lab.models import Event, LessonError, RunRequest, lesson_request
from agent_lab.policy import redact
from agent_lab.scripted_cli import ScriptedCLI

Emit = Callable[[Event], Awaitable[None]]


@dataclass
class StreamSession:
    application_handle: str
    max_messages: int = 2
    inputs: asyncio.Queue[dict[str, Any]] = field(default_factory=asyncio.Queue)
    wake: asyncio.Event = field(default_factory=asyncio.Event)
    commands: asyncio.Queue[Any] = field(default_factory=lambda: asyncio.Queue(maxsize=8))
    records: list[dict[str, Any]] = field(default_factory=list)
    submitted: list[dict[str, Any]] = field(default_factory=list)
    yielded: list[dict[str, Any]] = field(default_factory=list)
    initialization: list[str] = field(default_factory=list)
    results: list[dict[str, Any]] = field(default_factory=list)
    ready: bool = False
    manual_mode: bool = False
    input_closed: bool = False
    iterator_closed: bool = False
    output_closed: bool = False
    connection_closed: bool = False
    aborted: bool = False
    control_count: int = 0
    current_settings: dict[str, Any] = field(default_factory=dict)
    configured_settings: dict[str, Any] = field(default_factory=dict)
    pending_controls: set[asyncio.Future[None]] = field(default_factory=set)
    emit: Emit | None = None

    def note(self, stage: str, **data: Any) -> None:
        self.records.append({"stage": stage, "application_handle": self.application_handle, **data})

    def snapshot(self) -> dict[str, Any]:
        return redact(
            {
                "application_handle": self.application_handle,
                "sdk_identity": self.initialization[-1] if self.initialization else None,
                "ready": self.ready and not self.input_closed,
                "manual_mode": self.manual_mode,
                "input_closed": self.input_closed,
                "iterator_closed": self.iterator_closed,
                "output_closed": self.output_closed,
                "connection_closed": self.connection_closed,
                "aborted": self.aborted,
                "submitted_count": len(self.submitted),
                "yielded_count": len(self.yielded),
                "successful_results": sum(
                    r.get("subtype") == "success" and r.get("is_error") is False
                    for r in self.results
                ),
                "queued_count": self.inputs.qsize(),
                "message_limit": self.max_messages,
                "acknowledged_settings": self.current_settings,
                "configured_settings": self.configured_settings,
                "inputs": self.submitted,
                "yielded_inputs": self.yielded,
                "terminal_results": self.results,
                "timeline": self.records,
                "note": "Queued and yielded inputs are not completed turns. Results are separate SDK observations; recall and per-message completion are not certified.",
            }
        )

    async def publish(self) -> None:
        if self.emit:
            await self.emit(Event(kind="input_stream", data=self.snapshot()))

    def push(self, text: str) -> str:
        if self.input_closed:
            raise LessonError("The input queue is closed. Open a new session.")
        if not isinstance(text, str) or not text.strip() or len(text.strip()) > 10000:
            raise LessonError("Send a nonempty message of at most 10000 characters.")
        if len(self.submitted) >= self.max_messages:
            raise LessonError("The authorized message limit is reached. End this session.")
        identifier = str(uuid.uuid4())
        row = {
            "input_id": identifier,
            "text": text.strip(),
            "application_handle": self.application_handle,
        }
        self.submitted.append(row)
        self.inputs.put_nowait(row)
        self.note("queued", input_id=identifier)
        self.wake.set()
        return identifier

    def end(self) -> None:
        if not self.input_closed:
            self.input_closed = True
            self.note("input-close-requested")
            self.wake.set()  # An idle generator must wake even when there are no messages.

    async def messages(self) -> AsyncIterator[dict[str, Any]]:
        try:
            while True:
                self.wake.clear()
                if not self.inputs.empty():
                    row = self.inputs.get_nowait()
                    self.yielded.append(dict(row))
                    self.note("yielded", input_id=row["input_id"])
                    await self.publish()
                    yield {
                        "type": "user",
                        "uuid": row["input_id"],
                        "message": {"role": "user", "content": row["text"]},
                        "parent_tool_use_id": None,
                        "session_id": "default",
                    }
                elif self.input_closed:
                    break
                else:
                    await self.wake.wait()
        finally:
            self.iterator_closed = True
            self.note("input-iterator-closed")

    async def command(self, action: str, value: str | None = None) -> None:
        if not self.ready or self.input_closed:
            raise LessonError("The session is not open for runtime controls.")
        if action not in {"model", "permission"}:
            raise LessonError("Unknown runtime control.")
        if action == "model" and value not in {"haiku", "sonnet"}:
            raise LessonError("Choose haiku or sonnet.")
        if action == "permission" and value not in {"default", "plan"}:
            raise LessonError("Choose default or plan mode.")
        if self.control_count >= 12 or self.commands.full():
            raise LessonError("The runtime control limit is reached.")
        self.control_count += 1
        future: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self.pending_controls.add(future)
        future.add_done_callback(self.pending_controls.discard)
        self.commands.put_nowait((action, value, future))
        try:
            async with asyncio.timeout(10):
                await future
        except TimeoutError as exc:
            raise LessonError(
                "The runtime control was not acknowledged before its deadline."
            ) from exc


def stream_report(session: StreamSession, source: str, scenario: str = "success") -> dict[str, Any]:
    """Check actual queue identities, successful SDK results and complete closure."""
    state = copy.deepcopy(session.snapshot())
    init = list(session.initialization)
    if scenario == "missing-evidence":
        state["terminal_results"] = []
    elif scenario == "wrong-identity" and state["yielded_inputs"]:
        state["yielded_inputs"][0]["application_handle"] = "different-application"
    pushed, yielded = state["inputs"], state["yielded_inputs"]
    identifiers = [row["input_id"] for row in pushed]
    matching = (
        bool(identifiers)
        and len(set(identifiers)) == len(identifiers)
        and [row["input_id"] for row in yielded] == identifiers
        and all(row["application_handle"] == session.application_handle for row in pushed + yielded)
    )
    results = state["terminal_results"]
    state["successful_results"] = sum(
        r.get("subtype") == "success" and r.get("is_error") is False for r in results
    )
    successful = (
        bool(init and results)
        and all(
            r.get("session_id") == init[0]
            and r.get("subtype") == "success"
            and r.get("is_error") is False
            for r in results
        )
        and len(set(init)) == 1
    )
    passed = bool(
        matching
        and successful
        and not state["aborted"]
        and all(
            state[k]
            for k in ("input_closed", "iterator_closed", "output_closed", "connection_closed")
        )
    )
    return {
        "source": source,
        "scenario": scenario,
        "input_stream": state,
        "experiment_passed": passed,
        "check_scope": "Pushed/yielded message identities match this application, SDK results succeed under the initialized session identity, and input, output and connection close. Queue timing, recall and per-message completion are not graded.",
        "expected_check": "passed" if passed else "needs-review",
    }


class StreamingFixture(ScriptedCLI):
    async def connect(self) -> None:
        await super().connect()
        await self._outbox.put(
            {"type": "system", "subtype": "init", "session_id": self.session_id, "tools": []}
        )


def stream_options(
    request: RunRequest, work: Path, config: Path, settings: Settings
) -> ClaudeAgentOptions:
    from agent_lab.sdk import isolated_env, require_live_access, resolve_cli_path

    if request.mode == "live":
        require_live_access(settings)
    return ClaudeAgentOptions(
        model=settings.model,
        cli_path=resolve_cli_path(settings) if request.mode == "live" else None,
        cwd=str(work),
        tools=[],
        setting_sources=[],
        strict_mcp_config=True,
        include_partial_messages=False,
        max_turns=request.max_turns,
        max_budget_usd=request.max_budget_usd,
        permission_mode="default",
        env=isolated_env(config),
    )


async def execute_stream(
    session: StreamSession,
    request: RunRequest,
    work: Path,
    config: Path,
    settings: Settings,
    emit: Emit,
) -> dict[str, Any]:
    """Connect/disconnect in one owner; SDK tasks pump one async iterable and its responses."""
    from agent_lab.sdk import message_data

    request = lesson_request(12, request)
    selected = StreamingInputs.model_validate(request.lesson_options)
    options = stream_options(request, work, config, settings)
    session.configured_settings = {"model": options.model, "permission": "default"}
    await asyncio.to_thread(config.mkdir, parents=True, exist_ok=True)
    session.max_messages, session.emit = selected.max_messages, emit
    session.manual_mode = selected.interactive
    fixture = (
        StreamingFixture([["Recorded response", " to the input."]] * 4, chunk_delay=0.1)
        if request.mode == "offline"
        else None
    )
    client = ClaudeSDKClient(options=options, transport=fixture)
    tasks: list[asyncio.Task[Any]] = []
    incoming: asyncio.Queue[Any] = asyncio.Queue(maxsize=32)
    eof = object()
    interrupted = False

    async def pump() -> None:
        try:
            async for message in client.receive_messages():
                await incoming.put(message)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await incoming.put(exc)
        await incoming.put(eof)

    try:
        session.push(request.prompt)
        if not selected.interactive and selected.queue_timing == "immediate":
            session.push(request.follow_up)
            session.end()
        await emit(
            Event(
                kind="options",
                data={
                    "lesson_id": 12,
                    "sdk_options": {
                        "model": options.model,
                        "tools": options.tools,
                        "setting_sources": options.setting_sources,
                        "max_turns": options.max_turns,
                        "max_budget_usd": options.max_budget_usd,
                        "input": "one open async iterable",
                        "message_limit": selected.max_messages,
                    },
                },
            )
        )
        await client.connect(prompt=session.messages())
        session.ready = True
        session.note("connection-open")
        # Script controls run before the input is closed for later-turn scripts.
        if not selected.interactive and selected.runtime_control != "none":
            action = selected.runtime_control
            value = "haiku" if action == "model" else "plan"
            if action == "model":
                await client.set_model(value)
            else:
                await client.set_permission_mode("plan")
            session.note("control-acknowledged", action=action, value=value)
            session.current_settings[action] = value
        await session.publish()
        tasks.append(asyncio.create_task(pump()))
        next_message = asyncio.create_task(incoming.get())
        next_command = asyncio.create_task(session.commands.get())
        tasks.extend([next_message, next_command])
        while True:
            done, _ = await asyncio.wait(
                [next_message, next_command], return_when=asyncio.FIRST_COMPLETED
            )
            if next_command in done:
                action, value, future = next_command.result()
                if not future.done():
                    try:
                        if action == "model":
                            await client.set_model(value)
                        else:
                            await client.set_permission_mode(value)
                    except Exception:
                        session.note("control-rejected", action=action)
                        if not future.done():
                            future.set_exception(
                                LessonError("The SDK rejected this runtime control.")
                            )
                    else:
                        session.note("control-acknowledged", action=action, value=value)
                        session.current_settings[action] = value
                        if not future.done():
                            future.set_result(None)
                    await session.publish()
                next_command = asyncio.create_task(session.commands.get())
                tasks[2] = next_command
            if next_message not in done:
                continue
            message = next_message.result()
            if message is eof:
                session.output_closed = True
                session.note("output-closed")
                break
            if isinstance(message, Exception):
                raise message
            data = message_data(message)
            if isinstance(message, SystemMessage) and message.subtype == "init":
                identity = message.data.get("session_id")
                if isinstance(identity, str) and identity:
                    session.initialization.append(identity)
                    session.note("sdk-initialized", sdk_identity=identity)
            if isinstance(message, ResultMessage):
                session.results.append(dataclasses.asdict(message))
                session.note(
                    "terminal-result", subtype=message.subtype, sdk_identity=message.session_id
                )
                if (
                    not selected.interactive
                    and selected.queue_timing == "after-result"
                    and len(session.results) == 1
                ):
                    if message.subtype == "success" and not message.is_error:
                        session.push(request.follow_up)
                    session.end()
            await emit(
                Event(kind="result" if isinstance(message, ResultMessage) else "message", data=data)
            )
            if (
                request.mode == "live"
                and isinstance(message, ResultMessage)
                and (message.is_error or message.subtype != "success")
            ):
                session.end()
                raise LessonError(
                    "The SDK turn did not succeed. Inspect the terminal result and account/model access. No automatic retry was made."
                )
            if (
                request.scenario == "interrupted"
                and not interrupted
                and data.get("message_class") == "AssistantMessage"
            ):
                interrupted = session.aborted = True
                await client.interrupt()
                session.note("interrupt-acknowledged")
                session.end()
            await session.publish()
            next_message = asyncio.create_task(incoming.get())
            tasks[1] = next_message
    except BaseException:
        session.aborted = True
        raise
    finally:
        session.ready = False
        session.end()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        try:
            await client.disconnect()
            session.connection_closed = True
            session.note("connection-closed")
        finally:
            for future in list(session.pending_controls):
                if not future.done():
                    future.set_exception(
                        LessonError("The session closed before this control completed.")
                    )
            while not session.commands.empty():
                _, _, future = session.commands.get_nowait()
                if not future.done():
                    future.set_exception(LessonError("The session closed before this control ran."))
            report = stream_report(
                session,
                "live SDK stream and actual host callbacks"
                if request.mode == "live"
                else "official SDK client with a scripted CLI fixture; no model call",
                request.scenario,
            )
            # A disconnected consumer must not hold SDK cleanup behind a full event queue.
            try:
                async with asyncio.timeout(1):
                    await session.publish()
                    await emit(
                        Event(
                            kind="evidence",
                            data={
                                "lesson_id": 12,
                                "source": report["source"],
                                "result": {
                                    "experiment": report,
                                    "experiment_passed": report["experiment_passed"],
                                },
                            },
                        )
                    )
            except TimeoutError:
                pass
    return {"experiment": report, "experiment_passed": report["experiment_passed"]}


async def local_streaming(root: Path, request: RunRequest) -> dict[str, Any]:
    async def ignore(event: Event) -> None:
        pass

    request = lesson_request(12, request)
    if request.mode != "offline" or request.lesson_options["interactive"]:
        raise LessonError("Use the owned run service for live or interactive sessions.")
    return await execute_stream(
        StreamSession(root.parent.name),
        request,
        root,
        root.parent / "stream-config",
        Settings(),
        ignore,
    )
