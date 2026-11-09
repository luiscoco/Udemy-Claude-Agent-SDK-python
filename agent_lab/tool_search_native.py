"""Bounded native MCP discovery and silent context controls for Lesson 58."""

from __future__ import annotations

import asyncio
import json
import math
import uuid
from pathlib import Path
from typing import Any

from agent_lab.headless_native import MODEL, native_environment, private_key
from agent_lab.tool_search_lab import (
    REFUND_ARGS,
    Config,
    RunInput,
    catalog,
    new_ledger,
    refund,
    verify_ledger,
)


def server_for(selected: Config, handler: Any) -> Any:
    from claude_agent_sdk._internal._mcp_compat import build_tool_server
    from claude_agent_sdk.types import McpSdkServerConfig
    from mcp.types import CallToolResult, Tool

    rows = catalog(selected)
    tools = []
    for row in rows:
        metadata = {"anthropic/alwaysLoad": row["alwaysLoad"]}
        if row.get("searchHint"):
            metadata["anthropic/searchHint"] = row["searchHint"]
        tools.append(Tool.model_validate({"name": row["name"],
                                          "description": row["description"],
                                          "inputSchema": row["inputSchema"], "_meta": metadata}))

    async def invoke(name: str, args: dict[str, Any]) -> CallToolResult:
        result = await handler(name, args)
        return CallToolResult.model_validate({"content": [{"type": "text", "text": json.dumps(result)}],
                                              "isError": not result.get("ok", False)})

    instance = build_tool_server("ops", "1.0.0", tools, invoke)
    return McpSdkServerConfig(type="sdk", name="ops", instance=instance)


def _has_reference(value: Any, name: str) -> bool:
    if isinstance(value, dict):
        return (value.get("type") == "tool_reference" and value.get("tool_name") == name) or any(
            _has_reference(child, name) for child in value.values())
    if isinstance(value, list):
        return any(_has_reference(child, name) for child in value)
    return False


def _options(owned: Path, selected: Config, server: Any, hook: Any = None,
             callback: Any = None, budget: float = 0.15) -> Any:
    from claude_agent_sdk import ClaudeAgentOptions, HookMatcher

    home = owned / "config"
    home.mkdir(exist_ok=True)
    env = native_environment(home, private_key())
    env["CLAUDE_CODE_MAX_RETRIES"] = "0"
    env["ENABLE_TOOL_SEARCH"] = selected.searchMode
    kwargs: dict[str, Any] = {}
    if hook is not None:
        kwargs["hooks"] = {"PreToolUse": [HookMatcher(hooks=[hook])]}
        kwargs["can_use_tool"] = callback
    return ClaudeAgentOptions(cwd=owned, env=env, model=MODEL, tools=["ToolSearch"],
                              allowed_tools=[], mcp_servers={"ops": server},
                              strict_mcp_config=True, setting_sources=[],
                              thinking={"type": "disabled"}, max_turns=8,
                              max_budget_usd=budget, **kwargs)


