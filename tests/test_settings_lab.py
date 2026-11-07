"""Settings experiments separate actual process effects from SDK fixture evidence."""

import asyncio
import json
from pathlib import Path

import httpx
import pytest
from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    SystemMessage,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from agent_lab.api import create_app
from agent_lab.config import Settings
from agent_lab.foundation_models import SCENARIOS
from agent_lab.foundations import source_sections
from agent_lab.learning import check_evidence, guide
from agent_lab.models import RunRequest
from agent_lab.runtime import RunService
from agent_lab.settings_lab import MARKER, probe_environment, settings_options


@pytest.mark.parametrize("scenario", SCENARIOS[16])
async def test_settings_scenarios_check_correlated_observations(tmp_path, scenario):
    runner = RunService(Settings(data_dir=tmp_path))
    events = [e async for e in runner.events(runner.start(16, RunRequest(scenario=scenario)))]
    proof = next(e.data["result"] for e in events if e.kind == "evidence")
    assert proof["experiment_passed"] is (scenario == "success")
    assert check_evidence(16, proof, status="completed").status == (
        "passed" if scenario == "success" else "needs-review"
    )
    assert check_evidence(16, proof, status="completed", mode="live").status == "needs-review"
    assert proof["experiment"]["connection_closed"]
    assert "not CLI settings" in proof["experiment"]["environment_probe"]["source"]


@pytest.mark.parametrize(
    "sources,expected",
    [("none", []), ("project", ["project"]), ("project-local", ["project", "local"])],
)
@pytest.mark.parametrize("override", [True, False])
async def test_owned_sources_and_child_environment_do_not_mutate_host(
    tmp_path, monkeypatch, sources, expected, override
):
    monkeypatch.setenv(MARKER, "private-inherited-demo")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "private-inherited-credential")
    options = settings_options(
        tmp_path,
        tmp_path / "private-config",
        RunRequest(
            lesson_options={"sources": sources, "env_override": override, "demo_value": "beta"}
        ),
        Settings(),
    )
    assert options.setting_sources == expected and options.tools == ["Read"]
    for filename, value in (("settings.json", "project"), ("settings.local.json", "local")):
        assert json.loads((tmp_path / ".claude" / filename).read_text()) == {"env": {MARKER: value}}
    probe = await probe_environment(options)
    assert probe["demo_override_matches"] is (True if override else None)
    assert probe["config_matches"] and probe["auto_memory_disabled"]
    assert "private-inherited" not in str(probe)
    import os

    assert os.environ[MARKER] == "private-inherited-demo"


