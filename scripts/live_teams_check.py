"""One explicitly paid bounded Lesson 56 named-subagent observation."""

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--budget", type=float)
    args = parser.parse_args()
    if not args.live or args.budget is None or not 0.15 <= args.budget <= 1:
        parser.error("One paid run requires --live --budget between 0.15 and 1")

    from agent_lab.config import ROOT, Settings
    from agent_lab.teams_lab import LiveInput
    from agent_lab.teams_native import evaluate_native, native_run

    selected = LiveInput(consent=True, budget=args.budget)
    folder = ROOT / ".lab-data/offline-validation" / f"teams-native-{uuid.uuid4()}"
    folder.mkdir(parents=True, exist_ok=False)
    report = asyncio.run(native_run(selected, Settings(enable_live=True), folder))
    passed = evaluate_native(report)
    (folder / "report.json").write_text(json.dumps({"lesson": 56, "passed": passed,
        "report": report}, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"passed": passed, "report": str((folder / "report.json").relative_to(ROOT)),
                      "sdkQueries": report["sdkQueries"], "reportedSdkUsd": report["reportedSdkUsd"],
                      "sendMessageAttempted": report["sendMessageAttempted"],
                      "messagingRejected": report["messagingRejected"],
                      "deliveryVerified": report["deliveryVerified"],
                      "workerCompletionVerified": report["workerCompletionVerified"]}))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
