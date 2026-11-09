"""Injected SDK messages validate Lesson 56 identity, sequencing and limitations."""

import copy
import uuid

import pytest
from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from agent_lab.config import Settings
from agent_lab.teams_lab import LiveInput
from agent_lab.teams_native import evaluate_native, native_run


def terminal(session: str, cost: float) -> ResultMessage:
    return ResultMessage(subtype="success", duration_ms=1, duration_api_ms=1,
                         is_error=False, num_turns=1, session_id=session,
                         total_cost_usd=cost, result="observed", uuid=str(uuid.uuid4()))


def producer_variant(variant: str):
    async def producer(*, prompt, options):
        assert options.tools == ["Agent", "SendMessage"]
        assert options.allowed_tools == ["Agent", "SendMessage"]
        assert options.agents["calculator"].tools == []
        assert options.setting_sources == []
        assert options.env["CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"] == "0"
        assert options.max_turns == 8 and options.max_budget_usd == 0.15
        inputs = prompt.__aiter__()
        first = await anext(inputs)
        assert "12 + 18" in first["message"]["content"]
        session = str(uuid.uuid4())
        advertised = ["Task", "SendMessage"] if variant in {"task", "rejected"} else ["Agent", "SendMessage"]
        if variant == "unsupported":
            advertised = ["Agent"]
        yield SystemMessage(subtype="init", data={"session_id": session, "tools": advertised, "model": "injected"})
        if variant == "unsupported":
            return
        for turn in (1, 2):
            if turn == 2:
                followup = await anext(inputs)
                assert "add 7" in followup["message"]["content"]
                if variant == "foreign-init":
                    yield SystemMessage(subtype="init", data={"session_id": str(uuid.uuid4()),
                                                             "tools": advertised, "model": "injected"})
            name = "Agent" if turn == 1 else "SendMessage"
            raw = "Agent" if turn == 1 and variant == "task" else ("Task" if turn == 1 and variant == "rejected" else name)
            call_id = f"call-{turn}"
            args = ({"subagent_type": "calculator", "prompt": "compute 12 + 18"} if turn == 1 else
                    {"to": "researcher", "message": "add 7"})
            hook = options.hooks["PreToolUse"][0].hooks[0]
            decision = await hook({"tool_name": raw, "tool_input": args}, call_id, None)
            assert decision["hookSpecificOutput"]["permissionDecision"] == "allow"
            yield AssistantMessage(content=[ToolUseBlock(id=call_id, name=raw, input=args)], model="injected")
            result_id = "foreign" if variant == "foreign-result" and turn == 2 else call_id
            content = ('{"success":false,"message":"No agent named researcher is reachable."}'
                       if variant == "rejected" and turn == 2 else
                       '{"agentId":"worker-test","success":true}')
            yield UserMessage(content=[ToolResultBlock(tool_use_id=result_id, content=content,
                                                      is_error=variant == "error-result" and turn == 2)])
            yield AssistantMessage(content=[TextBlock(text="37 is an answer, not worker proof")], model="injected")
            yield terminal(session, 0.01 if turn == 1 else 0.02)
            if variant == "throw" and turn == 1:
                raise RuntimeError("later iterator failure")
    return producer


@pytest.mark.asyncio
async def test_injected_named_subagent_and_task_alias(tmp_path) -> None:
    for variant in ("ok", "task"):
        report = await native_run(LiveInput(consent=True), Settings(data_dir=tmp_path),
                                  tmp_path / variant, producer=producer_variant(variant))
        assert evaluate_native(report)
        assert report["sdkQueries"] == 1 and report["modelCalls"] is None
        assert report["reportedSdkUsd"] == 0.02
        assert report["deliveryVerified"] is False and report["workerCompletionVerified"] is False
        assert report["answerContains37"]
        if variant == "task":
            assert any(row["kind"] == "sdk-tool-call" and row["rawTool"] == "Agent" and
                       row["tool"] == "Agent" for row in report["frames"])
        forged = copy.deepcopy(report)
        forged["frames"] = [row for row in forged["frames"] if row["kind"] != "tool-result"]
        assert not evaluate_native(forged)
        denied = copy.deepcopy(report)
        extra = copy.deepcopy(next(row for row in denied["frames"] if row["kind"] == "hook"))
        extra.update(callId="foreign-denied", admitted=False)
        denied["frames"].append(extra)
        assert not evaluate_native(denied)
        foreign = copy.deepcopy(report)
        extra_result = copy.deepcopy(next(row for row in foreign["frames"] if row["kind"] == "tool-result"))
        extra_result["callId"] = "foreign-result"
        foreign["frames"].append(extra_result)
        assert not evaluate_native(foreign)


@pytest.mark.asyncio
async def test_injected_unsupported_foreign_rejected_and_exception(tmp_path) -> None:
    for variant in ("unsupported", "foreign-init", "foreign-result", "error-result", "rejected", "throw"):
        report = await native_run(LiveInput(consent=True), Settings(data_dir=tmp_path),
                                  tmp_path / variant, producer=producer_variant(variant))
        assert not evaluate_native(report), variant
        assert report["closed"] and report["deliveryVerified"] is False
        if variant == "throw":
            assert report["exception"] is not None


@pytest.mark.asyncio
async def test_pre_aborted_run_stays_partial(tmp_path) -> None:
    import asyncio

    abort = asyncio.Event()
    abort.set()
    report = await native_run(LiveInput(consent=True), Settings(data_dir=tmp_path),
                              tmp_path / "stopped", abort=abort, producer=producer_variant("ok"))
    assert report["sdkQueries"] == 0 and report["modelCalls"] == 0
    assert report["closed"] and report["interrupted"]
    assert not evaluate_native(report)
