"""Run all nine offline Lesson 55 candidate contracts with network/process guards."""

import json
import socket
import subprocess
import sys
import uuid
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    if len(sys.argv) != 1:
        print("This offline-only command accepts no arguments.", file=sys.stderr)
        return 2

    def blocked(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Network and child processes are forbidden in the offline workshop")

    with (patch.object(socket.socket, "connect", blocked),
          patch.object(socket, "create_connection", blocked),
          patch.object(subprocess.Popen, "__init__", blocked),
          patch.object(subprocess, "run", blocked),
          patch.object(subprocess, "call", blocked),
          patch.object(subprocess, "check_call", blocked),
          patch.object(subprocess, "check_output", blocked)):
        from agent_lab.config import ROOT
        from agent_lab.upgrading_lab import (
            SCENARIOS,
            RunInput,
            TransitionInput,
            criterion,
            dependency_snapshot,
            run_upgrade,
            transition,
        )

        before = dependency_snapshot()
        rows = []
        for scenario in SCENARIOS:
            selected = RunInput(scenario=scenario)
            report = run_upgrade(selected)
            passed = criterion(selected, report)
            rows.append({"scenario": scenario, "passed": passed, "decision": report["decision"],
                         "failedGates": [gate["name"] for gate in report["gates"] if not gate["passed"]],
                         "modelCalls": report["modelCalls"], "networkAttempts": report["networkAttempts"],
                         "reportedSdkUsd": report["reportedSdkUsd"]})
        stages = []
        state = "checked"
        for action in ("start-canary", "promote", "rollback"):
            outcome = transition(TransitionInput(scenario="compatible", state=state, action=action))
            state = outcome["newState"]
            stages.append(state)
        after = dependency_snapshot()
        passed = all(row["passed"] for row in rows) and before == after and stages == ["canary", "promoted", "rolled-back"]
        report = {"lesson": 55, "passed": passed, "simulated": True, "scenarios": rows,
                  "stages": stages, "before": before, "after": after,
                  "modelCalls": 0, "networkAttempts": 0, "childProcessAttempts": 0, "reportedSdkUsd": 0}
        folder = ROOT / ".lab-data/offline-validation" / f"upgrading-{uuid.uuid4()}"
        folder.mkdir(parents=True, exist_ok=False)
        (folder / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": passed, "report": str(folder.relative_to(ROOT)),
                      "scenarios": len(rows), "modelCalls": 0, "networkAttempts": 0,
                      "reportedSdkUsd": 0}))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
