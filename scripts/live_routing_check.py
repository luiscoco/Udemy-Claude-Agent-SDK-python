"""Opt-in paid Lesson 59 invoice review smoke check."""

import argparse
import asyncio
import json
import sys


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--budget", type=float)
    args = parser.parse_args()
    if not args.live or args.budget is None or not 0.1 <= args.budget <= 1:
        print("Use --live --budget 1 (0.1 through 1).", file=sys.stderr)
        return 2
    from agent_lab.config import ROOT
    from agent_lab.headless_native import private_key
    from agent_lab.routing_lab import RoutingInput
    from agent_lab.routing_native import live

    private_key()
    selected = RoutingInput(mode="live", strategies=["review"], taskIds=["invoice"],
                            consent=True, budget=args.budget)
    report = await live(selected, ROOT / ".lab-data")
    target = ROOT / ".lab-data" / "lesson-59" / report["runId"] / "report.json"
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"runId": report["runId"], "check": report["check"],
                      "sdkQueries": report["sdkQueries"], "reportedSdkUsd": report["reportedSdkUsd"],
                      "path": str(target)}))
    return 0 if report["check"]["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
