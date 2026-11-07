"""Lesson 48 route validation, state integrity and active-run exclusion."""

import asyncio

import httpx
import pytest

from agent_lab.api import create_app
from agent_lab.config import Settings
from agent_lab.runtime import RunService


@pytest.mark.asyncio
async def test_hardening_routes_validate_and_save(tmp_path) -> None:
    app = create_app(RunService(Settings(data_dir=tmp_path)))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        facts = await client.get("/api/c48/facts")
        assert facts.status_code == 200
        assert facts.json()["actions"] == ["permissions", "lockdown", "secrets", "injection"]
        assert (await client.get("/api/c48/state")).json() is None
        assert len((await client.get("/api/c48/code")).json()) == 3
        for action in facts.json()["actions"]:
            response = await client.post("/api/c48/" + action, json={})
            assert response.status_code == 200, response.text
            assert response.json()["experiment_passed"]
            assert response.json()["native"] is False
        assert (await client.get("/api/c48/state")).json()["action"] == "injection"
        for invalid in ({"limit": 3}, {"extra": True}, {"mode": "other"}, []):
            assert (await client.post("/api/c48/permissions", json=invalid)).status_code == 400
        assert (await client.post("/api/c48/permissions", json={"mode": "live"})).status_code == 403
        failed = await client.post("/api/c48/permissions", json={"scenario": "leaked"})
        assert failed.status_code == 200 and not failed.json()["experiment_passed"]
        assert (await client.get("/api/c48/state")).json()["action"] == "injection"
        (tmp_path / "lesson-48" / "latest.json").write_bytes(b"x" * 4097)
        assert (await client.get("/api/c48/state")).status_code == 409


@pytest.mark.asyncio
async def test_hardening_busy_reservation_blocks_overlap_and_state(tmp_path, monkeypatch) -> None:
    from agent_lab import api_hardening

    entered, release = asyncio.Event(), asyncio.Event()
    original = api_hardening.local_action

    async def slow(*args, **kwargs):
        entered.set()
        await release.wait()
        return await original(*args, **kwargs)

    monkeypatch.setattr(api_hardening, "local_action", slow)
    app = create_app(RunService(Settings(data_dir=tmp_path)))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        first = asyncio.create_task(client.post("/api/c48/permissions", json={}))
        await entered.wait()
        assert (await client.get("/api/c48/state")).status_code == 409
        assert (await client.post("/api/c48/lockdown", json={})).status_code == 409
        release.set()
        assert (await first).status_code == 200