@pytest.mark.parametrize(
    "options",
    [
        {"sources": "user"},
        {"env_override": "true"},
        {"demo_value": "secret"},
        {"env": {"PATH": "foreign"}},
        {"cwd": "../outside"},
    ],
)
async def test_invalid_settings_are_rejected_before_task_creation(tmp_path, options):
    runner = RunService(Settings(data_dir=tmp_path))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(runner, with_ui=False)), base_url="http://test"
    ) as client:
        response = await client.post("/api/lessons/16/run", json={"lesson_options": options})
    assert response.status_code == 422
    assert not runner.active and not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "case",
    [
        "success",
        "wrong-session",
        "unmatched-read",
        "missing-init",
        "missing-result",
        "failed-result",
        "disconnect-error",
        "auth-error",
        "auth-retry",
    ],
)
async def test_live_settings_observe_real_stream_and_close_same_owner(tmp_path, monkeypatch, case):
    import agent_lab.sdk as sdk
    import agent_lab.settings_lab as lab

    owners = []
    captured = []
    monkeypatch.setattr(sdk, "require_live_access", lambda settings: None)
    monkeypatch.setattr(lab, "resolve_cli_path", lambda settings: "injected-cli")

    class Client:
        def __init__(self, options):
            self.options = options
            captured.append(options)

        async def connect(self):
            owners.append(asyncio.current_task())
            if case == "auth-error":
                raise RuntimeError("private-inherited-credential")

        async def query(self, prompt):
            assert prompt

        async def receive_response(self):
            if case == "auth-retry":
                yield SystemMessage(subtype="api_retry", data={"error_status": 401})
                raise AssertionError("Must stop consuming authentication retries")
            if case != "missing-init":
                yield SystemMessage(
                    subtype="init", data={"session_id": "actual-session", "tools": ["Read"]}
                )
            yield AssistantMessage(
                model="injected",
                content=[
                    ToolUseBlock(id="actual-read", name="Read", input={"file_path": "notes.txt"})
                ],
            )
            yield UserMessage(
                content=[
                    ToolResultBlock(
                        tool_use_id="foreign" if case == "unmatched-read" else "actual-read",
                        content="Owned fixture",
                        is_error=False,
                    )
                ]
            )
            if case != "missing-result":
                yield ResultMessage(
                    subtype="error_max_turns" if case == "failed-result" else "success",
                    is_error=case == "failed-result",
                    duration_ms=1,
                    duration_api_ms=1,
                    num_turns=1,
                    session_id="foreign" if case == "wrong-session" else "actual-session",
                )

        async def disconnect(self):
            owners.append(asyncio.current_task())
            if case == "disconnect-error":
                raise RuntimeError("private-disconnect-error")

    monkeypatch.setattr(sdk, "ClaudeSDKClient", Client)
    runner = RunService(Settings(data_dir=tmp_path, enable_live=True))
    events = [e async for e in runner.events(runner.start(16, RunRequest(mode="live")))]
    proof = next(e.data["result"] for e in events if e.kind == "evidence")
    assert proof["experiment_passed"] is (case == "success")
    assert owners[0] is owners[-1] and len(owners) == 2
    assert not runner.active and "private-" not in str(events)
    assert proof["experiment"]["connection_closed"] is (case != "disconnect-error")
    options = captured[0]
    assert (
        await options.can_use_tool("Bash", {"command": "echo forbidden"}, None)
    ).behavior == "deny"
    assert (
        await options.can_use_tool("Read", {"file_path": ".claude/settings.json"}, None)
    ).behavior == "deny"


def test_settings_assessment_and_source_excerpts_are_current():
    assert len(guide(16).quiz) == 7
    for section in source_sections(16):
        lines = (
            (Path(__file__).resolve().parents[1] / section["path"])
            .read_text(encoding="utf-8")
            .splitlines()
        )
        assert section["code"].splitlines() == lines[section["start"] - 1 : section["end"]]


async def test_cancelled_settings_run_closes_client_in_owning_task(tmp_path, monkeypatch):
    import agent_lab.sdk as sdk
    import agent_lab.settings_lab as lab

    entered = asyncio.Event()
    owners = []
    monkeypatch.setattr(sdk, "require_live_access", lambda settings: None)
    monkeypatch.setattr(lab, "resolve_cli_path", lambda settings: "injected-cli")

    class Client:
        def __init__(self, options):
            pass

        async def connect(self):
            owners.append(asyncio.current_task())

        async def query(self, prompt):
            pass

        async def receive_response(self):
            entered.set()
            await asyncio.Event().wait()
            yield

        async def disconnect(self):
            owners.append(asyncio.current_task())

    monkeypatch.setattr(sdk, "ClaudeSDKClient", Client)
    runner = RunService(Settings(data_dir=tmp_path, enable_live=True))
    handle = runner.start(16, RunRequest(mode="live"))
    await asyncio.wait_for(entered.wait(), 5)
    await runner.cancel(handle)
    events = [e async for e in runner.events(handle)]
    proof = next(e.data["result"] for e in events if e.kind == "evidence")
    assert proof["experiment"]["connection_closed"]
    assert not proof["experiment_passed"]
    assert events[-1].data["status"] == "cancelled"
    assert len(owners) == 2 and owners[0] is owners[1] and not runner.active
