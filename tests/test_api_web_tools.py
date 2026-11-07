"""Strict lesson 42 web action routes."""

import httpx

from agent_lab.api import create_app
from agent_lab.config import Settings
from agent_lab.runtime import RunService


async def test_web_routes_prepared_and_live_consent(tmp_path) -> None:
    app = create_app(RunService(Settings(data_dir=tmp_path)))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/api/c42/facts")).status_code == 200
        assert (await client.post("/api/c42/fetch-lab", json={"url": "https://example.com"})).status_code == 422
        assert (await client.post("/api/c42/basics", json={"mode": "live"})).status_code == 403
        for action in ("basics", "fetch-lab", "injection", "guard", "research"):
            response = await client.post("/api/c42/" + action, json={})
            assert response.status_code == 200, response.text
            assert response.json()["experiment_passed"], action
        missing = await client.post("/api/c42/fetch-lab", json={"page": "missing"})
        assert not missing.json()["experiment_passed"]
        saved = await client.get("/api/c42/state")
        assert saved.status_code == 200 and saved.json()["action"] == "research"
        code = await client.get("/api/c42/code")
        assert code.status_code == 200 and len(code.json()["sections"]) == 3
