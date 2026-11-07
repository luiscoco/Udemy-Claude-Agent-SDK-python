"""Lesson 36 scoped dry and observed process routes."""

import httpx

from agent_lab.api import create_app


async def test_process_routes() -> None:
    app = create_app(with_ui=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        dry = (await client.post("/api/c36/dry", json={"location": "machine-b"})).json()
        assert dry["dry_run"] and not dry["launched"] and not dry["sdk_called"]
        assert (await client.post("/api/c36/run", json={"mode": "live"})).status_code == 403
        assert (await client.post("/api/c36/run", json={"lesson_options": {"location": "remote"}})).status_code == 422
        run = (await client.post("/api/c36/run", json={"lesson_options": {"location": "machine-b"}})).json()
        assert run["status"] == "completed"
        assert run["experiment"]["experiment_passed"]
        key = {"run_id": run["run_id"], "control_token": run["control_token"]}
        assert (await client.get("/api/c36/state", params={**key, "control_token": "invalid-token-000000"})).status_code == 403
        assert (await client.get("/api/c36/state", params=key)).json()["host_success"]
        assert (await client.get("/api/c36/alias", params=key)).json()["remote"] is False
        assert len((await client.get("/api/c36/debug", params=key)).json()["frames"]) == 3
        assert (await client.post("/api/c36/failures", json=key)).json()["child_cleaned"]
        assert len((await client.get("/api/c36/code")).json()["sections"]) == 3
        assert (await client.post("/api/c36/reset", json=key)).json() == {"reset": True}
        assert (await client.get("/api/c36/state", params=key)).status_code == 403
