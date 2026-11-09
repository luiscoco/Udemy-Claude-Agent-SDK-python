"""Exercise Lesson 58 Stop against one admitted native API run."""

import asyncio
import json
import uuid
from pathlib import Path

import httpx

from agent_lab.api import create_app
from agent_lab.config import Settings
from agent_lab.runtime import RunService


async def main() -> None:
    root = Path(".lab-data") / "offline-validation" / f"tool-search-stop-{uuid.uuid4()}"
    app = create_app(RunService(Settings(data_dir=root, enable_live=True)), with_ui=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                 base_url="http://lesson58", timeout=110) as client:
        running = asyncio.create_task(client.post("/api/c58/run", json={"mode": "live",
                                                                    "consent": True}))
        active = None
        for _ in range(50):
            response = await client.get("/api/c58/active")
            if response.status_code == 200:
                active = response.json()
                break
            await asyncio.sleep(0.05)
        assert active is not None, "No active native run appeared"
        stopped = await client.post("/api/c58/stop", json=active)
        assert stopped.status_code == 202
        response = await running
        assert response.status_code == 200, response.text[:200]
        report = response.json()
        print(json.dumps({key: report[key] for key in ("runId", "check", "costUsd",
                                                   "interrupted", "closed", "exception")}, indent=2))
        assert report["runId"] == active["runId"] and report["check"] == "needs-review"
        assert report["interrupted"] and report["closed"]


if __name__ == "__main__":
    asyncio.run(main())
