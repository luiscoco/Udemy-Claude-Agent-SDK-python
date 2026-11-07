"""One explicit provider-backed Lesson 46 run through the shared lesson runner."""

import argparse
import asyncio
import json

from agent_lab.config import ROOT, Settings
from agent_lab.curriculum import get_lesson
from agent_lab.models import RunRequest
from agent_lab.runtime import RunService


async def run() -> dict:
    service = RunService(Settings(enable_live=True, data_dir=ROOT / ".lab-data/cache-portal-live"))
    events = []
    try:
        handle = service.start(46, RunRequest(mode="live", prompt=get_lesson(46).prompt,
            lesson_options={"action": "anatomy", "consent": True}, max_turns=3,
            max_budget_usd=0.15))
        async for event in service.events(handle):
            events.append(event)
    finally:
        await service.close()
    done = [item for item in events if item.kind == "done"]
    evidence = [item for item in events if item.kind == "evidence"]
    result = [item for item in events if item.kind == "result"]
    report = evidence[-1].data["result"]["experiment"] if evidence else {}
    cost = result[-1].data.get("total_cost_usd") if result else None
    summary = {"status": done[-1].data.get("status") if done else None,
               "passed": report.get("experiment_passed"), "operation": report.get("operation"),
               "turns": len([row for row in report.get("frames", []) if row.get("kind") == "result"]),
               "sdk_last_cumulative_usd": cost}
    if summary["status"] != "completed" or summary["passed"] is not True or summary["turns"] != 2:
        raise ValueError("Shared Lesson 46 live criterion did not pass")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", required=True)
    parser.add_argument("--budget", type=float, required=True)
    args = parser.parse_args()
    if not args.live or args.budget != 0.15:
        parser.error("Confirm --live and the fixed $0.15 session ceiling.")
    print(json.dumps(asyncio.run(run())))


if __name__ == "__main__":
    main()
