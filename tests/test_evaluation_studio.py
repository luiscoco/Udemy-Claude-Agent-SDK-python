import json
import os
import subprocess
import sys

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
