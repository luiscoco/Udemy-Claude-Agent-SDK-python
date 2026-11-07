"""Lesson 51 HTTP streaming and strict admission remain entirely local."""

import asyncio
import json

import httpx
import pytest

from agent_lab.api import create_app
from agent_lab.config import Settings
from agent_lab.runtime import RunService


def events(response: httpx.Response) -> list[dict]:
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]


@pytest.mark.asyncio
async def test_offline_http_suite_replays_and_strict_inputs(tmp_path) -> None:
    app = create_app(RunService(Settings(data_dir=tmp_path, enable_live=True)), with_ui=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                 base_url="http://test") as client:
        facts = (await client.get("/api/c51/facts")).json()
        assert facts["live_enabled"] is False and facts["modelCalls"] == 0
        assert len(facts["cases"]) == 16
        assert len((await client.get("/api/c51/code")).json()) == 3
        for bad in ({"live": True}, {"group": "bad"}, {"url": "https://invalid.example"}):
            assert (await client.post("/api/c51/run", json=bad)).status_code == 400
        assert (await client.post("/api/c51/replay", json={"scenario": "foreign-result"})).status_code == 400
        suite = events(await client.post("/api/c51/run", json={}))
        report = suite[-1]["report"]
        assert suite[0]["kind"] == "started" and suite[-1]["kind"] == "complete"
        assert len([row for row in suite if row["kind"] == "assertion"]) == 16
        assert report["experiment_passed"] and report["summary"]["passed"] == 16
        assert report["modelCalls"] == report["actualBilledUsd"] == 0
        filtered = events(await client.post("/api/c51/run", json={"group": "store"}))[-1]["report"]
        assert filtered["summary"]["total"] == 2 and not filtered["experiment_passed"]
        mutated = events(await client.post("/api/c51/run", json={"mutation": True}))[-1]["report"]
        assert mutated["summary"]["failed"] == 1 and not mutated["experiment_passed"]
        for scenario, expected in (("success", "success"), ("budget", "budget"),
                                   ("api-error", "api-error"), ("invalid", "invalid"),
                                   ("truncated", "truncated"),
                                   ("malformed-tool", "invalid-tool")):
            stream = events(await client.post("/api/c51/replay", json={"scenario": scenario}))
            assert stream[-1]["report"]["status"] == expected
            assert stream[-1]["report"]["actualBilledUsd"] == 0
            assert not stream[-1]["report"]["experiment_passed"]


@pytest.mark.asyncio
async def test_offline_http_overlap_and_stop(tmp_path) -> None:
    app = create_app(RunService(Settings(data_dir=tmp_path)), with_ui=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                 base_url="http://test") as client:
        task = asyncio.create_task(client.post("/api/c51/run", json={}))
        active = None
        for _ in range(100):
            response = await client.get("/api/c51/active")
            if response.status_code == 200:
                active = response.json()
                break
            await asyncio.sleep(0.001)
        assert active is not None
        assert (await client.post("/api/c51/run", json={})).status_code == 409
        assert (await client.post("/api/c51/stop", json={"runId": active["runId"]})).status_code == 200
        report = events(await task)[-1]["report"]
        assert report["status"] == "cancelled" and "summary" not in report
        assert (await client.get("/api/c51/active")).status_code == 404
