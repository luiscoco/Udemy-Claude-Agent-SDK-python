"""Cancel an active Lesson 48 native query and verify both loopback listeners close."""

import argparse
import asyncio
import json

from agent_lab.config import ROOT, Settings
from agent_lab.curriculum import get_lesson
from agent_lab.models import RunRequest
from agent_lab.runtime import RunService


async def closed(port: int) -> bool:
    try:
        _reader, writer = await asyncio.wait_for(asyncio.open_connection("127.0.0.1", port), 0.5)
    except (OSError, TimeoutError):
        return True
    writer.close()
    await writer.wait_closed()
    return False


async def run() -> dict:
    data = ROOT / ".lab-data/hardening-cancel-live"
    probe_root = ROOT / ".lab-data/hardening-live"
    before = {path.name for path in probe_root.iterdir()} if probe_root.exists() else set()
    service = RunService(Settings(enable_live=True, data_dir=data))
    try:
        handle = service.start(48, RunRequest(mode="live", prompt=get_lesson(48).prompt,
            lesson_options={"action": "permissions", "consent": True}, max_turns=10,
            max_budget_usd=0.20))
        operation = None
        ports = None
        for _ in range(200):
            candidates = [path for path in probe_root.iterdir() if path.is_dir() and
                          path.name not in before and (path / "contrast/ports.json").is_file()]
            if candidates:
                operation = candidates[0].name
                ports = json.loads((candidates[0] / "contrast/ports.json").read_text())
                break
            await asyncio.sleep(0.05)
        if operation is None or ports is None:
            raise ValueError("Native query did not open its isolated listeners")
        if handle.task is None or handle.task.done():
            raise ValueError("Native query completed before cancellation")
        await service.cancel(handle)
        events = [event async for event in service.events(handle)]
        status = next((event.data["status"] for event in events if event.kind == "done"), None)
        if (status != "cancelled" or any(event.kind == "evidence" for event in events) or
                service.active or not await closed(ports["collector"]) or
                not await closed(ports["observer"])):
            raise ValueError("Cancellation left successful evidence, active run or listener")
        return {"status": status, "operation": operation, "saved_evidence": False,
                "active_runs": len(service.active), "collector_closed": True,
                "observer_closed": True}
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
