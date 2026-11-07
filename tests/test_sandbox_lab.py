"""Actual process counterexamples and correlated policy outcomes, without paid calls."""

import asyncio
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
from agent_lab.sandbox_lab import sandbox_policy, selected_target


@pytest.mark.parametrize("target", ["inside", "outside", "protected"])
@pytest.mark.parametrize("scenario", SCENARIOS[18])
async def test_policy_scenarios_need_actual_counterexample_and_matching_evidence(
    tmp_path, target, scenario
):
    runner = RunService(Settings(data_dir=tmp_path))
    events = [
        e
        async for e in runner.events(
            runner.start(18, RunRequest(lesson_options={"target": target}, scenario=scenario))
        )
    ]
    proof = next(e.data["result"] for e in events if e.kind == "evidence")
    assert proof["experiment_passed"] is (scenario == "success")
    assert check_evidence(18, proof, status="completed").status == (
        "passed" if scenario == "success" else "needs-review"
    )
    assert check_evidence(18, proof, status="completed", mode="live").status == "needs-review"
    report = proof["experiment"]
    assert (
        report["boundary_probe"]["child_read_neighbor"]
        and report["boundary_probe"]["read_policy_denied"]
    )
    assert report["connection_closed"] and report["neighbor_unchanged"]
    assert report["native_capability"]["enforcement_verified"] is False
    assert not list(tmp_path.glob("*/policy-neighbor.txt"))


@pytest.mark.parametrize(
    "options",
    [
        {"target": "../../foreign"},
        {"native_required": "true"},
        {"command": "arbitrary"},
        {"network": {}},
        {"native_required": True},
    ],
)
async def test_invalid_inputs_reject_before_files_and_provider(tmp_path, options):
    runner = RunService(Settings(data_dir=tmp_path))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(runner, with_ui=False)), base_url="http://test"
    ) as client:
        response = await client.post("/api/lessons/18/run", json={"lesson_options": options})
    assert response.status_code == 422
    assert not runner.active and not list(tmp_path.iterdir())


async def test_native_windows_requirement_rejects_before_model_or_workspace(tmp_path, monkeypatch):
    import agent_lab.sandbox_native as native

    monkeypatch.setattr(
        native,
        "sandbox_capability",
        lambda: {"supported": False, "reason": "Native Windows is unsupported; use WSL2."},
    )
    runner = RunService(Settings(data_dir=tmp_path, enable_live=True))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(runner, with_ui=False)), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/lessons/18/run",
            json={"mode": "live", "lesson_options": {"native_required": True}},
        )
    assert response.status_code == 422 and "unsupported" in response.text
    assert not runner.active and not list(tmp_path.iterdir())


@pytest.mark.parametrize("target", ["inside", "outside", "protected"])
@pytest.mark.parametrize(
    "case", ["success", "missing-decision", "wrong-result", "wrong-session", "auth-retry", "cancel"]
)
async def test_injected_live_policy_observes_actual_hook_and_closes_owner(
    tmp_path, monkeypatch, target, case
):
    import agent_lab.sdk as sdk

    monkeypatch.setattr(sdk, "require_live_access", lambda settings: None)
    monkeypatch.setattr(sdk, "resolve_cli_path", lambda settings: "injected-cli")
    entered = asyncio.Event()
    owners = []

    class Client:
        def __init__(self, options):
            self.options = options

        async def connect(self):
            owners.append(asyncio.current_task())

        async def query(self, prompt):
            self.prompt = prompt

        async def receive_response(self):
            entered.set()
            if case == "cancel":
                await asyncio.Event().wait()
            if case == "auth-retry":
                yield SystemMessage(subtype="api_retry", data={"error_status": 401})
                raise AssertionError("Stop authentication retry")
            path = selected_target(Path(self.options.cwd), target)
            args = {"file_path": str(path)}
            if case != "missing-decision":
                hook = self.options.hooks["PreToolUse"][0].hooks[0]
                result = await hook({"tool_name": "Read", "tool_input": args}, "owned-read", None)
                assert result["hookSpecificOutput"]["permissionDecision"] == (
                    "allow" if target == "inside" else "deny"
                )
            yield SystemMessage(subtype="init", data={"session_id": "actual-parent"})
            yield AssistantMessage(
                model="injected", content=[ToolUseBlock(id="owned-read", name="Read", input=args)]
            )
            yield UserMessage(
                content=[
                    ToolResultBlock(
                        tool_use_id="foreign" if case == "wrong-result" else "owned-read",
                        content="Synthetic result",
                        is_error=target != "inside",
                    )
                ]
            )
            yield ResultMessage(
                subtype="success",
                is_error=False,
                duration_ms=1,
                duration_api_ms=1,
                num_turns=1,
                session_id="foreign" if case == "wrong-session" else "actual-parent",
            )

        async def disconnect(self):
            owners.append(asyncio.current_task())

    monkeypatch.setattr(sdk, "ClaudeSDKClient", Client)
    runner = RunService(Settings(data_dir=tmp_path, enable_live=True))
    handle = runner.start(18, RunRequest(mode="live", lesson_options={"target": target}))
    if case == "cancel":
        await asyncio.wait_for(entered.wait(), 5)
        await runner.cancel(handle)
    events = [e async for e in runner.events(handle)]
    proof = next(e.data["result"] for e in events if e.kind == "evidence")
    assert proof["experiment_passed"] is (case == "success")
    assert proof["experiment"]["connection_closed"]
    assert len(owners) == 2 and owners[0] is owners[1]
    assert not runner.active and not list(tmp_path.glob("*/policy-neighbor.txt"))


def test_fixed_scope_and_exact_source_excerpts(tmp_path):
    assert sandbox_policy(tmp_path, "Read", {"file_path": "notes.txt"})[0]
    assert not sandbox_policy(tmp_path, "Read", {"file_path": ".env"})[0]
    assert not sandbox_policy(tmp_path, "Read", {"file_path": "../policy-neighbor.txt"})[0]
    assert not sandbox_policy(tmp_path, "Bash", {"file_path": "notes.txt"})[0]
    assert len(guide(18).quiz) == 7
    for section in source_sections(18):
        lines = (
            (Path(__file__).resolve().parents[1] / section["path"])
            .read_text(encoding="utf-8")
            .splitlines()
        )
        assert section["code"].splitlines() == lines[section["start"] - 1 : section["end"]]
