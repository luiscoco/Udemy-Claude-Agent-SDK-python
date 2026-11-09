"""Lesson 56 HTTP admission and request-local replay."""

import httpx
import pytest

from agent_lab.api import create_app
from agent_lab.config import Settings
from agent_lab.runtime import RunService


@pytest.mark.asyncio
async def test_team_replay_routes_and_live_guard(tmp_path) -> None:
    app = create_app(RunService(Settings(data_dir=tmp_path, enable_live=False)), with_ui=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        facts = (await client.get("/api/c56/facts")).json()
        assert len(facts["walkthrough"]) == 16
        assert len((await client.get("/api/c56/code")).json()) == 3
        assert facts["maxCommands"] == 100 and facts["maxMessages"] == 20
        report = (await client.post("/api/c56/replay", json={"commands": facts["walkthrough"]})).json()
        assert report["check"] == "passed"
        assert report["report"]["state"]["closed"]
        assert (await client.post("/api/c56/replay", json={"commands": []})).json()["check"] == "needs-review"
        for body in ({"commands": [{"type": "exec"}]}, {"commands": [], "mode": "live"}):
            assert (await client.post("/api/c56/replay", json=body)).status_code == 400
        assert (await client.post("/api/c56/live", json={"consent": True, "tools": ["Bash"]})).status_code == 400
        assert (await client.post("/api/c56/live", json={"consent": True})).status_code == 403
