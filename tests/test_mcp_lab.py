"""Real inventory MCP effects, lifecycle guards and agent evidence correlation."""

import asyncio
import copy
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from agent_lab.api import create_app
from agent_lab.config import Settings
from agent_lab.foundations import Evidence, source_sections
from agent_lab.integrations.inventory_mcp import Inventory
from agent_lab.learning import check_evidence
from agent_lab.mcp_lab import McpWorkshops, connected, local_mcp
from agent_lab.models import LessonError, RunRequest, lesson_request
from agent_lab.runtime import RunService


@pytest.mark.parametrize("transport", ["sdk", "stdio", "http"])
@pytest.mark.parametrize("lifecycle", ["none", "toggle", "reconnect"])
async def test_real_transports_discover_tools_change_owned_stock_and_close(
    tmp_path, transport, lifecycle
):
    result = await local_mcp(
        tmp_path, RunRequest(lesson_options={"transport": transport, "lifecycle": lifecycle})
    )
    assert result["experiment_passed"]
    report = result["experiment"]
    observed = report["local_effects"]
    assert observed["before"]["stock"]["notebook"] == 12
    assert observed["after"]["stock"]["notebook"] == 10
    assert observed["closed"] and not observed["connection_open"]
    assert {t["name"] for t in observed["discovered_tools"]} == {"stock", "reserve"}
    assert report["calls"][0]["id"] == report["results"][0]["id"]
    assert "recorded" in report["source"]
    assert check_evidence(13, result, status="completed").status == "passed"
    assert check_evidence(13, result, status="completed", mode="live").status == "needs-review"
    if lifecycle == "toggle":
        assert any(row.get("blocked") == "server disabled" for row in observed["timeline"])


@pytest.mark.parametrize("scenario", ["missing-evidence", "wrong-identity", "tool-error"])
async def test_missing_mismatched_and_real_server_errors_do_not_pass(tmp_path, scenario):
    result = await local_mcp(tmp_path, RunRequest(scenario=scenario))
    assert not result["experiment_passed"]
    if scenario == "tool-error":
        effects = result["experiment"]["local_effects"]
        assert effects["before"] == effects["after"]
        assert result["experiment"]["results"][0]["is_error"]


async def test_disabled_configuration_and_read_only_stock_do_not_manufacture_writes(tmp_path):
    disabled = await local_mcp(tmp_path, RunRequest(lesson_options={"enabled": False}))
    assert not disabled["experiment_passed"]
    assert not disabled["experiment"]["calls"]
    read_only = await local_mcp(tmp_path, RunRequest(lesson_options={"tool": "stock"}))
    assert read_only["experiment_passed"]
    assert (
        read_only["experiment"]["local_effects"]["before"]
        == read_only["experiment"]["local_effects"]["after"]
    )


@pytest.mark.parametrize("quantity", [True, 0, 6, "2"])
def test_rejected_handler_input_has_no_inventory_effect(tmp_path, quantity):
    inventory = Inventory(tmp_path / "inventory.json")
    before = inventory.reset()
    with pytest.raises((ValidationError, ValueError)):
        inventory.reserve({"sku": "notebook", "quantity": quantity})
    assert inventory.read() == before


def test_one_authorized_agent_reservation_cannot_be_changed_or_repeated(tmp_path):
    inventory = Inventory(
        tmp_path / "inventory.json", reserve_limit=1, expected={"sku": "pen", "quantity": 2}
    )
    inventory.reset()
    with pytest.raises(ValueError, match="exactly"):
        inventory.reserve({"sku": "notebook", "quantity": 2})
    assert inventory.read()["reservations"] == []
    assert inventory.reserve({"sku": "pen", "quantity": 2})["stock"]["pen"] == 18
    with pytest.raises(ValueError, match="limit"):
        inventory.reserve({"sku": "pen", "quantity": 2})


@pytest.mark.parametrize("transport", ["sdk", "stdio", "http"])
async def test_mcp_protocol_rejects_boolean_quantities_without_effects(tmp_path, transport):
    inventory = Inventory(tmp_path / "inventory.json")
    before = inventory.reset()
    async with connected(inventory, transport) as (client, _):
        result = await client.call_tool("reserve", {"sku": "notebook", "quantity": True})
    assert result.isError
    assert inventory.read() == before


