"""Checkpoint identity, actual file effects and owned client cleanup."""

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
from agent_lab.checkpointing import FIXTURE_CHECKPOINT, REPLACEMENTS, checkpoint_policy
from agent_lab.config import Settings
from agent_lab.foundation_models import SCENARIOS
from agent_lab.foundations import source_sections
from agent_lab.learning import check_evidence, guide
from agent_lab.models import RunRequest
from agent_lab.runtime import RunService


@pytest.mark.parametrize("scenario", SCENARIOS[17])
async def test_real_client_offline_rewind_scenarios(tmp_path, scenario):
    runner = RunService(Settings(data_dir=tmp_path))
    events = [e async for e in runner.events(runner.start(17, RunRequest(scenario=scenario)))]
    proof = next(e.data["result"] for e in events if e.kind == "evidence")
    report = proof["experiment"]
    assert proof["experiment_passed"] is (scenario == "success")
    assert check_evidence(17, proof, status="completed").status == (
        "passed" if scenario == "success" else "needs-review"
    )
    assert check_evidence(17, proof, status="completed", mode="live").status == "needs-review"
    assert report["connection_closed"]
    requests = [r for r in report["fixture_controls"] if r["subtype"] == "rewind_files"]
    if scenario == "success":
        assert requests == [{"subtype": "rewind_files", "user_message_id": FIXTURE_CHECKPOINT}]
        assert report["before_hash"] != report["changed_hash"]
        assert report["before_hash"] == report["after_hash"]
    if scenario == "no-effect":
        assert report["rewind_acknowledged"] and report["before_hash"] != report["after_hash"]


@pytest.mark.parametrize(
    "options", [{"checkpointing": False}, {"replay_messages": False}, {"action": "inspect"}]
)
async def test_disabled_or_inspect_only_does_not_restore_or_pass(tmp_path, options):
    runner = RunService(Settings(data_dir=tmp_path))
    events = [e async for e in runner.events(runner.start(17, RunRequest(lesson_options=options)))]
    proof = next(e.data["result"] for e in events if e.kind == "evidence")
    assert not proof["experiment_passed"]
    assert not proof["experiment"]["rewind_requested"]
    assert proof["experiment"]["before_hash"] != proof["experiment"]["after_hash"]


