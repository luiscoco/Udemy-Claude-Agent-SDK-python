"""Verify the shared Lesson 50 runner on one bounded native orders turn."""

import argparse
import asyncio
import json
import math
import sys
import uuid
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_lab.config import ROOT, Settings  # noqa: E402
from agent_lab.models import RunRequest  # noqa: E402
from agent_lab.runtime import RunService  # noqa: E402


async def run() -> dict:
    folder = ROOT / ".lab-data/desk-runner-live" / str(uuid.uuid4())
    runner = RunService(Settings(data_dir=folder, enable_live=True))
    try:
        events = [event async for event in runner.events(
            runner.start(50, RunRequest(mode="live", prompt="Please inspect my orders.")))]
    finally:
        await runner.close()
    evidence = next((event.data["result"] for event in events if event.kind == "evidence"), None)
    if events[-1].data["status"] != "completed" or not isinstance(evidence, dict):
        raise ValueError("Shared native desk run did not complete")
    terminal: dict[str, Any] = next((row for row in evidence.get("frames", []) if row.get("kind") == "result"), {})
    cost = evidence.get("cost_delta_usd")
    if (evidence.get("experiment_passed") is not True or evidence.get("native") is not True or
            [row["tool"] for row in evidence.get("calls", [])] != ["orders"] or
            not isinstance(cost, (int, float)) or not math.isfinite(cost) or not 0 <= cost <= 0.10 or
            terminal.get("subtype") != "success"):
        raise ValueError("Shared native desk evidence was incomplete")
    (folder / "report.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    return {"lesson": 50, "passed": True, "conversation": evidence["conversation"],
            "source": evidence["source"], "cost_delta_usd": cost, "report": str(folder / "report.json")}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--budget", type=float, default=0)
    args = parser.parse_args()
    if not args.live or args.budget != 0.10:
        parser.error("Use explicit --live --budget 0.10; the native action caps itself at $0.10.")
    print(json.dumps(asyncio.run(run()), indent=2))
