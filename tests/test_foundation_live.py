"""Exercise the actual SDK option assembly and host callbacks with injected streams."""

import asyncio
from types import SimpleNamespace

import pytest
from claude_agent_sdk import (
    AssistantMessage,
    PermissionResultAllow,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from agent_lab.config import Settings
from agent_lab.hooks import call_hook
from agent_lab.learning import check_evidence
from agent_lab.models import RunRequest
from agent_lab.runtime import RunService


async def recorded_live_run(
    tmp_path, monkeypatch, lesson, options=None, mismatch=False, missing=False, invalid_schema=False
):
    import agent_lab.sdk as sdk

    monkeypatch.setenv("ANTHROPIC_API_KEY", "fixture-not-a-key")
    monkeypatch.setattr(sdk, "resolve_cli_path", lambda settings: "fixture-cli")
    captured, tools, closed, owners = [], {}, [], []
    original_server = sdk.create_sdk_mcp_server

    def server(*, name, tools: list):
        for item in tools:
            globals_tools[item.name] = item
        return original_server(name=name, tools=tools)

    globals_tools = tools
    monkeypatch.setattr(sdk, "create_sdk_mcp_server", server)

    async def stream(configuration, session):
        owners.append(asyncio.current_task())
        try:
            yield SystemMessage(
                subtype="init", data={"session_id": session, "tools": configuration.tools}
            )
            tool_name = {3: "Read", 4: "Write", 5: "mcp__lesson__add", 7: "Read", 8: "Agent"}.get(
                lesson
            )
            arguments = {"file_path": "notes.txt"}
            if lesson == 4:
                arguments = {"file_path": "draft.txt", "content": "Owned live fixture"}
            elif lesson == 5:
                arguments = {"a": 19, "b": 23}
            elif lesson == 8:
                arguments = {"subagent_type": "reviewer", "prompt": "Inspect the fixture"}
            if tool_name:
                yield AssistantMessage(
                    content=[ToolUseBlock(id="call-A", name=tool_name, input=arguments)],
                    model="fixture",
                )
                payload = {
                    "hook_event_name": "PreToolUse",
                    "tool_name": tool_name,
                    "tool_input": arguments,
                    "session_id": session,
                }
                for matcher in (configuration.hooks or {}).get("PreToolUse", []):
                    for hook in matcher.hooks:
                        output = await call_hook(hook, payload, "call-A")
                        decision = output.get("hookSpecificOutput", {})
                        if decision.get("permissionDecision") == "deny":
                            raise AssertionError(
                                "Default passing fixture must not hit a pre-use denial"
                            )
                        arguments = decision.get("updatedInput", arguments)
                        payload["tool_input"] = arguments
                failed = False
                if lesson == 4:
                    permission = await configuration.can_use_tool(
                        tool_name,
                        arguments,
                        SimpleNamespace(tool_use_id="wrong-call" if mismatch else "call-A"),
                    )
                    failed = not isinstance(permission, PermissionResultAllow)
                    if not failed:
                        updated = permission.updated_input or arguments
                        from pathlib import Path

                        target = Path(configuration.cwd) / updated["file_path"]
                        target.write_text(updated["content"], encoding="utf-8")
                elif lesson == 5:
                    await tools["add"].handler(arguments)
                elif lesson == 7:
                    for matcher in (configuration.hooks or {}).get("PostToolUse", []):
                        for hook in matcher.hooks:
                            await call_hook(
                                hook,
                                {
                                    **payload,
                                    "hook_event_name": "PostToolUse",
                                    "tool_response": "fixture read",
                                },
                                "call-A",
                            )
                elif lesson == 8:
                    yield AssistantMessage(
                        content=[TextBlock(text="Recorded worker response")],
                        model="fixture",
                        parent_tool_use_id="call-A",
                    )
                # A missing is_error flag is represented by None in the public SDK.
                yield UserMessage(
                    content=[
                        ToolResultBlock(
                            tool_use_id="unmatched" if mismatch else "call-A",
                            content="Recorded tool result",
                            is_error=True if failed else None,
                        )
                    ]
                )
            yield AssistantMessage(
                content=[TextBlock(text="Recorded parent response")], model="fixture"
            )
            if not missing:
                structured = (
                    {"summary": "", "next_steps": []}
                    if invalid_schema
                    else {"summary": "A fixture value", "next_steps": ["Inspect it"]}
                    if lesson == 10
                    else None
                )
                yield ResultMessage(
                    subtype="success",
                    duration_ms=1,
                    duration_api_ms=1,
                    is_error=False,
                    num_turns=1,
                    session_id="wrong-session"
                    if mismatch and lesson not in {3, 4, 5, 7, 8}
                    else session,
                    total_cost_usd=0,
                    structured_output=structured,
                )
        finally:
            closed.append(True)

    class Client:
        def __init__(self, options):
            self.options = options
            self.active = None
            self.session = options.resume or f"session-{len(captured)}"
            captured.append(
                {
                    "model": options.model,
                    "resume": options.resume,
                    "max_turns": options.max_turns,
                    "max_budget_usd": options.max_budget_usd,
                    "system_prompt": options.system_prompt,
                }
            )

        async def __aenter__(self):
            owners.append(asyncio.current_task())
            return self

        async def __aexit__(self, *args):
            if self.active is not None:
                await self.active.aclose()
            owners.append(asyncio.current_task())

        async def query(self, prompt):
            owners.append(asyncio.current_task())

        def receive_response(self):
            self.active = stream(self.options, self.session)
            return self.active

    async def query(*, prompt, options):
        captured.append(
            {
                "model": options.model,
                "max_turns": options.max_turns,
                "max_budget_usd": options.max_budget_usd,
                "system_prompt": options.system_prompt,
            }
        )
        async for message in stream(options, "query-session"):
            yield message

    monkeypatch.setattr(sdk, "ClaudeSDKClient", Client)
    monkeypatch.setattr(sdk, "query", query)
    runner = RunService(Settings(enable_live=True, data_dir=tmp_path / "runs"))
    try:
        events = [
            event
            async for event in runner.events(
                runner.start(lesson, RunRequest(mode="live", lesson_options=options or {}))
            )
        ]
        evidence = next(
            (event.data["result"] for event in events if event.kind == "evidence"), None
        )
        return events, evidence, captured, closed, owners
    finally:
        await runner.close()


@pytest.mark.parametrize("lesson", range(2, 11))
async def test_live_foundation_proofs_use_actual_stream_and_callbacks(
    tmp_path, monkeypatch, lesson
):
    events, evidence, captured, closed, owners = await recorded_live_run(
        tmp_path, monkeypatch, lesson
    )
    assert events[-1].data["status"] == "completed", events
    assert evidence is not None and evidence["experiment_passed"]
    assert evidence["experiment"]["source"] == "live SDK stream and actual host callbacks"
    assert check_evidence(lesson, evidence, status="completed", mode="live").status == "passed"
    assert closed and owners and all(owner is owners[0] for owner in owners)
    if lesson == 5:
        assert len(evidence["experiment"]["handler_events"]) == 1
    if lesson == 4:
        assert evidence["experiment"]["permission_decisions"][0]["decision"] == "deny"
    if lesson == 6:
        assert evidence["experiment"]["sent_sessions"] == []
        assert evidence["experiment"]["session_identity"]["outgoing_resume"] is None


@pytest.mark.parametrize("lesson", range(2, 11))
async def test_live_missing_terminal_never_passes(tmp_path, monkeypatch, lesson):
    events, evidence, _, closed, _ = await recorded_live_run(tmp_path, monkeypatch, lesson, missing=True)
    if lesson == 6:
        assert events[-1].data["status"] == "failed"
        assert evidence is None and len(closed) == 1
        return
    assert evidence is not None and not evidence["experiment_passed"]
    assert (
        check_evidence(lesson, evidence, status=events[-1].data["status"], mode="live").status
        == "needs-review"
    )


@pytest.mark.parametrize("lesson", range(2, 11))
async def test_live_mismatched_identity_needs_review(tmp_path, monkeypatch, lesson):
    events, evidence, *_ = await recorded_live_run(tmp_path, monkeypatch, lesson, mismatch=True)
    assert evidence is not None and not evidence["experiment_passed"]


async def test_omitted_sdk_limits_remain_omitted_and_do_not_echo_host_defaults(
    tmp_path, monkeypatch
):
    _, evidence, captured, *_ = await recorded_live_run(
        tmp_path,
        monkeypatch,
        2,
        {
            "omit_turn_limit": True,
            "omit_budget_limit": True,
            "system_mode": "custom",
            "system_text": "A custom instruction",
        },
    )
    assert captured[0]["max_turns"] is None and captured[0]["max_budget_usd"] is None
    assert captured[0]["model"] is None
    assert captured[0]["system_prompt"] == "A custom instruction"
    assert evidence["experiment_passed"]


@pytest.mark.parametrize("strategy,passed", [("resume", True), ("fresh", False)])
async def test_live_session_strategy_wires_resume_to_the_new_client(
    tmp_path, monkeypatch, strategy, passed
):
    _, evidence, captured, *_ = await recorded_live_run(
        tmp_path, monkeypatch, 6, {"strategy": strategy}
    )
    assert len(captured) == 2
    assert (captured[1]["resume"] == "session-0") is passed
    assert evidence["experiment_passed"] is passed


async def test_live_schema_errors_show_issues_and_fail_the_run(tmp_path, monkeypatch):
    events, evidence, *_ = await recorded_live_run(tmp_path, monkeypatch, 10, invalid_schema=True)
    assert events[-1].data["status"] == "failed"
    assert any(event.kind == "validation_error" for event in events)
    assert any("course schema" in event.data.get("message", "") for event in events)
