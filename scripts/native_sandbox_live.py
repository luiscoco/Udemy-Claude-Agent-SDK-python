"""Explicitly opted-in native sandbox acceptance on Linux/macOS (or inside WSL)."""

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent_lab.sandbox_native import run_native_probe, sandbox_capability  # noqa: E402


async def main(live: bool, model: str) -> int:
    if not live:
        print(json.dumps({"model_calls": 0, "capability": sandbox_capability()}))
        return 0
    folder = (
        ROOT / ".lab-data" / "native-sandbox-live" / datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    )
    folder.mkdir(parents=True)
    result = await run_native_probe(folder / "work", folder / "config", model)
    (folder / "report.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                key: result.get(key)
                for key in [
                    "passed",
                    "status",
                    "error_type",
                    "capability",
                    "baseline_loopback_reachable",
                    "outside_unchanged",
                    "inside_write_observed",
                    "reported_cost_usd",
                ]
            }
        ),
        flush=True,
    )
    print(f"Report: {folder / 'report.json'}", flush=True)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--model", default="claude-haiku-4-5")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.live, args.model)))
