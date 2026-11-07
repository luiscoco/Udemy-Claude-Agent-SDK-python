"""One bounded native Lesson 49 CI action through the shared lesson runner."""

import argparse
import asyncio
import json
import math

from agent_lab.config import ROOT, Settings
from agent_lab.curriculum import get_lesson
from agent_lab.models import RunRequest
from agent_lab.runtime import RunService


async def run() -> dict:
    service = RunService(Settings(enable_live=True, data_dir=ROOT / ".lab-data/headless-portal-live"))
    events = []
    try:
        handle = service.start(49, RunRequest(mode="live", prompt=get_lesson(49).prompt,
            lesson_options={"action": "ci", "consent": True}, max_turns=4,
            max_budget_usd=0.20))
        async for event in service.events(handle):
            events.append(event)
    finally:
        await service.close()
    done = [event for event in events if event.kind == "done"]
    evidence = [event for event in events if event.kind == "evidence"]
    result = [event for event in events if event.kind == "result"]
    report = evidence[-1].data["result"]["experiment"] if evidence else {}
    cost = result[-1].data.get("total_cost_usd") if result else None
    summary = {"status": done[-1].data.get("status") if done else None,
               "passed": report.get("experiment_passed"), "operation": report.get("operation"),
               "ci_codes": [row.get("ci_exit") for row in report.get("outcomes", [])],
               "sdk_cost_usd": cost}
    if (summary["status"] != "completed" or summary["passed"] is not True or
            summary["ci_codes"] != [0, 20] or not isinstance(cost, (int, float)) or
            not math.isfinite(cost) or not 0 <= cost <= 0.20):
        raise ValueError("Shared Lesson 49 live criterion did not pass")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", required=True)
    parser.add_argument("--budget", type=float, required=True)
    args = parser.parse_args()
    if not args.live or args.budget != 0.20:
        parser.error("Confirm --live and the fixed $0.20 two-query ceiling.")
    print(json.dumps(asyncio.run(run())))
