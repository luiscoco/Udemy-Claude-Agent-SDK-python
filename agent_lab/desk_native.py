"""Bounded native Python SDK support chat over host-scoped synthetic desk tools."""

import asyncio
import hashlib
import json
import math
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    HookMatcher,
    ResultMessage,
    SystemMessage,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
    create_sdk_mcp_server,
    query,
    tool,
)

from agent_lab.desk_approver import DeskApprover, Pending
from agent_lab.desk_lab import DeskOperation, Intent, evaluate_chat
from agent_lab.desk_store import CRM, DeskStore
from agent_lab.headless_native import native_environment, private_key

HAIKU = "claude-haiku-4-5-20251001"
DecisionCallback = Callable[[Pending], Awaitable[None]]


def _tool_result(value: dict[str, Any]) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": json.dumps(value, separators=(",", ":"))}],
            "is_error": value.get("is_error") is True}


def _native_passed(report: dict[str, Any], root: Path) -> bool:
    if not evaluate_chat(report, root) or report.get("native") is not True:
        return False
    frames = report.get("frames", [])
    init = [row for row in frames if row.get("kind") == "init"]
    terminal = [row for row in frames if row.get("kind") == "result"]
    if len(init) != 1 or len(terminal) != 1:
        return False
    result = terminal[0]
    cost = result.get("cost_usd")
    if (not isinstance(init[0].get("session_id"), str) or
            init[0]["session_id"] != result.get("session_id") or
            not isinstance(result.get("uuid"), str) or not result["uuid"] or
            result.get("subtype") != "success" or result.get("is_error") is not False or
            not isinstance(cost, (int, float)) or not math.isfinite(cost) or
            not 0 <= cost <= 0.10 or result.get("permission_denials") != []):
        return False
    tool_uses = [item for row in frames if row.get("kind") == "assistant"
                 for item in row.get("tools", [])]
    tool_results = [item for row in frames if row.get("kind") == "tool-results"
                    for item in row.get("results", [])]
    expected = {row["id"] for row in report["calls"]}
    if ({item.get("id") for item in tool_uses} != expected or
            {item.get("id") for item in tool_results} != expected or
            len(tool_uses) != len(expected) or len(tool_results) != len(expected)):
        return False
    for item in tool_results:
        matching = next((row for row in report["results"] if row["call"] == item.get("id")), None)
        if matching is None or item.get("is_error") is not matching["is_error"]:
            return False
    return True


