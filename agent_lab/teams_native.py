"""Bounded named-subagent observation; never claims an interactive native team."""

import asyncio
import json
import math
import re
import uuid
from pathlib import Path
from typing import Any

from agent_lab.config import Settings
from agent_lab.headless_native import MODEL, bundled_cli, native_environment, private_key
from agent_lab.teams_lab import LiveInput

ROW_LIMIT = 490
BYTE_LIMIT = 480_000


def admission(settings: Settings, selected: LiveInput) -> str:
    if not settings.enable_live or not selected.consent or selected.budget < 0.15:
        raise PermissionError("Live SDK access and fresh consent with at least $0.15 budget are required")
    bundled_cli()
    return private_key()


def semantic_rejection(value: str) -> bool:
    plain = value.replace("\\", "")
    return bool(re.search(r'"success"\s*:\s*false|No agent .*reachable|agent .*not found',
                          plain, re.IGNORECASE))


def _redact(value: Any, key: str, root: Path) -> Any:
    if isinstance(value, dict):
        return {name: _redact(item, key, root) for name, item in value.items()}
    if isinstance(value, list):
        return [_redact(item, key, root) for item in value]
    if isinstance(value, str):
        safe = value.replace(key, "[PRIVATE_KEY]") if key else value
        safe = safe.replace(str(root), "[OWNED_RUN]")
        return re.sub(r"sk-ant-[A-Za-z0-9_-]+", "[REDACTED_KEY]", safe)
    return value


def evaluate_native(report: dict[str, Any]) -> bool:
    try:
        if (report["native"] is not True or report["closed"] is not True or report["interrupted"] or
                report["overflow"] or report["exception"] is not None or
                report["sdkQueries"] != 1 or report["modelCalls"] is not None or
                report["deliveryVerified"] is not False or report["workerCompletionVerified"] is not False):
            return False
        frames = report["frames"]
        run_id = report["runId"]
        if not frames or any(row["runId"] != run_id for row in frames):
            return False
        inits = [row for row in frames if row["kind"] == "init"]
        if not 1 <= len(inits) <= 8:
            return False
        session = inits[0]["sessionId"]
        if not session or any(row["sessionId"] != session for row in inits):
            return False
        advertised = inits[0]["tools"]
        if not ("SendMessage" in advertised and ("Agent" in advertised or "Task" in advertised)):
            return False
        consumed = [row["turn"] for row in frames if row["kind"] == "input-consumed"]
        if consumed != [1, 2]:
            return False
        terminal = [row for row in frames if row["kind"] == "terminal"]
        if len(terminal) != 2 or any(row["sessionId"] != session or
                                     row["subtype"] != "success" or row["isError"] is not False
                                     for row in terminal):
            return False
        first_terminal = frames.index(terminal[0])
        second_input = next(index for index, row in enumerate(frames)
                            if row["kind"] == "input-consumed" and row["turn"] == 2)
        if second_input <= first_terminal:
            return False
        costs = [row["costUsd"] for row in terminal]
        if (any(not isinstance(cost, (int, float)) or isinstance(cost, bool) or
                not math.isfinite(cost) or cost < 0 for cost in costs) or
                costs != sorted(costs) or max(costs) > 0.15 or report["reportedSdkUsd"] != max(costs)):
            return False
        hooks = [row for row in frames if row["kind"] == "hook"]
        calls = [row for row in frames if row["kind"] == "sdk-tool-call"]
        results = [row for row in frames if row["kind"] == "tool-result"]
        if (not hooks or any(not row["admitted"] or row["tool"] not in {"Agent", "SendMessage"}
                             for row in hooks) or
                len({row["callId"] for row in hooks}) != len(hooks) or
                len({row["callId"] for row in calls}) != len(calls) or
                len({row["callId"] for row in results}) != len(results)):
            return False
        if any(not any(hook["callId"] == call["callId"] and hook["tool"] == call["tool"]
                       for hook in hooks) for call in calls):
            return False
        if any(result["isError"] is not False or semantic_rejection(result["text"]) or
               not any(call["callId"] == result["callId"] for call in calls)
               for result in results):
            return False
        for tool in ("Agent", "SendMessage"):
            selected_hooks = [row for row in hooks if row["tool"] == tool]
            selected_calls = [row for row in calls if row["tool"] == tool]
            if not any(call["callId"] == hook["callId"] and
                       any(result["callId"] == call["callId"] and result["isError"] is False and
                           not semantic_rejection(result["text"]) for result in results)
                       for hook in selected_hooks for call in selected_calls):
                return False
        return True
    except (KeyError, TypeError, ValueError, StopIteration):
        return False


