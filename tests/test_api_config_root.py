"""Strict lesson 39 origin, takeover, dry and startup routes."""

from pathlib import Path

import httpx

from agent_lab.api import create_app
from agent_lab.config import Settings
from agent_lab.runtime import RunService


async def test_config_root_routes(tmp_path: Path) -> None:
    app = create_app(RunService(Settings(data_dir=tmp_path)), with_ui=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        assert (await client.post("/api/c39/dry", json={"path": "../outside"})).status_code == 422
        dry = (await client.post("/api/c39/dry", json={})).json()
        assert dry["all_serialized"] and not dry["sdk_called"]
        assert len((await client.get("/api/c39/code")).json()["sections"]) == 3
        assert (await client.post("/api/c39/where", json={"mode": "live"})).status_code == 403
        assert (await client.post("/api/c39/where", json={"root": "../outside"})).status_code == 422
        where = (await client.post("/api/c39/where", json={})).json()
        assert where["experiment"]["experiment_passed"]
        takeover = (await client.post("/api/c39/takeover", json={"root": "omitted"})).json()
        assert takeover["experiment"]["experiment_passed"]
        bad = (await client.post("/api/c39/try", json={"mode": "startup", "root": "trusted"}))
        assert bad.status_code == 422
        probe = (await client.post("/api/c39/try", json={"mode": "startup", "root": "relative"})).json()
        assert probe["startup"]["startup_failure_observed"]
