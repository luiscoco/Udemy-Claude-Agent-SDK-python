"""Validate real TodoWrite proposals and commit only successful tool results."""

import asyncio
import json
from pathlib import Path
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, HookMatcher, SystemMessage

from agent_lab.config import Settings
from agent_lab.foundations import Evidence, record_call
from agent_lab.models import Event, LessonError, RunRequest, lesson_request

TASKS = ("Read lesson note", "Verify evidence", "Publish summary")
FORMS = ("Reading lesson note", "Verifying evidence", "Publishing summary")
STATUSES = frozenset({"pending", "in_progress", "completed"})
ADVANCE = frozenset({("pending", "in_progress"), ("in_progress", "completed")})


def proposals(sequence: str) -> list[dict[str, str]]:
    steps = {
        "valid": [("in_progress", "pending", "pending"), ("completed", "in_progress", "pending"), ("completed", "completed", "pending")],
        "skip": [("completed", "pending", "pending")],
        "parallel": [("in_progress", "in_progress", "pending")],
        "reopen": [("in_progress", "pending", "pending"), ("completed", "pending", "pending"), ("pending", "pending", "pending")],
    }[sequence]
    return [dict(zip(TASKS, row, strict=True)) for row in steps]


def todo_items(statuses: dict[str, str]) -> list[dict[str, str]]:
    return [{"content": name, "status": statuses[name], "activeForm": form} for name, form in zip(TASKS, FORMS, strict=True)]


def validate_todos(ledger: dict[str, str], argument: Any) -> tuple[bool, str, dict[str, str]]:
    if not isinstance(argument, dict) or not isinstance(argument.get("todos"), list):
        return False, "Expected a todos list.", {}
    items = argument["todos"]
    if len(items) != len(TASKS) or any(not isinstance(item, dict) for item in items):
        return False, "Provide exactly the three owned tasks.", {}
    names = [item.get("content") for item in items]
    if any(not isinstance(name, str) for name in names):
        return False, "Task identities must be text.", {}
    if set(names) != set(TASKS) or len(set(names)) != len(TASKS):
        return False, "Task identities must match the owned list exactly.", {}
    if any(item.get("activeForm") != FORMS[TASKS.index(item["content"])] for item in items):
        return False, "Use the fixed active forms.", {}
    candidate = {item["content"]: item.get("status") for item in items}
    if any(status not in STATUSES for status in candidate.values()):
        return False, "Unknown task status.", {}
    if sum(status == "in_progress" for status in candidate.values()) > 1:
        return False, "Only one task may be in progress.", {}
    for name in TASKS:
        old, new = ledger[name], candidate[name]
        if old != new and (old, new) not in ADVANCE:
            return False, f"{name}: {old} cannot change to {new}.", {}
    return True, "", candidate


def todo_options(root: Path, config: Path, request: RunRequest, settings: Settings, pre: Any, post: Any) -> ClaudeAgentOptions:
    from agent_lab.sdk import isolated_env, resolve_cli_path

    return ClaudeAgentOptions(
        cwd=str(root.resolve()),
        model=settings.model,
        cli_path=resolve_cli_path(settings) if request.mode == "live" else None,
        tools=["TodoWrite"],
        allowed_tools=["TodoWrite"],
        setting_sources=[],
        strict_mcp_config=True,
        env=isolated_env(config.resolve()) | {"CLAUDE_CODE_ENABLE_TASKS": "0"},
        system_prompt={"type": "preset", "preset": "claude_code", "append": "This is a fixed TodoWrite validation lesson. For each user turn, call TodoWrite exactly once with exactly the requested three items, even if the host may reject a transition. Do not alter statuses or retry autonomously. Use no other tools."},
        hooks={"PreToolUse": [HookMatcher(matcher="TodoWrite", hooks=[pre])], "PostToolUse": [HookMatcher(matcher="TodoWrite", hooks=[post])]},
        max_turns=request.max_turns,
        max_budget_usd=request.max_budget_usd,
    )