async def native_chat(store: DeskStore, approver: DeskApprover, *, customer: str = "ada",
                      conversation: uuid.UUID | None = None, intent: Intent = "orders",
                      message: str = "Please inspect my orders.",
                      on_approval: DecisionCallback | None = None) -> dict[str, Any]:
    key = private_key()
    selected = await store.open(customer, "live") if conversation is None else store.require_open(conversation, customer, "live")
    run = uuid.uuid4()
    operation = DeskOperation(store, approver, run, selected.id, customer, "live", intent, on_approval)
    await store.append_message(selected.id, customer, "live", "customer", message)
    owned = store.root / "native" / str(selected.id)
    work, home = owned / "work", owned / "config"
    work.mkdir(parents=True, exist_ok=True)
    home.mkdir(parents=True, exist_ok=True)
    environment = native_environment(home, key)
    frames: list[dict[str, Any]] = []
    denials: list[dict[str, Any]] = []
    stops: list[dict[str, Any]] = []

    async def pre(data: dict[str, Any], call_id: str | None, _context: Any) -> dict[str, Any]:
        name = data.get("tool_name")
        raw = data.get("tool_input")
        tool_name = name.removeprefix("mcp__desk__") if isinstance(name, str) else ""
        try:
            operation.admit(tool_name, raw, call_id or "")
        except ValueError as exc:
            denials.append({"id": call_id, "tool": name, "reason": str(exc)})
            return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                    "permissionDecision": "deny", "permissionDecisionReason": str(exc)}}
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                "permissionDecision": "allow", "permissionDecisionReason": "Fixed synthetic desk tool"}}

    async def stop(data: dict[str, Any], _call_id: str | None, _context: Any) -> dict[str, Any]:
        required = {"orders", intent}
        missing = sorted(required - {row["tool"] for row in operation.calls.values()})
        active = data.get("stop_hook_active") is True
        stops.append({"missing": missing, "second_stop": active})
        if missing and not active:
            return {"decision": "block", "reason": "Call only the missing desk tool(s): " +
                    ", ".join("mcp__desk__" + name for name in missing) +
                    ". Use the exact host customer and fixed synthetic proposal."}
        return {}

    @tool("orders", "Read only the host customer's synthetic orders.", {})
    async def orders_handler(arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            return _tool_result(await operation.handle("orders", arguments))
        except ValueError as exc:
            return _tool_result({"is_error": True, "error": str(exc)})

    @tool("ticket", "Create one synthetic support ticket after reading orders.", {"subject": str})
    async def ticket_handler(arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            return _tool_result(await operation.handle("ticket", arguments))
        except ValueError as exc:
            return _tool_result({"is_error": True, "error": str(exc)})

    @tool("refund", "Propose the fixed 1000-cent synthetic refund for human decision.",
          {"orderId": str, "amountCents": int})
    async def refund_handler(arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            return _tool_result(await operation.handle("refund", arguments))
        except ValueError as exc:
            return _tool_result({"is_error": True, "error": str(exc)})

    expected = ["mcp__desk__orders"] + ([] if intent == "orders" else ["mcp__desk__" + intent])
    instruction = (f"You are the synthetic classroom support desk for host customer {customer}. "
                   "Never use a different customer or real payment system. "
                   "For THIS request first call mcp__desk__orders with {} even if earlier turns showed orders. "
                   "If the selected intent is ticket, then call mcp__desk__ticket with subject Delivery follow-up. "
                   f"If the selected intent is refund, then call mcp__desk__refund with "
                   f"orderId order-{customer} and amountCents 1000. "
                   "The host will request a human decision. Finish after the required tool results. "
                   f"Selected intent: {intent}. Call only the required tools for that intent.")
    options = ClaudeAgentOptions(
        cwd=work, model=HAIKU, system_prompt=instruction, env=environment,
        setting_sources=[], strict_mcp_config=True,
        mcp_servers={"desk": create_sdk_mcp_server(name="desk", tools=[
            orders_handler, ticket_handler, refund_handler])},
        tools=[], allowed_tools=expected, permission_mode="bypassPermissions",
        thinking={"type": "disabled"}, max_turns=6, max_budget_usd=0.10,
        resume=selected.nativeSession, fork_session=False,
        hooks={"PreToolUse": [HookMatcher(hooks=[pre])],  # type: ignore[list-item]
               "Stop": [HookMatcher(hooks=[stop])]},  # type: ignore[list-item]
    )
    error = None
    try:
        async with asyncio.timeout(150):
            followup = (f"Then call mcp__desk__{intent} once." if intent != "orders"
                        else "Then finish without another tool.")
            native_prompt = (f"NEW HOST OPERATION {run}. For this turn, first call "
                             "mcp__desk__orders with empty input. Wait for its tool result. "
                             f"{followup} Do not use old session order data as this turn's read. "
                             "Never call a write tool before the fresh orders result. "
                             f"Customer request: {message}")
            async for item in query(prompt=native_prompt, options=options):
                if isinstance(item, SystemMessage) and item.subtype == "init":
                    frames.append({"kind": "init", "session_id": item.data.get("session_id")})
                elif isinstance(item, AssistantMessage):
                    frames.append({"kind": "assistant", "session_id": item.session_id,
                                   "tools": [{"id": block.id, "name": block.name}
                                             for block in item.content if isinstance(block, ToolUseBlock)]})
                elif isinstance(item, UserMessage) and isinstance(item.content, list):
                    frames.append({"kind": "tool-results", "results": [
                        {"id": block.tool_use_id, "is_error": block.is_error is True}
                        for block in item.content if isinstance(block, ToolResultBlock)]})
                elif isinstance(item, ResultMessage):
                    frames.append({"kind": "result", "session_id": item.session_id,
                                   "uuid": item.uuid, "subtype": item.subtype,
                                   "is_error": item.is_error,
                                   "cost_usd": item.total_cost_usd,
                                   "permission_denials": item.permission_denials or []})
                if len(frames) > 100 or len(json.dumps(frames)) > 100_000:
                    raise ValueError("Native desk frame limit")
    except Exception as exc:
        error = type(exc).__name__
    finally:
        for call, pending in tuple(approver.pending.items()):
            if pending.run == run:
                approver.abort(call)
    terminal = next((row for row in frames if row["kind"] == "result"), None)
    init = next((row for row in frames if row["kind"] == "init"), None)
    delta = None
    if (error is None and terminal and init and terminal.get("subtype") == "success" and
            terminal.get("is_error") is False and terminal.get("session_id") == init.get("session_id") and
            isinstance(terminal.get("cost_usd"), (int, float))):
        try:
            delta = await store.record_native(selected.id, customer, terminal["session_id"],
                                              terminal["cost_usd"])
        except ValueError as exc:
            error = type(exc).__name__
    if error is None:
        await store.append_message(selected.id, customer, "live", "assistant",
                                   "Native support turn completed; inspect host evidence.")
    report = operation.report("normal", "failed" if error else "completed")
    report.update({"native": True, "source": "native-python-sdk/real-host-effects",
                   "frames": frames, "denials": denials, "stop_checks": stops,
                   "error_class": error, "cost_delta_usd": delta})
    report["experiment_passed"] = _native_passed(report, store.root)
    return report


async def native_close(store: DeskStore, customer: str,
                       conversation: uuid.UUID) -> dict[str, Any]:
    key = private_key()
    selected = store.require_open(conversation, customer, "live")
    parent = selected.nativeSession
    if parent is None or not selected.messages or selected.nativeReported is None:
        raise ValueError("A successful native chat is required before CRM close")
    before = hashlib.sha256(json.dumps([row.model_dump() for row in selected.messages],
                                       sort_keys=True).encode()).hexdigest()
    owned = store.root / "native" / str(conversation)
    work, home = owned / "work", owned / "config"
    environment = native_environment(home, key)
    schema = {"type": "object", "properties": {
        "customer": {"type": "string", "const": customer},
        "conversationId": {"type": "string", "const": str(conversation)},
        "summary": {"type": "string", "minLength": 1, "maxLength": 500},
        "resolution": {"type": "string", "enum": ["resolved", "needs-follow-up"]}},
        "required": ["customer", "conversationId", "summary", "resolution"],
        "additionalProperties": False}
    options = ClaudeAgentOptions(
        cwd=work, model=HAIKU, env=environment, setting_sources=[],
        strict_mcp_config=True, mcp_servers={}, tools=[], allowed_tools=[],
        permission_mode="dontAsk", thinking={"type": "disabled"},
        max_turns=4, max_budget_usd=0.10, resume=parent, fork_session=True,
        output_format={"type": "json_schema", "schema": schema},
        system_prompt="Return one concise synthetic CRM summary for the host conversation identity. No tools.",
    )
    frames: list[dict[str, Any]] = []
    error = None
    try:
        async with asyncio.timeout(75):
            async for item in query(
                prompt=(f"Close synthetic support conversation {conversation} for host customer "
                        f"{customer}. Summarize the prior support discussion as the exact schema object."),
                options=options):
                if isinstance(item, SystemMessage) and item.subtype == "init":
                    frames.append({"kind": "init", "session_id": item.data.get("session_id")})
                elif isinstance(item, AssistantMessage):
                    frames.append({"kind": "assistant", "session_id": item.session_id,
                                   "tool_names": [block.name for block in item.content
                                                  if isinstance(block, ToolUseBlock)]})
                elif isinstance(item, ResultMessage):
                    frames.append({"kind": "result", "session_id": item.session_id,
                                   "uuid": item.uuid, "subtype": item.subtype,
                                   "is_error": item.is_error, "cost_usd": item.total_cost_usd,
                                   "structured_output": item.structured_output,
                                   "permission_denials": item.permission_denials or []})
                if len(frames) > 25 or len(json.dumps(frames)) > 50_000:
                    raise ValueError("Native CRM frame limit")
    except Exception as exc:
        error = type(exc).__name__
    init = next((row for row in frames if row["kind"] == "init"), None)
    terminal = next((row for row in frames if row["kind"] == "result"), None)
    passed = False
    crm = None
    if error is None and init and terminal:
        cost = terminal.get("cost_usd")
        try:
            crm = CRM.model_validate_json(json.dumps(terminal.get("structured_output")))
            passed = (isinstance(init.get("session_id"), str) and
                      init["session_id"] != parent and
                      terminal.get("session_id") == init["session_id"] and
                      isinstance(terminal.get("uuid"), str) and terminal["uuid"] and
                      terminal.get("subtype") == "success" and
                      terminal.get("is_error") is False and
                      terminal.get("permission_denials") == [] and
                      isinstance(cost, (int, float)) and math.isfinite(cost) and
                      0 <= cost <= 0.10 and crm.customer == customer and
                      crm.conversationId == conversation and
                      all(row.get("tool_names") in ([], ["StructuredOutput"])
                          for row in frames if row["kind"] == "assistant"))
        except ValueError:
            passed = False
    if passed and crm is not None and terminal is not None:
        await store.close_native(conversation, customer, parent, crm, terminal["cost_usd"])
        after = DeskStore(store.root).state()
        selected_after = next(row for row in after.conversations if row.id == conversation)
        after_hash = hashlib.sha256(json.dumps([row.model_dump() for row in selected_after.messages],
                                               sort_keys=True).encode()).hexdigest()
        passed = (selected_after.status == "closed" and selected_after.crm == crm and
                  before == after_hash)
    return {"lesson": 50, "conversation": str(conversation), "customer": customer,
            "mode": "live", "native": True, "source": "native-python-sdk-restricted-fork",
            "parent_session": parent, "frames": frames, "error_class": error,
            "crm": crm.model_dump(mode="json") if crm else None,
            "transcript_sha256_before": before,
            "experiment_passed": passed}
