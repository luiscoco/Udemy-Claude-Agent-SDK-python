"""Strict lesson 41 HTTP actions."""

import httpx

from agent_lab.api import create_app
from agent_lab.config import Settings
from agent_lab.runtime import RunService


async def test_client_lifecycle_routes_and_fresh_live_consent(tmp_path) -> None:
    app = create_app(RunService(Settings(data_dir=tmp_path)))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        facts = await client.get("/api/c41/facts")
        assert facts.status_code == 200
        assert "Python" in facts.json()["migration_note"]
        assert (await client.post("/api/c41/client", json={"unexpected": 1})).status_code == 422
        assert (await client.post("/api/c41/client", json={"mode": "live"})).status_code == 403
        built = await client.post("/api/c41/client", json={})
        assert built.status_code == 200 and built.json()["experiment_passed"]
        build_id = built.json()["build_id"]
        saved = await client.get("/api/c41/state")
        assert saved.json()["build_id"] == build_id
        assert (await client.post("/api/c41/resume", json={"build_id": build_id, "mode": "live"})).status_code == 403
        followed = await client.post("/api/c41/resume", json={"build_id": build_id})
        assert followed.status_code == 200 and followed.json()["experiment_passed"]
        failed = await client.post("/api/c41/resume", json={"build_id": build_id, "scenario": "foreign"})
        assert failed.status_code == 200 and not failed.json()["experiment_passed"]
        compared = await client.post("/api/c41/compare", json={})
        assert compared.status_code == 200 and compared.json()["experiment_passed"]
        code = await client.get("/api/c41/code")
        assert code.status_code == 200 and len(code.json()["sections"]) == 3