def todo_report(state: Evidence, selected: dict, pre_events: list[dict], post_events: list[dict], ledger: dict[str, str], closed: bool) -> dict:
    base = state.report()
    requested = proposals(selected["sequence"])
    expected_allowed = [True] * (len(requested) - (selected["sequence"] != "valid")) + ([False] if selected["sequence"] != "valid" else [])
    expected_ledger = requested[-1] if selected["sequence"] == "valid" else requested[-2] if selected["sequence"] == "reopen" else dict.fromkeys(TASKS, "pending")
    init = state.initialized[-1] if state.initialized else {}
    session = init.get("session_id")
    terminals_ok = bool(session and len(state.terminals) == len(requested) and all(row.get("session_id") == session and row.get("subtype") == "success" and row.get("is_error") is False for row in state.terminals))
    calls = [row for row in state.calls if row.get("name") == "TodoWrite" and not row.get("parent_tool_use_id")]
    paired = bool(
        len(calls) == len(state.calls) == len(state.results) == len(pre_events) == len(requested)
        and len({call.get("id") for call in calls}) == len(calls)
        and all(
            call.get("run_id") == state.run_id
            and result.get("id") == call.get("id")
            and result.get("run_id") == state.run_id
            and result.get("is_error") is (not expected_allowed[index])
            and pre.get("id") == call.get("id")
            and pre.get("allowed") is expected_allowed[index]
            and pre.get("proposal") == requested[index]
            for index, (call, result, pre) in enumerate(zip(calls, state.results, pre_events, strict=True))
        )
    )
    accepted_ids = [row["id"] for row in pre_events if row.get("allowed")]
    post_ok = [row.get("id") for row in post_events] == accepted_ids and all(row.get("committed") is True for row in post_events)
    ledger_ok = ledger == expected_ledger and sum(status == "in_progress" for status in ledger.values()) <= 1
    suggestion = next((f"Finish {name}." for name in TASKS if ledger[name] == "in_progress"), None) or next((f"Start {name}." for name in TASKS if ledger[name] == "pending"), "All tasks are complete.")
    observed = bool(base["experiment_passed"] and terminals_ok and paired and post_ok and ledger_ok and closed)
    return {
        **base,
        "selected": selected,
        "pre_tool_events": pre_events,
        "post_tool_events": post_events,
        "ledger": ledger.copy(),
        "suggestion": suggestion,
        "call_result_correlated": paired,
        "accepted_commits_verified": post_ok,
        "ledger_verified": ledger_ok,
        "connection_closed": closed,
        "observation_passed": observed,
        "experiment_passed": observed,
        "check_scope": "Each fixed TodoWrite proposal must have one matching SDK call/result and PreToolUse decision. Only accepted calls with a PostToolUse callback commit the host ledger. Rejected transitions preserve the prior state. All turns share one initialized SDK session; the suggestion comes from the final host ledger.",
    }


