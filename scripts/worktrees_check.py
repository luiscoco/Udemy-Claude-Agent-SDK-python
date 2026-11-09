"""Run both real-Git Lesson 57 prepared scenarios without model calls."""

import asyncio
import hashlib
import json
import socket
import sys
import uuid
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    if len(sys.argv) != 1:
        print("This free command accepts no arguments.", file=sys.stderr)
        return 2

    original_connect = socket.socket.connect

    def blocked(instance: socket.socket, address: object) -> None:
        if isinstance(address, tuple) and address and address[0] in {"127.0.0.1", "::1"}:
            original_connect(instance, address)
            return
        raise AssertionError("Parent network request forbidden")

    with patch.object(socket.socket, "connect", blocked), patch.object(socket, "create_connection", blocked):
        from agent_lab.config import ROOT
        from agent_lab.worktrees_lab import RunInput, grade, load_report, run_workshop

        def dependencies() -> dict[str, str]:
            return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                    for name in ("pyproject.toml", "uv.lock")}

        before = dependencies()
        root = ROOT / ".lab-data/offline-validation" / f"worktrees-{uuid.uuid4()}"
        root.mkdir(parents=True)

        async def both() -> list[dict[str, object]]:
            return [await run_workshop(RunInput(scenario=scenario), root)
                    for scenario in ("independent", "conflict")]

        independent, conflict = asyncio.run(both())
        recovered = [load_report(root, row["runId"]) for row in (independent, conflict)]
        after = dependencies()
        passed = bool(
            grade(independent) and independent["check"] == "passed" and
            not grade(conflict) and conflict["status"] == "conflict" and
            conflict["check"] == "needs-review" and
            conflict["conflict"]["unmerged"] == ["greeting.mjs"] and
            conflict["conflict"]["aborted"] and len(conflict["integration"]) == 1 and
            len(conflict["combinedTests"]) == 0 and len(conflict["cleanup"]) == 0 and
            conflict["worktreeCount"] == 3 and
            all(item["report"] == row and item["source"] == "persisted-owned-report"
                for item, row in zip(recovered, (independent, conflict), strict=True)) and
            all(row["sdkQueries"] == row["modelCalls"] == row["reportedSdkUsd"] == 0
                for row in (independent, conflict)) and before == after
        )
        summary = {"lesson": 57, "passed": passed, "root": str(root.relative_to(ROOT)),
                   "independentRunId": independent["runId"], "conflictRunId": conflict["runId"],
                   "independent": independent["check"], "conflict": conflict["check"],
                   "modelCalls": 0, "reportedSdkUsd": 0, "parentNetworkAttempts": 0,
                   "dependencyHashesUnchanged": before == after}
        (root / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
