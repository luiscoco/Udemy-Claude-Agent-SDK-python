"""Cancel an active owned Lesson 47 native query through the shared runner."""

import argparse
import asyncio
import json

from agent_lab.config import ROOT, Settings
from agent_lab.curriculum import get_lesson
from agent_lab.models import RunRequest
from agent_lab.runtime import RunService


async def run() -> dict:
    data = ROOT / ".lab-data/orchestra-cancel-live"
    probe_root = ROOT / ".lab-data/orchestra-live"
    before = {path.name for path in probe_root.iterdir()} if probe_root.exists() else set()
    service = RunService(Settings(enable_live=True, data_dir=data))
    try:
        handle = service.start(47, RunRequest(mode="live", prompt=get_lesson(47).prompt,
            lesson_options={"action": "orchestrator", "consent": True}, max_turns=8,
            max_budget_usd=0.20))
        operation = None
        for _ in range(150):
            candidates = [path for path in probe_root.iterdir() if path.is_dir() and
                          path.name not in before and (path / "home-lead").exists()]
            if candidates:
                operation = candidates[0].name
                break
            await asyncio.sleep(0.1)
        if operation is None:
            raise ValueError("Native query did not create its isolated home")
        await asyncio.sleep(1)
        if handle.task is None or handle.task.done():
            raise ValueError("Native query completed before cancellation")
        await service.cancel(handle)
        events = [event async for event in service.events(handle)]
        status = next((event.data["status"] for event in events if event.kind == "done"), None)
        if status != "cancelled" or any(event.kind == "evidence" for event in events) or service.active:
            raise ValueError("Cancellation left a successful or active run")
        return {"status": status, "operation": operation, "saved_evidence": False,
                "active_runs": len(service.active)}
    finally:
        await service.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", required=True)
    parser.add_argument("--budget", type=float, required=True)
    args = parser.parse_args()
    if not args.live or args.budget != 0.20:
        parser.error("Confirm --live and the fixed $0.20 root-query ceiling.")
    print(json.dumps(asyncio.run(run())))


if __name__ == "__main__":
    main()
