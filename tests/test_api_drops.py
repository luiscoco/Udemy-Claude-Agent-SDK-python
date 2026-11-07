"""Lesson 40 strict routes, persisted state and separate single-undo action."""

from pathlib import Path

import httpx

from agent_lab.api import create_app
from agent_lab.config import Settings
from agent_lab.runtime import RunService


async def test_drops_routes_and_mode_ownership(tmp_path: Path) -> None:
    app = create_app(RunService(Settings(data_dir=tmp_path)), with_ui=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        assert (await client.post("/api/c40/dry", json={"path": "elsewhere"})).status_code == 422
        assert (await client.post("/api/c40/dry", json={})).json()["all_serialized"]
        assert (await client.get("/api/c40/state")).status_code == 404
        assert len((await client.get("/api/c40/code")).json()["sections"]) == 3
        assert (await client.post("/api/c40/build", json={"mode": "live"})).status_code == 403
        built = (await client.post("/api/c40/build", json={})).json()
        assert built["build_passed"]
        key = built["build_id"]
        assert (await client.get("/api/c40/state")).json()["manifest"]["build_id"] == key
        assert (await client.get("/api/c40/state", params={"build_id": key})).status_code == 200
        assert (await client.post("/api/c40/cases", json={"build_id": "../elsewhere"})).status_code == 422
        assert (await client.post("/api/c40/cases", json={"build_id": key, "mode": "live"})).status_code == 403
        report = (await client.post("/api/c40/cases", json={"build_id": key, "recover": True})).json()
        assert report["experiment_passed"]
        undo = (await client.post("/api/c40/undo", json={"build_id": key, "turn": 4})).json()
        assert undo["full_comparison_claimed"] is False
        negative = (await client.post("/api/c40/cases", json={"build_id": key, "scenario": "missing"})).json()
        assert not negative["experiment_passed"]
