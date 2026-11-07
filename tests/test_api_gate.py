"""Lesson 37 route ownership and prepared gate observations."""

import asyncio

import httpx

from agent_lab.api import create_app


async def test_gate_routes() -> None:
    app = create_app(with_ui=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        dry = (await client.post("/api/c37/dry", json={"action": "edit"})).json()
        assert dry["dry_run"] and not dry["launched"] and not dry["sdk_called"]
        assert (await client.post("/api/c37/run", json={"mode": "live"})).status_code == 403
        assert (await client.post("/api/c37/run", json={"lesson_options": {"action": "arbitrary"}})).status_code == 422
        result = (await client.post("/api/c37/run", json={"lesson_options": {"action": "edit"}})).json()
        assert result["status"] == "completed"
        assert result["experiment"]["experiment_passed"]
        key = {"run_id": result["run_id"], "control_token": result["control_token"]}
        assert (await client.post("/api/c37/gate-log", json={**key, "control_token": "invalid-token-000000"})).status_code == 403
        log = (await client.post("/api/c37/gate-log", json=key)).json()
        assert len(log["process_receipts"]) == 1
        assert (await client.post("/api/c37/who", json=key)).json()["run_id"] == key["run_id"]
        assert (await client.post("/api/c37/answers", json=key)).json()["file_inventory"]["edited"] == "GATE_EDITED_37"
        assert (await client.post("/api/c37/failures", json=key)).json()["file_effect_verified"]
        assert (await client.post("/api/c37/decide", json={**key, "gate_id": log["gate_decisions"][0]["gate_id"], "action": "allow"})).status_code == 409
        assert (await client.post("/api/c37/decide", json={**key, "gate_id": "other", "action": "allow"})).status_code == 409
        assert len((await client.get("/api/c37/code")).json()["sections"]) == 3


async def test_manual_gate_rejects_wrong_identity_then_accepts_once() -> None:
    app = create_app(with_ui=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        started = (await client.post("/api/c37/run", json={"lesson_options": {"action": "manual"}})).json()
        assert started["status"] == "running"
        key = {"run_id": started["run_id"], "control_token": started["control_token"]}
        pending = None
        for _ in range(100):
            pending = (await client.post("/api/c37/gate-log", json=key)).json().get("pending")
            if pending:
                break
            await asyncio.sleep(0.05)
        assert pending and pending["tool_name"] == "Write"
        wrong = {**key, "gate_id": "other", "action": "edit"}
        assert (await client.post("/api/c37/decide", json=wrong)).status_code == 409
        decision = {**key, "gate_id": pending["gate_id"], "action": "edit"}
        assert (await client.post("/api/c37/decide", json=decision)).json()["accepted"]
        assert (await client.post("/api/c37/decide", json=decision)).status_code == 409
        for _ in range(100):
            response = await client.post("/api/c37/answers", json=key)
            if response.status_code == 200:
                break
            await asyncio.sleep(0.05)
        assert response.status_code == 200
        assert response.json()["experiment_passed"]
        assert response.json()["file_inventory"]["edited"] == "GATE_EDITED_37"
