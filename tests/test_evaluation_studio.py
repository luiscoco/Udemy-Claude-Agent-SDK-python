import asyncio
import json
import os
import socket
import subprocess
import sys
from unittest.mock import AsyncMock

import pytest

from agent_lab.config import ROOT, Settings
from agent_lab.evaluation_studio import (
    MAX_RUNS,
    PROJECT,
    StudioService,
    catalog,
    load_studio,
    message_to_dict,
    stage_of,
    validate_mcp_addresses,
)

REFERENCE = load_studio("reference")


def test_reference_passes_every_stage_and_the_learner_file_loads():
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(PROJECT)],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=os.environ | {"STUDIO_IMPLEMENTATION": "reference"},
        timeout=120,
    )
    assert result.returncode == 0 and "skipped" not in result.stdout, result.stdout
    # The learner file is student work in progress; they check it with `agent-lab studio check`.
    assert 1 <= stage_of(load_studio("learner")) <= 7


def test_catalog_is_python_and_complete():
    data = catalog()
    assert len(data["cases"]) == 170 and len(data["sections"]) == 17
    assert len({case["id"] for case in data["cases"]}) == 170
    text = json.dumps(data)
    for term in ("TypeScript", "maxTurns", "allowedTools", "settingSources", "Zod", "npm "):
        assert term not in text, term


@pytest.mark.parametrize(
    ("scenario", "subtype", "is_error"),
    [
        ("success", "success", False),
        ("max_turns", "error_max_turns", True),
        ("max_turns_then_stream_error", "error_max_turns", True),
    ],
)
def test_prepared_runs_cover_success_and_limit_scenarios(tmp_path, scenario, subtype, is_error):
    run = StudioService(Settings(data_dir=tmp_path)).prepared_run(
        REFERENCE, "first-query", "guided", scenario
    )
    assert (run["subtype"], run["is_error"], run["run_mode"]) == (subtype, is_error, "prepared")
    assert run["source"] == "Prepared fixture" and run["cost_usd"] == 0


def test_real_sdk_messages_convert_to_the_dicts_students_read():
    from claude_agent_sdk import (
        AssistantMessage,
        ResultMessage,
        SystemMessage,
        TextBlock,
        ToolUseBlock,
    )

    assistant = AssistantMessage(
        content=[TextBlock(text="Hi"), ToolUseBlock(id="t1", name="mcp__docs__search", input={})],
        model="m",
    )
    assert message_to_dict(assistant)["content"] == [
        {"type": "text", "text": "Hi"},
        {"type": "tool_use", "name": "mcp__docs__search", "input": {}},
    ]
    result = ResultMessage(
        subtype="success",
        duration_ms=1,
        duration_api_ms=1,
        is_error=False,
        num_turns=1,
        session_id="s",
    )
    assert message_to_dict(result)["subtype"] == "success"
    system = SystemMessage(
        subtype="init", data={"mcp_servers": [{"name": "docs", "status": "connected"}]}
    )
    assert message_to_dict(system)["mcp_servers"][0]["status"] == "connected"


def stub_live(monkeypatch, seen, fail_after_result=False):
    import claude_agent_sdk
    from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock

    async def fake_query(prompt, options):
        seen.append(options)
        yield AssistantMessage(content=[TextBlock(text="Partial")], model="m")
        yield ResultMessage(
            subtype="error_max_turns" if fail_after_result else "success",
            duration_ms=1,
            duration_api_ms=1,
            is_error=fail_after_result,
            num_turns=1,
            session_id="s",
            total_cost_usd=0.002,
        )
        if fail_after_result:
            raise RuntimeError("iterator failed after the result")

    monkeypatch.setattr(claude_agent_sdk, "query", fake_query)
    monkeypatch.setattr("agent_lab.doctor.resolve_cli_path", lambda settings: "claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fixture-not-a-real-key")
    monkeypatch.setattr(
        asyncio.get_running_loop(), "getaddrinfo", AsyncMock(return_value=dns_answers("8.8.8.8"))
    )


def dns_answers(*addresses):
    return [
        (
            socket.AF_INET6 if ":" in address else socket.AF_INET,
            socket.SOCK_STREAM,
            socket.IPPROTO_TCP,
            "",
            (address, 443, 0, 0) if ":" in address else (address, 443),
        )
        for address in addresses
    ]


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.1",
        "172.16.0.1",
        "192.168.1.1",
        "169.254.169.254",
        "100.64.0.1",
        "0.0.0.0",
        "224.0.0.1",
        "192.0.2.1",
        "::1",
        "::",
        "fc00::1",
        "fe80::1",
        "ff02::1",
        "::ffff:127.0.0.1",
    ],
)
async def test_live_run_rejects_any_non_public_dns_answer(tmp_path, monkeypatch, address):
    seen: list = []
    stub_live(monkeypatch, seen)
    resolver = AsyncMock(return_value=dns_answers("8.8.8.8", address))
    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", resolver)
    service = StudioService(Settings(data_dir=tmp_path, enable_live=True))
    custom = REFERENCE.mcp_settings("custom", "kb", "https://kb.example.com/mcp", "search")
    with pytest.raises(ValueError, match="only to public"):
        await service.live_run(
            REFERENCE,
            "first-query",
            "guided",
            REFERENCE.parse_run_options("guided", 8, 0.15),
            custom,
            consent=True,
            mcp_consent=True,
        )
    assert not seen and not service.runs and not service.root.exists()
    resolver.assert_awaited_once_with("kb.example.com", 443, type=socket.SOCK_STREAM)


