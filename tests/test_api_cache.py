"""Lesson 46 local routes keep inspection free and options strict."""

from fastapi.testclient import TestClient

from agent_lab.api import create_app
from agent_lab.config import Settings
from agent_lab.runtime import RunService


def test_cache_routes_local_and_negative(tmp_path) -> None:
    app = create_app(RunService(Settings(data_dir=tmp_path, enable_live=False)), with_ui=False)
    with TestClient(app) as client:
        facts = client.get("/api/c46/facts")
        assert facts.status_code == 200
        assert "no guaranteed cache saving" in facts.json()["criterion"]
        assert client.get("/api/c46/state").json() is None
        code = client.get("/api/c46/code").json()
        assert len(code) == 3
        assert code == client.get("/api/c46/source").json()
        assert client.post("/api/c46/anatomy", json={"unknown": True}).status_code == 400
        assert client.post("/api/c46/anatomy", json=[]).status_code == 400
        assert client.post("/api/c46/anatomy", json={"mode": "live", "consent": True}).status_code == 403
        passed = client.post("/api/c46/anatomy", json={}).json()
        assert passed["experiment_passed"] is True
        assert len(passed["turns"]) == 2
        assert client.get("/api/c46/state").json()["operation"] == passed["operation"]
        failed = client.post("/api/c46/breakers", json={"scenario": "foreign"}).json()
        assert failed["experiment_passed"] is False
        assert client.get("/api/c46/state").json()["operation"] == passed["operation"]
