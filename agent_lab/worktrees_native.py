"""Two bounded SDK file workers; the host alone validates and commits their work."""

import asyncio
import math
import re
import uuid
from pathlib import Path
from typing import Any

from agent_lab.headless_native import MODEL, native_environment, private_key


def exact_file(tool: str, value: dict[str, Any], checkout: Path, assigned: str) -> bool:
    if tool not in {"Read", "Write", "Edit"} or not isinstance(value.get("file_path"), str):
        return False
    target = checkout / value["file_path"]
    try:
        stat = target.lstat()
        return (target.resolve() == (checkout / assigned).resolve() and target.is_file() and
                not target.is_symlink() and stat.st_nlink == 1)
    except OSError:
        return False


def grade_native(report: dict[str, Any]) -> bool:
    try:
        if (report["closed"] is not True or report["interrupted"] or report["exception"] or
                report["sdkQueries"] != 1 or report["modelCalls"] is not None or
                not isinstance(report["costUsd"], (int, float)) or
                not math.isfinite(report["costUsd"]) or not 0 <= report["costUsd"] <= 0.08):
            return False
        rows = report["frames"]
        inits = [row for row in rows if row["kind"] == "init"]
        terminals = [row for row in rows if row["kind"] == "terminal"]
        hooks = [row for row in rows if row["kind"] == "hook"]
        callbacks = [row for row in rows if row["kind"] == "callback"]
        calls = [row for row in rows if row["kind"] == "call"]
        results = [row for row in rows if row["kind"] == "result"]
        if (len(inits) != 1 or len(terminals) != 1 or not inits[0]["session"] or
                terminals[0]["session"] != inits[0]["session"] or
                terminals[0]["subtype"] != "success" or terminals[0]["isError"] is not False or
                terminals[0]["costUsd"] != report["costUsd"] or
                not terminals[0]["id"] or not calls or
                len({row["id"] for row in calls}) != len(calls)):
            return False
        for call in calls:
            call_id, tool = call["id"], call["tool"]
            if (tool not in {"Read", "Write", "Edit"} or not call["exact"] or
                    not any(row["id"] == call_id and row["tool"] == tool and row["admitted"]
                            for row in hooks) or
                    not any(row["id"] == call_id and row["tool"] == tool and row["admitted"]
                            for row in callbacks) or
                    not any(row["id"] == call_id and row["isError"] is False for row in results)):
                return False
        if (any(not row["admitted"] for row in hooks + callbacks) or
                any(row["isError"] is not False or row["id"] not in {call["id"] for call in calls}
                    for row in results)):
            return False
        return any(row["tool"] in {"Write", "Edit"} for row in calls)
    except (KeyError, TypeError, ValueError):
        return False


async def native_worker(checkout: Path, item: dict[str, str], owned: Path,
                        abort: asyncio.Event | None = None, producer: Any = None) -> dict[str, Any]:
    key = private_key() if producer is None else "injected-test-only"
    from claude_agent_sdk import (  # Imported only after paid admission or injection.
        AssistantMessage,
        ClaudeAgentOptions,
        HookMatcher,
        PermissionResultAllow,
        PermissionResultDeny,
        ResultMessage,
        SystemMessage,
        ToolResultBlock,
        ToolUseBlock,
        UserMessage,
        query,
    )

    home = owned / ("config-" + str(uuid.uuid4()))
    home.mkdir()
    env = native_environment(home, key) if producer is None else {}
    env["CLAUDE_CODE_MAX_RETRIES"] = "0"
    frames: list[dict[str, Any]] = []
    stream: Any = None
    closed = False
    interrupted = False
    exception: str | None = None
    sdk_queries = 0
    cost: float | None = None

    async def hook(data: dict[str, Any], call_id: str | None, _context: Any) -> dict[str, Any]:
        tool = str(data.get("tool_name", ""))
        raw = data.get("tool_input")
        value: dict[str, Any] = raw if isinstance(raw, dict) else {}
        admitted = bool(call_id and exact_file(tool, value, checkout, item["file"]))
        frames.append({"kind": "hook", "id": call_id, "tool": tool, "admitted": admitted})
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                "permissionDecision": "ask" if admitted else "deny",
                "permissionDecisionReason": "Only the exact assigned existing file is permitted"}}

    async def callback(tool: str, value: dict[str, Any], context: Any) -> Any:
        call_id = context.tool_use_id
        admitted = bool(call_id and exact_file(tool, value, checkout, item["file"]))
        frames.append({"kind": "callback", "id": call_id, "tool": tool, "admitted": admitted})
        return (PermissionResultAllow() if admitted else
                PermissionResultDeny(message="Only the assigned file is permitted"))

    options = ClaudeAgentOptions(
        cwd=checkout, env=env, model=MODEL, tools=["Read", "Write", "Edit"], allowed_tools=[],
        setting_sources=[], strict_mcp_config=True, mcp_servers={}, thinking={"type": "disabled"},
        max_turns=4, max_budget_usd=0.08,
        hooks={"PreToolUse": [HookMatcher(hooks=[hook])]}, can_use_tool=callback,  # type: ignore[list-item]
        system_prompt="You may only replace the single named existing file. Do not run commands, use Git, delegate, or edit any other file. The host will test and commit.",
    )
    prompt = (f"Replace only {item['file']} with these exact UTF-8 bytes, including the final newline. "
              "Use Write or Edit once and finish.\n<source>\n" + item["source"] + "</source>")
    try:
        if abort is not None and abort.is_set():
            raise asyncio.CancelledError
        async with asyncio.timeout(70):
            sdk_queries = 1
            stream = (producer or query)(prompt=prompt, options=options)
            async for message in stream:
                if abort is not None and abort.is_set():
                    raise asyncio.CancelledError
                if isinstance(message, SystemMessage) and message.subtype == "init":
                    frames.append({"kind": "init", "session": message.data.get("session_id")})
                elif isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, ToolUseBlock):
                            frames.append({"kind": "call", "id": block.id, "tool": block.name,
                                           "exact": exact_file(block.name, block.input, checkout, item["file"])})
                elif isinstance(message, UserMessage) and isinstance(message.content, list):
                    for block in message.content:
                        if isinstance(block, ToolResultBlock):
                            frames.append({"kind": "result", "id": block.tool_use_id,
                                           "isError": block.is_error is True})
                elif isinstance(message, ResultMessage):
                    cost = message.total_cost_usd if isinstance(message.total_cost_usd, (int, float)) and math.isfinite(message.total_cost_usd) else None
                    detail = str(message.result or "")[:600].replace(key, "[PRIVATE_KEY]")
                    detail = re.sub(r"sk-ant-[A-Za-z0-9_-]+", "[REDACTED_KEY]", detail)
                    frames.append({"kind": "terminal", "session": message.session_id,
                                   "id": message.uuid, "subtype": message.subtype,
                                   "isError": message.is_error, "costUsd": cost, "detail": detail})
                    break
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
    report = {"frames": frames[:100], "closed": closed, "interrupted": interrupted,
              "exception": exception, "sdkQueries": sdk_queries, "modelCalls": None if sdk_queries else 0,
              "costUsd": cost}
    report["passed"] = grade_native(report)
    return report
