"""Strict Lesson 57 HTTP contracts and persisted report recovery."""

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from agent_lab import api_worktrees
from agent_lab.api import create_app
from agent_lab.config import Settings
from agent_lab.runtime import RunService


@pytest.mark.asyncio
async def test_worktree_routes(tmp_path: Path) -> None:
    app = create_app(RunService(Settings(data_dir=tmp_path, enable_live=False)), with_ui=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                 base_url="http://worktrees") as client:
        assert (await client.get("/api/c57/code")).status_code == 200
        assert len((await client.get("/api/c57/code")).json()) == 3
        assert (await client.post("/api/c57/run", json={"path": "bad"})).status_code == 400
        assert (await client.post("/api/c57/run", json={"mode": "live"})).status_code == 403
        response = await client.post("/api/c57/run", json={"scenario": "independent"})
        assert response.status_code == 200
        frames = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
        report = next(row["report"] for row in frames if row["kind"] == "result")
        assert report["check"] == "passed" and report["worktreeCount"] == 1
        recovered = await client.get(f"/api/c57/runs/{report['runId']}")
        assert recovered.status_code == 200 and recovered.headers["cache-control"] == "no-store"
        assert recovered.json()["report"] == report
        assert (await client.get("/api/c57/runs/not-a-uuid")).status_code == 400
        assert (await client.post("/api/c57/stop", json={"runId": report["runId"]})).status_code == 404


@pytest.mark.asyncio
async def test_active_conflict_stop_and_retained_partial(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    actual = api_worktrees.run_workshop
    entered = asyncio.Event()

    async def stall(_name: str, _path: Path, _item: dict[str, str]) -> None:
        entered.set()
        await asyncio.sleep(20)

    async def slowed(*args, **kwargs):
        return await actual(*args, **kwargs, prepared_hook=stall)

    monkeypatch.setattr(api_worktrees, "run_workshop", slowed)
    app = create_app(RunService(Settings(data_dir=tmp_path, enable_live=False)), with_ui=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                 base_url="http://worktrees", timeout=40) as client:
        first = asyncio.create_task(client.post("/api/c57/run", json={}))
        await asyncio.wait_for(entered.wait(), 10)
        active = await client.get("/api/c57/active")
        assert active.status_code == 200
        run_id = active.json()["runId"]
        assert (await client.post("/api/c57/run", json={})).status_code == 409
        assert (await client.post("/api/c57/stop", json={"runId": run_id})).status_code == 202
        response = await asyncio.wait_for(first, 10)
        assert response.status_code == 200
        recovered = await client.get(f"/api/c57/runs/{run_id}")
        assert recovered.status_code == 200
        report = recovered.json()["report"]
        assert report["interrupted"] and report["check"] == "needs-review"
        assert (await client.get("/api/c57/active")).status_code == 404
