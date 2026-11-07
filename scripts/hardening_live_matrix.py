"""Opt-in bounded Lesson 48 live API matrix with sanitized summary."""

import argparse
import asyncio
import json
import math
import sys
import uuid
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_lab.api import create_app  # noqa: E402
from agent_lab.config import ROOT, Settings  # noqa: E402
from agent_lab.hardening_lab import ACTIONS  # noqa: E402
from agent_lab.runtime import RunService  # noqa: E402


async def run(budget: float) -> dict[str, Any]:
    group = str(uuid.uuid4())
    folder = ROOT / ".lab-data/hardening-api-live" / group
    folder.mkdir(parents=True)
    app = create_app(RunService(Settings(data_dir=folder, enable_live=True)))
    rows: list[dict[str, Any]] = []
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                 base_url="http://test") as client:
        facts = await client.get("/api/c48/facts")
        if facts.status_code != 200 or facts.json().get("actions") != list(ACTIONS):
            raise RuntimeError("Lesson 48 API facts mismatch")
        for action in ACTIONS:
            response = await client.post("/api/c48/" + action,
                                         json={"mode": "live", "consent": True})
            if response.status_code != 200:
                raise RuntimeError(f"{action} HTTP {response.status_code}")
            report = response.json()
            costs = [next((frame["cost_usd"] for frame in lane["frames"]
                           if frame.get("kind") == "result"), None)
                     for lane in report["lanes"]]
            if (report.get("experiment_passed") is not True or
                    not all(isinstance(cost, (int, float)) and math.isfinite(cost)
                            and 0 <= cost <= 0.10 for cost in costs)):
                raise RuntimeError(f"{action} live evidence failed: {report.get('operation')}")
            rows.append({"action": action, "operation": report["operation"],
                         "cost_usd": sum(costs), "lane_costs_usd": costs,
                         "calls": [len(lane["calls"]) for lane in report["lanes"]],
                         "receipts": [len(lane["receipts"]) for lane in report["lanes"]],
                         "closed": all(lane["closed"] for lane in report["lanes"])})
            if sum(row["cost_usd"] for row in rows) > budget:
                raise RuntimeError("Combined budget exceeded")
        state = await client.get("/api/c48/state")
        if state.status_code != 200 or state.json().get("action") != ACTIONS[-1]:
            raise RuntimeError("Latest passing state mismatch")
    summary = {"lesson": 48, "group": group, "actions": rows,
               "total_cost_usd": sum(row["cost_usd"] for row in rows),
               "budget_usd": budget, "passed": len(rows) == len(ACTIONS)}
    (folder / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--budget", type=float, default=0.80)
    options = parser.parse_args()
    if not options.live or not math.isfinite(options.budget) or options.budget <= 0 or options.budget > 0.80:
        parser.error("Explicit --live and a positive budget no greater than $0.80 are required")
    print(json.dumps(asyncio.run(run(options.budget)), indent=2))
