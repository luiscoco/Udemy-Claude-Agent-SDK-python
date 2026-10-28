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
