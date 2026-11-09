"""One opt-in provider-backed Lesson 57 API stream and recovery smoke run."""

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def run(budget: float) -> dict:
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
                                     "scenario": "independent", "consent": True, "budget": budget})
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
        passed = (starts[0]["runId"] == report["runId"] and recovered.status_code == 200 and
                  recovered.headers.get("cache-control") == "no-store" and
                  recovered.json()["report"] == report and grade(report) and
                  results[0]["check"] == "passed")
        summary = {"lesson": 57, "passed": passed, "runId": report["runId"],
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
    args = parser.parse_args()
    if not args.live or args.budget is None or not 0.16 <= args.budget <= 1:
        parser.error("One paid API run requires --live --budget between 0.16 and 1")
    result = asyncio.run(run(args.budget))
    print(json.dumps(result))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
