"""Run the real Lesson 51 host suite with Python network paths blocked."""

import argparse
import asyncio
import importlib
import json
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent_lab.offline_guard import NetworkGuard  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mutation", action="store_true")
    args = parser.parse_args()
    for name in ("ANTHROPIC_API_KEY", "INWORLD_API_KEY", "OPENAI_API_KEY"):
        os.environ.pop(name, None)
    folder = ROOT / ".lab-data/offline-validation" / ("host-" + str(uuid.uuid4()))
    folder.mkdir(parents=True)
    # Windows creates a loopback socketpair while constructing its event loop.
    # Build that local wake-up channel before guarding host-suite network paths.
    loop = asyncio.new_event_loop()
    guard = NetworkGuard()
    try:
        with guard:
            module = importlib.import_module("agent_lab.offline_lab")
            report = loop.run_until_complete(module.run_suite(folder, mutation=args.mutation))
    finally:
        loop.close()
    (folder / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    result = {"lesson": 51, "check_passed": report["experiment_passed"],
              "summary": report.get("summary"), "modelCalls": report["modelCalls"],
              "networkAttempts": guard.attempts,
              "actualBilledUsd": report["actualBilledUsd"],
              "evidence": str(folder / "report.json")}
    print(json.dumps(result, indent=2))
    if guard.attempts or (not args.mutation and not report["experiment_passed"]):
        return 1
    if args.mutation:
        if (report.get("summary", {}).get("passed") != 15 or
                report.get("summary", {}).get("failed") != 1):
            return 3
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
