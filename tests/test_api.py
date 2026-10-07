import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

from agent_lab.api import create_app
from agent_lab.config import Settings
from agent_lab.models import RunRequest
from agent_lab.runtime import BusyError, RunService


@pytest.fixture
def service(tmp_path):
    return RunService(Settings(data_dir=tmp_path))


async def test_api_catalog_validation_sse_and_live_gate(service):
    app = create_app(service, with_ui=False)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:
        assert len((await client.get("/api/lessons")).json()) == 75
        assert (await client.get("/api/lessons/76")).status_code == 404
        assert (await client.post("/api/lessons/1/run", json={"cwd": "outside"})).status_code == 422
        assert (await client.post("/api/lessons/1/run", json={"max_turns": 0})).status_code == 422
        assert (await client.post("/api/lessons/1/run", json={"mode": "live"})).status_code == 403
        response = await client.post("/api/lessons/5/stream", json={})
        assert response.status_code == 200
        assert "event: evidence" in response.text
        assert '"sum":42.0' in response.text
        assert response.text.count("event: done") == 1
        assert not service.active


def test_websocket_protocol_and_validation(service):
    with TestClient(create_app(service, with_ui=False)) as client:
        with client.websocket_connect("/api/lessons/66/ws") as socket:
            socket.send_json({"mode": "offline"})
            events = []
            while True:
                event = socket.receive_json()
                events.append(event)
                if event["kind"] == "done":
                    break
            assert events[-1]["data"]["status"] == "completed"


async def test_slot_limit_and_cancellation_await_cleanup(tmp_path, monkeypatch):
    import agent_lab.runtime

    started, cleaned = asyncio.Event(), asyncio.Event()

    async def blocking(*args):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleaned.set()

    monkeypatch.setattr(agent_lab.runtime, "run_exercise", blocking)
    service = RunService(Settings(data_dir=tmp_path, max_concurrent_runs=1))
    handle = service.start(1, RunRequest())
    await started.wait()
    with pytest.raises(BusyError):
        service.start(2, RunRequest())
    await service.cancel(handle)
    assert cleaned.is_set()
    assert not service.active
    events = [event async for event in service.events(handle)]
    assert events[-1].data["status"] == "cancelled"


async def test_document_download_does_not_allow_arbitrary_paths(service):
    app = create_app(service, with_ui=False)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:
        result = (await client.post("/api/lessons/72/run", json={})).json()
        run_id = result["run_id"]
        download = await client.get(f"/api/runs/{run_id}/artifacts/incident-report.docx")
        assert download.content.startswith(b"PK")
        assert (await client.get(f"/api/runs/{run_id}/artifacts/.env")).status_code == 404
