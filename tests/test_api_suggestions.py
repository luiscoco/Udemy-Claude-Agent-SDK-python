"""Lesson 38 interactive route and ownership checks."""

import asyncio

import httpx

from agent_lab.api import create_app


async def test_chat_queue_ownership_and_closure() -> None:
    app = create_app(with_ui=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        assert (await client.post("/api/c38/dry", json={})).json()["options_only"]
        assert (await client.post("/api/c38/chat", json={"mode": "live"})).status_code == 403
        assert (await client.post("/api/c38/when", json={})).json()["metadata_only"]
        assert (await client.post("/api/c38/switches", json={})).json()["metadata_only"]
        assert (await client.post("/api/c38/cache", json={})).json()["metadata_only"]
        selected = (await client.post("/api/c38/when", json={"mode": "offline", "variant": "enabled"})).json()
        assert selected["experiment"]["experiment_passed"]
        assert len((await client.get("/api/c38/code")).json()["sections"]) == 3
        started = (await client.post("/api/c38/chat", json={})).json()
        key = {"run_id": started["run_id"], "control_token": started["control_token"]}
        assert (await client.post("/api/c38/chat", json={})).status_code == 409
        assert (await client.post("/api/c38/send", json={**key, "text": " "})).status_code == 409
        assert (await client.post("/api/c38/send", json={**key, "text": "first", "extra": 1})).status_code == 422
        wrong = {**key, "control_token": "invalid-token-000000"}
        assert (await client.post("/api/c38/send", json={**wrong, "text": "first"})).status_code == 403
        for prompt in ("first", "second"):
            sent = (await client.post("/api/c38/send", json={**key, "text": prompt})).json()
            assert sent["submitted"]["text"] == prompt
        await asyncio.sleep(0.05)
        report = (await client.post("/api/c38/end", json=key)).json()
        assert report["experiment_passed"]
        assert len(report["inputs"]) == len(report["results"]) == 2
        assert report["normal_end"] and report["connection_closed"]
        assert (await client.post("/api/c38/status", json=key)).json()["experiment_passed"]
        assert (await client.post("/api/c38/send", json={**key, "text": "after"})).status_code == 403
