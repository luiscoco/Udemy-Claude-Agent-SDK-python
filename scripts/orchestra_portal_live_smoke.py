"""One explicit provider-backed Lesson 47 run through the shared lesson runner."""

import argparse
import asyncio
import json

from agent_lab.config import ROOT, Settings
from agent_lab.curriculum import get_lesson
from agent_lab.models import RunRequest
from agent_lab.runtime import RunService


async def run() -> dict:
    service = RunService(Settings(enable_live=True, data_dir=ROOT / ".lab-data/orchestra-portal-live"))
    events = []
    try:
        handle = service.start(47, RunRequest(mode="live", prompt=get_lesson(47).prompt,
            lesson_options={"action": "orchestrator", "consent": True}, max_turns=8,
            max_budget_usd=0.20))
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
               "workers": len(report.get("starts", [])), "queries": len(report.get("queries", [])),
               "sdk_cost_usd": cost}
    if (summary["status"] != "completed" or summary["passed"] is not True or
            summary["workers"] != 2 or summary["queries"] != 1 or
            not isinstance(cost, (int, float)) or not 0 <= cost <= 0.20):
        raise ValueError("Shared Lesson 47 live criterion did not pass")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", required=True)
    parser.add_argument("--budget", type=float, required=True)
    args = parser.parse_args()
    if not args.live or args.budget != 0.20:
        parser.error("Confirm --live and the fixed $0.20 root-query ceiling.")
    print(json.dumps(asyncio.run(run())))


if __name__ == "__main__":
    main()
