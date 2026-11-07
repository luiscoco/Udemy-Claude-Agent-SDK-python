"""Own a host background task across one real SDK turn and settle it before exit."""

import asyncio
from pathlib import Path
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, SystemMessage

from agent_lab.config import Settings
from agent_lab.foundations import Evidence
from agent_lab.models import Event, LessonError, RunRequest, lesson_request

MARKER = "BACKGROUND_27"


def background_options(root: Path, config: Path, request: RunRequest, settings: Settings) -> ClaudeAgentOptions:
    from agent_lab.sdk import isolated_env, resolve_cli_path

    return ClaudeAgentOptions(
        cwd=str(root.resolve()),
        model=settings.model,
        cli_path=resolve_cli_path(settings) if request.mode == "live" else None,
        tools=[],
        allowed_tools=[],
        setting_sources=[],
        strict_mcp_config=True,
        env=isolated_env(config.resolve()),
        system_prompt={"type": "preset", "preset": "claude_code", "append": "This is a fixed host-task ownership lesson. Use no tools and reply with the requested marker only."},
        max_turns=request.max_turns,
        max_budget_usd=request.max_budget_usd,
    )


def background_report(state: Evidence, selected: dict, watcher: dict, answers: list[str], closed: bool) -> dict:
    base = state.report()
    terminal = state.terminals[-1] if state.terminals else {}
    init = state.initialized[-1] if state.initialized else {}
    session_ok = bool(init.get("session_id") and init.get("session_id") == terminal.get("session_id"))
    task_ok = bool(
        watcher.get("started") is True
        and watcher.get("running_during_query") is True
        and watcher.get("awaited") is True
        and watcher.get("done") is True
        and watcher.get("cleanup_ran") is True
        and watcher.get("owner_same_task") is True
        and watcher.get("cancelled") is (selected["ending"] == "cancel")
        and watcher.get("released") is (selected["ending"] == "finish")
    )
    observed = bool(base["experiment_passed"] and session_ok and task_ok and answers and answers[-1].strip() == MARKER and closed)
    return {
        **base,
        "selected": selected,
        "watcher": watcher,
        "sdk_session_matches": session_ok,
        "task_lifecycle_verified": task_ok,
        "connection_closed": closed,
        "observation_passed": observed,
        "experiment_passed": observed,
        "check_scope": "The host watcher starts before the actual SDK turn, remains pending during it, and is either cancelled or released, then awaited until its finally cleanup runs before the SDK client disconnects. This does not exercise CLI-managed task IDs or stop_task().",
    }


async def execute_background(root: Path, request: RunRequest, settings: Settings, emit: Any, config: Path | None = None) -> dict:
    from agent_lab.sdk import message_data, require_live_access

    request = lesson_request(27, request)
    root = await asyncio.to_thread(root.resolve)
    selected = request.lesson_options
    config = config or root.parent / "config"
    state = Evidence(27, root.parent.name, root, selected, "live SDK stream and actual host callbacks" if request.mode == "live" else "local host effects plus explicitly recorded SDK correlation fixtures", request.max_turns, request.max_budget_usd)
    state.configured = {"tools": [], "allowed_tools": [], "setting_sources": [], "strict_mcp_config": True, "ending": selected["ending"]}
    await emit(Event(kind="options", data={"lesson_id": 27, "sdk_options": state.configured}))
    owner = asyncio.current_task()
    started = asyncio.Event()
    release = asyncio.Event()
    watcher = {"started": False, "running_during_query": False, "awaited": False, "done": False, "cleanup_ran": False, "owner_same_task": False, "cancelled": False, "released": False}

    async def watch() -> None:
        watcher["started"] = True
        started.set()
        try:
            await release.wait()
            watcher["released"] = True
        finally:
            watcher["cleanup_ran"] = True

    task = asyncio.create_task(watch(), name="lesson-27-host-watcher")
    await started.wait()
    client = None
    answers: list[str] = []
    closed = False
    try:
        watcher["owner_same_task"] = asyncio.current_task() is owner
        if request.mode == "live":
            require_live_access(settings)
            config.mkdir(parents=True, exist_ok=True)
            client = ClaudeSDKClient(options=background_options(root, config, request, settings))
            await client.connect()
            watcher["running_during_query"] = not task.done()
            await client.query(f"Reply with exactly {MARKER} and nothing else.")
            async for message in client.receive_response():
                if isinstance(message, SystemMessage) and message.subtype == "api_retry" and message.data.get("error_status") == 401:
                    raise PermissionError("Claude rejected authentication (HTTP 401). No host retry was attempted.")
                data = message_data(message)
                if data["message_class"] == "AssistantMessage":
                    answers.extend(block["text"] for block in data.get("content", []) if isinstance(block, dict) and isinstance(block.get("text"), str))
                if data["message_class"] == "ResultMessage" and isinstance(data.get("result"), str):
                    answers.append(data["result"])
                event = Event(kind="result" if data["message_class"] == "ResultMessage" else "message", data=data)
                state.observe(event)
                await emit(event)
            if not state.report()["experiment_passed"]:
                raise LessonError("Background lesson did not finish with a successful SDK result.")
        else:
            watcher["running_during_query"] = not task.done()
            state.initialized = [{"session_id": "background-fixture"}]
            state.terminals = [{"session_id": "background-fixture", "subtype": "success", "is_error": False}]
            answers = [MARKER]
            if request.scenario == "missing-evidence":
                state.terminals.clear()
            elif request.scenario == "wrong-identity":
                state.terminals[-1]["session_id"] = "foreign"
    finally:
        if selected["ending"] == "cancel":
            task.cancel()
        else:
            release.set()
        try:
            await task
        except asyncio.CancelledError:
            pass
        watcher["awaited"] = True
        watcher["done"] = task.done()
        watcher["cancelled"] = task.cancelled()
        if request.scenario == "missing-cleanup":
            watcher["cleanup_ran"] = False
        elif request.scenario == "unawaited":
            watcher["awaited"] = False
        elif request.scenario == "not-running":
            watcher["running_during_query"] = False
        if client is not None:
            await client.disconnect()
        closed = True
        report = background_report(state, selected, watcher, answers, closed)
        report["scenario"] = request.scenario
        report["expected_check"] = "passed" if report["experiment_passed"] else "needs-review"
        proof = {"experiment": report, "experiment_passed": report["experiment_passed"]}
        async with asyncio.timeout(1):
            await emit(Event(kind="evidence", data={"lesson_id": 27, "result": proof}))
    return proof


async def local_background(root: Path, request: RunRequest) -> dict:
    async def ignore(event: Event) -> None:
        pass

    return await execute_background(root, request.model_copy(update={"mode": "offline"}), Settings(), ignore)
