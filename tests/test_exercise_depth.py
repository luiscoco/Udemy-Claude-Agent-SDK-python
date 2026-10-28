"""Deepened exercises: shared hooks, idempotent retries, validated state and routing.

Several tests pin the outcomes that lesson challenges ask students to predict.
"""

import pytest

from agent_lab.curriculum import LESSONS
from agent_lab.exercises import (
    TOOL_CALLS,
    hook_pipeline,
    hooks,
    permission_callback_cases,
    retry,
    routing,
    seed_workspace,
    todos,
    tool_design,
)
from agent_lab.hooks import call_hook, lesson_hooks, matches
from agent_lab.models import RunRequest
from agent_lab.policy import decide, redact


@pytest.fixture
def work(tmp_path):
    seed_workspace(tmp_path, LESSONS[7])
    return tmp_path


async def test_offline_hook_lesson_uses_the_live_hook_callbacks(work):
    audit = []

    async def record(kind, data):
        audit.append((kind, data))

    config = lesson_hooks(lambda name, arguments: decide(work, name, arguments), record)
    pre_tool = config["PreToolUse"][0].hooks[0]
    output = await call_hook(
        pre_tool, {"tool_name": "Read", "tool_input": {"file_path": ".env"}}, "toolu_1"
    )
    assert output["hookSpecificOutput"]["permissionDecision"] == "deny"
    post_tool = config["PostToolUse"][0].hooks[0]
    await call_hook(post_tool, {"tool_name": "Read", "tool_response": "secret text"}, "toolu_2")
    # The audit records size only, never the tool's content.
    assert audit[-1] == (
        "audit",
        {"tool": "Read", "tool_use_id": "toolu_2", "result_characters": 11},
    )
    evidence = await hooks(work, RunRequest(), LESSONS[7])
    assert evidence["denied"] == 4 and len(evidence["audit_log"]) == len(TOOL_CALLS)


async def test_hook_pipeline_audits_every_execution_and_blocks_before_post_hooks(work):
    evidence = await hook_pipeline(work, RunRequest(), LESSONS[20])
    assert evidence["executed"] == evidence["audited"] == 1
    assert evidence["write_alerts"] == 0
    steps = [row["step"] for row in evidence["timeline"]]
    assert steps[:4] == ["tool requested", "PreToolUse hook", "tool executed", "PostToolUse audit"]
    assert steps.count("tool blocked") == 4


def test_matcher_follows_the_cli_regex_rule():
    assert matches(None, "Bash") and matches("*", "Bash")
    assert matches("Write|Edit", "Edit") and not matches("Write|Edit", "Read")
    assert not matches("Read", "ReadFile")  # full match, not a prefix


async def test_permission_callback_returns_sdk_result_objects(work):
    evidence = await permission_callback_cases(work, RunRequest(), LESSONS[37])
    types = {row["case"]: row["result_type"] for row in evidence["results"]}
    assert types["normal read"] == "PermissionResultAllow"
    assert types["secret read"] == "PermissionResultDeny"
    assert (evidence["allowed"], evidence["denied"]) == (1, 4)


async def test_retry_recovers_within_deadline_and_applies_the_write_once(work):
    evidence = await retry(work, RunRequest(), LESSONS[28])
    assert [row["outcome"] for row in evidence["attempts"]] == [
        "ConnectionError",
        "TimeoutError",
        "succeeded",
    ]
    assert evidence["writes_applied"] == 1 and evidence["duplicate_write_prevented"]


def test_todo_transitions_are_validated_and_drive_the_suggestion(work):
    evidence = todos(work, RunRequest(), LESSONS[30])
    rejected = [row["reason"] for row in evidence["transitions"] if not row["accepted"]]
    assert rejected == [
        "pending cannot move to completed",
        "another task is already in progress",
        "completed cannot move to pending",
    ]
    assert evidence["suggestion"] == "Finish verify before starting another task."


def test_tool_design_feedback_names_field_problem_and_fix(work):
    evidence = tool_design(work, RunRequest(), LESSONS[54])
    fields = {row["case"]: row["field"] for row in evidence["feedback"]}
    assert fields["missing argument"] == "b" and fields["unexpected field"] == "shell"
    assert evidence["every_error_actionable"]


def test_routing_sends_complex_tasks_to_the_capable_tier(work):
    evidence = routing(work, RunRequest(prompt="Migrate the session store to SQLite"), LESSONS[59])
    tiers = [route["tier"] for route in evidence["routes"]]
    assert tiers == ["fast", "capable", "capable", "capable"]
    assert evidence["routes"][-1]["reason"] == "matched migrate"


def test_redaction_keeps_usage_counts_but_masks_credentials():
    usage = {"input_tokens": 100, "output_tokens": 50, "access_token": "abc", "has_token": True}
    assert redact(usage) == {
        "input_tokens": 100,
        "output_tokens": 50,
        "access_token": "[REDACTED]",
        "has_token": "[REDACTED]",
    }


