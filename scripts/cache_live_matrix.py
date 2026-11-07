"""Opt-in five-action Lesson 46 native cache acceptance through the public API."""

import argparse
import asyncio
import json
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx

from agent_lab.api import create_app
from agent_lab.config import ROOT, Settings
from agent_lab.runtime import RunService

CASES = (("anatomy", {}), ("switches", {"ttl": "1h"}),
         ("breakers", {"prefix": "changed"}),
         ("model-switch", {"policy": "cap"}),
         ("model-switch", {"policy": "allow"}))


async def run(budget: float) -> dict[str, Any]:
    folder = ROOT / ".lab-data" / "cache-api-live" / str(uuid.uuid4())
    folder.mkdir(parents=True)
    runner = RunService(Settings(enable_live=True, data_dir=folder))
    app = create_app(runner, with_ui=False)
    transport = httpx.ASGITransport(app=app)
    summaries: list[dict[str, Any]] = []
    total = 0.0
    async with httpx.AsyncClient(transport=transport, base_url="http://owned.test", timeout=190) as client:
        for index, (action, selection) in enumerate(CASES, 1):
            response = await client.post("/api/c46/" + action,
                                         json={"mode": "live", "consent": True, **selection})
            if response.status_code != 200:
                raise ValueError(f"Cache action {index} returned HTTP {response.status_code}")
            report = response.json()
            (folder / f"action-{index}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            results = [row for row in report.get("frames", []) if row.get("kind") == "result"]
            cost = results[-1].get("total_cost_usd") if results else None
            summary = {"action": action, "selection": selection,
                       "operation": report.get("operation"), "passed": report.get("experiment_passed"),
                       "turns": len(results), "forwarded": report.get("forwarded"),
                       "sdk_last_cumulative_usd": cost}
            summaries.append(summary)
            if not isinstance(cost, (int, float)) or not 0 <= cost <= 0.15:
                raise ValueError(f"Cache action {index} has unknown or excessive cost")
            total += cost
            (folder / "summary.json").write_text(json.dumps({"cases": summaries,
                "total_sdk_usd": total, "created_at": datetime.now(UTC).isoformat()}, indent=2), encoding="utf-8")
            if total > min(budget, 0.75) or not report.get("experiment_passed"):
                raise ValueError(f"Cache action {index} failed its evidence or budget check")
    return {"folder": str(folder), "cases": summaries, "total_sdk_usd": total}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", required=True)
    parser.add_argument("--budget", type=float, required=True)
    args = parser.parse_args()
    if not args.live or not 0.75 <= args.budget <= 1:
        parser.error("Confirm --live and a finite budget from $0.75 to $1.00.")
    report = asyncio.run(run(args.budget))
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
