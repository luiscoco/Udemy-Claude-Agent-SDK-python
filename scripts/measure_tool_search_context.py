"""Opt-in two silent native SDK context measurements for Lesson 58."""

import argparse
import asyncio
import json
from pathlib import Path

from agent_lab.tool_search_lab import Config
from agent_lab.tool_search_native import measure


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", required=True)
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()
    for mode in ("true", "false"):
        report = await measure(Config(searchMode=mode), Path(".lab-data"))
        output = {"searchMode": mode, "runId": report["runId"],
                  "connected": report["connected"], "catalogCount": report["catalogCount"],
                  "totalTokens": report["totalTokens"], "loadedCount": report["loadedCount"],
                  "mcpToolCount": len(report["mcpTools"])} if args.summary else {"searchMode": mode, **report}
        print(json.dumps(output, indent=2, default=str))
        assert report["connected"] and report["catalogCount"] == 64


if __name__ == "__main__":
    asyncio.run(main())