async def test_mcp_lessons_use_real_transports(work):
    from agent_lab.exercises import mcp_stdio, remote_mcp

    stdio = await mcp_stdio(work, RunRequest(), LESSONS[13])
    assert stdio["valid_call"]["is_error"] is False
    assert stdio["invalid_call"]["is_error"] is True
    http = await remote_mcp(work, RunRequest(), LESSONS[43])
    assert (http["tools"], http["resources"]) == (["read_note"], ["notes://welcome"])
    assert http["insecure_url"] == "Use HTTPS or a local HTTP MCP endpoint."


async def test_agent_mcp_exercise_never_starts_a_paid_run(work, monkeypatch):
    import agent_lab.sdk
    from agent_lab.exercises import agent_mcp

    # Even with live access configured in the environment, the exercise forces it off.
    monkeypatch.setenv("LAB_ENABLE_LIVE", "true")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fixture-not-a-real-key")

    async def forbidden(*args, **kwargs):
        raise AssertionError("The offline exercise must not start the SDK")

    monkeypatch.setattr(agent_lab.sdk, "run_sdk", forbidden)
    evidence = await agent_mcp(work, RunRequest(), LESSONS[61])
    assert evidence["call_is_error"] is True
    assert "LAB_ENABLE_LIVE" in evidence["call_result"]


async def test_ci_exercise_reports_real_exit_codes(work):
    from agent_lab.exercises import ci

    evidence = await ci(work, RunRequest(), LESSONS[49])
    codes = {row["case"]: row["exit_code"] for row in evidence["runs"]}
    assert codes == {"passing lesson": 0, "unknown lesson": 2}


async def test_websocket_rejects_bad_requests_and_leaves_no_run_behind(work):
    from agent_lab.exercises import websocket

    evidence = await websocket(work, RunRequest(), LESSONS[66])
    assert evidence["server_events"] == ["started", "evidence", "done"]
    assert evidence["invalid_request_close_code"] == 1008
    assert evidence["owned_runs_after_disconnect"] == 0


def test_support_refund_requires_the_exact_approval(work):
    from agent_lab.exercises import support

    evidence = support(work, RunRequest(), LESSONS[50])
    assert [row["outcome"] for row in evidence["approval_steps"]] == [
        "Approval is not usable.",
        "Invalid approval credential.",
        "approved",
        "Approval belongs to a different action.",
        "consumed",
    ]


def test_tenant_comes_from_the_session_not_tool_arguments(work):
    from agent_lab.exercises import tenancy

    checks = {
        row["check"]: row["result"] for row in tenancy(work, RunRequest(), LESSONS[67])["checks"]
    }
    assert checks["alice passes tenant=bob"] == ["A-001"]
    assert checks["bob cancels alice's order"] is False
    assert checks["alice cancels her current order"] is True


async def test_scheduled_triggers_deduplicate_and_finish_before_shutdown(work):
    from agent_lab.exercises import scheduled

    evidence = await scheduled(work, RunRequest(), LESSONS[68])
    assert evidence["accepted"] == ["evt-1", "evt-2", "evt-3"]
    assert evidence["completed_before_exit"] == ["evt-1", "evt-2", "evt-3"]


async def test_review_applies_only_the_in_scope_patch_and_proves_it(work):
    from agent_lab.exercises import review

    evidence = await review(work, RunRequest(), LESSONS[73])
    assert (evidence["test_before_patch"], evidence["test_after_patch"]) == ("failed", "passed")
    assert evidence["out_of_scope_file_unchanged"]
    assert (work / ".github" / "workflows" / "ci.yml").read_text() == "name: CI\n"


async def test_scripted_cli_drives_the_real_client_control_protocol(work):
    from agent_lab.exercises import client_lifecycle, control, structured

    interrupted = (await structured(work, RunRequest(), LESSONS[10]))["interrupt"]
    assert interrupted["chunks_received"] == 2
    assert interrupted["result_subtype"] == "error_during_execution"
    assert interrupted["control_requests"] == ["initialize", "interrupt"]
    controlled = await control(work, RunRequest(), LESSONS[26])
    assert controlled["before"]["models"] == ["scripted-model"]
    assert controlled["after"]["models"] == ["claude-sonnet-5-5"]
    assert controlled["unsupported_request"] == "The scripted CLI does not support mcp_status."
    lifecycle = await client_lifecycle(work, RunRequest(), LESSONS[41])
    assert lifecycle["same_session"] and not lifecycle["transport_ready_after_exit"]
    assert lifecycle["query_after_disconnect"].startswith("CLIConnectionError")


def test_options_are_built_only_from_validated_requests(work):
    from agent_lab.exercises import options

    evidence = options(work, RunRequest(), LESSONS[2])
    assert [row["field"] for row in evidence["rejected"]] == [
        "max_turns",
        "max_budget_usd",
        "max_budget_usd",
        "cwd",
    ]
    assert evidence["built_options"]["max_turns"] == 2
    assert evidence["sdk_defaults"]["max_turns"] is None


async def test_path_policy_does_not_confine_child_processes(work):
    from agent_lab.exercises import sandbox

    evidence = await sandbox(work, RunRequest(), LESSONS[18])
    assert evidence["read_tool_through_policy"]["allowed"] is False
    assert evidence["child_process_read_outside"] is True
    assert not (work.parent / "outside-secret.txt").exists()  # the fixture cleans up
