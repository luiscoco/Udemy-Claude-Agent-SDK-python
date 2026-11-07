"""Host-owned bounded retries around a real SDK MCP refund tool."""

import asyncio
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    ClaudeAgentOptions,
    ClaudeSDKClient,
    SystemMessage,
    create_sdk_mcp_server,
    tool,
)

from agent_lab.config import Settings
from agent_lab.foundations import Evidence, record_call
from agent_lab.models import Event, LessonError, RunRequest, lesson_request

TOOL = "mcp__billing__refund"
ORDER = "A-100"
KEY = f"refund:{ORDER}:500"
MAX_ATTEMPTS = 3
BACKOFF = (0.01, 0.02)


def refund_attempt(outcome: str, attempt: int, ledger: set[str], order_id: str | None) -> dict[str, Any]:
    """Apply at most one in-memory write; describe the selected fixed failure."""
    if order_id != ORDER:
        return {"attempt": attempt, "key": KEY, "status": "permanent", "transient": False, "is_error": True, "writes_applied": len(ledger)}
    if outcome == "permanent":
        return {"attempt": attempt, "key": KEY, "status": "permanent", "transient": False, "is_error": True, "writes_applied": len(ledger)}
    if attempt == 1:
        ledger.add(KEY)
        status = "ambiguous-after-write"
    elif outcome == "exhausted" or attempt == 2:
        status = "transient-timeout"
    else:
        status = "already-applied"
    return {"attempt": attempt, "key": KEY, "status": status, "transient": status != "already-applied", "is_error": status != "already-applied", "writes_applied": len(ledger)}


def retry_options(root: Path, config: Path, request: RunRequest, settings: Settings, handler: Any) -> ClaudeAgentOptions:
    from agent_lab.sdk import isolated_env, resolve_cli_path

    return ClaudeAgentOptions(
        cwd=str(root.resolve()),
        model=settings.model,
        cli_path=resolve_cli_path(settings) if request.mode == "live" else None,
        mcp_servers={"billing": create_sdk_mcp_server(name="billing", tools=[handler])},
        tools=[TOOL],
        allowed_tools=[TOOL],
        setting_sources=[],
        strict_mcp_config=True,
        env=isolated_env(config.resolve()),
        system_prompt={"type": "preset", "preset": "claude_code", "append": "This is a fixed retry lesson. In each user turn call the one billing tool exactly once for A-100, then stop. Never retry autonomously; the host decides whether to send another turn. Use no other tools."},
        max_turns=request.max_turns,
        max_budget_usd=request.max_budget_usd,
    )


def retry_report(state: Evidence, selected: dict, callbacks: list[dict], ledger: set[str], decisions: list[dict], closed: bool) -> dict:
    base = state.report()
    expected = {"recover": ["ambiguous-after-write", "transient-timeout", "already-applied"], "permanent": ["permanent"], "exhausted": ["ambiguous-after-write", "transient-timeout", "transient-timeout"]}[selected["outcome"]]
    expected_decisions = ["retry"] * (len(expected) - 1) + [{"recover": "confirmed", "permanent": "reject", "exhausted": "exhausted"}[selected["outcome"]]]
    init = state.initialized[-1] if state.initialized else {}
    session = init.get("session_id")
    terminals_ok = bool(session and len(state.terminals) == len(expected) and all(row.get("session_id") == session and row.get("subtype") == "success" and row.get("is_error") is False for row in state.terminals))
    calls = [row for row in state.calls if row.get("name") == TOOL and not row.get("parent_tool_use_id")]
    paired = bool(
        len(calls) == len(state.calls) == len(state.results) == len(callbacks) == len(expected)
        and all(
            call.get("run_id") == state.run_id
            and call.get("arguments", {}).get("order_id") == ORDER
            and result.get("id") == call.get("id")
            and result.get("run_id") == state.run_id
            and result.get("is_error") is callback.get("is_error")
            for call, result, callback in zip(calls, state.results, callbacks, strict=True)
        )
        and len({row.get("id") for row in calls}) == len(calls)
    )
    callback_ok = [row.get("status") for row in callbacks] == expected and all(row.get("attempt") == index and row.get("key") == KEY for index, row in enumerate(callbacks, 1))
    ledger_ok = len(ledger) == (0 if selected["outcome"] == "permanent" else 1) and (not ledger or ledger == {KEY}) and all(row.get("writes_applied") == len(ledger) for row in callbacks)
    policy_ok = [row.get("decision") for row in decisions] == expected_decisions and [row.get("attempt") for row in decisions] == list(range(1, len(expected) + 1)) and all(row.get("delay_seconds") == BACKOFF[index] for index, row in enumerate(decisions[:-1]))
    observed = bool(base["experiment_passed"] and terminals_ok and paired and callback_ok and ledger_ok and policy_ok and closed)
    return {
        **base,
        "selected": selected,
        "callbacks": callbacks,
        "ledger_keys": sorted(ledger),
        "decisions": decisions,
        "max_attempts": MAX_ATTEMPTS,
        "deadline_seconds": 90,
        "call_result_correlated": paired,
        "single_write_verified": ledger_ok,
        "retry_policy_verified": policy_ok,
        "connection_closed": closed,
        "observation_passed": observed,
        "experiment_passed": observed,
        "check_scope": "One fixed MCP refund call/result per host attempt, a single in-memory ledger effect, bounded backoff and attempts, correct transient/permanent stop decision, and successful SDK turns in one initialized session. No real refund or arbitrary order is authorized.",
    }


