"""Stop one owned Lesson 57 API run after two real SDK workers finish."""

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def run(budget: float) -> dict:
    from agent_lab import api_worktrees
    from agent_lab.api import create_app
    from agent_lab.config import ROOT, Settings
    from agent_lab.runtime import RunService

    root = ROOT / ".lab-data/offline-validation" / f"worktrees-api-stop-native-{uuid.uuid4()}"
    root.mkdir(parents=True)
    reached = asyncio.Event()
    actual = api_worktrees.run_workshop

    async def hold_before_integration(_repo: Path) -> None:
        reached.set()
        await asyncio.sleep(30)

    async def controlled(*args, **kwargs):
        return await actual(*args, **kwargs, before_integration=hold_before_integration)

    api_worktrees.run_workshop = controlled
    app = create_app(RunService(Settings(data_dir=root, enable_live=True)), with_ui=False)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url="http://worktrees", timeout=120) as client:
            pending = asyncio.create_task(client.post("/api/c57/run", json={"mode": "live",
                "scenario": "independent", "consent": True, "budget": budget}))
            await asyncio.wait_for(reached.wait(), 85)
            active = await client.get("/api/c57/active")
            if active.status_code != 200:
                raise RuntimeError("Live run became inactive before Stop")
            run_id = active.json()["runId"]
            stop = await client.post("/api/c57/stop", json={"runId": run_id})
            response = await asyncio.wait_for(pending, 20)
            frames = [json.loads(line[6:]) for line in response.text.splitlines()
                      if line.startswith("data: ")]
            results = [row for row in frames if row["kind"] == "result"]
            recovered = await client.get(f"/api/c57/runs/{run_id}",
                                         headers={"Cache-Control": "no-store"})
            report = recovered.json()["report"] if recovered.status_code == 200 else None
            passed = bool(stop.status_code == 202 and response.status_code == 200 and
                          len(results) == 1 and report is not None and
                          recovered.headers.get("cache-control") == "no-store" and
                          results[0]["report"] == report and report["runId"] == run_id and
                          report["interrupted"] and report["check"] == "needs-review" and
                          report["status"] == "needs-review" and report["settled"] and
                          report["sdkQueries"] == 2 and len(report["workers"]) == 2 and
                          all(worker["native"]["passed"] and worker["workerSHA"]
                              for worker in report["workers"]) and
                          report["reportedSdkUsd"] is not None and
                          not report["integration"] and report["worktreeCount"] == 3 and
                          (await client.get("/api/c57/active")).status_code == 404)
            summary = {"lesson": 57, "passed": passed, "runId": run_id,
                       "report": str((root / "lesson-57" / run_id / "report.json").relative_to(ROOT)),
                       "stopStatus": stop.status_code, "sdkQueries": report["sdkQueries"] if report else None,
                       "reportedSdkUsd": report["reportedSdkUsd"] if report else None,
                       "interrupted": report["interrupted"] if report else None,
                       "recoveredSHA256": recovered.json()["sha256"] if report else None}
            (root / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
            return summary
    finally:
        api_worktrees.run_workshop = actual


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--budget", type=float)
    args = parser.parse_args()
    if not args.live or args.budget is None or not 0.16 <= args.budget <= 1:
        parser.error("One paid Stop probe requires --live --budget between 0.16 and 1")
    result = asyncio.run(run(args.budget))
    print(json.dumps(result))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
