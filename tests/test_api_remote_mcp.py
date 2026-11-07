"""Strict lesson 43 action routes."""

import asyncio

import httpx

from agent_lab.api import create_app
from agent_lab.config import Settings
from agent_lab.runtime import RunService


async def test_remote_routes_and_consent(tmp_path):
    app = create_app(RunService(Settings(data_dir=tmp_path)), with_ui=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/api/c43/facts")).status_code == 200
        assert (await client.get("/api/c43/state")).status_code == 404
        assert (await client.post("/api/c43/auth", json={"token": "not-allowed"})).status_code == 400
        assert (await client.post("/api/c43/auth", json={"transport": "sse"})).status_code == 400
        assert (await client.post("/api/c43/auth", json={"mode": "live", "consent": True})).status_code == 403
        assert (await client.post("/api/c43/resources", json={"resource": "incident"})).status_code == 400
        assert (await client.post("/api/c43/reconnect", json={})).status_code == 404
        assert (await client.post("/api/c43/live", json={"mode": "live"})).status_code == 403
        assert (await client.post("/api/c43/live", json={"mode": "live", "consent": True,
                                                          "scenario": "foreign"})).status_code == 400
        assert (await client.post("/api/c43/live", json={"mode": "live", "consent": True,
                                                          "step": "rotate"})).status_code == 403
        for path in ("auth", "cache", "transports", "toolsets", "resources", "host-read"):
            response = await client.post("/api/c43/" + path, json={})
            assert response.status_code == 200, response.text
            assert response.json()["experiment_passed"], path
            assert response.json()["mode"] == "local"
        for step in ("tool", "resource", "rotate"):
            response = await client.post("/api/c43/live", json={"step": step})
            assert response.status_code == 200, response.text
            assert response.json()["agent_executed"] is False
            assert response.json()["experiment_passed"]
        for scenario in ("missing", "foreign", "failed"):
            response = await client.post("/api/c43/live", json={"scenario": scenario})
            assert response.status_code == 200
            assert not response.json()["experiment_passed"]
            assert response.json()["probe"]["status_payload"] or scenario == "failed"
        code = await client.get("/api/c43/code")
        assert code.status_code == 200 and len(code.json()["sections"]) == 3
        assert (await client.get("/api/c43/state")).json()["action"] == "rotation"


async def test_remote_operation_slot_blocks_overlap_and_state(tmp_path, monkeypatch):
    import agent_lab.api_remote_mcp as routes

    entered, release = asyncio.Event(), asyncio.Event()

    async def slow_run(*args, **kwargs):
        entered.set()
        await release.wait()
        return {"experiment_passed": True}

    monkeypatch.setattr(routes, "run", slow_run)
    app = create_app(RunService(Settings(data_dir=tmp_path)), with_ui=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        first = asyncio.create_task(client.post("/api/c43/auth", json={}))
        await asyncio.wait_for(entered.wait(), 3)
        assert (await client.get("/api/c43/state")).status_code == 409
        assert (await client.post("/api/c43/cache", json={})).status_code == 409
        release.set()
        assert (await first).status_code == 200