async def live(selected: RunInput, root: Path, run_id: str | None = None,
               abort: asyncio.Event | None = None) -> dict[str, Any]:
    from claude_agent_sdk import (
        AssistantMessage,
        PermissionResultAllow,
        PermissionResultDeny,
        ResultMessage,
        SystemMessage,
        ToolResultBlock,
        ToolUseBlock,
        UserMessage,
        query,
    )

    run_id = run_id or str(uuid.uuid4())
    new_ledger(root, run_id)
    owned = root / "lesson-58" / run_id
    target = "billing_refund_invoice" if selected.metadata == "clear" else "billing_op_7"
    target_full = f"mcp__ops__{target}"
    frames: list[dict[str, Any]] = []
    pending: dict[str, Any] = {}
    exception = None
    interrupted = False
    closed = False
    cost = None
    stream: Any = None

    async def hook(data: dict[str, Any], call_id: str | None, _context: Any) -> dict[str, Any]:
        name, value = data.get("tool_name"), data.get("tool_input")
        admit = bool(call_id and (name == "ToolSearch" or
                     (name == target_full and value == REFUND_ARGS and pending.get("searched"))))
        if admit and name == target_full:
            pending.update({"id": call_id, "args": value})
        frames.append({"kind": "hook", "id": call_id, "tool": name, "admitted": admit})
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                "permissionDecision": "ask" if admit else "deny",
                "permissionDecisionReason": "Only ToolSearch and the exact synthetic refund are permitted"}}

    async def callback(name: str, value: dict[str, Any], context: Any) -> Any:
        admit = bool(context.tool_use_id and (name == "ToolSearch" or
                     (name == target_full and value == REFUND_ARGS and
                      pending.get("id") == context.tool_use_id)))
        frames.append({"kind": "callback", "id": context.tool_use_id,
                       "tool": name, "admitted": admit})
        return PermissionResultAllow() if admit else PermissionResultDeny(message="Outside synthetic refund scope")

    async def handler(name: str, args: dict[str, Any]) -> dict[str, Any]:
        if name != target or args != REFUND_ARGS or not pending.get("searched") or not pending.get("id"):
            return {"ok": False, "error": "unsupported or unadmitted"}
        result = refund(root, run_id, pending["id"], args)
        frames.append({"kind": "handler", "id": pending["id"], "tool": target_full,
                       "ok": result.get("ok", False), "receipt": result.get("refundId")})
        pending.pop("id", None)
        return result

    server = server_for(selected, handler)
    options = _options(owned, selected, server, hook, callback, selected.budget)
    prompt = ("Use ToolSearch to discover the synthetic billing refund tool before calling it. "
              "Refund the duplicate charge on invoice INV-2042 for exactly 4900 EUR cents, "
              "reason duplicate-charge. Call only the discovered refund tool once. "
              "Do not use other tools or change any other records.")
    try:
        async with asyncio.timeout(90):
            stream = query(prompt=prompt, options=options)
            async for message in stream:
                if abort and abort.is_set():
                    raise asyncio.CancelledError
                if isinstance(message, SystemMessage) and message.subtype == "init":
                    frames.append({"kind": "init", "session": message.data.get("session_id"),
                                   "tools": message.data.get("tools")})
                elif isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, ToolUseBlock):
                            frames.append({"kind": "call", "id": block.id, "tool": block.name,
                                           "input": block.input})
                elif isinstance(message, UserMessage) and isinstance(message.content, list):
                    for block in message.content:
                        if isinstance(block, ToolResultBlock):
                            raw = str(block.content)
                            reference = _has_reference(block.content, target_full)
                            frames.append({"kind": "result", "id": block.tool_use_id,
                                           "isError": block.is_error is True,
                                           "reference": reference,
                                           "receipt": "RF-2042-1" in raw})
                            if reference and block.is_error is not True:
                                pending["searched"] = True
                elif isinstance(message, ResultMessage):
                    cost = message.total_cost_usd if isinstance(message.total_cost_usd, (float, int)) and math.isfinite(message.total_cost_usd) else None
                    frames.append({"kind": "terminal", "session": message.session_id,
                                   "subtype": message.subtype, "isError": message.is_error,
                                   "costUsd": cost})
                    break
    except (asyncio.CancelledError, TimeoutError) as exc:
        interrupted = True
        exception = type(exc).__name__
    except Exception as exc:
        exception = type(exc).__name__
    finally:
        if stream is not None:
            try:
                await stream.aclose()
                closed = True
            except Exception as exc:
                exception = type(exc).__name__
        else:
            closed = True
    ledger, digest = verify_ledger(root, run_id)
    kinds = [row["kind"] for row in frames]
    search_results = [i for i, row in enumerate(frames) if row["kind"] == "result" and row["reference"]]
    handlers = [i for i, row in enumerate(frames) if row["kind"] == "handler" and row["ok"]]
    refund_id = frames[handlers[0]]["id"] if len(handlers) == 1 else None
    search_id = frames[search_results[0]]["id"] if search_results else None
    checked = bool(search_results and handlers and search_results[0] < handlers[0] and
                   len(handlers) == 1 and len(ledger["refunds"]) == 1 and
                   ledger["refunds"][0] == {"refundId": "RF-2042-1", "callId": refund_id,
                                             "args": REFUND_ARGS} and
                   any(row["kind"] == "call" and row["id"] == search_id and
                       row["tool"] == "ToolSearch" for row in frames) and
                   any(row["kind"] == "call" and row["id"] == refund_id and
                       row["tool"] == target_full and row["input"] == REFUND_ARGS for row in frames) and
                   all(any(row["kind"] == gate and row["id"] == refund_id and row["admitted"]
                           for row in frames) for gate in ("hook", "callback")) and
                   any(row["kind"] == "result" and row["id"] == refund_id and
                       row["receipt"] and not row["isError"] for row in frames) and
                   kinds.count("init") == 1 and kinds.count("terminal") == 1 and
                   frames[-1]["kind"] == "terminal" and frames[-1]["subtype"] == "success" and
                   frames[-1]["session"] == frames[0]["session"] and
                   not frames[-1]["isError"] and cost is not None and cost <= 0.15 and
                   closed and not interrupted and not exception)
    return {"runId": run_id, "mode": "live", "metadata": selected.metadata,
            "frames": frames[:100], "ledger": ledger, "ledgerSha256": digest,
            "sdkQueries": 1, "costUsd": cost, "closed": closed, "interrupted": interrupted,
            "exception": exception, "check": "pass" if checked else "needs-review"}


async def measure(selected: Config, root: Path, run_id: str | None = None) -> dict[str, Any]:
    from claude_agent_sdk import ClaudeSDKClient

    run_id = run_id or str(uuid.uuid4())
    new_ledger(root, run_id)
    owned = root / "lesson-58" / run_id

    async def unsupported(_name: str, _args: dict[str, Any]) -> dict[str, Any]:
        return {"ok": False, "error": "measurement forbids all calls"}

    server = server_for(selected, unsupported)
    options = _options(owned, selected, server)
    client = ClaudeSDKClient(options=options)

    async def silent() -> Any:
        await asyncio.Event().wait()
        if False:
            yield None

    connected = False
    try:
        async with asyncio.timeout(30):
            await client.connect(silent())
            for _ in range(30):
                status = await client.get_mcp_status()
                connected = any(row.get("name") == "ops" and row.get("status") == "connected"
                                for row in status.get("mcpServers", []))
                if connected:
                    break
                await asyncio.sleep(0.2)
            usage = await client.get_context_usage()
    finally:
        await client.disconnect()
    mcp = usage.get("mcpTools", [])
    return {"runId": run_id, "kind": "native-silent-context", "connected": connected,
            "mcpStatus": [{"name": row.get("name"), "status": row.get("status"),
                           "toolCount": len(row.get("tools", []))}
                          for row in status.get("mcpServers", [])],
            "catalogCount": 64, "totalTokens": usage.get("totalTokens"),
            "categories": usage.get("categories"), "mcpTools": mcp,
            "loadedCount": sum(bool(row.get("isLoaded")) for row in mcp),
            "sdkQueries": 0, "modelInputTurns": 0,
            "note": "No model input turns; control traffic may still occur."}
