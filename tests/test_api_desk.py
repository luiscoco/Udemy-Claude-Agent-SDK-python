"""Lesson 50 routes validate scope and real synthetic effects."""

import asyncio

import httpx
import pytest

from agent_lab.api import create_app
from agent_lab.config import Settings
from agent_lab.runtime import RunService


@pytest.mark.asyncio
async def test_desk_routes_local_journey_and_scope(tmp_path) -> None:
    app = create_app(RunService(Settings(data_dir=tmp_path)), with_ui=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/api/c50/facts")).json()["synthetic_only"]
        assert len((await client.get("/api/c50/code")).json()) == 3
        first = await client.post("/api/c50/chat", json={"intent": "orders"})
        assert first.status_code == 200 and first.json()["experiment_passed"]
        conversation = first.json()["conversation"]
        assert (await client.get("/api/c50/conversation/" + conversation,
                                 params={"customer": "bo"})).status_code == 404
        assert (await client.get("/api/c50/conversation/bad")).status_code == 400
        assert (await client.get("/api/c50/conversation/" + conversation)).status_code == 200
        ticket = await client.post("/api/c50/chat", json={
            "conversationId": conversation, "intent": "ticket"})
        assert ticket.status_code == 200 and ticket.json()["experiment_passed"]
        assert len((await client.get("/api/c50/state")).json()["tickets"]) == 1

        denied_task = asyncio.create_task(client.post("/api/c50/chat", json={
            "conversationId": conversation, "intent": "refund"}))
        pending = await _pending(client)
        assert (await client.get("/api/c50/state")).status_code == 409
        assert (await client.post("/api/c50/reset", json={"confirm": True})).status_code == 409
        assert (await client.post("/api/c50/chat", json={})).status_code == 409
        wrong = {**pending, "approvalToken": "00000000-0000-0000-0000-000000000000", "choice": "approve"}
        wrong = {key: wrong[key] for key in ("runId", "conversationId", "callId", "approvalToken", "choice")}
        assert (await client.post("/api/c50/approve", json=wrong)).status_code == 409
        decision = {**wrong, "approvalToken": pending["approvalToken"], "choice": "deny"}
        assert (await client.post("/api/c50/approve", json=decision)).status_code == 200
        assert (await client.post("/api/c50/approve", json=decision)).status_code == 409
        denied = await denied_task
        assert denied.status_code == 200 and denied.json()["experiment_passed"]
        assert (await client.get("/api/c50/state")).json()["refunds"] == []

        approved_task = asyncio.create_task(client.post("/api/c50/chat", json={
            "conversationId": conversation, "intent": "refund"}))
        pending = await _pending(client)
        decision = {key: pending[key] for key in ("runId", "conversationId", "callId", "approvalToken")}
        assert (await client.post("/api/c50/approve", json=decision | {"choice": "approve"})).status_code == 200
        approved = await approved_task
        assert approved.status_code == 200 and approved.json()["experiment_passed"]
        assert len((await client.get("/api/c50/state")).json()["refunds"]) == 1
        closed = await client.post("/api/c50/close", json={"conversationId": conversation})
        assert closed.status_code == 200 and closed.json()["experiment_passed"]
        assert (await client.post("/api/c50/close", json={"conversationId": conversation})).status_code == 409
        evaluated = await client.post("/api/c50/evals", json={})
        assert evaluated.status_code == 200 and evaluated.json()["experiment_passed"]
        assert (await client.post("/api/c50/reset", json={"confirm": True})).status_code == 200
        assert (await client.get("/api/c50/state")).json()["conversations"] == []


async def _pending(client: httpx.AsyncClient) -> dict:
    for _ in range(100):
        response = await client.get("/api/c50/pending")
        if response.status_code == 200:
            return response.json()
        await asyncio.sleep(0.01)
    raise AssertionError("Synthetic approval proposal did not appear")


@pytest.mark.asyncio
async def test_desk_strict_inputs_and_interruption(tmp_path) -> None:
    app = create_app(RunService(Settings(data_dir=tmp_path)), with_ui=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        for invalid in ({"customer": "other"}, {"message": " "}, {"extra": 1},
                        {"conversationId": "bad"}, []):
            assert (await client.post("/api/c50/chat", json=invalid)).status_code == 400
        assert (await client.post("/api/c50/chat", json={"mode": "live", "consent": True})).status_code == 403
        assert (await client.post("/api/c50/evals", json={"mode": "live"})).status_code == 403
        assert (await client.post("/api/c50/reset", json={})).status_code == 400
        for scenario in ("missing", "foreign", "failed"):
            response = await client.post("/api/c50/chat", json={"scenario": scenario})
            assert response.status_code == 200 and not response.json()["experiment_passed"]
        task = asyncio.create_task(client.post("/api/c50/chat", json={"intent": "refund"}))
        pending = await _pending(client)
        stopped = await client.post("/api/c50/stop", json={"runId": pending["runId"]})
        assert stopped.status_code == 200 and stopped.json() == {"stopped": True, "pending": 0}
        with pytest.raises(asyncio.CancelledError):
            await task
        assert (await client.get("/api/c50/state")).json()["refunds"] == []
