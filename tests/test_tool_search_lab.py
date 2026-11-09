"""Lesson 58 catalog, ledger and HTTP contracts."""

import asyncio
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from agent_lab import api_tool_search
from agent_lab.api import create_app
from agent_lab.config import Settings
from agent_lab.runtime import RunService
from agent_lab.tool_search_lab import (
    REFUND_ARGS,
    Config,
    PlanInput,
    RunInput,
    SearchInput,
    catalog,
    new_ledger,
    plan,
    prepared,
    refund,
    search,
    verify_ledger,
)
from agent_lab.tool_search_native import _has_reference, server_for


def test_catalog_scoring_and_plans() -> None:
    clear = catalog(Config())
    assert len(clear) == len({row["fullName"] for row in clear}) == 64
    assert search(SearchInput())["references"] == ["mcp__ops__billing_refund_invoice"]
    assert search(SearchInput(metadata="vague"))["references"] == []
    assert search(SearchInput(metadata="vague", query="select:mcp__ops__billing_op_7"))["references"] == ["mcp__ops__billing_op_7"]
    assert plan(PlanInput())["loadedCount"] == 0
    assert plan(PlanInput(searchMode="false"))["loadedCount"] == 64
    assert plan(PlanInput(alwaysLoad=True))["loadedCount"] == 1
    assert plan(PlanInput(searchMode="auto:0"))["deferredCount"] == 64
    assert plan(PlanInput(searchMode="auto:100"))["loadedCount"] == 64
    with pytest.raises(ValidationError):
        Config(searchMode="auto:101")
    with pytest.raises(ValidationError):
        SearchInput(query=" refund")


def test_ledger_exact_once_and_owner(tmp_path: Path) -> None:
    run_id = "7cd7ff2c-4b38-4b04-a090-0ce2a8b1dd9c"
    new_ledger(tmp_path, run_id)
    assert not refund(tmp_path, run_id, "c1", {**REFUND_ARGS, "amountCents": 4901})["ok"]
    assert refund(tmp_path, run_id, "c1", REFUND_ARGS)["ok"]
    assert refund(tmp_path, run_id, "c2", REFUND_ARGS)["error"] == "already-recorded"
    ledger, digest = verify_ledger(tmp_path, run_id)
    assert len(ledger["refunds"]) == 1 and len(digest) == 64
    assert prepared(RunInput(), tmp_path)["check"] == "pass"
    assert prepared(RunInput(metadata="vague"), tmp_path)["check"] == "needs-review"
    assert prepared(RunInput(metadata="vague", query="select:billing_op_7"), tmp_path)["check"] == "pass"
    (tmp_path / "lesson-58" / run_id / "ledger.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError):
        verify_ledger(tmp_path, run_id)


def test_structured_reference_and_server() -> None:
    assert _has_reference([{"type": "tool_reference", "tool_name": "mcp__ops__billing_refund_invoice"}],
                          "mcp__ops__billing_refund_invoice")
    assert not _has_reference("tool_reference mcp__ops__billing_refund_invoice",
                              "mcp__ops__billing_refund_invoice")

    async def handler(_name, _args):
        return {"ok": False}

    server = server_for(Config(), handler)
    assert server["type"] == "sdk"


@pytest.mark.asyncio
async def test_routes(tmp_path: Path) -> None:
    app = create_app(RunService(Settings(data_dir=tmp_path, enable_live=False)), with_ui=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                 base_url="http://lesson58") as client:
        assert (await client.get("/api/c58/facts")).json()["catalogCount"] == 64
        assert len((await client.get("/api/c58/code")).json()) == 3
        assert (await client.post("/api/c58/search", json={})).json()["references"] == ["mcp__ops__billing_refund_invoice"]
        assert (await client.post("/api/c58/search", json={"metadata": "bad"})).status_code == 400
        assert (await client.post("/api/c58/plan", json={"searchMode": "false"})).json()["loadedCount"] == 64
        assert (await client.post("/api/c58/run", json={"mode": "live"})).status_code == 403
        assert (await client.post("/api/c58/measure", json={})).status_code == 403
        report = (await client.post("/api/c58/run", json={})).json()
        assert report["check"] == "pass" and report["costUsd"] == 0
        assert (await client.post("/api/c58/stop", json={"runId": report["runId"]})).status_code == 404


@pytest.mark.asyncio
async def test_active_stop_and_conflict(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    entered = asyncio.Event()

    async def delayed(_selected, _root, run_id):
        entered.set()
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            return {"runId": run_id, "check": "needs-review", "interrupted": True}
        raise AssertionError("Expected Stop")

    monkeypatch.setattr(api_tool_search, "live", delayed)
    monkeypatch.setattr(api_tool_search, "bundled_cli", lambda: Path("fixture-cli"))
    monkeypatch.setattr(api_tool_search, "private_key", lambda: "fixture-only")
    app = create_app(RunService(Settings(data_dir=tmp_path, enable_live=True)), with_ui=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                 base_url="http://lesson58", timeout=10) as client:
        running = asyncio.create_task(client.post("/api/c58/run", json={"mode": "live", "consent": True}))
        await asyncio.wait_for(entered.wait(), 5)
        active = (await client.get("/api/c58/active")).json()
        assert (await client.post("/api/c58/run", json={})).status_code == 409
        assert (await client.post("/api/c58/stop", json=active)).status_code == 202
        response = await running
        assert response.status_code == 200 and response.json()["interrupted"]
        assert (await client.get("/api/c58/active")).status_code == 404
