"""Lesson 54 strict API and direct host handler behavior."""

import asyncio
import json
import uuid

import httpx
import pytest

from agent_lab.api import create_app
from agent_lab.config import Settings
from agent_lab.runtime import RunService


def frames(response: httpx.Response) -> list[dict]:
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]


@pytest.mark.asyncio
async def test_tool_design_routes_and_prepared_grade(tmp_path) -> None:
    app = create_app(RunService(Settings(data_dir=tmp_path, enable_live=False)), with_ui=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://catalog") as client:
        facts = (await client.get("/api/c54/facts")).json()
        assert facts["expectedIds"] == ["SKU-101", "SKU-104"] and facts["liveEnabled"] is False
        assert len((await client.get("/api/c54/code")).json()) == 3
        for body in ({"profile": "wrong"}, {"format": "wide"}, {"budget": 5}, {"extra": 1}):
            assert (await client.post("/api/c54/run", json=body)).status_code == 400
        assert (await client.post("/api/c54/run", json={"mode": "live", "consent": True})).status_code == 403
        assert (await client.post("/api/c54/call", json={"profile": "vague", "tool": "catalog_get", "input": {}})).status_code == 400
        invalid = (await client.post("/api/c54/call", json={"profile": "focused", "tool": "catalog_get",
                                                        "input": {"sku": "Trail mug"}})).json()
        assert invalid["receipt"]["errorCode"] == "INVALID_INPUT" and not invalid["receipt"]["executed"]
        valid = (await client.post("/api/c54/call", json={"profile": "focused", "tool": "catalog_get",
                                                      "input": {"sku": "SKU-101"}})).json()
        assert valid["receipt"]["ok"] and valid["snapshotSha256"] == valid["afterSha256"]
        result = frames(await client.post("/api/c54/run", json={"profile": "focused"}))
        assert result[0]["kind"] == "start" and result[-1]["kind"] == "done"
        assert next(row for row in result if row["kind"] == "result")["check"] == "passed"
        assert (await client.post("/api/c54/stop", json={"runId": str(uuid.uuid4())})).status_code == 409


@pytest.mark.asyncio
async def test_tool_design_overlap_and_stop(tmp_path) -> None:
    app = create_app(RunService(Settings(data_dir=tmp_path, enable_live=False)), with_ui=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://catalog") as client:
        pending = asyncio.create_task(client.post("/api/c54/run", json={"profile": "focused"}))
        active = None
        for _ in range(100):
            response = await client.get("/api/c54/active")
            if response.status_code == 200:
                active = response.json()["runId"]
                break
            await asyncio.sleep(.001)
        assert active
        assert (await client.post("/api/c54/run", json={})).status_code == 409
        assert (await client.post("/api/c54/stop", json={"runId": active})).status_code == 200
        result = frames(await pending)
        report = next(row for row in result if row["kind"] == "result")["report"]
        assert report["interrupted"] and report["closed"]
        assert (await client.get("/api/c54/active")).status_code == 404
