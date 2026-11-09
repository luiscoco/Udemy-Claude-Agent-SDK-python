"""One opt-in, two-worker provider-backed Lesson 57 Git workshop."""

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
    if not args.live or args.budget is None or not 0.16 <= args.budget <= 1:
        parser.error("One paid workshop requires --live --budget between 0.16 and 1")

    from agent_lab.config import ROOT
    from agent_lab.headless_native import bundled_cli, private_key
    from agent_lab.worktrees_lab import RunInput, load_report, run_workshop

    bundled_cli()
    private_key()
    root = ROOT / ".lab-data/offline-validation" / f"worktrees-native-{uuid.uuid4()}"
    root.mkdir(parents=True)
    report = asyncio.run(run_workshop(RunInput(mode="live", consent=True, budget=args.budget),
                                      root, allow_live=True))
    retained = load_report(root, report["runId"])
    passed = report["check"] == "passed" and retained["report"] == report
    result = {"lesson": 57, "passed": passed, "runId": report["runId"],
              "report": str((root / "lesson-57" / report["runId"] / "report.json").relative_to(ROOT)),
              "sdkQueries": report["sdkQueries"], "modelCalls": report["modelCalls"],
              "reportedSdkUsd": report["reportedSdkUsd"], "status": report["status"]}
    (root / "summary.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
