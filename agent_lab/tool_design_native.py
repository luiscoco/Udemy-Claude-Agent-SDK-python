"""Optional bounded native Agent SDK comparison over the same catalog handlers."""

import asyncio
import json
import math
import uuid
from pathlib import Path
from typing import Any

from agent_lab.config import Settings
from agent_lab.headless_native import MODEL, native_environment, private_key
from agent_lab.tool_design_catalog import PROFILE_TOOLS, SCHEMAS, Catalog
from agent_lab.tool_design_lab import BYTE_LIMIT, ROW_LIMIT, DesignInput, summarize


def admission(settings: Settings, selected: DesignInput) -> str:
    if (selected.mode != "live" or not selected.consent or not settings.enable_live or
            selected.budget < 0.25):
        raise PermissionError("Live access, fresh consent and a $0.25 reservation are required")
    return private_key()


async def native(selected: DesignInput, run_id: uuid.UUID, settings: Settings,
                 root: Path, abort: asyncio.Event | None = None,
                 on_frame: Any = None, catalog: Catalog | None = None) -> dict[str, Any]:
    key = admission(settings, selected)
    from claude_agent_sdk import (  # Imported only after paid admission.
        AssistantMessage,
        ClaudeAgentOptions,
        HookMatcher,
        ResultMessage,
        SystemMessage,
        TextBlock,
        ToolResultBlock,
        ToolUseBlock,
        UserMessage,
        create_sdk_mcp_server,
        query,
        tool,
    )
    from mcp.types import ToolAnnotations

    catalog = catalog or Catalog()
    before = catalog.snapshot_sha256
    owned = root / str(run_id)
    owned.mkdir(parents=True, exist_ok=False)
    work, home = owned / "work", owned / "config"
    work.mkdir()
    home.mkdir()
    environment = native_environment(home, key)
    environment["CLAUDE_CODE_MAX_RETRIES"] = "0"
    frames: list[dict[str, Any]] = []
    receipts: list[dict[str, Any]] = []
    pending: dict[str, tuple[str, dict[str, Any]]] = {}
    used: set[str] = set()
    terminal: dict[str, Any] | None = None
    exception: str | None = None
    interrupted = False
    closed = False
    overflow = False
    stream: Any = None

    async def emit(kind: str, **data: Any) -> None:
        nonlocal overflow
        frame = {"runId": str(run_id), "seq": len(frames) + 1, "kind": kind, **data}
        if len(frames) >= ROW_LIMIT or len(json.dumps(frames, default=str)) + len(json.dumps(frame, default=str)) > BYTE_LIMIT:
            overflow = True
            raise OverflowError("Bounded native tool trace exceeded")
        frames.append(frame)
        if on_frame is not None:
            await on_frame(frame)

    def normalized(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return SCHEMAS[name].model_validate(arguments).model_dump()

    async def pre(data: dict[str, Any], call_id: str | None, _context: Any) -> dict[str, Any]:
        name = str(data.get("tool_name", ""))
        tool_name = name.removeprefix("mcp__catalog__")
        raw = data.get("tool_input")
        reason = "Only selected catalog tools and fixed format are allowed"
        try:
            if (name != "mcp__catalog__" + tool_name or tool_name not in PROFILE_TOOLS[selected.profile] or
                    not isinstance(raw, dict) or not call_id or len(pending) >= 12):
                raise ValueError(reason)
            arguments = normalized(tool_name, raw)
            if tool_name != "lookup" and arguments["format"] != selected.format:
                raise ValueError("Use the selected format; change the run selector before requesting another format")
            pending[call_id] = (tool_name, arguments)
            await emit("admitted", callId=call_id, tool=tool_name, input=arguments)
            allowed = True
        except Exception:
            allowed = False
            await emit("denied", callId=call_id, tool=tool_name, reason=reason)
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                "permissionDecision": "allow" if allowed else "deny",
                "permissionDecisionReason": "Selected read-only catalog" if allowed else reason}}

    async def handle(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            parsed = normalized(name, arguments)
            candidates = [identifier for identifier, item in pending.items()
                          if identifier not in used and item == (name, parsed)]
            if len(candidates) != 1:
                raise ValueError("Handler call did not match exactly one admitted SDK tool use")
            call_id = candidates[0]
            used.add(call_id)
            row = catalog.invoke(selected.profile, name, arguments, call_id=call_id)
            receipts.append(row)
            await emit("receipt", callId=call_id, tool=name, envelopeBytes=row["envelopeBytes"],
                       executed=row["executed"], errorCode=row["errorCode"])
            return {"content": row["envelope"]["content"], "is_error": row["envelope"]["isError"]}
        except Exception as exc:
            await emit("handler-error", tool=name, error=type(exc).__name__)
            return {"content": [{"type": "text", "text": json.dumps({"error": "UNMATCHED_ADMISSION",
                       "recovery": "Use one selected catalog tool with the declared arguments"})}], "is_error": True}

    tools = []
    for name in PROFILE_TOOLS[selected.profile]:
        schema = SCHEMAS[name].model_json_schema()
        if name != "lookup":
            schema["properties"]["format"]["enum"] = [selected.format]
            schema["properties"]["format"]["default"] = selected.format
        description = ("Look things up. Pass q." if name == "lookup" else
                       "Search synthetic read-only catalog by exact category and integer EUR cents. "
                       "Stock means stock > 0. Follow nextCursor with unchanged filters until null; empty items is success. "
                       "Clear mismatched cursor and restart." if name == "catalog_search" else
                       "Get one synthetic read-only product by stable SKU-###, not name. "
                       "If missing, search for an existing ID. Price is integer EUR cents.")

        def make_handler(tool_name: str) -> Any:
            async def handler(arguments: dict[str, Any]) -> dict[str, Any]:
                return await handle(tool_name, arguments)
            return handler

        tools.append(tool(name, description, schema,
                          annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False))
                     (make_handler(name)))

    allowed = ["mcp__catalog__" + name for name in PROFILE_TOOLS[selected.profile]]
    options = ClaudeAgentOptions(
        cwd=work, model=MODEL, env=environment, setting_sources=[], strict_mcp_config=True,
        mcp_servers={"catalog": create_sdk_mcp_server(name="catalog", tools=tools)},
        tools=[], allowed_tools=allowed, permission_mode="bypassPermissions",
        thinking={"type": "disabled"}, max_turns=8, max_budget_usd=0.25,
        hooks={"PreToolUse": [HookMatcher(hooks=[pre])]},  # type: ignore[list-item]
    )
    prompt = ("Find all in-stock camping items costing at most 3000 integer EUR cents. "
              "Return stable SKU and price. Verify each item using detail if available. "
              "For catalog_search use pageSize 1, and follow nextCursor until null. Use format " + selected.format + ". "
              "Use only the selected catalog tools; do not invent product IDs.")
    await emit("operation", mode="live", profile=selected.profile, format=selected.format)
    try:
        async with asyncio.timeout(60):
            stream = query(prompt=prompt, options=options)
            async for message in stream:
                if abort is not None and abort.is_set():
                    raise asyncio.CancelledError
                if isinstance(message, SystemMessage) and message.subtype == "init":
                    await emit("init", sessionId=message.data.get("session_id"), model=MODEL)
                elif isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, ToolUseBlock):
                            await emit("tool-call", callId=block.id, tool=block.name)
                        elif isinstance(block, TextBlock):
                            await emit("text", text=block.text[:1200])
                elif isinstance(message, UserMessage) and isinstance(message.content, list):
                    for block in message.content:
                        if isinstance(block, ToolResultBlock):
                            text = str(block.content)
                            await emit("tool-result", callId=block.tool_use_id, isError=block.is_error is True,
                                       containsReceipt=any(row["callId"] in text for row in receipts))
                elif isinstance(message, ResultMessage):
                    cost = message.total_cost_usd
                    terminal = {"sessionId": message.session_id, "resultUuid": message.uuid,
                                "subtype": message.subtype, "isError": message.is_error,
                                "costUsd": cost if isinstance(cost, (int, float)) and math.isfinite(cost) else None}
                    await emit("terminal", **terminal)
    except asyncio.CancelledError:
        interrupted = True
    except TimeoutError:
        interrupted = True
        exception = "TimeoutError"
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
    after = catalog.current_hash()
    cost = terminal["costUsd"] if terminal else None
    summary = summarize(receipts, model_calls=1, cost=cost)
    await emit("summary", **summary)
    await emit("cleanup", closed=closed)
    await emit("done", ok=bool(terminal and terminal["subtype"] == "success" and
                                terminal["isError"] is False and not interrupted and not exception and not overflow))
    return {"runId": str(run_id), "mode": "live", "profile": selected.profile,
            "format": selected.format, "native": True, "frames": frames,
            "receipts": receipts, "summary": summary, "beforeSha256": before,
            "afterSha256": after, "closed": closed, "interrupted": interrupted,
            "overflow": overflow, "error": None, "exception": exception,
            "terminal": terminal, "scripted": False}
