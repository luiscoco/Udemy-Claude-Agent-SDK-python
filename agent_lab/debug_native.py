"""Bounded, isolated native Agent SDK diagnostic producer for Lesson 53."""

import asyncio
import json
import math
import os
import uuid
from pathlib import Path
from typing import Any

from agent_lab.config import Settings
from agent_lab.debug_lab import (
    LIVE_SCENARIOS,
    Collector,
    DebugInput,
    bounded_debug_log,
    correlate,
    diagnose,
    effective,
    prepare_fixture,
)
from agent_lab.headless_native import MODEL, native_environment, private_key


def admission(settings: Settings, selected: DebugInput) -> str:
    if (not settings.enable_live or not selected.consent or selected.mode != "live" or
            selected.scenario not in LIVE_SCENARIOS or selected.budget < 0.10):
        raise PermissionError("A supported native scenario, live access, fresh consent and $0.10 reservation are required")
    return private_key()


async def native_run(selected: DebugInput, root: Path, run_id: uuid.UUID, settings: Settings,
                     abort: asyncio.Event | None = None, on_row: Any = None) -> dict[str, Any]:
    key = admission(settings, selected)
    from claude_agent_sdk import (  # Imported only after paid admission.
        AssistantMessage,
        ClaudeAgentOptions,
        HookMatcher,
        PermissionResultAllow,
        PermissionResultDeny,
        ResultMessage,
        SystemMessage,
        TextBlock,
        ToolResultBlock,
        ToolUseBlock,
        UserMessage,
        query,
    )

    owned = root / str(run_id)
    path, before = prepare_fixture(owned, run_id, missing=selected.scenario == "missing")
    work, home = owned / "work", owned / "config"
    work.mkdir()
    home.mkdir()
    collector = Collector(run_id, owned)
    log_path = owned / "raw-debug.log"
    log_descriptor = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600) if selected.captureLog else None
    log_written = 0
    expected = f"LESSON53:{run_id}:verified"
    terminal_costs: list[float | None] = []
    interrupted = False
    closed = False
    stream: Any = None

    async def emit(kind: str, name: str, data: dict[str, Any], *, forced: bool = False) -> None:
        row = collector.add(kind, name, data, forced=forced)
        if row is not None and on_row is not None:
            await on_row(row)
        if collector.overflow and not forced:
            raise OverflowError("Diagnostic trace ceiling reached")

    def valid_target(name: str, arguments: dict[str, Any]) -> bool:
        raw = arguments.get("file_path")
        if name != "Read" or not isinstance(raw, str):
            return False
        try:
            return (work / raw).resolve() == path.resolve()
        except (OSError, ValueError):
            return False

    async def pre(data: dict[str, Any], call_id: str | None, _context: Any) -> dict[str, Any]:
        name, arguments = data.get("tool_name"), data.get("tool_input")
        allowed = (isinstance(arguments, dict) and valid_target(str(name), arguments) and
                   selected.scenario != "denied")
        await emit("hook", "pre-read", {"callId": call_id, "allowed": allowed,
                                        "exactTarget": isinstance(arguments, dict) and valid_target(str(name), arguments)})
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                "permissionDecision": "allow" if allowed else "deny",
                "permissionDecisionReason": "Only the fixed owned fixture Read is allowed."}}

    async def fallback(name: str, arguments: dict[str, Any], _context: Any) -> Any:
        allowed = valid_target(name, arguments) and selected.scenario != "denied"
        await emit("permission", "callback", {"allowed": allowed, "tool": name})
        return PermissionResultAllow() if allowed else PermissionResultDeny(message="Only the fixed fixture Read is allowed")

    async def post(data: dict[str, Any], call_id: str | None, _context: Any) -> dict[str, Any]:
        await emit("hook", "post-success", {"callId": call_id, "tool": data.get("tool_name")})
        return {}

    async def post_failure(data: dict[str, Any], call_id: str | None, _context: Any) -> dict[str, Any]:
        await emit("hook", "post-failure", {"callId": call_id,
                                            "reason": str(data.get("error", "tool failure"))[:500]})
        return {}

    def stderr(chunk: str) -> None:
        nonlocal log_written
        if log_descriptor is not None:
            payload = chunk[:8192].encode("utf-8", errors="replace")
            written = os.write(log_descriptor, payload[:max(0, 128001 - log_written)])
            log_written += written
        collector.add("stderr", "stderr", {"text": chunk[:8192]})

    environment = native_environment(home, key)
    environment["CLAUDE_CODE_MAX_RETRIES"] = "0"
    options = ClaudeAgentOptions(
        cwd=work, model=MODEL, env=environment,
        tools=["Read"], allowed_tools=["Read"], mcp_servers={}, strict_mcp_config=True,
        setting_sources=[], permission_mode="default", can_use_tool=fallback,
        hooks={"PreToolUse": [HookMatcher(hooks=[pre])],  # type: ignore[list-item]
               "PostToolUse": [HookMatcher(hooks=[post])],  # type: ignore[list-item]
               "PostToolUseFailure": [HookMatcher(hooks=[post_failure])]},  # type: ignore[list-item]
        thinking={"type": "disabled"}, include_partial_messages=True,
        max_turns=effective(selected)["maxTurns"], max_budget_usd=0.10,
        stderr=stderr if selected.captureLog else None,
    )
    prompt = ("Read exactly this one absolute file path with Read, without substitutions or retries: "
              f"{path.resolve()}. Then accurately report the tool outcome. Do not use any other tool.")
    try:
        stream = query(prompt=prompt, options=options)
        async with asyncio.timeout(60):
            async for item in stream:
                if abort is not None and abort.is_set():
                    interrupted = True
                    break
                await emit("sdk", "message", {"type": type(item).__name__})
                if isinstance(item, SystemMessage) and item.subtype == "init":
                    await emit("sdk", "init", {"session": item.data.get("session_id")})
                elif isinstance(item, AssistantMessage):
                    await emit("sdk", "assistant", {"session": item.session_id, "model": item.model})
                    for block in item.content:
                        if isinstance(block, ToolUseBlock):
                            arguments = block.input if isinstance(block.input, dict) else {}
                            await emit("sdk", "read-call", {"callId": block.id, "tool": block.name,
                                                            "exactTarget": valid_target(block.name, arguments),
                                                            "target": "fixture.txt" if valid_target(block.name, arguments) else "other"})
                        elif isinstance(block, TextBlock):
                            await emit("sdk", "text", {"text": block.text[:8192]})
                elif isinstance(item, UserMessage) and isinstance(item.content, list):
                    for block in item.content:
                        if isinstance(block, ToolResultBlock):
                            body = str(block.content)[:8192]
                            await emit("sdk", "read-result", {"callId": block.tool_use_id,
                                                                "isError": block.is_error is True,
                                                                "containsFixture": expected in body,
                                                                "fixtureMissing": (block.is_error is True and
                                                                                   any(term in body.casefold() for term in
                                                                                       ("enoent", "does not exist", "not found"))),
                                                                "excerpt": body[:300]})
                elif isinstance(item, ResultMessage):
                    cost = item.total_cost_usd
                    terminal_costs.append(cost if isinstance(cost, (int, float)) and math.isfinite(cost) and cost >= 0 else None)
                    await emit("sdk", "terminal", {"session": item.session_id, "uuid": item.uuid,
                                                   "subtype": item.subtype, "isError": item.is_error,
                                                   "costUsd": terminal_costs[-1],
                                                   "errors": item.errors or []})
                elif type(item).__name__ == "StreamEvent":
                    event = getattr(item, "event", {})
                    if isinstance(event, dict):
                        await emit("sdk", "partial", {"type": event.get("type"),
                                                      "text": json.dumps(event)[:300]})
    except TimeoutError:
        interrupted = True
        await emit("host", "timeout", {"seconds": 60}, forced=True)
    except asyncio.CancelledError:
        interrupted = True
        await emit("host", "cancelled", {"reason": "owned Stop"}, forced=True)
    except OverflowError:
        interrupted = True
    except Exception as exc:
        await emit("host", "iterator-exception", {"class": type(exc).__name__}, forced=True)
    finally:
        if stream is not None:
            try:
                await stream.aclose()
                closed = True
            except Exception as exc:
                await emit("host", "cleanup-error", {"class": type(exc).__name__}, forced=True)
        else:
            closed = True
        if log_descriptor is not None:
            os.close(log_descriptor)
    await emit("host", "stream-end", {"closed": closed}, forced=True)
    await emit("host", "cleanup", {"closed": closed}, forced=True)
    observations = correlate(collector.rows, path, before)
    return {"id": str(run_id), "mode": "live", "scenario": selected.scenario,
            "effectiveConfig": effective(selected), "compareId": str(selected.compareId) if selected.compareId else None,
            "rows": collector.rows, "findings": diagnose(collector.rows, observations),
            "observations": observations, "closed": closed, "interrupted": interrupted,
            "overflow": collector.overflow, "modelCalls": 1,
            "reportedSdkUsd": terminal_costs[0] if len(terminal_costs) == 1 else None,
            "log": bounded_debug_log(log_path, owned) if selected.captureLog else
                   {"found": False, "truncated": False, "text": "Log capture was disabled."},
            "limitations": ["Native SDK evidence is limited to this fixed owned fixture and model call.",
                            "SDK terminal cost is an estimate, not an invoice.",
                            "Redaction is best effort; review before sharing."]}