async def test_workshop_api_owns_stock_guards_disabled_calls_and_changes_only_owned_servers(
    tmp_path,
):
    runner = RunService(Settings(data_dir=tmp_path))
    app = create_app(runner, with_ui=False)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/api/c13/session", json={})
            assert response.status_code == 200
            key = {k: response.json()[k] for k in ("application_handle", "control_token")}

            async def stock():
                r = await client.get(
                    "/api/c13/stock",
                    params={"application_handle": key["application_handle"]},
                    headers={"x-control-token": key["control_token"]},
                )
                assert r.status_code == 200
                return r.json()

            before = await stock()
            assert (await client.post("/api/c13/mcp", json=key)).json()["configured"]["inventory"][
                "type"
            ] == "sdk"
            probe = (await client.post("/api/c13/status", json=key)).json()
            assert probe["state"]["last_probe_connected"] and not probe["state"]["connection_open"]
            assert (
                await client.post("/api/c13/toggle", json=key | {"enabled": False})
            ).status_code == 200
            assert (
                await client.post("/api/c13/send", json=key | {"tool": "reserve"})
            ).status_code == 409
            assert await stock() == before
            assert (
                await client.post("/api/c13/toggle", json=key | {"enabled": True})
            ).status_code == 200
            assert (await client.post("/api/c13/reconnect", json=key)).status_code == 200
            result = await client.post(
                "/api/c13/send", json=key | {"tool": "reserve", "sku": "pen", "quantity": 3}
            )
            assert result.json()["inventory"]["stock"]["pen"] == 17
            assert (
                await client.post("/api/c13/set-servers", json=key | {"transport": "stdio"})
            ).status_code == 200
            assert (await client.post("/api/c13/status", json=key)).json()["state"][
                "transport"
            ] == "stdio"
            assert (await client.post("/api/c13/stock/reset", json=key)).json()[
                "inventory"
            ] == before
            assert (
                await client.post("/api/c13/log", json=key | {"control_token": "x" * 32})
            ).status_code == 403
            assert (
                await client.post("/api/c13/send", json=key | {"quantity": True})
            ).status_code == 422
            assert (
                await client.post(
                    "/api/c13/set-servers", json=key | {"transport": "http://outside.test"}
                )
            ).status_code == 422
            assert (await client.post("/api/c13/end", json=key)).json()["state"]["closed"]
            assert (
                await client.post("/api/c13/send", json=key | {"tool": "reserve"})
            ).status_code == 409
            assert await stock() == before
    finally:
        await app.state.mcp_workshops.close()
        await runner.close()


@pytest.mark.parametrize(
    "options",
    [
        {"transport": "sse"},
        {"url": "http://example.com"},
        {"quantity": True},
        {"quantity": 10},
        {"tool": "delete"},
        {"enabled": "true"},
    ],
)
async def test_bad_query_options_are_rejected_before_task_or_workspace(tmp_path, options):
    runner = RunService(Settings(data_dir=tmp_path))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(runner, with_ui=False)), base_url="http://test"
    ) as client:
        response = await client.post("/api/c13/query", json={"lesson_options": options})
        assert response.status_code == 422
        assert (await client.post("/api/c13/query", json={"mode": "live"})).status_code == 403
    assert not runner.active and not list(tmp_path.iterdir())


async def test_concurrent_workshop_opens_respect_the_slot_limit(tmp_path):
    registry = McpWorkshops(Settings(data_dir=tmp_path, max_concurrent_runs=1))
    results = await asyncio.gather(
        registry.start("sdk"), registry.start("sdk"), return_exceptions=True
    )
    assert sum(isinstance(result, LessonError) for result in results) == 1
    assert len(registry.items) == 1
    await registry.close()


async def test_correlated_evidence_rejects_duplicate_child_and_failed_parent_records(tmp_path):
    report = (await local_mcp(tmp_path, RunRequest()))["experiment"]
    proof = Evidence(13, report["run"], tmp_path, lesson_request(13, {}).lesson_options, "test")
    proof.configured, proof.initialized = report["configured"], report["initialization"]
    proof.calls, proof.results, proof.terminals = (
        report["calls"],
        report["results"],
        report["terminal_results"],
    )
    assert proof.report()["experiment_passed"]
    proof.results += copy.deepcopy(proof.results)
    assert not proof.report()["experiment_passed"]
    proof.results = proof.results[:1]
    proof.calls[0]["parent_tool_use_id"] = "child"
    assert not proof.report()["experiment_passed"]
    proof.calls[0]["parent_tool_use_id"] = None
    proof.terminals[0]["is_error"] = True
    assert not proof.report()["experiment_passed"]


def test_exact_mcp_source_excerpts():
    for section in source_sections(13):
        lines = (
            (Path(__file__).resolve().parents[1] / section["path"])
            .read_text(encoding="utf-8")
            .splitlines()
        )
        assert section["code"].splitlines() == lines[section["start"] - 1 : section["end"]]