async def execute_todos(root: Path, request: RunRequest, settings: Settings, emit: Any, config: Path | None = None) -> dict:
    from agent_lab.sdk import message_data, require_live_access

    request = lesson_request(30, request)
    root = await asyncio.to_thread(root.resolve)
    selected = request.lesson_options
    config = config or root.parent / "config"
    ledger = dict.fromkeys(TASKS, "pending")
    state = Evidence(30, root.parent.name, root, selected, "live SDK stream and actual host callbacks" if request.mode == "live" else "local host effects plus explicitly recorded SDK correlation fixtures", request.max_turns, request.max_budget_usd)
    pre_events: list[dict] = []
    post_events: list[dict] = []
    pending: dict[str, dict[str, str]] = {}

    async def pre(data: dict, tool_use_id: str | None, context: Any) -> dict:
        argument = data.get("tool_input")
        allowed, reason, candidate = validate_todos(ledger, argument)
        items = argument.get("todos", []) if isinstance(argument, dict) else []
        row = {"id": tool_use_id, "allowed": allowed, "reason": reason, "proposal": candidate if allowed else {item.get("content"): item.get("status") for item in items if isinstance(item, dict)}}
        pre_events.append(row)
        if allowed and tool_use_id:
            pending[tool_use_id] = candidate
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow" if allowed else "deny", "permissionDecisionReason": reason or "Validated owned todo transition."}}

    async def post(data: dict, tool_use_id: str | None, context: Any) -> dict:
        candidate = pending.pop(tool_use_id, None) if tool_use_id else None
        if candidate is not None:
            ledger.update(candidate)
            post_events.append({"id": tool_use_id, "committed": True, "ledger": ledger.copy()})
        return {}

    if request.mode == "live":
        require_live_access(settings)
    options = todo_options(root, config, request, settings, pre, post)
    state.configured = {"tools": options.tools, "allowed_tools": options.allowed_tools, "setting_sources": options.setting_sources, "strict_mcp_config": options.strict_mcp_config, "hooks": sorted(options.hooks or {})}
    await emit(Event(kind="options", data={"lesson_id": 30, "sdk_options": state.configured}))
    client = None
    closed = False
    try:
        if request.mode == "live":
            config.mkdir(parents=True, exist_ok=True)
            client = ClaudeSDKClient(options=options)
            await client.connect()
            for statuses in proposals(selected["sequence"]):
                previous = len(pre_events)
                await client.query("Call TodoWrite exactly once with this JSON todos list. Preserve every content, activeForm and status value exactly, including invalid transitions for host validation. Do not retry within this turn: " + json.dumps({"todos": todo_items(statuses)}))
                async for message in client.receive_response():
                    if isinstance(message, SystemMessage) and message.subtype == "api_retry" and message.data.get("error_status") == 401:
                        raise PermissionError("Claude rejected authentication (HTTP 401). No host retry was attempted.")
                    item = message_data(message)
                    event = Event(kind="result" if item["message_class"] == "ResultMessage" else "message", data=item)
                    state.observe(event)
                    await emit(event)
                if not state.terminals or state.terminals[-1].get("subtype") != "success" or state.terminals[-1].get("is_error") is not False:
                    raise LessonError("TodoWrite SDK turn did not finish successfully.")
                if len(pre_events) != previous + 1:
                    raise LessonError("The model did not make exactly one TodoWrite proposal in this turn.")
        else:
            state.initialized = [{"session_id": "todo-fixture"}]
            for index, statuses in enumerate(proposals(selected["sequence"]), 1):
                cid = f"todo-{index}"
                argument = {"todos": todo_items(statuses)}
                await pre({"tool_input": argument}, cid, None)
                record_call(state, "TodoWrite", argument, cid)
                allowed = pre_events[-1]["allowed"]
                state.results.append({"id": cid, "run_id": state.run_id, "is_error": not allowed})
                state.terminals.append({"session_id": "todo-fixture", "subtype": "success", "is_error": False})
                if allowed:
                    await post({}, cid, None)
            if request.scenario == "missing-evidence":
                state.terminals.clear()
            elif request.scenario == "wrong-identity":
                state.terminals[-1]["session_id"] = "foreign"
            elif request.scenario == "missing-hook":
                pre_events.clear()
            elif request.scenario == "unmatched-call":
                state.results[0]["id"] = "foreign"
            elif request.scenario == "wrong-ledger":
                ledger[TASKS[0]] = "pending"
            elif request.scenario == "extra-post":
                post_events.append({"id": "foreign", "committed": True})
    finally:
        if client is not None:
            await client.disconnect()
        closed = True
        report = todo_report(state, selected, pre_events, post_events, ledger, closed)
        report["scenario"] = request.scenario
        report["expected_check"] = "passed" if report["experiment_passed"] else "needs-review"
        proof = {"experiment": report, "experiment_passed": report["experiment_passed"]}
        async with asyncio.timeout(1):
            await emit(Event(kind="evidence", data={"lesson_id": 30, "result": proof}))
    return proof


async def local_todos(root: Path, request: RunRequest) -> dict:
    async def ignore(event: Event) -> None:
        pass

    return await execute_todos(root, request.model_copy(update={"mode": "offline"}), Settings(), ignore)
