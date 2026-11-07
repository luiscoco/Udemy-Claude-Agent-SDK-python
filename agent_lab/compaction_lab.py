"""A bounded MCP result, host summary, and observable compaction boundary."""

import asyncio
import json
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    ClaudeAgentOptions,
    ClaudeSDKClient,
    HookMatcher,
    SystemMessage,
    create_sdk_mcp_server,
    tool,
)

from agent_lab.config import Settings
from agent_lab.foundations import Evidence, record_call
from agent_lab.models import Event, LessonError, RunRequest, lesson_request

TOOL = "mcp__context__read_log"
MARKER = "BOUND_25"


def bounded_result(limit: int, retain_summary: bool) -> dict[str, Any]:
    rows = [{"step": index, "status": "done", "details": "fixture detail " * 40} for index in range(8)]
    raw = json.dumps(rows)
    removed = max(0, len(raw) - limit)
    suffix = f"\n[truncated {removed} characters; ask for a specific step]" if removed else ""
    delivered = raw[:limit] + suffix if removed else raw
    return {
        "raw_characters": len(raw),
        "limit_characters": limit,
        "delivered_characters": len(delivered),
        "marker": suffix.strip(),
        "delivered": delivered,
        "summary": {"completed": list(range(8)), "next": "verify"} if retain_summary else None,
    }


def compaction_options(root: Path, config: Path, request: RunRequest, settings: Settings, handler: Any, before_compact: Any) -> ClaudeAgentOptions:
    from agent_lab.sdk import isolated_env, resolve_cli_path

    return ClaudeAgentOptions(
        cwd=str(root.resolve()),
        model=settings.model,
        cli_path=resolve_cli_path(settings) if request.mode == "live" else None,
        mcp_servers={"context": create_sdk_mcp_server(name="context", tools=[handler])},
        tools=[TOOL],
        allowed_tools=[TOOL],
        setting_sources=[],
        strict_mcp_config=True,
        env=isolated_env(config.resolve()),
        system_prompt={"type": "preset", "preset": "claude_code", "append": "This is a fixed context lesson. Call the one allowed context tool exactly once. Do not use any other tool. End your response with BOUND_25."},
        hooks={"PreCompact": [HookMatcher(hooks=[before_compact])]},
        max_turns=request.max_turns,
        max_budget_usd=request.max_budget_usd,
    )


def compaction_report(state: Evidence, selected: dict, callbacks: list[dict], compact_events: list[dict], answers: list[str], closed: bool) -> dict:
    base = state.report()
    expected = bounded_result(selected["limit"], selected["retain_summary"])
    calls = [row for row in state.calls if row["name"] == TOOL and not row.get("parent_tool_use_id")]
    paired = (
        len(calls) == len(state.calls) == len(state.results) == len(callbacks) == 1
        and calls[0].get("run_id") == state.run_id
        and state.results[0].get("id") == calls[0].get("id")
        and state.results[0].get("run_id") == state.run_id
        and state.results[0].get("is_error") is False
        if calls else False
    )
    callback = callbacks[0] if callbacks else {}
    bound_ok = callback.get("raw_characters") == expected["raw_characters"] and callback.get("delivered_characters") == expected["delivered_characters"] and callback.get("marker") == expected["marker"] and callback.get("limit_characters") == selected["limit"] and callback.get("delivered") == expected["delivered"]
    summary_ok = callback.get("summary") == expected["summary"]
    terminal = state.terminals[-1] if state.terminals else {}
    identity_ok = bool(state.initialized and state.initialized[-1].get("session_id") and state.initialized[-1].get("session_id") == terminal.get("session_id"))
    observed = bool(base["experiment_passed"] and closed and identity_ok and paired and bound_ok and summary_ok and answers and answers[-1].rstrip().endswith(MARKER))
    return {
        **base,
        "selected": selected,
        "callbacks": callbacks,
        "precompact_events": compact_events,
        "tool_call_correlated": paired,
        "bound_verified": bound_ok,
        "summary_verified": summary_ok,
        "connection_closed": closed,
        "observation_passed": observed,
        "experiment_passed": bool(observed and selected["retain_summary"]),
        "check_scope": "One actual MCP callback must deliver the exact bounded text, correlate with a successful SDK call/result, and retain the host summary when selected. PreCompact events are reported only if observed; this short run does not force automatic compaction.",
    }