async def test_public_mcp_dns_is_checked_again_on_every_live_run(tmp_path, monkeypatch):
    seen: list = []
    stub_live(monkeypatch, seen)
    resolver = AsyncMock(
        side_effect=[dns_answers("8.8.8.8", "2606:4700:4700::1111"), dns_answers("10.0.0.1")]
    )
    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", resolver)
    service = StudioService(Settings(data_dir=tmp_path, enable_live=True))
    custom = REFERENCE.mcp_settings("custom", "kb", "https://kb.example.com:8443/mcp", "search")
    options = REFERENCE.parse_run_options("guided", 8, 0.15)
    run = await service.live_run(
        REFERENCE, "first-query", "guided", options, custom, consent=True, mcp_consent=True
    )
    assert run["subtype"] == "success" and seen[0].mcp_servers == custom["mcp_servers"]
    with pytest.raises(ValueError, match="only to public"):
        await service.live_run(
            REFERENCE, "first-query", "guided", options, custom, consent=True, mcp_consent=True
        )
    assert len(seen) == 1 and resolver.await_count == 2
    resolver.assert_awaited_with("kb.example.com", 8443, type=socket.SOCK_STREAM)


@pytest.mark.parametrize("failure", [socket.gaierror("not found"), [], TimeoutError()])
async def test_mcp_dns_failure_stops_validation(monkeypatch, failure):
    resolver = AsyncMock(
        **(
            {"side_effect": failure}
            if isinstance(failure, Exception)
            else {"return_value": failure}
        )
    )
    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", resolver)
    with pytest.raises(ValueError, match="resolve|timed out"):
        await validate_mcp_addresses({"kb": {"type": "http", "url": "https://kb.example.com"}})


async def test_mcp_dns_deadline_cancels_slow_lookup(monkeypatch):
    async def slow_lookup(*args, **kwargs):
        await asyncio.Event().wait()

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", slow_lookup)
    monkeypatch.setattr("agent_lab.evaluation_studio.MCP_DNS_TIMEOUT_SECONDS", 0.01)
    with pytest.raises(ValueError, match="timed out"):
        await validate_mcp_addresses({"kb": {"type": "http", "url": "https://kb.example.com"}})


async def test_no_mcp_means_no_dns_lookup(monkeypatch):
    resolver = AsyncMock(side_effect=AssertionError("Unexpected DNS lookup"))
    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", resolver)
    await validate_mcp_addresses({})
    resolver.assert_not_awaited()


@pytest.mark.parametrize(
    "url",
    [
        "http://kb.example.com",
        "https://user:secret@kb.example.com",
        "https://localhost./mcp",
        "https://api.localhost/mcp",
        "https://kb.example.com:invalid",
        "https://kb.example.com?q=token",
    ],
)
async def test_host_rechecks_url_contract_even_for_unfinished_learner_code(monkeypatch, url):
    resolver = AsyncMock(side_effect=AssertionError("Unexpected DNS lookup"))
    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", resolver)
    with pytest.raises(ValueError):
        await validate_mcp_addresses({"kb": {"type": "http", "url": url}})
    resolver.assert_not_awaited()


async def test_live_runs_need_consent_for_the_run_and_the_mcp_connection(tmp_path, monkeypatch):
    stub_live(monkeypatch, [])
    service = StudioService(Settings(data_dir=tmp_path, enable_live=True))
    options = REFERENCE.parse_run_options("guided", 8, 0.15)
    docs = REFERENCE.mcp_settings("docs")
    with pytest.raises(PermissionError, match="paid run"):
        await service.live_run(
            REFERENCE, "first-query", "guided", options, docs, consent=False, mcp_consent=True
        )
    with pytest.raises(PermissionError, match="MCP"):
        await service.live_run(
            REFERENCE, "first-query", "guided", options, docs, consent=True, mcp_consent=False
        )


async def test_live_run_uses_the_students_options_and_reports_limits_honestly(
    tmp_path, monkeypatch
):
    seen: list = []
    stub_live(monkeypatch, seen, fail_after_result=True)
    service = StudioService(Settings(data_dir=tmp_path, enable_live=True))
    options = REFERENCE.parse_run_options("worked", 8, 0.15, True)
    mcp = REFERENCE.mcp_settings("docs")
    run = await service.live_run(
        REFERENCE, "mcp-basics", "guided", options, mcp, consent=True, mcp_consent=True
    )
    (sdk_options,) = seen
    assert sdk_options.max_turns == 8 and sdk_options.max_budget_usd == 0.15
    assert "claude_docs" in sdk_options.mcp_servers
    assert sdk_options.allowed_tools == ["Agent", "mcp__claude_docs__*"]
    assert "source_reviewer" in sdk_options.agents and sdk_options.setting_sources == []
    assert sdk_options.strict_mcp_config  # Only the separately authorized MCP may load.
    assert run["subtype"] == "error_max_turns" and run["is_error"] is True
    assert any(event["label"] == "SDK stream stopped" for event in run["events"])


def test_reviews_suites_and_history_persist(tmp_path):
    service = StudioService(Settings(data_dir=tmp_path))
    run = service.prepared_run(REFERENCE, "first-query", "guided")
    record = service.save_review(REFERENCE, run["id"], [True] * len(run["criteria"]), "ok")
    assert record["passed"] and record["kind"] == "prepared fixture"
    suite = service.run_suite(REFERENCE, "guided", "v1")
    assert len(suite["results"]) == 170 and suite["results"]["first-query"]["passed"] is True
    for _ in range(MAX_RUNS + 5):
        service.prepared_run(REFERENCE, "first-query", "baseline")
    assert len(service.runs) == MAX_RUNS
    reloaded = StudioService(Settings(data_dir=tmp_path))
    assert set(reloaded.suites) == {"v1"} and len(reloaded.runs) == MAX_RUNS
