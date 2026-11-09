"""Provider-backed Lesson 58 API admission and discovery check."""

import asyncio
import json
import uuid
from pathlib import Path

import httpx

from agent_lab.api import create_app
from agent_lab.config import Settings
from agent_lab.runtime import RunService


async def main() -> None:
    root = Path(".lab-data") / "offline-validation" / f"tool-search-api-{uuid.uuid4()}"
    app = create_app(RunService(Settings(data_dir=root, enable_live=True)), with_ui=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                 base_url="http://lesson58", timeout=110) as client:
        assert (await client.post("/api/c58/run", json={"mode": "live"})).status_code == 403
        response = await client.post("/api/c58/run", json={"mode": "live", "consent": True})
        assert response.status_code == 200, response.text[:300]
        report = response.json()
        print(json.dumps({key: report[key] for key in ("runId", "check", "costUsd", "exception",
                                                   "ledgerSha256")}, indent=2))
        assert report["check"] == "pass"
        assert (await client.post("/api/c58/stop", json={"runId": report["runId"]})).status_code == 404


if __name__ == "__main__":
    asyncio.run(main())