@pytest.mark.parametrize(
    "options",
    [
        {"checkpointing": "true"},
        {"replay_messages": 1},
        {"action": "foreign-session"},
        {"replacement": "private"},
        {"checkpoint_id": FIXTURE_CHECKPOINT},
        {"path": "../outside"},
    ],
)
async def test_untrusted_checkpoint_inputs_fail_before_files_or_tasks(tmp_path, options):
    runner = RunService(Settings(data_dir=tmp_path))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(runner, with_ui=False)), base_url="http://test"
    ) as client:
        result = await client.post("/api/lessons/17/run", json={"lesson_options": options})
    assert result.status_code == 422
    assert not runner.active and not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "case",
    [
        "success",
        "missing-uuid",
        "tool-result-uuid",
        "late-uuid",
        "invalid-uuid",
        "wrong-session",
        "unmatched-write",
        "no-change",
        "rewind-error",
        "no-effect",
        "disconnect-error",
        "missing-result",
        "auth-retry",
        "cancel",
    ],
)
async def test_live_native_rewind_uses_only_observed_user_checkpoint(tmp_path, monkeypatch, case):
    import agent_lab.sdk as sdk

    monkeypatch.setattr(sdk, "require_live_access", lambda settings: None)
    monkeypatch.setattr(sdk, "resolve_cli_path", lambda settings: "injected-cli")
    owners, rewinds, clients = [], [], []
    entered = asyncio.Event()

    class Client:
        def __init__(self, options):
            self.options = options
            self.path = Path(options.cwd) / "notes.txt"
            self.before = self.path.read_bytes()
            clients.append(self)

        async def connect(self):
            owners.append(asyncio.current_task())

        async def query(self, prompt):
            assert json.dumps(REPLACEMENTS["short"]) in prompt
            assert "First Read notes.txt" in prompt
            self.prompt = prompt

        async def receive_response(self):
            entered.set()
            if case == "cancel":
                await asyncio.Event().wait()
            if case == "auth-retry":
                yield SystemMessage(subtype="api_retry", data={"error_status": 401})
                raise AssertionError("Must stop authentication retries")
            yield SystemMessage(
                subtype="init", data={"session_id": "actual-parent", "tools": ["Read", "Write"]}
            )
            if case not in {"missing-uuid", "tool-result-uuid", "late-uuid"}:
                yield UserMessage(
                    content=self.prompt,
                    uuid="invalid" if case == "invalid-uuid" else FIXTURE_CHECKPOINT,
                )
            text = REPLACEMENTS["short"]
            yield AssistantMessage(
                model="injected",
                content=[
                    ToolUseBlock(
                        id="write-one",
                        name="Write",
                        input={"file_path": str(self.path), "content": text},
                    )
                ],
            )
            if case != "no-change":
                self.path.write_text(text, encoding="utf-8")
            yield UserMessage(
                content=[
                    ToolResultBlock(
                        tool_use_id="foreign" if case == "unmatched-write" else "write-one",
                        content="Written",
                        is_error=False,
                    )
                ],
                uuid=FIXTURE_CHECKPOINT if case == "tool-result-uuid" else None,
            )
            if case == "late-uuid":
                yield UserMessage(content=self.prompt, uuid=FIXTURE_CHECKPOINT)
            if case != "missing-result":
                yield ResultMessage(
                    subtype="success",
                    is_error=False,
                    duration_ms=1,
                    duration_api_ms=1,
                    num_turns=1,
                    session_id="foreign" if case == "wrong-session" else "actual-parent",
                )

        async def rewind_files(self, checkpoint):
            owners.append(asyncio.current_task())
            rewinds.append(checkpoint)
            if case == "rewind-error":
                raise RuntimeError("private-rewind-error")
            if case != "no-effect":
                self.path.write_bytes(self.before)

        async def disconnect(self):
            owners.append(asyncio.current_task())
            if case == "disconnect-error":
                raise RuntimeError("private-disconnect-error")

    monkeypatch.setattr(sdk, "ClaudeSDKClient", Client)
    runner = RunService(Settings(data_dir=tmp_path, enable_live=True))
    handle = runner.start(17, RunRequest(mode="live"))
    if case == "cancel":
        await asyncio.wait_for(entered.wait(), 5)
        await runner.cancel(handle)
    events = [e async for e in runner.events(handle)]
    proof = next(e.data["result"] for e in events if e.kind == "evidence")
    assert proof["experiment_passed"] is (case == "success")
    assert all(o is owners[0] for o in owners) and len(owners) >= 2
    assert not runner.active and "private-" not in str(events)
    assert proof["experiment"]["connection_closed"] is (case != "disconnect-error")
    if case in {
        "missing-uuid",
        "tool-result-uuid",
        "late-uuid",
        "invalid-uuid",
        "wrong-session",
        "missing-result",
        "auth-retry",
        "cancel",
    }:
        assert rewinds == []
    if rewinds:
        assert rewinds == [FIXTURE_CHECKPOINT]
    options = clients[0].options
    assert options.enable_file_checkpointing and options.extra_args == {
        "replay-user-messages": None
    }
    assert options.setting_sources == [] and options.allowed_tools == []
    assert (
        await options.can_use_tool(
            "Write", {"file_path": "../outside", "content": REPLACEMENTS["short"]}, None
        )
    ).behavior == "deny"
    assert (
        await options.can_use_tool("Write", {"file_path": "notes.txt", "content": "foreign"}, None)
    ).behavior == "deny"


def test_checkpoint_policy_and_exact_source_excerpts(tmp_path):
    replacement = REPLACEMENTS["short"]
    assert checkpoint_policy(
        tmp_path, replacement, "Write", {"file_path": "notes.txt", "content": replacement}
    )[0]
    assert not checkpoint_policy(
        tmp_path, replacement, "Bash", {"file_path": "notes.txt", "content": replacement}
    )[0]
    assert not checkpoint_policy(
        tmp_path,
        replacement,
        "Write",
        {"file_path": ".claude/settings.json", "content": replacement},
    )[0]
    assert len(guide(17).quiz) == 7
    for section in source_sections(17):
        lines = (
            (Path(__file__).resolve().parents[1] / section["path"])
            .read_text(encoding="utf-8")
            .splitlines()
        )
        assert section["code"].splitlines() == lines[section["start"] - 1 : section["end"]]
