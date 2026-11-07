"""Lesson 45 strict routes and actual local HTTP effects."""

from pathlib import Path

from fastapi.testclient import TestClient

from agent_lab.api import create_app
from agent_lab.config import Settings
from agent_lab.runtime import RunService


def client(tmp_path: Path) -> TestClient:
    settings = Settings(data_dir=tmp_path / "data", enable_live=False)
    return TestClient(create_app(RunService(settings), with_ui=False))


def test_cloud_routes_local_actions_and_source(tmp_path: Path) -> None:
    with client(tmp_path) as http:
        facts = http.get("/api/c45/facts")
        assert facts.status_code == 200 and len(facts.json()["providers"]) == 5
        sections = http.get("/api/c45/code").json()["sections"]
        assert len(sections) == 3 and all(row["start_line"] < row["end_line"] for row in sections)
        for action in ("catalog", "same", "auth", "models", "failures"):
            response = http.post("/api/c45/" + action, json={"mode": "local"})
            assert response.status_code == 200, response.text[:500]
            data = response.json()
            assert data["experiment_passed"] and data["mode"] == "local"
        state = http.get("/api/c45/state")
        assert state.status_code == 200 and state.json()["action"] == "failures"


def test_cloud_routes_reject_unknown_and_unconsented_live(tmp_path: Path) -> None:
    with client(tmp_path) as http:
        assert http.get("/api/c45/state").status_code == 404
        for body in ({"url": "https://example.com"}, {"mode": "other"},
                     {"auth_case": "custom"}, {"model_case": "private"}):
            assert http.post("/api/c45/same", json=body).status_code == 400
        assert http.post("/api/c45/same", json={"mode": "live"}).status_code == 403
        assert http.post("/api/c45/same", json={"mode": "live", "consent": True}).status_code == 403
        for scenario in ("missing", "foreign", "failed"):
            data = http.post("/api/c45/same", json={"scenario": scenario}).json()
            assert not data["experiment_passed"]
