"""Opt-in Lesson 49 live API matrix with two paid and two local actions."""

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
from agent_lab.headless_lab import ACTIONS  # noqa: E402
from agent_lab.runtime import RunService  # noqa: E402


async def run(budget: float) -> dict[str, Any]:
    group = str(uuid.uuid4())
    folder = ROOT / ".lab-data/headless-api-live" / group
    folder.mkdir(parents=True)
    app = create_app(RunService(Settings(data_dir=folder, enable_live=True)))
    rows: list[dict[str, Any]] = []
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                 base_url="http://test") as client:
        facts = await client.get("/api/c49/facts")
        if facts.status_code != 200 or facts.json().get("actions") != list(ACTIONS):
            raise RuntimeError("Lesson 49 API facts mismatch")
        for action in ACTIONS:
            paid = action in {"headless", "ci"}
            response = await client.post("/api/c49/" + action,
                                         json={"mode": "live" if paid else "local",
                                               "consent": paid})
            if response.status_code != 200:
                raise RuntimeError(f"{action} HTTP {response.status_code}")
            report = response.json()
            if report.get("experiment_passed") is not True:
                raise RuntimeError(f"{action} evidence failed: {report.get('operation')}")
            costs = [outcome.get("terminal", {}).get("cost_usd")
                     for outcome in report.get("outcomes", [])] if paid else []
            if any(not isinstance(cost, (int, float)) or not math.isfinite(cost) or
                   not 0 <= cost <= 0.10 for cost in costs):
                raise RuntimeError(f"{action} has missing or excessive SDK cost")
            rows.append({"action": action, "operation": report["operation"],
                         "mode": report["mode"], "cost_usd": sum(costs),
                         "outcomes": len(report.get("outcomes", [])),
                         "worker_job_status": report.get("worker", {}).get("job_status")})
            if sum(row["cost_usd"] for row in rows) > budget:
                raise RuntimeError("Combined budget exceeded")
        state = await client.get("/api/c49/state")
        if state.status_code != 200 or state.json().get("action") != ACTIONS[-1]:
            raise RuntimeError("Latest passing state mismatch")
    summary = {"lesson": 49, "group": group, "actions": rows,
               "total_cost_usd": sum(row["cost_usd"] for row in rows),
               "budget_usd": budget, "passed": len(rows) == len(ACTIONS)}
    (folder / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--budget", type=float, default=0.40)
    options = parser.parse_args()
    if not options.live or not math.isfinite(options.budget) or not 0.40 <= options.budget <= 1:
        parser.error("Explicit --live and finite budget in [$0.40, $1] are required")
    print(json.dumps(asyncio.run(run(options.budget)), indent=2))
