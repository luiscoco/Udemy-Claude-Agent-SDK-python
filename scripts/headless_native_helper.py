"""One isolated Lesson 49 SDK query with bounded machine-result evidence."""

import asyncio
import json
import sys
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    SystemMessage,
    query,
)


async def main() -> None:
    job = json.loads(sys.stdin.buffer.read(64_000))
    options = ClaudeAgentOptions(
        cwd=job["cwd"], model="claude-haiku-4-5-20251001",
        system_prompt="Classify only the supplied fixed source. Return the required JSON schema. No tools.",
        setting_sources=[], strict_mcp_config=True, mcp_servers={}, tools=[],
        allowed_tools=[], permission_mode="dontAsk", thinking={"type": "disabled"},
        max_turns=4, max_budget_usd=0.10, output_format={"type": "json_schema",
                                                   "schema": job["schema"]},
        env=job["environment"],
    )
    frames: list[dict[str, Any]] = []
    try:
        async with asyncio.timeout(65):
            async for message in query(prompt=job["prompt"], options=options):
                if isinstance(message, SystemMessage) and message.subtype == "init":
                    frames.append({"kind": "init", "session_id": message.data.get("session_id")})
                elif isinstance(message, AssistantMessage):
                    tool_names = [name for block in message.content
                                  if isinstance((name := getattr(block, "name", None)), str)]
                    frames.append({"kind": "assistant", "message_id": message.message_id,
                                   "session_id": message.session_id,
                                   "tool_names": tool_names})
                elif isinstance(message, ResultMessage):
                    frames.append({"kind": "result", "session_id": message.session_id,
                                   "uuid": message.uuid, "subtype": message.subtype,
                                   "is_error": message.is_error,
                                   "cost_usd": message.total_cost_usd,
                                   "structured_output": message.structured_output,
                                   "permission_denials": message.permission_denials or []})
                if len(frames) > 20:
                    raise ValueError("Native frame limit")
    except Exception as exc:
        frames.append({"kind": "error", "class": type(exc).__name__})
    sys.stdout.write(json.dumps({"frames": frames}, separators=(",", ":")))


if __name__ == "__main__":
    asyncio.run(main())
