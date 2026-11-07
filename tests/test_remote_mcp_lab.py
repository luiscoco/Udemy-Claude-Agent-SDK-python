"""Real loopback MCP transport and credential checks for lesson 43."""

import json
import socket
from urllib.parse import urlsplit

import httpx
import pytest

from agent_lab.config import Settings
from agent_lab.exercises import EmbeddedServer
from agent_lab.remote_fixture_lab import RemoteFixture, discover
from agent_lab.remote_mcp_lab import RESOURCES, run, scrub_evidence, state


def test_secret_scrubber_removes_values_and_credential_fields():
    source = {"authorization": "Bearer fixture-private", "nested": [
        {"access_token": "fixture-private", "text": "header Bearer fixture-private"},
        "sk-ant-very-long-provider-key-value"]}
    cleaned = scrub_evidence(source, ["fixture-private"])
    assert "fixture-private" not in json.dumps(cleaned)
    assert "sk-ant-" not in json.dumps(cleaned)
    assert "authorization" not in cleaned
    assert "access_token" not in cleaned["nested"][0]


async def test_live_rotation_refuses_unverified_sdk_version(tmp_path, monkeypatch):
    import agent_lab.remote_mcp_lab as lab

    monkeypatch.setattr(lab, "_rotation_control_supported", lambda: False)
    with pytest.raises(ValueError, match="verified only"):
        await lab.live_action(tmp_path, Settings(), "rotation")


async def test_fixture_origin_audience_and_listener_cleanup():
    fixture = RemoteFixture()
    async with EmbeddedServer(fixture).running() as base:
        fixture.base = base
        async with httpx.AsyncClient(timeout=8, trust_env=False) as client:
            challenge = await client.post(base + "/mcp", json={"jsonrpc": "2.0", "id": 1,
                "method": "tools/list"})
            assert challenge.status_code == 401
            assert base + "/.well-known/oauth-protected-resource/mcp" in challenge.headers["www-authenticate"]
            bad_origin = await client.get(base + "/.well-known/oauth-protected-resource/mcp",
                                          headers={"Origin": "https://foreign.example"})
            assert bad_origin.status_code == 400
            wrong_grant = await client.post(base + "/issuer/credential", data={
                "client_id": fixture.client_id, "client_secret": fixture.client_secret,
                "grant_type": "client_credentials", "resource": base + "/wrong"})
            assert wrong_grant.status_code == 401
        token, _, steps = await discover(base, fixture)
        assert token and [item["status"] for item in steps] == [401, 200, 200, 200]
        port = urlsplit(base).port
    assert port is not None
    with pytest.raises(OSError):
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            pass


@pytest.mark.parametrize("action", ["auth", "cache", "transports", "toolsets", "resources", "host-read", "rotation"])
async def test_local_remote_actions_use_real_transport(tmp_path, action):
    report = await run(tmp_path, Settings(), action, "prepared")
    assert report["experiment_passed"], report
    assert report["mode"] == "local"
    assert state(tmp_path)["run_id"] == report["run_id"]
    assert "Bearer " not in json.dumps(report)
    assert "access_token" not in json.dumps(report)
    if action == "auth":
        assert report["expired_status"] == 401
    if action == "transports":
        assert [lane["transport"] for lane in report["lanes"]] == ["http", "sse"]
    else:
        assert report["handlers"]
        assert report["probe"]["status_payload"]["receiptId"] == report["handlers"][0]["receipt_id"]
        assert report["probe"]["resource_links"][0]["uri"] == "orders://1001"
        assert report["probe"]["resource_links"][0]["type"] == "resource_link"
        assert all(pair["call"]["scoped_key"] == pair["result"]["scoped_key"]
                   and pair["result"]["receipt_id"] for pair in report["protocol_pairs"])
        assert len({pair["call"]["scoped_key"] for pair in report["protocol_pairs"]}) == len(report["protocol_pairs"])
        assert any(row.get("rpc_method") == "tools/call" and
                   row.get("marker") == report["handlers"][0]["marker"] and
                   str(row.get("rpc_id")) == str(report["handlers"][0]["rpc_id"])
                   for row in report["wire"])


@pytest.mark.parametrize("transport", ["http", "sse"])
@pytest.mark.parametrize("resource", sorted(RESOURCES))
async def test_resources_match_handler_digest(tmp_path, transport, resource):
    report = await run(tmp_path, Settings(), "host-read", "prepared", transport, resource)
    assert report["experiment_passed"], report
    assert report["resource_reads"][0]["uri"] == RESOURCES[resource]
    assert report["probe"]["resource_contents"][0]["uri"] == RESOURCES[resource]
    if resource == "order":
        assert report["probe"]["followed_order_link"] is True


@pytest.mark.parametrize("scenario", ["missing", "foreign", "failed"])
async def test_fault_does_not_replace_latest(tmp_path, scenario):
    good = await run(tmp_path, Settings(), "auth", "prepared")
    bad = await run(tmp_path, Settings(), "auth", "prepared", scenario=scenario)
    assert not bad["experiment_passed"]
    assert bad["scenario"] == scenario
    if scenario == "missing":
        assert "receiptId" not in bad["probe"]["status_payload"]
    elif scenario == "foreign":
        assert bad["probe"]["status_payload"]["fixtureId"] == "foreign-fixture"
    else:
        assert bad["probe"]["status_is_error"] is True
    assert state(tmp_path)["run_id"] == good["run_id"]


async def test_state_rejects_missing_and_foreign_pointer(tmp_path):
    good = await run(tmp_path, Settings(), "auth", "prepared")
    pointer = tmp_path / "latest.json"
    pointer.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid lesson 43 run pointer"):
        state(tmp_path)
    pointer.write_text(json.dumps({"run_id": "../foreign"}), encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid lesson 43 run pointer"):
        state(tmp_path)
    pointer.write_text(json.dumps({"run_id": good["run_id"]}), encoding="utf-8")
    summary = tmp_path / good["run_id"] / "summary.json"
    item = json.loads(summary.read_text(encoding="utf-8"))
    item["mode"] = "foreign"
    summary.write_text(json.dumps(item), encoding="utf-8")
    with pytest.raises(ValueError, match="summary identity mismatch"):
        state(tmp_path)


async def test_report_limit_rejects_oversized_local_evidence(tmp_path, monkeypatch):
    import agent_lab.remote_mcp_lab as lab

    async def oversized(*args, **kwargs):
        return {"experiment_passed": True, "wire": [{"x": "a" * 2_000_001}]}

    monkeypatch.setattr(lab, "local_action", oversized)
    with pytest.raises(ValueError, match="bounded report limit"):
        await run(tmp_path, Settings(), "auth", "local")
    assert not (tmp_path / "latest.json").exists()
