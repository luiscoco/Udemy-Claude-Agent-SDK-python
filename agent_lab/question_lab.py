"""Bounded AskUserQuestion routing with an explicitly simulated answer."""

import asyncio
from pathlib import Path
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, SystemMessage
from claude_agent_sdk.types import PermissionResultAllow, PermissionResultDeny

from agent_lab.config import Settings
from agent_lab.foundations import Evidence, record_call
from agent_lab.models import Event, RunRequest, lesson_request
from agent_lab.sdk import Questions

QUESTION = "Which teaching style?"
OPTIONS = ("Concise", "Detailed")


def question_input() -> dict[str, Any]:
    return {"questions": [{"question": QUESTION, "header": "Style", "options": [
        {"label": "Concise", "description": "One short example"},
        {"label": "Detailed", "description": "Explain each step"},
    ], "multiSelect": False}]}


def validate_question(arguments: dict[str, Any]) -> bool:
    """Accept only the host's exact fixed question and listed options."""
    try:
        return Questions.model_validate(arguments).model_dump() == question_input()
    except ValueError:
        return False


def question_options(root: Path, config: Path, request: RunRequest, settings: Settings, callback: Any) -> ClaudeAgentOptions:
    from agent_lab.sdk import isolated_env, resolve_cli_path

    return ClaudeAgentOptions(
        cwd=str(root.resolve()), model=settings.model,
        cli_path=resolve_cli_path(settings) if request.mode == "live" else None,
        tools=["AskUserQuestion"], allowed_tools=[], setting_sources=[],
        strict_mcp_config=True, env=isolated_env(config.resolve()),
        can_use_tool=callback,
        system_prompt={"type": "preset", "preset": "claude_code", "append": "This is a fixed AskUserQuestion lesson. Call AskUserQuestion exactly once with the user-supplied JSON question. Wait for its answer, then state the chosen style and give a one-sentence explanation. Use no other tools."},
        max_turns=request.max_turns, max_budget_usd=request.max_budget_usd,
    )


def question_report(state: Evidence, selected: dict[str, str], callbacks: list[dict[str, Any]], closed: bool) -> dict[str, Any]:
    base = state.report()
    calls = [call for call in state.calls if call.get("name") == "AskUserQuestion" and not call.get("parent_tool_use_id")]
    matched = bool(len(calls) == len(state.calls) == len(state.results) == len(callbacks) == 1
        and calls[0].get("arguments") == question_input()
        and state.results[0].get("id") == calls[0].get("id")
        and state.results[0].get("is_error") is False
        and callbacks[0].get("accepted") is True
        and callbacks[0].get("answer") == selected["answer"])
    terminal = state.terminals[-1] if state.terminals else {}
    initialized = state.initialized[-1] if state.initialized else {}
    session_ok = bool(initialized.get("session_id") and terminal.get("session_id") == initialized.get("session_id"))
    passed = bool(base["experiment_passed"] and session_ok and matched and closed)
    return {**base, "selected": selected, "callback_observations": callbacks,
        "question_call_result_correlated": matched, "session_verified": session_ok,
        "simulated_answer": selected["answer"], "connection_closed": closed,
        "observation_passed": passed, "experiment_passed": passed,
        "check_scope": "The host accepts only the fixed question, injects a labelled simulated choice through can_use_tool, and correlates one SDK AskUserQuestion call/result with that callback and the terminal session. The answer is not a real user click."}


async def execute_question(root: Path, request: RunRequest, settings: Settings, emit: Any, config: Path | None = None) -> dict[str, Any]:
    from agent_lab.sdk import message_data, require_live_access

    request = lesson_request(31, request)
    root = await asyncio.to_thread(root.resolve)
    config = config or root.parent / "config"
    selected = request.lesson_options
    state = Evidence(31, root.parent.name, root, selected,
        "live SDK stream and actual host callbacks" if request.mode == "live" else "recorded SDK correlation fixture with actual host callback",
        request.max_turns, request.max_budget_usd)
    callbacks: list[dict[str, Any]] = []

    async def callback(name: str, arguments: dict[str, Any], context: Any) -> Any:
        accepted = name == "AskUserQuestion" and validate_question(arguments)
        callbacks.append({"name": name, "accepted": accepted, "answer": selected["answer"] if accepted else None})
        if not accepted:
            return PermissionResultDeny(message="Only the fixed, valid AskUserQuestion is enabled.")
        return PermissionResultAllow(updated_input={**arguments, "answers": {QUESTION: selected["answer"]}})

    if request.mode == "live":
        require_live_access(settings)
    options = question_options(root, config, request, settings, callback)
    state.configured = {"tools": options.tools, "allowed_tools": options.allowed_tools,
        "setting_sources": options.setting_sources, "strict_mcp_config": options.strict_mcp_config,
        "can_use_tool": options.can_use_tool is not None}
    await emit(Event(kind="options", data={"lesson_id": 31, "sdk_options": state.configured}))
    client = None
    closed = False
    try:
        if request.mode == "live":
            config.mkdir(parents=True, exist_ok=True)
            client = ClaudeSDKClient(options=options)
            await client.connect()
            import json
            await client.query("Call AskUserQuestion exactly once with this JSON input: " + json.dumps(question_input()) + " The host will supply a simulated answer. Do not invent one.")
            async for message in client.receive_response():
                if isinstance(message, SystemMessage) and message.subtype == "api_retry" and message.data.get("error_status") == 401:
                    raise PermissionError("Claude rejected authentication (HTTP 401). No host retry was attempted.")
                item = message_data(message)
                event = Event(kind="result" if item["message_class"] == "ResultMessage" else "message", data=item)
                state.observe(event)
                await emit(event)
        else:
            state.initialized = [{"session_id": "question-fixture"}]
            argument = question_input()
            await callback("AskUserQuestion", argument, None)
            record_call(state, "AskUserQuestion", argument, "question-1")
            state.results = [{"id": "question-1", "run_id": state.run_id, "is_error": False}]
            state.terminals = [{"session_id": "question-fixture", "subtype": "success", "is_error": False}]
            if request.scenario == "missing-evidence":
                state.terminals.clear()
            elif request.scenario == "wrong-identity":
                state.results[0]["id"] = "foreign"
            elif request.scenario == "missing-callback":
                callbacks.clear()
            elif request.scenario == "wrong-answer":
                callbacks[0]["answer"] = OPTIONS[1 - OPTIONS.index(selected["answer"])]
            elif request.scenario == "changed-question":
                state.calls[0]["arguments"]["questions"][0]["header"] = "Other"
    finally:
        if client is not None:
            await client.disconnect()
        closed = True
        report = question_report(state, selected, callbacks, closed)
        report["scenario"] = request.scenario
        report["expected_check"] = "passed" if report["experiment_passed"] else "needs-review"
        proof = {"experiment": report, "experiment_passed": report["experiment_passed"]}
        await emit(Event(kind="evidence", data={"lesson_id": 31, "result": proof}))
    return proof


async def local_question(root: Path, request: RunRequest) -> dict[str, Any]:
    async def ignore(event: Event) -> None:
        pass

    return await execute_question(root, request.model_copy(update={"mode": "offline"}), Settings(), ignore)
