"""Run the fixed Lesson 52 evaluation from a standalone host process."""

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
    parser.add_argument("--demo", choices=("baseline", "cold-tone", "false-refund", "fix-findings"),
                        default="baseline")
    parser.add_argument("--trials", type=int, choices=(1, 2, 3), default=3)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--budget", type=float)
    args = parser.parse_args()
    if args.live and args.budget != 1.0:
        parser.error("Paid evaluation requires explicit --live --budget 1")
    if not args.live and args.budget is not None:
        parser.error("The free demo does not accept a paid budget")
    folder = ROOT / ".lab-data/offline-validation" / ("evals-" + str(uuid.uuid4()))
    folder.mkdir(parents=True, exist_ok=False)
    loop = asyncio.new_event_loop()  # Windows needs its local socketpair before the guard.
    guard = NetworkGuard()
    try:
        if args.live:
            from agent_lab.config import Settings
            from agent_lab.evals_live import native_eval

            core = importlib.import_module("agent_lab.evals_core")
            store_module = importlib.import_module("agent_lab.evals_store")
            settings = Settings(enable_live=True, data_dir=folder)
            candidate = loop.run_until_complete(native_eval(folder, settings,
                                                 variant=args.demo, trials=args.trials,
                                                 judge="model", budget=args.budget, consent=True))
            store = store_module.EvalStore(folder)
            store.save(candidate)
            baseline = store_module.EvalStore(Settings().data_dir / "lesson-52").baseline("live", "model")
            comparison = core.compare(baseline, candidate)
            attempts = 0
        else:
            for name in ("ANTHROPIC_API_KEY", "INWORLD_API_KEY", "OPENAI_API_KEY"):
                os.environ.pop(name, None)
            with guard:
                core = importlib.import_module("agent_lab.evals_core")
                baseline = json.loads(core.BASELINE_PATH.read_text(encoding="utf-8"))
                candidate = core.synthetic_report(args.demo, args.trials)
                comparison = core.compare(baseline, candidate)
            attempts = guard.attempts
    finally:
        loop.close()
    report = {"lesson": 52, "baselineId": baseline["id"] if baseline else None,
              "candidateId": candidate["id"], "mode": candidate["mode"],
              "variant": candidate["variant"], "status": comparison["status"],
              "rows": len(candidate["rows"]), "metrics": len(comparison["metrics"]),
              "modelCalls": candidate["modelCalls"], "actualBilledUsd": candidate["actualBilledUsd"],
              "knownPartialCostUsd": candidate.get("knownPartialCostUsd"),
              "networkAttempts": attempts, "evidence": str(folder / "report.json")}
    (folder / "report.json").write_text(json.dumps({"baseline": baseline, "candidate": candidate,
                                                     "comparison": comparison}, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if attempts or comparison["status"] in {"stale", "error"}:
        return 2
    return 0 if comparison["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