async def native_run(selected: LiveInput, settings: Settings, root: Path,
                     abort: asyncio.Event | None = None, on_frame: Any = None,
                     producer: Any = None, run_id: uuid.UUID | None = None) -> dict[str, Any]:
    key = admission(settings, selected) if producer is None else "injected-test-only"
    from claude_agent_sdk import (  # Imported only after paid admission or an injected test producer.
        AgentDefinition,
        AssistantMessage,
        ClaudeAgentOptions,
        HookMatcher,
        PermissionResultDeny,
        ResultMessage,
        SystemMessage,
        TextBlock,
        ToolResultBlock,
        ToolUseBlock,
        UserMessage,
        query,
    )

    run_id_text = str(run_id or uuid.uuid4())
    owned = root / run_id_text
    owned.mkdir(parents=True, exist_ok=False)
    work, home = owned / "work", owned / "config"
    work.mkdir()
    home.mkdir()
    env = native_environment(home, key) if producer is None else {"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "0"}
    env["CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"] = "0"
    env["CLAUDE_CODE_MAX_RETRIES"] = "0"
    frames: list[dict[str, Any]] = []
    size = 0
    overflow = False
    interrupted = False
    exception: str | None = None
    closed = False
    sdk_queries = 0
    stream: Any = None
    spawn_tool: str | None = None
    known_targets = {"researcher"}
    queued: asyncio.Queue[tuple[int, str] | None] = asyncio.Queue()
    terminal_costs: list[float | None] = []
    terminal_count = 0
    answer = ""

    async def emit(kind: str, **data: Any) -> None:
        nonlocal size, overflow
        row = _redact({"runId": run_id_text, "seq": len(frames) + 1, "kind": kind, **data},
                      key, owned)
        amount = len(json.dumps(row, ensure_ascii=False, default=str).encode())
        if kind not in {"summary", "done", "exception", "cleanup"} and (
                len(frames) >= ROW_LIMIT or size + amount > BYTE_LIMIT):
            overflow = True
            raise OverflowError("Bounded native team trace exceeded")
        frames.append(row)
        size += amount
        if on_frame is not None:
            await on_frame(row)

    async def inputs() -> Any:
        while item := await queued.get():
            turn, content = item
            await emit("input-consumed", turn=turn)
            yield {"type": "user", "message": {"role": "user", "content": content},
                   "parent_tool_use_id": None, "session_id": "default"}

    async def pre(data: dict[str, Any], call_id: str | None, _context: Any) -> dict[str, Any]:
        raw_name = str(data.get("tool_name", ""))
        value = data.get("tool_input")
        if not isinstance(value, dict):
            value = {}
        is_spawn = raw_name in {"Agent", "Task"} and spawn_tool is not None
        target = value.get("to", value.get("recipient"))
        admitted = bool(call_id and (
            (is_spawn and value.get("subagent_type") == "calculator" and
             value.get("name") in {None, "researcher"} and isinstance(value.get("prompt"), str) and
             0 < len(value["prompt"]) <= 1000 and value.get("run_in_background") is not True and
             not any(value.get(name) for name in ("isolation", "resume", "team_name"))) or
            (raw_name == "SendMessage" and isinstance(target, str) and target in known_targets)))
        await emit("hook", callId=call_id, rawTool=raw_name,
                   tool="Agent" if is_spawn else raw_name, input=value, admitted=admitted)
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                "permissionDecision": "allow" if admitted else "deny",
                "permissionDecisionReason": "Only the bounded foreground calculator or controlled message target is admitted"}}

    async def deny(_name: str, _value: dict[str, Any], _context: Any) -> Any:
        return PermissionResultDeny(message="Only exact pre-use-admitted calls are permitted")

    options = ClaudeAgentOptions(
        cwd=work, env=env, model=MODEL,
        system_prompt="Use only the selected Agent/Task and SendMessage tools for a controlled arithmetic observation. No files, shell, or interactive team setup. Report unsupported messaging honestly.",
        tools=["Agent", "SendMessage"], allowed_tools=["Agent", "SendMessage"],
        agents={"calculator": AgentDefinition(description="Controlled arithmetic worker",
                 prompt="Compute the requested arithmetic. No files, tools or delegation.", tools=[], model="haiku")},
        setting_sources=[], strict_mcp_config=True, mcp_servers={}, thinking={"type": "disabled"},
        max_turns=8, max_budget_usd=0.15, extra_args={"replay-user-messages": None},
        hooks={"PreToolUse": [HookMatcher(hooks=[pre])]}, can_use_tool=deny,  # type: ignore[list-item]
    )
    await queued.put((1, "Use the advertised Agent or Task spawning tool to run calculator in the foreground, named researcher if supported. Ask it to compute 12 + 18. Return actual tool evidence. Do not create an interactive team."))
    await emit("operation", scope="Named SDK subagent observation, not an interactive native team",
               experimentalTeams=False, maxBudgetUsd=0.15, maxTurns=8)
    try:
        if abort is not None and abort.is_set():
            raise asyncio.CancelledError
        async with asyncio.timeout(90):
            sdk_queries = 1
            stream = (producer or query)(prompt=inputs(), options=options)
            async for message in stream:
                if abort is not None and abort.is_set():
                    raise asyncio.CancelledError
                if isinstance(message, SystemMessage) and message.subtype == "init":
                    tools = list(message.data.get("tools") or [])
                    spawn_tool = "Agent" if "Agent" in tools else "Task" if "Task" in tools else None
                    await emit("init", sessionId=message.data.get("session_id"), tools=tools,
                               spawnTool=spawn_tool, model=message.data.get("model"))
                    if not spawn_tool or "SendMessage" not in tools:
                        raise RuntimeError("Installed SDK did not advertise Agent/Task and SendMessage")
                elif isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, ToolUseBlock):
                            await emit("sdk-tool-call", callId=block.id, rawTool=block.name,
                                       tool="Agent" if block.name in {"Agent", "Task"} else block.name,
                                       input=block.input)
                        elif isinstance(block, TextBlock):
                            answer = block.text[:2000]
                            await emit("text", text=answer)
                elif isinstance(message, UserMessage) and isinstance(message.content, list):
                    for block in message.content:
                        if isinstance(block, ToolResultBlock):
                            value = str(block.content)[:12000]
                            for match in re.finditer(r'(?:agentId|agent_id)["\s:]+([A-Za-z0-9_-]{4,100})', value):
                                known_targets.add(match.group(1))
                            await emit("tool-result", callId=block.tool_use_id,
                                       isError=block.is_error is True, text=value)
                elif isinstance(message, ResultMessage):
                    terminal_count += 1
                    cost = message.total_cost_usd
                    terminal_costs.append(cost if isinstance(cost, (int, float)) and
                                          math.isfinite(cost) and cost >= 0 else None)
                    await emit("terminal", sessionId=message.session_id, resultId=message.uuid,
                               subtype=message.subtype, isError=message.is_error,
                               costUsd=terminal_costs[-1])
                    if message.subtype != "success" or message.is_error:
                        raise RuntimeError("First native turn failed; no follow-up")
                    if terminal_count == 1:
                        await queued.put((2, "Use SendMessage to ask the same actual worker to add 7 to its prior result. Prefer its returned agent ID; otherwise try researcher. Report the real messaging response and do not claim delivery or worker completion without independent proof."))
                    else:
                        await queued.put(None)
                        break
    except asyncio.CancelledError:
        interrupted = True
    except TimeoutError:
        interrupted = True
        exception = "TimeoutError"
    except Exception as exc:
        exception = type(exc).__name__
        await emit("exception", name=type(exc).__name__)
    finally:
        await queued.put(None)
        if stream is not None:
            try:
                await stream.aclose()
                closed = True
            except Exception as exc:
                exception = type(exc).__name__
        else:
            closed = True
    numeric_costs = [cost for cost in terminal_costs if cost is not None]
    known_cost = (len(numeric_costs) == len(terminal_costs) == 2 and
                  numeric_costs == sorted(numeric_costs))
    reported = max(numeric_costs) if known_cost else None
    result_rows = [row for row in frames if row["kind"] == "tool-result"]
    send_hooks = [row for row in frames if row["kind"] == "hook" and row["tool"] == "SendMessage"]
    rejected = any(semantic_rejection(result["text"]) for hook in send_hooks for result in result_rows
                   if hook["callId"] == result["callId"])
    summary = {"sdkQueries": sdk_queries, "modelCalls": None if sdk_queries else 0,
               "reportedSdkUsd": reported, "closed": closed, "interrupted": interrupted,
               "overflow": overflow, "exception": exception,
               "sendMessageAttempted": bool(send_hooks), "messagingRejected": rejected,
               "answerContains37": bool(re.search(r"\b37\b", answer)),
               "deliveryVerified": False, "workerCompletionVerified": False}
    await emit("summary", **summary)
    await emit("cleanup", closed=closed)
    report = {"runId": run_id_text, "native": True, "frames": frames, **summary}
    await emit("done", status="passed" if evaluate_native(report) else "needs-review")
    return report
