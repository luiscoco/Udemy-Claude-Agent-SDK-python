"""Lesson 53 strict route, saved recovery and free SSE behavior."""

import asyncio
import json
import uuid

import httpx
import pytest

from agent_lab.api import create_app
from agent_lab.config import Settings
from agent_lab.runtime import RunService


def frames(response: httpx.Response) -> list[dict]:
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]


@pytest.mark.asyncio
async def test_debug_routes_strict_free_saved_and_comparison(tmp_path):
    app = create_app(RunService(Settings(data_dir=tmp_path, enable_live=False)), with_ui=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://debug") as client:
        facts = (await client.get("/api/c53/facts")).json()
        assert len(facts["scenarios"]) == 7 and facts["liveEnabled"] is False
        assert len((await client.get("/api/c53/code")).json()) == 3
        for body in ({"path": "../.env"}, {"scenario": "foreign"}, {"maxTurns": 0}):
            assert (await client.post("/api/c53/run", json=body)).status_code == 400
        assert (await client.post("/api/c53/run", content='{"budget": 1e999}',
                                  headers={"content-type": "application/json"})).status_code == 400
        assert (await client.post("/api/c53/run", json={"mode": "live", "consent": True})).status_code == 403
        assert (await client.post("/api/c53/run", json={"compareId": str(uuid.uuid4())})).status_code == 404
        assert (await client.get("/api/c53/runs/not-a-uuid")).status_code == 400
        assert (await client.get(f"/api/c53/runs/{uuid.uuid4()}")).status_code == 404

        first = frames(await client.post("/api/c53/run", json={"scenario": "denied"}))
        assert first[0]["kind"] == "start" and first[-1]["kind"] == "done"
        assert first[-1]["saved"] is True
        bundle = next(row for row in first if row["kind"] == "bundle")
        assert bundle["check"] == "passed"
        run_id = first[0]["runId"]
        recovered = (await client.get(f"/api/c53/runs/{run_id}")).json()
        assert recovered == bundle["loaded"]
        assert recovered["bundle"]["findings"][0]["code"] == "permission-denied"
        second = frames(await client.post("/api/c53/run", json={"scenario": "success",
                                                                 "compareId": run_id}))
        current = next(row for row in second if row["kind"] == "bundle")["loaded"]["bundle"]
        assert current["comparison"]["oneVariable"] and current["comparison"]["changed"] == ["policy"]
        assert (await client.post("/api/c53/stop", json={"runId": run_id})).status_code == 409


@pytest.mark.asyncio
async def test_debug_overlap_and_stop_retains_partial(tmp_path):
    app = create_app(RunService(Settings(data_dir=tmp_path, enable_live=False)), with_ui=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://debug") as client:
        pending = asyncio.create_task(client.post("/api/c53/run", json={"scenario": "success"}))
        active = None
        for _ in range(100):
            observed = await client.get("/api/c53/active")
            if observed.status_code == 200:
                active = observed.json()["runId"]
                break
            await asyncio.sleep(0.001)
        assert active is not None
        assert (await client.post("/api/c53/run", json={})).status_code == 409
        assert (await client.post("/api/c53/stop", json={"runId": active})).status_code == 200
        result = frames(await pending)
        assert result[-1]["kind"] == "done" and result[-1]["saved"]
        recovered = (await client.get(f"/api/c53/runs/{active}")).json()["bundle"]
        assert recovered["interrupted"] and recovered["closed"]
        assert (await client.get("/api/c53/active")).status_code == 404
