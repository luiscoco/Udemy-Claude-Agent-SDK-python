"""Retry only a failed, effect-free Lesson 50 native CRM close with explicit ceiling."""

import argparse
import asyncio
import json
import math
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_lab.config import ROOT  # noqa: E402
from agent_lab.desk_native import native_close  # noqa: E402
from agent_lab.desk_store import DeskStore  # noqa: E402


async def run(group: uuid.UUID) -> dict:
    folder = ROOT / ".lab-data/desk-api-live" / str(group)
    previous = json.loads((folder / "close.json").read_text(encoding="utf-8"))
    if previous.get("experiment_passed") is not False:
        raise ValueError("Only a failed native close may be retried")
    store = DeskStore(folder / "lesson-50")
    conversation = uuid.UUID(previous["conversation"])
    store.require_open(conversation, previous["customer"], "live")
    report = await native_close(store, previous["customer"], conversation)
    (folder / "close-final.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    terminal = next((row for row in report["frames"] if row.get("kind") == "result"), {})
    return {"group": str(group), "passed": report["experiment_passed"],
            "conversation": str(conversation), "cost_usd": terminal.get("cost_usd")}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--budget", type=float, default=0)
    parser.add_argument("--group", type=uuid.UUID, required=True)
    args = parser.parse_args()
    if not args.live or not math.isfinite(args.budget) or args.budget != 0.10:
        parser.error("Use explicit --live --budget 0.10")
    summary = asyncio.run(run(args.group))
    print(json.dumps(summary, indent=2))
    if not summary["passed"] or not isinstance(summary["cost_usd"], (int, float)) or summary["cost_usd"] > args.budget:
        raise SystemExit(1)
