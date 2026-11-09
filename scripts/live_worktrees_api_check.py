"""One opt-in provider-backed Lesson 57 API stream and recovery scenario."""

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def run(budget: float, scenario: str = "independent") -> dict:
    from agent_lab.api import create_app
    from agent_lab.config import ROOT, Settings
    from agent_lab.runtime import RunService
    from agent_lab.worktrees_lab import grade

    root = ROOT / ".lab-data/offline-validation" / f"worktrees-api-native-{uuid.uuid4()}"
    root.mkdir(parents=True)
    app = create_app(RunService(Settings(data_dir=root, enable_live=True)), with_ui=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                 base_url="http://worktrees", timeout=120) as client:
        response = await client.post("/api/c57/run", json={"mode": "live",
                                     "scenario": scenario, "consent": True, "budget": budget})
        if response.status_code != 200:
            raise RuntimeError(f"Native API admission returned HTTP {response.status_code}")
        frames = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
        starts = [row for row in frames if row["kind"] == "start"]
        results = [row for row in frames if row["kind"] == "result"]
        if len(starts) != 1 or len(results) != 1:
            raise RuntimeError("Native API did not yield one start and one result")
        report = results[0]["report"]
        recovered = await client.get(f"/api/c57/runs/{report['runId']}",
                                     headers={"Cache-Control": "no-store"})
        shared = (starts[0]["runId"] == report["runId"] and
                  starts[0]["scenario"] == scenario and recovered.status_code == 200 and
                  recovered.headers.get("cache-control") == "no-store" and
                  recovered.json()["report"] == report and report["sdkQueries"] == 2 and
                  report["settled"] and not report["interrupted"] and not report["errors"] and
                  len(report["workers"]) == 2 and
                  all(worker["native"]["passed"] for worker in report["workers"]))
        if scenario == "independent":
            passed = shared and grade(report) and results[0]["check"] == "passed"
        else:
            conflict = report.get("conflict", {})
            owned = root / "lesson-57" / report["runId"]
            passed = bool(shared and not grade(report) and
                          report["status"] == "conflict" and results[0]["check"] == "needs-review" and
                          conflict.get("unmerged") == ["greeting.mjs"] and
                          conflict.get("aborted") is True and conflict.get("priorPicks") == 1 and
                          len(report["integration"]) == 1 and
                          report["mainHEAD"] == report["integration"][0]["integratedSHA"] and
                          report["mainClean"] is True and report["worktreeCount"] == 3 and
                          not report["combinedTests"] and not report["cleanup"] and
                          all(report["workerRefs"][worker["name"]] == worker["workerSHA"]
                              for worker in report["workers"]) and
                          (owned / "greeting").is_dir() and (owned / "alternative").is_dir())
        summary = {"lesson": 57, "passed": passed, "runId": report["runId"],
                   "scenario": scenario, "status": report["status"],
                   "report": str((root / "lesson-57" / report["runId"] / "report.json").relative_to(ROOT)),
                   "sdkQueries": report["sdkQueries"], "reportedSdkUsd": report["reportedSdkUsd"],
                   "progressEvents": len([row for row in frames if row["kind"] == "progress"]),
                   "recoveredSHA256": recovered.json()["sha256"] if recovered.status_code == 200 else None}
        (root / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--budget", type=float)
    parser.add_argument("--scenario", choices=["independent", "conflict"], default="independent")
    args = parser.parse_args()
    if not args.live or args.budget is None or not 0.16 <= args.budget <= 1:
        parser.error("One paid API run requires --live --budget between 0.16 and 1")
    result = asyncio.run(run(args.budget, args.scenario))
    print(json.dumps(result))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
