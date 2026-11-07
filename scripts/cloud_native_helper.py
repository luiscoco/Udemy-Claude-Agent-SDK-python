"""Isolated Lesson 45 native SDK query; accepts one private JSON job on stdin.

This helper is launched with a scrubbed process environment. It never prints
the prompt, configuration, credentials, model response text or raw errors.
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    SystemMessage,
)


async def main() -> None:
    job = json.loads(sys.stdin.buffer.read(65536))
    work = Path(job["work"])
    options = ClaudeAgentOptions(
        cwd=str(work), model=job["model"],
        fallback_model=job.get("fallback_model"),
        setting_sources=[], strict_mcp_config=True, mcp_servers={},
        tools=[], allowed_tools=[], thinking={"type": "disabled"},
        max_turns=2, max_budget_usd=0.10, env=job["environment"])
    frames: list[dict[str, Any]] = []
    try:
        async with asyncio.timeout(min(160, max(10, int(job.get("timeout_seconds", 160))))):
            async with ClaudeSDKClient(options=options) as client:
                info = await client.get_server_info() or {}
                account = info.get("account")
                models = info.get("models")
                frames.append({"kind": "catalog", "account_provider": account.get("apiProvider")
                               if isinstance(account, dict) else None,
                               "models": [{"value": item.get("value"), "display_name": item.get("displayName")}
                                          for item in models[:20] if isinstance(item, dict)]
                               if isinstance(models, list) else []})
                if not job.get("inspect_only"):
                    await client.query("Reply READY with this exact run marker: " + job["marker"])
                    async for message in client.receive_response():
                        if isinstance(message, SystemMessage) and message.subtype == "init":
                            data = message.data
                            frames.append({"kind": "init", "session_id": data.get("session_id"),
                                           "model": data.get("model")})
                        elif isinstance(message, AssistantMessage):
                            frames.append({"kind": "assistant", "id": message.message_id,
                                           "model": message.model, "session_id": message.session_id})
                        elif isinstance(message, ResultMessage):
                            frames.append({"kind": "result", "subtype": message.subtype,
                                           "is_error": message.is_error, "session_id": message.session_id,
                                           "uuid": message.uuid, "cost_usd": message.total_cost_usd,
                                           "model_usage": list((message.model_usage or {}).keys())})
                        else:
                            frames.append({"kind": "other", "class": type(message).__name__,
                                           "subtype": getattr(message, "subtype", None),
                                           "data_keys": sorted(message.data)[:20]
                                           if isinstance(message, SystemMessage) and isinstance(message.data, dict)
                                           else []})
    except Exception as exc:
        frames.append({"kind": "error", "class": type(exc).__name__})
    sys.stdout.write(json.dumps({"frames": frames}, separators=(",", ":")))


if __name__ == "__main__":
    asyncio.run(main())
