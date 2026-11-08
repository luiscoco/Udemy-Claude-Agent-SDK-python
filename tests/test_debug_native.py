"""Injected SDK sequence verifies terminal-plus-exception and exact Read ownership."""

import uuid

import pytest
from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    SystemMessage,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from agent_lab.config import Settings
from agent_lab.debug_lab import DebugInput, criterion
from agent_lab.debug_native import native_run
from agent_lab.debug_store import DebugStore


@pytest.mark.asyncio
async def test_native_injected_exact_read_and_terminal_then_exception(tmp_path, monkeypatch):
    monkeypatch.setattr("agent_lab.debug_native.private_key", lambda: "sk-ant-injected")
    seen = {}

    async def fake_query(*, prompt, options):
        seen["prompt"] = prompt
        seen["options"] = options
        path = next((tmp_path / "lesson-53").glob("*/fixture.txt"))
        call_id = "read-owned"
        yield SystemMessage(subtype="init", data={"session_id": "sdk-session"})
        await options.hooks["PreToolUse"][0].hooks[0](
            {"tool_name": "Read", "tool_input": {"file_path": str(path)}}, call_id, None)
        yield AssistantMessage(model="claude-haiku-4-5-20251001",
                               content=[ToolUseBlock(id=call_id, name="Read",
                                                     input={"file_path": str(path)})])
        yield UserMessage(content=[ToolResultBlock(tool_use_id=call_id,
                                                   content=path.read_text(encoding="utf-8"), is_error=False)])
        yield ResultMessage(subtype="success", is_error=False, duration_ms=1, duration_api_ms=1,
                            num_turns=1, session_id="sdk-session", total_cost_usd=0.007)
        raise RuntimeError("private exception after terminal")

    monkeypatch.setattr("claude_agent_sdk.query", fake_query)
    store = DebugStore(tmp_path / "lesson-53")
    selected = DebugInput(mode="live", consent=True, budget=1.0)
    identifier = uuid.uuid4()
    bundle = await native_run(selected, store.root, identifier,
                              Settings(enable_live=True, data_dir=tmp_path))
    loaded = store.save(bundle)
    names = [row["name"] for row in bundle["rows"]]
    assert names.index("terminal") < names.index("iterator-exception")
    assert bundle["reportedSdkUsd"] == 0.007 and bundle["closed"]
    assert bundle["observations"]["readVerified"]
    assert not criterion(str(identifier), selected, bundle, loaded)
    assert "private exception after terminal" not in str(bundle)
    assert seen["options"].tools == ["Read"] and seen["options"].max_budget_usd == 0.10


@pytest.mark.asyncio
async def test_native_injected_denied_exact_path_hook(tmp_path, monkeypatch):
    monkeypatch.setattr("agent_lab.debug_native.private_key", lambda: "sk-ant-injected")
    seen = {}

    async def fake_query(*, prompt, options):
        path = next((tmp_path / "lesson-53").glob("*/fixture.txt"))
        pre = options.hooks["PreToolUse"][0].hooks[0]
        denial = await pre({"tool_name": "Read", "tool_input": {"file_path": str(path)}},
                           "read-denied", None)
        foreign = await pre({"tool_name": "Read", "tool_input": {"file_path": str(tmp_path / '.env')}},
                            "foreign", None)
        seen.update({"denial": denial, "foreign": foreign})
        yield SystemMessage(subtype="init", data={"session_id": "sdk-session"})
        yield AssistantMessage(model="claude-haiku-4-5-20251001",
                               content=[ToolUseBlock(id="read-denied", name="Read",
                                                     input={"file_path": str(path)})])
        yield UserMessage(content=[ToolResultBlock(tool_use_id="read-denied",
                                                   content="permission denied", is_error=True)])
        yield ResultMessage(subtype="success", is_error=False, duration_ms=1, duration_api_ms=1,
                            num_turns=1, session_id="sdk-session", total_cost_usd=0.006)

    monkeypatch.setattr("claude_agent_sdk.query", fake_query)
    store = DebugStore(tmp_path / "lesson-53")
    selected = DebugInput(mode="live", scenario="denied", consent=True, budget=1.0)
    identifier = uuid.uuid4()
    bundle = await native_run(selected, store.root, identifier,
                              Settings(enable_live=True, data_dir=tmp_path))
    loaded = store.save(bundle)
    assert seen["denial"]["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert seen["foreign"]["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert bundle["findings"][0]["code"] == "permission-denied"
    assert criterion(str(identifier), selected, bundle, loaded)