async def execute_retry(root: Path, request: RunRequest, settings: Settings, emit: Any, config: Path | None = None) -> dict:
    from agent_lab.sdk import message_data, require_live_access

    request = lesson_request(28, request)
    root = await asyncio.to_thread(root.resolve)
    selected = request.lesson_options
    config = config or root.parent / "config"
    state = Evidence(28, root.parent.name, root, selected, "live SDK stream and actual host callbacks" if request.mode == "live" else "local host effects plus explicitly recorded SDK correlation fixtures", request.max_turns, request.max_budget_usd)
    callbacks: list[dict] = []
    decisions: list[dict] = []
    ledger: set[str] = set()

    @tool("refund", "Apply the fixed in-memory A-100 refund key once; return its selected teaching status.", {"order_id": str})
    async def refund(arguments: dict) -> dict:
        row = refund_attempt(selected["outcome"], len(callbacks) + 1, ledger, arguments.get("order_id"))
        callbacks.append(row)
        return {"content": [{"type": "text", "text": row["status"]}], "is_error": row["is_error"]}

    if request.mode == "live":
        require_live_access(settings)
    options = retry_options(root, config, request, settings, refund)
    state.configured = {"tools": options.tools, "allowed_tools": options.allowed_tools, "setting_sources": options.setting_sources, "strict_mcp_config": options.strict_mcp_config, "max_attempts": MAX_ATTEMPTS}
    await emit(Event(kind="options", data={"lesson_id": 28, "sdk_options": state.configured}))
    client = None
    closed = False
    try:
        if request.mode == "live":
            config.mkdir(parents=True, exist_ok=True)
            client = ClaudeSDKClient(options=options)
            await client.connect()
            async with asyncio.timeout(90):
                for attempt in range(1, MAX_ATTEMPTS + 1):
                    previous = len(callbacks)
                    await client.query(f"Call {TOOL} exactly once with order_id {ORDER}. Do not call any other tool or retry within this turn. Then briefly report the tool status.")
                    async for message in client.receive_response():
                        if isinstance(message, SystemMessage) and message.subtype == "api_retry" and message.data.get("error_status") == 401:
                            raise PermissionError("Claude rejected authentication (HTTP 401). No host retry was attempted.")
                        data = message_data(message)
                        event = Event(kind="result" if data["message_class"] == "ResultMessage" else "message", data=data)
                        state.observe(event)
                        await emit(event)
                    if not state.terminals or state.terminals[-1].get("subtype") != "success" or state.terminals[-1].get("is_error") is not False:
                        raise LessonError("The SDK turn failed; the host did not retry an unknown provider outcome.")
                    if len(callbacks) != previous + 1:
                        raise LessonError("The model did not make exactly one fixed refund call in this turn.")
                    row = callbacks[-1]
                    decision = "retry" if row["transient"] and attempt < MAX_ATTEMPTS else "exhausted" if row["transient"] else "reject" if row["status"] == "permanent" else "confirmed"
                    decisions.append({"attempt": attempt, "decision": decision, **({"delay_seconds": BACKOFF[attempt - 1]} if decision == "retry" else {})})
                    if decision != "retry":
                        break
                    await asyncio.sleep(BACKOFF[attempt - 1])
        else:
            state.initialized = [{"session_id": "retry-fixture"}]
            for attempt in range(1, MAX_ATTEMPTS + 1):
                row = refund_attempt(selected["outcome"], attempt, ledger, ORDER)
                callbacks.append(row)
                record_call(state, TOOL, {"order_id": ORDER}, f"refund-{attempt}")
                state.results.append({"id": f"refund-{attempt}", "run_id": state.run_id, "is_error": row["is_error"]})
                state.terminals.append({"session_id": "retry-fixture", "subtype": "success", "is_error": False})
                decision = "retry" if row["transient"] and attempt < MAX_ATTEMPTS else "exhausted" if row["transient"] else "reject" if row["status"] == "permanent" else "confirmed"
                decisions.append({"attempt": attempt, "decision": decision, **({"delay_seconds": BACKOFF[attempt - 1]} if decision == "retry" else {})})
                if decision != "retry":
                    break
            if request.scenario == "missing-evidence":
                state.terminals.clear()
            elif request.scenario == "wrong-identity":
                state.terminals[-1]["session_id"] = "foreign"
            elif request.scenario == "missing-handler":
                callbacks.clear()
            elif request.scenario == "unmatched-result":
                state.results[0]["id"] = "foreign"
            elif request.scenario == "duplicate-write":
                ledger.add("duplicate")
            elif request.scenario == "wrong-stop":
                decisions[-1]["decision"] = "retry"
    finally:
        if client is not None:
            await client.disconnect()
        closed = True
        report = retry_report(state, selected, callbacks, ledger, decisions, closed)
        report["scenario"] = request.scenario
        report["expected_check"] = "passed" if report["experiment_passed"] else "needs-review"
        proof = {"experiment": report, "experiment_passed": report["experiment_passed"]}
        async with asyncio.timeout(1):
            await emit(Event(kind="evidence", data={"lesson_id": 28, "result": proof}))
    return proof


async def local_retry(root: Path, request: RunRequest) -> dict:
    async def ignore(event: Event) -> None:
        pass

    return await execute_retry(root, request.model_copy(update={"mode": "offline"}), Settings(), ignore)
