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
    parser.add_argument("--pinned", action="store_true")
    args = parser.parse_args()
    cases = [("true", False), ("false", False)]
    if args.pinned:
        cases.append(("true", True))
    for mode, pinned in cases:
        report = await measure(Config(searchMode=mode, alwaysLoad=pinned), Path(".lab-data"))
        output = {"searchMode": mode, "alwaysLoad": pinned, "runId": report["runId"],
                  "connected": report["connected"], "catalogCount": report["catalogCount"],
                  "totalTokens": report["totalTokens"],
                  "usedMcpDefinitionTokens": report["usedMcpDefinitionTokens"],
                  "deferredMcpDefinitionTokens": report["deferredMcpDefinitionTokens"],
                  "loadedFlagCount": report["loadedFlagCount"],
                  "mcpToolCount": len(report["mcpTools"]),
                  "mcpToolTokenSum": sum(row.get("tokens", 0) for row in report["mcpTools"]),
                  "categories": [{key: row.get(key) for key in ("id", "name", "tokens", "kind")}
                                 for row in report["categories"]]}
        if not args.summary:
            output = {"searchMode": mode, "alwaysLoad": pinned, **report}
        print(json.dumps(output, indent=2, default=str))
        assert report["connected"] and report["catalogCount"] == 64
        if pinned:
            assert 0 < report["usedMcpDefinitionTokens"] < report["deferredMcpDefinitionTokens"]
        elif mode == "true":
            assert report["usedMcpDefinitionTokens"] == 0
            assert report["deferredMcpDefinitionTokens"] > 0
        else:
            assert report["usedMcpDefinitionTokens"] > 0
            assert report["deferredMcpDefinitionTokens"] == 0


if __name__ == "__main__":
    asyncio.run(main())