async def execute_compaction(root: Path, request: RunRequest, settings: Settings, emit: Any, config: Path | None = None) -> dict:
    from agent_lab.sdk import message_data, require_live_access

    request = lesson_request(25, request)
    root = await asyncio.to_thread(root.resolve)
    selected = request.lesson_options
    config = config or root.parent / "config"
    state = Evidence(25, root.parent.name, root, selected, "live SDK stream and actual host callbacks" if request.mode == "live" else "local host effects plus explicitly recorded SDK correlation fixtures", request.max_turns, request.max_budget_usd)
    callbacks: list[dict] = []
    compact_events: list[dict] = []
    answers: list[str] = []

    @tool("read_log", "Read the fixed eight-step log with a strict character bound and explicit truncation marker.", {})
    async def read_log(arguments: dict) -> dict:
        result = bounded_result(selected["limit"], selected["retain_summary"])
        callbacks.append(result)
        return {"content": [{"type": "text", "text": result["delivered"]}]}

    async def before_compact(data: dict, tool_use_id: str | None, context: Any) -> dict:
        compact_events.append({"trigger": data.get("trigger"), "session_id": data.get("session_id")})
        return {}

    if request.mode == "live":
        require_live_access(settings)
    options = compaction_options(root, config, request, settings, read_log, before_compact)
    state.configured = {"tools": options.tools, "allowed_tools": options.allowed_tools, "setting_sources": options.setting_sources, "strict_mcp_config": options.strict_mcp_config, "limit": selected["limit"], "precompact_hook": True}
    await emit(Event(kind="options", data={"lesson_id": 25, "sdk_options": state.configured}))
    client = None
    closed = False
    try:
        if request.mode == "live":
            config.mkdir(parents=True, exist_ok=True)
            client = ClaudeSDKClient(options=options)
            await client.connect()
            await client.query(f"Call {TOOL} exactly once to read the bounded log. Say how many characters were removed and what the marker means. End with {MARKER}.")
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
                raise LessonError("Compaction lesson did not finish with a successful SDK result.")
        else:
            callback = bounded_result(selected["limit"], selected["retain_summary"])
            callbacks.append(callback)
            state.initialized = [{"session_id": "compaction-fixture"}]
            state.terminals = [{"session_id": "compaction-fixture", "subtype": "success", "is_error": False}]
            record_call(state, TOOL, {}, "bounded-call")
            state.results = [{"id": "bounded-call", "run_id": state.run_id, "is_error": False}]
            answers = [MARKER]
            if request.scenario == "missing-evidence":
                state.terminals.clear()
            elif request.scenario == "wrong-identity":
                state.terminals[-1]["session_id"] = "foreign"
            elif request.scenario == "missing-handler":
                callbacks.clear()
            elif request.scenario == "wrong-call":
                state.results[0]["id"] = "foreign"
            elif request.scenario == "wrong-bound":
                callbacks[0]["delivered"] += "extra"
    finally:
        if client is not None:
            await client.disconnect()
        closed = True
        report = compaction_report(state, selected, callbacks, compact_events, answers, closed)
        report["scenario"] = request.scenario
        report["expected_check"] = "passed" if report["experiment_passed"] else "needs-review"
        proof = {"experiment": report, "experiment_passed": report["experiment_passed"]}
        async with asyncio.timeout(1):
            await emit(Event(kind="evidence", data={"lesson_id": 25, "result": proof}))
    return proof


async def local_compaction(root: Path, request: RunRequest) -> dict:
    async def ignore(event: Event) -> None:
        pass

    return await execute_compaction(root, request.model_copy(update={"mode": "offline"}), Settings(), ignore)
