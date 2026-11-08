"""Free seven-replay Lesson 53 check; paid native matrix requires explicit flags."""

import argparse
import asyncio
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
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--budget", type=float)
    args = parser.parse_args()
    if args.live and args.budget != 1.0:
        parser.error("Paid diagnostics require explicit --live --budget 1")
    if not args.live and args.budget is not None:
        parser.error("The free replay does not accept a paid budget")
    folder = ROOT / ".lab-data/offline-validation" / ("debug-" + str(uuid.uuid4()))
    folder.mkdir(parents=True, exist_ok=False)
    loop = asyncio.new_event_loop()
    guard = NetworkGuard()
    try:
        if args.live:
            from agent_lab.config import Settings
            from agent_lab.debug_lab import LIVE_SCENARIOS, DebugInput, criterion
            from agent_lab.debug_native import native_run
            from agent_lab.debug_store import DebugStore

            names: tuple[str, ...] = LIVE_SCENARIOS
            store = DebugStore(folder / "lesson-53")
            settings = Settings(enable_live=True, data_dir=folder)
            rows = []
            for name in names:
                selected = DebugInput.model_validate({"mode": "live", "scenario": name,
                                                      "consent": True, "budget": 1.0})
                identifier = uuid.uuid4()
                bundle = loop.run_until_complete(native_run(selected, store.root, identifier, settings))
                loaded = store.save(bundle)
                passed = criterion(str(identifier), selected, bundle, loaded)
                rows.append({"scenario": name, "runId": str(identifier), "passed": passed,
                             "modelCalls": bundle["modelCalls"], "reportedSdkUsd": bundle["reportedSdkUsd"],
                             "firstFinding": bundle["findings"][0]["code"] if bundle["findings"] else None,
                             "bundleSha256": loaded["sha256"]})
                if bundle["reportedSdkUsd"] is None:
                    break
            attempts = 0
        else:
            for name in ("ANTHROPIC_API_KEY", "INWORLD_API_KEY", "OPENAI_API_KEY"):
                os.environ.pop(name, None)
            with guard:
                from agent_lab.debug_lab import SCENARIOS, DebugInput, criterion, prepared_run
                from agent_lab.debug_store import DebugStore

                names = SCENARIOS
                store = DebugStore(folder / "lesson-53")
                rows = []
                for name in names:
                    selected = DebugInput.model_validate({"scenario": name})
                    identifier = uuid.uuid4()
                    bundle = loop.run_until_complete(prepared_run(selected, store.root, identifier))
                    loaded = store.save(bundle)
                    rows.append({"scenario": name, "runId": str(identifier),
                                 "passed": criterion(str(identifier), selected, bundle, loaded),
                                 "modelCalls": bundle["modelCalls"],
                                 "reportedSdkUsd": bundle["reportedSdkUsd"],
                                 "firstFinding": bundle["findings"][0]["code"] if bundle["findings"] else None,
                                 "bundleSha256": loaded["sha256"]})
            attempts = guard.attempts
    finally:
        loop.close()
    report = {"lesson": 53, "mode": "live" if args.live else "prepared", "rows": rows,
              "passed": len(rows) == len(names) and all(row["passed"] for row in rows),
              "modelCalls": sum(row["modelCalls"] for row in rows),
              "knownSdkUsd": sum(row["reportedSdkUsd"] or 0 for row in rows),
              "unknownCost": any(row["reportedSdkUsd"] is None for row in rows),
              "networkAttempts": attempts}
    (folder / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({**report, "evidence": str(folder / "report.json")}, indent=2))
    return 0 if report["passed"] and attempts == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
