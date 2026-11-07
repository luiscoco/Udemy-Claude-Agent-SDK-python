"""Lesson 38: prompt suggestions observed after completed SDK turns."""

import asyncio
import secrets
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, ResultMessage, SystemMessage
from claude_agent_sdk._internal.transport import Transport
from claude_agent_sdk._internal.transport.subprocess_cli import SubprocessCLITransport

from agent_lab.config import Settings
from agent_lab.models import Event, RunRequest, lesson_request

SOURCE_LIVE = "live SDK stream and actual host callbacks"
FIRST = "Suggest one small next step for a Python CLI that tracks study tasks. Reply in one sentence."
SECOND = "Now suggest one improvement to that CLI's task output. Reply in one sentence."
SECOND_EDITED = "How could I show task status clearly in that CLI? Give one concise example."
VARIANTS = {"enabled", "omitted", "disabled", "env-off", "setting-off", "env-on", "plan", "small", "cached", "uncached", "queued"}
UNSUPPORTED_LIVE = {"setting-off", "cached", "uncached"}


async def empty_messages() -> AsyncIterator[dict[str, Any]]:
    return
    yield {}


class SuggestionTap:
    """Capture raw suggestion envelopes the installed Python parser skips."""

    def __init__(self, inner: SubprocessCLITransport) -> None:
        self.inner = inner
        self.suggestions: list[dict[str, Any]] = []
        self.changed = asyncio.Event()

    async def connect(self) -> None:
        await self.inner.connect()

    async def write(self, data: str) -> None:
        await self.inner.write(data)

    async def end_input(self) -> None:
        await self.inner.end_input()

    async def close(self) -> None:
        await self.inner.close()

    def is_ready(self) -> bool:
        return self.inner.is_ready()

    async def read_messages(self) -> AsyncIterator[dict[str, Any]]:
        async for raw in self.inner.read_messages():
            if raw.get("type") == "prompt_suggestion":
                self.suggestions.append({"suggestion": raw.get("suggestion"),
                                         "session_id": raw.get("session_id"),
                                         "uuid": raw.get("uuid")})
                self.changed.set()
            yield raw


def suggestion_options(root: Path, config: Path, settings: Settings,
                       variant: str, mode: str) -> ClaudeAgentOptions:
    from agent_lab.sdk import isolated_env, resolve_cli_path

    if mode == "live" and variant in UNSUPPORTED_LIVE:
        raise ValueError(f"{variant} is a comparison-only variant in this Python CLI build.")

    extra: dict[str, str | None] = {"no-session-persistence": None}
    if variant not in {"omitted", "disabled"}:
        extra["prompt-suggestions"] = None
    env = isolated_env(config)
    if variant in {"env-off", "disabled"}:
        env["CLAUDE_CODE_ENABLE_PROMPT_SUGGESTION"] = "false"
    elif variant == "env-on":
        env["CLAUDE_CODE_ENABLE_PROMPT_SUGGESTION"] = "true"
    return ClaudeAgentOptions(
        cwd=str(root), model="haiku" if variant == "small" else settings.model,
        cli_path=resolve_cli_path(settings) if mode == "live" else None,
        tools=[], allowed_tools=[], mcp_servers={}, setting_sources=[],
        strict_mcp_config=True, env=env, extra_args=extra,
        permission_mode="plan" if variant == "plan" else "default",
        max_turns=6, max_budget_usd=0.10,
    )


