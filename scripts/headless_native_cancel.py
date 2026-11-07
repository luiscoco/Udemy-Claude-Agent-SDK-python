"""Cancel an active Lesson 49 native headless action through the shared runner."""

import argparse
import asyncio
import json

from agent_lab.config import ROOT, Settings
from agent_lab.curriculum import get_lesson
from agent_lab.models import RunRequest
from agent_lab.runtime import RunService


async def run() -> dict:
    data = ROOT / ".lab-data/headless-cancel-live"
    probe_root = ROOT / ".lab-data/headless-live"
    before = {path.name for path in probe_root.iterdir()} if probe_root.exists() else set()
    service = RunService(Settings(enable_live=True, data_dir=data))
    try:
        handle = service.start(49, RunRequest(mode="live", prompt=get_lesson(49).prompt,
            lesson_options={"action": "headless", "consent": True}, max_turns=4,
            max_budget_usd=0.20))
        operation = None
        for _ in range(200):
            candidates = [path for path in probe_root.iterdir() if path.is_dir() and
                          path.name not in before and (path / "cli/clean.py").is_file()]
            if candidates:
                operation = candidates[0].name
                break
            await asyncio.sleep(0.05)
        if operation is None or handle.task is None or handle.task.done():
            raise ValueError("Native CLI did not start before cancellation")
        await service.cancel(handle)
        events = [event async for event in service.events(handle)]
        status = next((event.data["status"] for event in events if event.kind == "done"), None)
        report = probe_root / operation / "report.json"
        if (status != "cancelled" or any(event.kind == "evidence" for event in events) or
                service.active or report.exists()):
            raise ValueError("Cancellation left successful evidence or active run")
        return {"status": status, "operation": operation, "saved_evidence": False,
                "active_runs": len(service.active)}
    finally:
        await service.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", required=True)
    parser.add_argument("--budget", type=float, required=True)
    args = parser.parse_args()
    if not args.live or args.budget != 0.20:
        parser.error("Confirm --live and the fixed $0.20 action ceiling.")
    print(json.dumps(asyncio.run(run())))
