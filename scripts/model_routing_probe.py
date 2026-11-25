"""Silent installed-SDK model metadata observation for Lesson 59."""

import argparse
import asyncio
import json
import sys
import uuid


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", action="store_true")
    args = parser.parse_args()
    if not args.models:
        print("Use --models for an explicit silent native control.", file=sys.stderr)
        return 2
    from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

    from agent_lab.config import ROOT
    from agent_lab.headless_native import native_environment, private_key
    from agent_lab.routing_lab import LIGHT

    folder = ROOT / ".lab-data" / "lesson-59" / "models" / str(uuid.uuid4())
    folder.mkdir(parents=True)
    home = folder / "config"
    home.mkdir()
    options = ClaudeAgentOptions(cwd=folder, env=native_environment(home, private_key()),
                                 model=LIGHT, tools=[], allowed_tools=[], mcp_servers={},
                                 setting_sources=[], strict_mcp_config=True,
                                 extra_args={"no-session-persistence": None},
                                 max_turns=1, max_budget_usd=.1)
    async with asyncio.timeout(20):
        async with ClaudeSDKClient(options=options) as client:
            info = await client.get_server_info() or {}
    models = info.get("supportedModels") or info.get("models")
    report = {"source": "native-sdk-initialization", "keys": sorted(info),
              "models": models, "status": "success" if isinstance(models, list) and models else "unsupported"}
    target = folder / "report.json"
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "keys": report["keys"],
                      "modelCount": len(models) if isinstance(models, list) else 0,
                      "path": str(target)}))
    return 0 if report["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