@dataclass
class SuggestionSession:
    root: Path
    config: Path
    settings: Settings
    mode: str
    variant: str = "enabled"
    scenario: str = "success"
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    token: str = field(default_factory=lambda: secrets.token_urlsafe(24))
    inputs: asyncio.Queue[dict[str, Any]] = field(default_factory=asyncio.Queue)
    wake: asyncio.Event = field(default_factory=asyncio.Event)
    submitted: list[dict[str, Any]] = field(default_factory=list)
    results: list[dict[str, Any]] = field(default_factory=list)
    suggestions: list[dict[str, Any]] = field(default_factory=list)
    timeline: list[dict[str, Any]] = field(default_factory=list)
    initialized: list[dict[str, Any]] = field(default_factory=list)
    busy: bool = False
    input_closed: bool = False
    connection_closed: bool = False
    normal_end: bool = False
    aborted: bool = False
    edited_requested: bool = False
    edited_submission: bool = False
    task: asyncio.Task[None] | None = None

    def snapshot(self) -> dict[str, Any]:
        return {"run_id": self.run_id, "mode": self.mode, "variant": self.variant,
                "scenario": self.scenario, "submitted": list(self.submitted),
                "results": list(self.results), "suggestions": list(self.suggestions),
                "timeline": list(self.timeline), "busy": self.busy,
                "input_closed": self.input_closed, "connection_closed": self.connection_closed,
                "normal_end": self.normal_end, "aborted": self.aborted,
                "edited_requested": self.edited_requested, "edited_submission": self.edited_submission,
                "initialized": list(self.initialized)}

    def send(self, text: str) -> dict[str, Any]:
        if self.input_closed or self.aborted:
            raise ValueError("This chat is closed.")
        if not isinstance(text, str) or not text.strip() or len(text) > 2000:
            raise ValueError("Send 1 to 2000 nonblank characters.")
        if len(self.submitted) >= 3:
            raise ValueError("This chat accepts at most three inputs.")
        row = {"input_id": uuid.uuid4().hex, "text": text.strip(),
               "order": len(self.submitted) + 1, "queued_busy": self.busy}
        self.submitted.append(row)
        self.inputs.put_nowait(row)
        self.timeline.append({"kind": "send", "input_id": row["input_id"], "queued_busy": self.busy})
        self.wake.set()
        return row

    def end(self) -> None:
        self.input_closed = True
        self.timeline.append({"kind": "end"})
        self.wake.set()

    def start(self) -> None:
        if self.task is not None:
            raise ValueError("This chat already started.")
        self.task = asyncio.create_task(self._run())

    async def wait(self) -> dict[str, Any]:
        if self.task is None:
            raise ValueError("Start the chat first.")
        await self.task
        return self.snapshot()

    async def _run(self) -> None:
        try:
            async with asyncio.timeout(60):
                if self.mode == "live":
                    await self._live()
                else:
                    await self._prepared()
                self.normal_end = self.input_closed
        except (TimeoutError, asyncio.CancelledError):
            self.aborted = True
            raise
        finally:
            self.connection_closed = True

    async def _next(self) -> dict[str, Any] | None:
        while self.inputs.empty():
            if self.input_closed:
                return None
            self.wake.clear()
            await self.wake.wait()
        return self.inputs.get_nowait()

    async def _prepared(self) -> None:
        session_id = "prepared-" + self.run_id
        self.initialized.append({"session_id": session_id, "authored_fixture": True})
        while row := await self._next():
            self.busy = True
            await asyncio.sleep(0)
            result = {"input_id": row["input_id"], "turn_id": uuid.uuid4().hex,
                      "session_id": session_id, "subtype": "success", "is_error": False,
                      "cost_usd": None, "authored_fixture": True}
            if self.scenario == "failed-result":
                result["subtype"] = "error"
                result["is_error"] = True
            self.results.append(result)
            self.timeline.append({"kind": "result", "input_id": row["input_id"]})
            if self.variant not in {"omitted", "disabled", "env-off", "setting-off", "plan"} and self.scenario != "missing-suggestion":
                suggestion = {"input_id": row["input_id"], "session_id": session_id,
                              "text": "Ask for one small Python CLI example.",
                              "attributed": not row["queued_busy"] and self.inputs.empty(),
                              "authored_fixture": True}
                if self.scenario == "foreign-suggestion":
                    suggestion["session_id"] = "foreign"
                self.suggestions.append(suggestion)
                self.timeline.append({"kind": "prompt_suggestion", "input_id": row["input_id"]})
            self.busy = False

    async def _live(self) -> None:
        from agent_lab.sdk import require_live_access

        require_live_access(self.settings)
        await asyncio.to_thread(self.root.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(self.config.mkdir, parents=True, exist_ok=True)
        options = suggestion_options(self.root, self.config, self.settings, self.variant, "live")
        tap = SuggestionTap(SubprocessCLITransport(prompt=empty_messages(), options=options))
        client = ClaudeSDKClient(options=options, transport=cast(Transport, tap))
        try:
            await client.connect()
            while row := await self._next():
                self.busy = True
                before = len(tap.suggestions)
                tap.changed.clear()
                await client.query(row["text"])
                terminal: dict[str, Any] | None = None
                async for message in client.receive_response():
                    if isinstance(message, SystemMessage) and message.subtype == "init":
                        self.initialized.append({"session_id": message.data.get("session_id")})
                    if isinstance(message, ResultMessage):
                        terminal = {"input_id": row["input_id"],
                                    "turn_id": getattr(message, "uuid", None) or uuid.uuid4().hex,
                                    "session_id": message.session_id, "subtype": message.subtype,
                                    "is_error": message.is_error, "cost_usd": message.total_cost_usd}
                        self.results.append(terminal)
                        self.timeline.append({"kind": "result", "input_id": row["input_id"]})
                if terminal is not None:
                    if len(tap.suggestions) == before:
                        try:
                            await asyncio.wait_for(tap.changed.wait(), 10)
                        except TimeoutError:
                            pass
                    for raw in tap.suggestions[before:]:
                        suggestion = {"input_id": row["input_id"], "session_id": raw["session_id"],
                                      "text": raw["suggestion"],
                                      "attributed": bool(raw["session_id"] == terminal["session_id"]
                                                         and not row["queued_busy"] and self.inputs.empty())}
                        self.suggestions.append(suggestion)
                        self.timeline.append({"kind": "prompt_suggestion", "input_id": row["input_id"]})
                self.busy = False
        finally:
            await client.disconnect()


def evaluate(session: SuggestionSession) -> dict[str, Any]:
    rows = session.submitted
    results = session.results
    suggestions = session.suggestions
    identity = session.initialized[-1].get("session_id") if session.initialized else None
    ordered = bool(rows and len(rows) == len(results)
                   and [row["input_id"] for row in rows] == [item["input_id"] for item in results]
                   and len({item["turn_id"] for item in results}) == len(results)
                   and all(item["subtype"] == "success" and item["is_error"] is False
                           and item["session_id"] == identity for item in results))
    observed = [item for item in suggestions if isinstance(item.get("text"), str)
                and item["text"].strip() and item["attributed"]
                and item["session_id"] == identity and item["input_id"] in {row["input_id"] for row in rows}]
    passed = bool(session.variant not in {"omitted", "disabled", "env-off", "setting-off", "plan", "cached", "uncached"}
                  and ordered and observed and session.normal_end and session.connection_closed
                  and not session.aborted and session.scenario == "success"
                  and (not session.edited_requested or session.edited_submission))
    return {"source": SOURCE_LIVE if session.mode == "live" else "actual host queue and authored SDK fixtures",
            "selected": {"variant": session.variant}, "inputs": rows, "results": results,
            "suggestions": suggestions, "timeline": session.timeline,
            "ordered_successful_turns": ordered, "observed_attributed_suggestion": bool(observed),
            "edited_requested": session.edited_requested, "edited_submission": session.edited_submission,
            "normal_end": session.normal_end, "connection_closed": session.connection_closed,
            "experiment_passed": passed,
            "expected_check": "passed" if passed else "needs-review",
            "check_scope": "The bounded chat checks ordered successful turns, matching SDK session identity, a nonempty post-result suggestion, normal input closure and a separate host ledger. A suggestion is proposed text; it is sent only through the validated input queue. Python SDK skips this raw message type, so a transport tap observes it before parsing."}


async def execute_suggestions(root: Path, request: RunRequest, settings: Settings,
                              emit: Any, config: Path | None = None) -> dict[str, Any]:
    request = lesson_request(38, request)
    root = await asyncio.to_thread(root.resolve)
    variant = request.lesson_options["variant"]
    session = SuggestionSession(root, config or root.parent / "config", settings,
                                request.mode, variant, request.scenario)
    session.edited_requested = request.lesson_options["edited"]
    await emit(Event(kind="options", data={"lesson_id": 38, "variant": variant,
                                           "prompt_suggestions_requested": variant not in {"omitted", "disabled"},
                                           "tools": [], "setting_sources": [], "max_turns": 6,
                                           "max_budget_usd": 0.10}))
    session.start()
    session.send(FIRST)
    while not session.results or session.busy:
        if session.task is not None and session.task.done():
            await session.task
            break
        await asyncio.sleep(0.05)
    session.send(SECOND_EDITED if session.edited_requested else SECOND)
    if session.edited_requested:
        while len(session.results) < 2 or session.busy:
            if session.task is not None and session.task.done():
                await session.task
                break
            await asyncio.sleep(0.05)
        candidates = [item for item in session.suggestions if item["attributed"] and isinstance(item["text"], str) and item["text"].strip()]
        if candidates:
            session.send(candidates[-1]["text"].strip() + " Include one example.")
            session.edited_submission = True
    session.end()
    await session.wait()
    costs = [result["cost_usd"] for result in session.results if isinstance(result["cost_usd"], (int, float))]
    if costs:
        await emit(Event(kind="result", data={"lesson_id": 38, "session_id": session.results[-1]["session_id"],
                                               "subtype": session.results[-1]["subtype"],
                                               "is_error": session.results[-1]["is_error"],
                                               "total_cost_usd": sum(costs)}))
    if request.scenario == "missing-evidence":
        session.results.pop()
    elif request.scenario == "wrong-identity":
        session.results[0]["session_id"] = "foreign"
    elif request.scenario == "duplicate-result":
        session.results.append(dict(session.results[0]))
    elif request.scenario == "misordered-result":
        session.results.reverse()
    elif request.scenario == "interrupted":
        session.aborted = True
        session.normal_end = False
    report = evaluate(session)
    report["scenario"] = request.scenario
    proof = {"experiment": report, "experiment_passed": report["experiment_passed"]}
    await emit(Event(kind="evidence", data={"lesson_id": 38, "result": proof}))
    return proof


async def local_suggestions(root: Path, request: RunRequest) -> dict[str, Any]:
    async def ignore(event: Event) -> None:
        pass

    return await execute_suggestions(root, request.model_copy(update={"mode": "offline"}), Settings(), ignore)
