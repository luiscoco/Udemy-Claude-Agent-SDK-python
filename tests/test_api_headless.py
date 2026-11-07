"""Lesson 49 strict routes, saved state and action exclusion."""

import asyncio

import httpx
import pytest

from agent_lab.api import create_app
from agent_lab.config import Settings
from agent_lab.runtime import RunService


@pytest.mark.asyncio
async def test_headless_routes_and_latest_summary(tmp_path) -> None:
    app = create_app(RunService(Settings(data_dir=tmp_path)))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/api/c49/facts")).json()["actions"] == ["headless", "ci", "limits", "deploy"]
        assert len((await client.get("/api/c49/files")).json()) == 7
        assert len((await client.get("/api/c49/code")).json()) == 3
        assert (await client.get("/api/c49/state")).json() is None
        for action in ("headless", "ci", "limits", "deploy"):
            response = await client.post("/api/c49/" + action, json={})
            assert response.status_code == 200 and response.json()["experiment_passed"]
        assert (await client.get("/api/c49/state")).json()["action"] == "deploy"
        for invalid in ({"path": "../../.env"}, {"mode": "other"}, {"extra": 1}, []):
            assert (await client.post("/api/c49/headless", json=invalid)).status_code == 400
        for action in ("headless", "ci", "limits", "deploy"):
            assert (await client.post("/api/c49/" + action, json={"mode": "live"})).status_code == 403
        failed = await client.post("/api/c49/headless", json={"scenario": "foreign"})
        assert failed.status_code == 200 and not failed.json()["experiment_passed"]
        assert (await client.get("/api/c49/state")).json()["action"] == "deploy"
        (tmp_path / "lesson-49" / "latest.json").write_bytes(b"x" * 4097)
        assert (await client.get("/api/c49/state")).status_code == 409


@pytest.mark.asyncio
async def test_headless_busy_state_is_409(tmp_path, monkeypatch) -> None:
    from agent_lab import api_headless

    entered, release = asyncio.Event(), asyncio.Event()
    original = api_headless.local_action

    async def slow(*args, **kwargs):
        entered.set()
        await release.wait()
        return await original(*args, **kwargs)

    monkeypatch.setattr(api_headless, "local_action", slow)
    app = create_app(RunService(Settings(data_dir=tmp_path)))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        first = asyncio.create_task(client.post("/api/c49/headless", json={}))
        await entered.wait()
        assert (await client.get("/api/c49/state")).status_code == 409
        assert (await client.post("/api/c49/ci", json={})).status_code == 409
        release.set()
        assert (await first).status_code == 200
