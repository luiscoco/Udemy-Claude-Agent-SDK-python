"""Opt-in five-action Lesson 47 native orchestration acceptance through the public API."""

import argparse
import asyncio
import json
import math
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx

from agent_lab.api import create_app
from agent_lab.config import ROOT, Settings
from agent_lab.runtime import RunService

CASES = ("orchestrator", "hierarchy", "pipeline", "fanout", "evaluator")
CEILINGS = {"orchestrator": 0.20, "hierarchy": 0.25,
            "pipeline": 0.15, "fanout": 0.15, "evaluator": 0.10}


async def run(budget: float) -> dict[str, Any]:
    folder = ROOT / ".lab-data" / "orchestra-api-live" / str(uuid.uuid4())
    folder.mkdir(parents=True)
    runner = RunService(Settings(enable_live=True, data_dir=folder))
    app = create_app(runner, with_ui=False)
    summaries: list[dict[str, Any]] = []
    total = 0.0
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                 base_url="http://owned.test", timeout=190) as client:
        for index, action in enumerate(CASES, 1):
            response = await client.post("/api/c47/" + action,
                                         json={"mode": "live", "consent": True, "limit": 2})
            if response.status_code != 200:
                raise ValueError(f"Orchestration action {index} returned HTTP {response.status_code}")
            report = response.json()
            (folder / f"action-{index}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            costs = [row.get("cost_usd") for row in report.get("queries", [])]
            valid_cost = bool(costs) and all(isinstance(value, (int, float)) and
                                             math.isfinite(value) and 0 <= value
                                             for value in costs)
            cost = sum(costs) if valid_cost else None
            summary = {"action": action, "operation": report.get("operation"),
                       "passed": report.get("experiment_passed"),
                       "workers": len(report.get("starts", [])),
                       "queries": len(report.get("queries", [])),
                       "sdk_cost_usd": cost}
            summaries.append(summary)
            (folder / "summary.json").write_text(json.dumps({"cases": summaries,
                "total_sdk_usd": total, "created_at": datetime.now(UTC).isoformat()}, indent=2), encoding="utf-8")
            if cost is None or cost > CEILINGS[action]:
                raise ValueError(f"Orchestration action {index} has unknown or excessive cost")
            total += cost
            (folder / "summary.json").write_text(json.dumps({"cases": summaries,
                "total_sdk_usd": total, "created_at": datetime.now(UTC).isoformat()}, indent=2), encoding="utf-8")
            if total > min(budget, 0.85) or not report.get("experiment_passed"):
                raise ValueError(f"Orchestration action {index} failed its evidence or budget check")
    return {"folder": str(folder), "cases": summaries, "total_sdk_usd": total}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", required=True)
    parser.add_argument("--budget", type=float, required=True)
    args = parser.parse_args()
    if not args.live or not math.isfinite(args.budget) or not 0.85 <= args.budget <= 1:
        parser.error("Confirm --live and a finite budget from $0.85 to $1.00.")
    print(json.dumps(asyncio.run(run(args.budget)), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
