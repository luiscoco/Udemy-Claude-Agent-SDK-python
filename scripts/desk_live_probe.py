"""One explicit bounded native Lesson 50 synthetic desk probe."""

import argparse
import asyncio
import json
import math
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_lab.config import ROOT  # noqa: E402
from agent_lab.desk_approver import DeskApprover  # noqa: E402
from agent_lab.desk_native import native_chat  # noqa: E402
from agent_lab.desk_store import DeskStore  # noqa: E402


async def run() -> dict:
    root = ROOT / ".lab-data/desk-live" / str(uuid.uuid4())
    store = DeskStore(root)
    report = await native_chat(store, DeskApprover(), customer="ada", intent="orders")
    encoded = json.dumps(report, indent=2)
    if len(encoded.encode()) > 500_000:
        raise ValueError("Native support report exceeded bound")
    root.mkdir(parents=True, exist_ok=True)
    (root / "report.json").write_text(encoded, encoding="utf-8")
    terminal = next((row for row in report.get("frames", []) if row.get("kind") == "result"), {})
    summary = {"path": str(root / "report.json"), "run": report["run"],
               "conversation": report["conversation"],
               "passed": report["experiment_passed"],
               "cost_usd": terminal.get("cost_usd"),
               "calls": [row["tool"] for row in report["calls"]],
               "result_count": len(report["results"]),
               "error_class": report.get("error_class")}
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--budget", type=float, default=0)
    options = parser.parse_args()
    if not options.live or not math.isfinite(options.budget) or options.budget != 0.10:
        parser.error("Use explicit --live --budget 0.10 for one fixed native query")
    result = asyncio.run(run())
    print(json.dumps(result, indent=2))
    if not result["passed"] or not isinstance(result["cost_usd"], (int, float)) or result["cost_usd"] > options.budget:
        raise SystemExit(1)
