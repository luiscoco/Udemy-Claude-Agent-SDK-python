"""Lesson 55 HTTP routes keep inspection, assessment and simulation separate."""

import httpx
import pytest

from agent_lab.api import create_app
from agent_lab.config import Settings
from agent_lab.runtime import RunService


@pytest.mark.asyncio
async def test_upgrading_routes_and_strict_statuses(tmp_path) -> None:
    app = create_app(RunService(Settings(data_dir=tmp_path)), with_ui=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        facts = (await client.get("/api/c55/facts")).json()
        assert facts["mode"] == "offline" and facts["modelCalls"] == 0
        assert facts["inventory"]["consistent"]
        assert len(facts["scenarios"]) == 9
        assert len((await client.get("/api/c55/code")).json()) == 3
        for scenario in facts["scenarios"]:
            response = await client.post("/api/c55/run", json={"scenario": scenario})
            assert response.status_code == 200
            payload = response.json()
            assert payload["check"] == "passed"
            assert payload["report"]["eligible"] is (scenario == "compatible")
        for body in ({"scenario": "unknown"}, {"scenario": "compatible", "live": True},
                     {"scenario": "compatible", "version": "9.9.9"}):
            assert (await client.post("/api/c55/run", json=body)).status_code == 400
        assert (await client.post("/api/c55/transition", json={"scenario": "compatible", "state": "baseline", "action": "promote"})).status_code == 409
        assert (await client.post("/api/c55/transition", json={"scenario": "removed-export", "state": "checked", "action": "start-canary"})).status_code == 409
        canary = await client.post("/api/c55/transition", json={"scenario": "compatible", "state": "checked", "action": "start-canary"})
        assert canary.status_code == 200 and canary.json()["newState"] == "canary"
        assert (await client.post("/api/c55/transition", json={"scenario": "compatible", "state": "canary", "action": "promote"})).json()["newState"] == "promoted"
        assert (await client.post("/api/c55/transition", json={"scenario": "compatible", "state": "promoted", "action": "rollback"})).json()["newState"] == "rolled-back"
