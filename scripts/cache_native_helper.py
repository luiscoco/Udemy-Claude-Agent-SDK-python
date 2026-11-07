"""Run one isolated two-turn native cache session; emit only sanitized evidence."""

import asyncio
import json
import sys
import uuid
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    HookMatcher,
    ResultMessage,
    SystemMessage,
)


async def main() -> None:
    job = json.loads(sys.stdin.buffer.read(65536))
    hooks: list[dict[str, Any]] = []

    async def pre(data: dict[str, Any], _tool_id: str | None, _context: Any) -> dict[str, Any]:
        observed = {key: data.get(key) for key in (
            "from_model", "to_model", "prompt_cache_warm", "estimated_cache_write_usd",
            "context_tokens", "cache_ttl")}
        warm = data.get("prompt_cache_warm") is True
        estimate = data.get("estimated_cache_write_usd")
        deny = job["policy"] == "cap" and warm and isinstance(estimate, (int, float)) and estimate > 0
        hooks.append({"kind": "pre-model-switch", "source": "native-hook", **observed,
                      "decision": "deny" if deny else "allow"})
        return {"hookSpecificOutput": {"hookEventName": "PreModelSwitch",
                                       "permissionDecision": "deny" if deny else "allow",
                                       "permissionDecisionReason": "Owned zero-dollar rewrite cap" if deny
                                       else "Owned allow policy"}}

    async def post(data: dict[str, Any], _tool_id: str | None, _context: Any) -> dict[str, Any]:
        hooks.append({"kind": "post-model-switch", "source": "native-hook",
                      "from_model": data.get("from_model"), "to_model": data.get("to_model")})
        return {}

    options = ClaudeAgentOptions(
        cwd=str(Path(job["work"])), model=job["haiku"],
        system_prompt=job["handbook"], setting_sources=[], strict_mcp_config=True,
        mcp_servers={}, tools=[], allowed_tools=[], thinking={"type": "disabled"},
        max_turns=3, max_budget_usd=0.15, env=job["environment"],
        hooks={"PreModelSwitch": [HookMatcher(hooks=[pre])],
               "PostModelSwitch": [HookMatcher(hooks=[post])]},  # type: ignore[dict-item]
    )
    frames: list[dict[str, Any]] = []
    inbox: asyncio.Queue[str | None] = asyncio.Queue(maxsize=2)

    async def inputs() -> Any:
        while True:
            prompt = await inbox.get()
            if prompt is None:
                break
            yield {"type": "user", "uuid": str(uuid.uuid4()),
                   "message": {"role": "user", "content": prompt},
                   "parent_tool_use_id": None, "session_id": "default"}

    try:
        async with asyncio.timeout(165):
            client = ClaudeSDKClient(options=options)
            try:
                await inbox.put(f"Turn 1. Nonce {job['nonce']}. Reply only READY.")
                await client.connect(prompt=inputs())
                turn = 1
                async for message in client.receive_messages():
                    if isinstance(message, SystemMessage) and message.subtype == "init":
                        frames.append({"kind": "init", "turn": turn,
                                       "session_id": message.data.get("session_id"),
                                       "model": message.data.get("model")})
                    elif isinstance(message, AssistantMessage):
                        frames.append({"kind": "assistant", "turn": turn,
                                       "message_id": message.message_id,
                                       "session_id": message.session_id, "model": message.model})
                    elif isinstance(message, ResultMessage):
                        frames.append({"kind": "result", "turn": turn,
                                       "subtype": message.subtype, "is_error": message.is_error,
                                       "session_id": message.session_id, "uuid": message.uuid,
                                       "total_cost_usd": message.total_cost_usd,
                                       "usage": message.usage})
                        if turn == 1:
                            if job["action"] == "model-switch":
                                try:
                                    await client.set_model(job["sonnet"])
                                    frames.append({"kind": "switch-result", "accepted": True})
                                except Exception as exc:
                                    reason = str(exc).casefold()
                                    code = ("hook-denial" if "hook" in reason and "den" in reason else
                                            "streaming-required" if "stream" in reason else
                                            "model-unavailable" if "model" in reason else "other")
                                    frames.append({"kind": "switch-result", "accepted": False,
                                                   "error_class": type(exc).__name__,
                                                   "reason_code": code})
                            turn = 2
                            await inbox.put(f"Turn 2. Nonce {job['nonce']}. Reply only READY.")
                            await inbox.put(None)
                        else:
                            break
            finally:
                await client.disconnect()
    except Exception as exc:
        frames.append({"kind": "error", "class": type(exc).__name__})
    sys.stdout.write(json.dumps({"frames": frames, "hooks": hooks}, separators=(",", ":")))


if __name__ == "__main__":
    asyncio.run(main())
