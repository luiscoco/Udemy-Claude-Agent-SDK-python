"""Lesson 52 strict local API and zero-call free actions."""

import uuid

import httpx
import pytest

from agent_lab.api import create_app
from agent_lab.config import Settings
from agent_lab.runtime import RunService


@pytest.mark.asyncio
async def test_evals_routes_free_report_calibration_promotion_and_negative(tmp_path):
    app = create_app(RunService(Settings(data_dir=tmp_path, enable_live=False)), with_ui=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://evals") as client:
        facts = (await client.get("/api/c52/facts")).json()
        assert len(facts["cases"]) == 3 and facts["liveEnabled"] is False
        code = (await client.get("/api/c52/code")).json()
        assert len(code) == 3 and all(row["code"] for row in code)
        assert (await client.get("/api/c52/baseline")).json()["report"] is not None
        assert (await client.get("/api/c52/baseline?mode=live&judge=model")).json()["report"] is None
        assert (await client.get("/api/c52/baseline?path=foreign")).status_code == 400
        for invalid in ({"mode": "synthetic", "judge": "model"}, {"url": "https://example.org"},
                        {"trials": 0}, {"variant": "foreign"}):
            assert (await client.post("/api/c52/demo", json=invalid)).status_code == 400
        assert (await client.post("/api/c52/demo", content='{"budget": 1e999}',
                                  headers={"content-type": "application/json"})).status_code == 400
        demo = (await client.post("/api/c52/demo", json={})).json()
        assert demo["experiment_passed"] and demo["modelCalls"] == 0
        assert demo["comparison"]["status"] == "pass" and len(demo["candidate"]["rows"]) == 9
        calibration = (await client.post("/api/c52/calibrate", json={})).json()
        assert calibration["summary"]["decisions"] == 40
        assert (await client.post("/api/c52/calibrate", json={"judge": "model"})).status_code == 400
        baseline = (await client.post("/api/c52/run", json={})).json()
        cold = (await client.post("/api/c52/run", json={"variant": "cold-tone"})).json()
        assert baseline["experiment_passed"] and cold["comparison"]["status"] == "fail"
        assert (await client.post("/api/c52/run", json={"mode": "live", "consent": False})).status_code == 403
        assert (await client.post("/api/c52/run", json={"mode": "live", "consent": True})).status_code == 403
        run_id = baseline["candidate"]["id"]
        digest = baseline["review"]["reviewHash"]
        missing = {"runId": str(uuid.uuid4()), "expectedHash": digest, "confirm": True, "note": "Reviewed trial set"}
        assert (await client.post("/api/c52/promote", json=missing)).status_code == 404
        assert (await client.post("/api/c52/promote", json={**missing, "runId": cold["candidate"]["id"]})).status_code == 409
        assert (await client.post("/api/c52/promote", json={**missing, "runId": run_id, "expectedHash": "0" * 64})).status_code == 409
        promoted = (await client.post("/api/c52/promote", json={**missing, "runId": run_id})).json()
        assert promoted["promoted"] and (await client.get("/api/c52/baseline")).json()["report"]["id"] == run_id
        pair = (await client.post("/api/c52/pairwise", json={"left": run_id,
                            "right": cold["candidate"]["id"], "caseId": "orders"})).json()
        assert pair["ab"]["winner"] == "A" and pair["ba"]["winner"] == "B"
        assert (await client.post("/api/c52/pairwise", json={"left": str(uuid.uuid4()),
                            "right": run_id, "caseId": "orders"})).status_code == 404
        assert (await client.post("/api/c52/stop", json={"runId": str(uuid.uuid4())})).status_code == 409
