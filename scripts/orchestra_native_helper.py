"""One isolated native Lesson 47 query; emit bounded sanitized lifecycle records."""

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    AgentDefinition,
    AssistantMessage,
    ClaudeAgentOptions,
    HookMatcher,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ToolUseBlock,
    query,
)


def report_line(value: str) -> str:
    return value.strip()[:500]


async def main() -> None:
    job = json.loads(sys.stdin.buffer.read(65536))
    target = Path(job["work"]) / job["file"]
    role = job["role"]
    tree = job["action"] in {"orchestrator", "hierarchy"}
    observations: list[dict[str, Any]] = []
    agent_ids: dict[str, str] = {}
    delegated: set[str] = set()
    expected = {"lead": "manager" if job["action"] == "hierarchy" else "analyst",
                "manager": "analyst"}
    analyst_instruction = (f"Read exactly {target} with Read. Sum units and choose the product "
        "with greatest units. Return only REGION=north; TOTAL=<sum>; BEST=<P-number>. "
        "No Markdown, quotes, headings, code fences, or explanation.")
    manager_instruction = ("Delegate exactly once to analyst to read the owned north.csv. "
        "Return only the analyst's exact region report line. No Markdown or explanation.")

    async def pre(data: dict[str, Any], tool_id: str | None, _ctx: Any) -> dict[str, Any]:
        name = data.get("tool_name")
        caller_id = data.get("agent_id")
        caller = next((name for name, agent_id in agent_ids.items() if agent_id == caller_id),
                      ("lead" if tree else role) if caller_id is None else "unknown")
        args = data.get("tool_input") or {}
        allowed = False
        update: dict[str, Any] | None = None
        if name == "Agent" and tree and caller in expected and caller not in delegated:
            destination = expected[caller]
            if args.get("subagent_type") == destination:
                allowed = True
                delegated.add(caller)
                update = dict(args)
                update.update({"subagent_type": destination, "run_in_background": False,
                               "prompt": manager_instruction if destination == "manager"
                               else analyst_instruction})
        elif name == "Read" and caller == ("analyst" if tree else role):
            supplied = args.get("file_path")
            allowed = isinstance(supplied, str) and Path(supplied).resolve() == target.resolve()  # noqa: ASYNC240
        observations.append({"kind": "pre", "tool": name, "id": tool_id,
                             "caller": caller, "caller_id": caller_id,
                             "allowed": allowed, "target_role": args.get("subagent_type")
                             if name == "Agent" else None})
        output: dict[str, Any] = {"hookEventName": "PreToolUse",
                                  "permissionDecision": "allow" if allowed else "deny",
                                  "permissionDecisionReason": "Fixed owned task" if allowed else "Tool or path outside fixed role"}
        if update is not None:
            output["updatedInput"] = update
        return {"hookSpecificOutput": output}

    async def post(data: dict[str, Any], tool_id: str | None, _ctx: Any) -> dict[str, Any]:
        name = data.get("tool_name")
        caller_id = data.get("agent_id")
        caller = next((name for name, agent_id in agent_ids.items() if agent_id == caller_id),
                      ("lead" if tree else role) if caller_id is None else "unknown")
        if name == "Read" and Path(job["work"], job["file"]).is_file():  # noqa: ASYNC240
            import hashlib

            actual = hashlib.sha256(target.read_bytes()).hexdigest()
            observations.append({"kind": "read", "id": tool_id, "caller": caller,
                                 "caller_id": caller_id, "sha256": actual,
                                 "path_ok": Path(str(data.get("tool_input", {}).get("file_path", ""))).resolve()  # noqa: ASYNC240
                                 == target.resolve()})
        return {}

    async def agent_start(data: dict[str, Any], _id: str | None, _ctx: Any) -> dict[str, Any]:
        kind = data.get("agent_type")
        agent_id = data.get("agent_id")
        if isinstance(kind, str) and isinstance(agent_id, str):
            agent_ids[kind] = agent_id
        observations.append({"kind": "agent-start", "role": kind, "id": agent_id})
        return {}

    async def agent_stop(data: dict[str, Any], _id: str | None, _ctx: Any) -> dict[str, Any]:
        kind = data.get("agent_type")
        text = report_line(str(data.get("last_assistant_message") or ""))
        active = data.get("stop_hook_active") is True
        decision = "allow"
        if kind == "analyst" and text != "REGION=north; TOTAL=55; BEST=P2" and not active:
            decision = "block"
        observations.append({"kind": "agent-stop", "role": kind,
                             "id": data.get("agent_id"), "text": text,
                             "decision": "second-stop-bypass" if active else decision})
        if decision == "block":
            return {"decision": "block", "reason": "Read north.csv if needed, then return only REGION=north; TOTAL=55; BEST=P2 without Markdown or explanation."}
        return {}

    agents = {
        "analyst": AgentDefinition(description="Read the fixed north sales file and report its totals",
                                   prompt=analyst_instruction, tools=["Read"], model="haiku"),
        "manager": AgentDefinition(description="Delegate once to the analyst and return its report",
                                   prompt=manager_instruction, tools=["Agent"], model="haiku"),
    } if tree else {}
    system = ("Return exactly one plain report line in this format: REGION=<region>; TOTAL=<sum>; BEST=<P-number>. "
              "No Markdown, headings, explanation, apology, quotes or code fences. "
              "Use only the assigned tools and fixed owned file.") if role != "critic" else "Reply only PASS or FAIL."
    options = ClaudeAgentOptions(
        cwd=str(Path(job["work"])), model=job["model"],
        system_prompt=system, setting_sources=[], strict_mcp_config=True,
        mcp_servers={}, tools=["Agent", "Read"] if tree else (["Read"] if job["file"] else []),
        allowed_tools=["Agent", "Read"] if tree else (["Read"] if job["file"] else []),
        agents=agents, thinking={"type": "disabled"},
        max_turns=8 if tree else 4,
        max_budget_usd=job["budget"], env=job["environment"],
        hooks={"PreToolUse": [HookMatcher(hooks=[pre])],
               "PostToolUse": [HookMatcher(hooks=[post])],
               "SubagentStart": [HookMatcher(hooks=[agent_start])],
               "SubagentStop": [HookMatcher(hooks=[agent_stop])]},  # type: ignore[dict-item]
    )
    prompt = job["prompt"]
    frames: list[dict[str, Any]] = []
    try:
        async with asyncio.timeout(155):
            async for message in query(prompt=prompt, options=options):
                if isinstance(message, SystemMessage):
                    frames.append({"kind": "system", "subtype": message.subtype,
                                   "session_id": message.data.get("session_id"),
                                   "model": message.data.get("model"),
                                   "task_id": message.data.get("task_id"),
                                   "tool_use_id": message.data.get("tool_use_id"),
                                   "subagent_type": message.data.get("subagent_type"),
                                   "spawn_depth": message.data.get("spawn_depth"),
                                   "status": message.data.get("status")})
                elif isinstance(message, AssistantMessage):
                    frames.append({"kind": "assistant", "message_id": message.message_id,
                                   "session_id": message.session_id,
                                   "parent_tool_use_id": message.parent_tool_use_id,
                                   "model": message.model,
                                   "tools": [{"name": block.name, "id": block.id,
                                              "target_role": block.input.get("subagent_type")}
                                             for block in message.content if isinstance(block, ToolUseBlock)],
                                   "text": report_line("\n".join(block.text for block in message.content
                                                                if isinstance(block, TextBlock)))})
                elif isinstance(message, ResultMessage):
                    frames.append({"kind": "result", "subtype": message.subtype,
                                   "is_error": message.is_error,
                                   "session_id": message.session_id, "uuid": message.uuid,
                                   "cost_usd": message.total_cost_usd,
                                   "text": report_line(message.result or "")})
                if len(frames) + len(observations) > 400:
                    raise ValueError("Native evidence frame limit")
    except Exception as exc:
        frames.append({"kind": "error", "class": type(exc).__name__})
    sys.stdout.write(json.dumps({"frames": frames, "hooks": observations}, separators=(",", ":")))


if __name__ == "__main__":
    asyncio.run(main())
