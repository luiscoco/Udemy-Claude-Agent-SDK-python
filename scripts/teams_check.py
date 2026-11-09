"""Run the guarded sixteen-step Lesson 56 team reducer with no model or network."""

import hashlib
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
        print("This free command accepts no arguments.", file=sys.stderr)
        return 2

    def blocked(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Offline workshop forbids network and child processes")

    with (patch.object(socket.socket, "connect", blocked),
          patch.object(socket, "create_connection", blocked),
          patch.object(subprocess.Popen, "__init__", blocked),
          patch.object(subprocess, "run", blocked),
          patch.object(subprocess, "call", blocked),
          patch.object(subprocess, "check_call", blocked),
          patch.object(subprocess, "check_output", blocked)):
        from agent_lab.config import ROOT
        from agent_lab.teams_lab import canonical_input, grade, run_replay

        def dependency_hashes() -> dict[str, str]:
            return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                    for name in ("pyproject.toml", "uv.lock")}

        before = dependency_hashes()
        rows = []
        for count in range(17):
            selected = canonical_input(count)
            report = run_replay(selected)
            passed = grade(selected, report)
            rows.append({"prefix": count, "passed": passed, "closed": report["state"]["closed"],
                         "rejected": sum(not row["accepted"] for row in report["state"]["receipts"]),
                         "messages": len(report["state"]["messages"])})
        after = dependency_hashes()
        passed = (all(not row["passed"] for row in rows[:-1]) and rows[-1]["passed"] and
                  rows[-1]["rejected"] == 5 and rows[-1]["messages"] == 1 and before == after)
        result = {"lesson": 56, "passed": passed, "steps": 16, "prefixes": rows,
                  "before": before, "after": after, "modelCalls": 0,
                  "networkAttempts": 0, "childProcessAttempts": 0, "reportedSdkUsd": 0}
        folder = ROOT / ".lab-data/offline-validation" / f"teams-{uuid.uuid4()}"
        folder.mkdir(parents=True, exist_ok=False)
        (folder / "report.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": passed, "report": str(folder.relative_to(ROOT)),
                      "steps": 16, "rejected": rows[-1]["rejected"],
                      "modelCalls": 0, "networkAttempts": 0, "reportedSdkUsd": 0}))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
