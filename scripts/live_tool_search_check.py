"""One explicitly paid native Lesson 58 ToolSearch scenario."""

import argparse
import asyncio
import json
from pathlib import Path

from agent_lab.tool_search_lab import RunInput
from agent_lab.tool_search_native import live


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", required=True)
    parser.add_argument("--budget", type=float, default=1)
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()
    selected = RunInput(mode="live", consent=True, budget=args.budget)
    report = await live(selected, Path(".lab-data"))
    print(json.dumps({key: report[key] for key in ("runId", "check", "costUsd", "exception",
                                               "ledgerSha256")}, indent=2) if args.summary
          else json.dumps(report, indent=2, default=str))
    if report["check"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
