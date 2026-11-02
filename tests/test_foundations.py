"""Validate effects and correlated evidence in the first SDK learning block."""

import copy
from pathlib import Path

import httpx
import pytest
from claude_agent_sdk import ClaudeAgentOptions, PermissionResultDeny

from agent_lab.api import create_app
from agent_lab.config import Settings
from agent_lab.curriculum import LESSONS
from agent_lab.exercises import seed_workspace
from agent_lab.foundation_models import SCENARIOS
from agent_lab.foundations import Evidence, configure, permission_decision, run_local
from agent_lab.learning import check_evidence
from agent_lab.models import RunRequest, lesson_request
from agent_lab.runtime import RunService


@pytest.mark.parametrize("lesson,scenario", [(lesson, scenario) for lesson, scenarios in SCENARIOS.items() for scenario in scenarios if scenario not in {"success", "missing-evidence", "wrong-identity"}])
async def test_additional_named_scenarios_have_the_documented_negative_outcome(tmp_path, lesson, scenario):
    root = tmp_path / "work"
    seed_workspace(root, LESSONS[lesson])
    result = await run_local(root, RunRequest(scenario=scenario), LESSONS[lesson])
    assert result["experiment_passed"] is False
    assert result["experiment"]["expected_check"] == "needs-review"


@pytest.mark.parametrize("lesson", range(2, 11))
@pytest.mark.parametrize("scenario", ["success", "missing-evidence", "wrong-identity"])
async def test_foundation_scenarios_grade_evidence_not_prose(tmp_path, lesson, scenario):
    root = tmp_path / "work"
    seed_workspace(root, LESSONS[lesson])
    result = await run_local(root, RunRequest(scenario=scenario), LESSONS[lesson])
    assert result["experiment_passed"] is (scenario == "success")
    assert check_evidence(lesson, result, status="completed").status == (
        "passed" if scenario == "success" else "needs-review"
    )
    assert "recorded" in result["experiment"]["source"]
    assert (
        check_evidence(lesson, result, status="completed", mode="live", responded=True).status
        == "needs-review"
    )


@pytest.mark.parametrize(
    "lesson,options",
    [
        (2, {"omit_turn_limit": "true"}),
        (2, {"model": ""}),
        (3, {"tool": "Delete"}),
        (3, {"permit_tool": 1}),
        (4, {"target": "../outside.txt"}),
        (4, {"decision": "bypass"}),
        (5, {"a": True}),
        (5, {"b": "23"}),
        (5, {"a": 1e7}),
        (6, {"strategy": "unowned-session"}),
        (7, {"post_hook": "true"}),
        (8, {"worker_tools": "Bash"}),
        (8, {"worker_model": "invented"}),
        (9, {"variant": "inherit-user-settings"}),
        (10, {"payload": []}),
    ],
)
async def test_rejected_options_create_no_task_or_workspace(tmp_path, lesson, options):
    runner = RunService(Settings(data_dir=tmp_path))
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app(runner, with_ui=False)),
            base_url="http://test",
        ) as client:
            response = await client.post(
                f"/api/lessons/{lesson}/run", json={"lesson_options": options}
            )
        assert response.status_code == 422, response.text
        assert not runner.active and not list(tmp_path.iterdir())
    finally:
        await runner.close()


@pytest.mark.parametrize("lesson", range(2, 11))
async def test_negative_scenarios_cannot_be_used_as_live_results(tmp_path, lesson):
    runner = RunService(Settings(data_dir=tmp_path, enable_live=True))
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app(runner, with_ui=False)),
            base_url="http://test",
        ) as client:
            response = await client.post(
                f"/api/lessons/{lesson}/run", json={"mode": "live", "scenario": "missing-evidence"}
            )
        assert response.status_code == 422
        assert not runner.active and not list(tmp_path.iterdir())
    finally:
        await runner.close()


@pytest.mark.parametrize("tool", ["Read", "Glob", "Grep", "Bash"])
async def test_inventory_and_permission_control_actual_local_effects(tmp_path, tool):
    seed_workspace(tmp_path, LESSONS[3])
    good = await run_local(tmp_path, RunRequest(lesson_options={"tool": tool}), LESSONS[3])
    denied = await run_local(
        tmp_path, RunRequest(lesson_options={"tool": tool, "permit_tool": False}), LESSONS[3]
    )
    assert good["experiment_passed"] and not denied["experiment_passed"]
    assert good["experiment"]["local_effects"]["tool_result"] is not None
    assert denied["experiment"]["local_effects"]["tool_result"] is None
    assert (
        good["experiment"]["local_effects"]["before_hash"]
        == good["experiment"]["local_effects"]["after_hash"]
    )


@pytest.mark.parametrize("decision", ["deny", "allow", "update"])
async def test_permission_choices_apply_only_to_owned_targets(tmp_path, decision):
    seed_workspace(tmp_path, LESSONS[4])
    result = await run_local(
        tmp_path,
        RunRequest(lesson_options={"decision": decision, "content": "Owned content"}),
        LESSONS[4],
    )
    assert (tmp_path / "draft.txt").exists() is (decision == "allow")
    assert (tmp_path / "approved.txt").exists() is (decision == "update")
    assert result["experiment_passed"] is (decision == "deny")
    if decision == "deny":
        row = result["experiment"]["permission_decisions"][0]
        assert row["hash_at_decision"] is row["final_hash"] is None
        assert row["call_id"] == result["experiment"]["calls"][0]["id"]


async def test_permission_dialog_can_deny_and_unknown_targets_fail_closed(tmp_path):
    selected = lesson_request(4, {"lesson_options": {"decision": "ask"}})
    state = Evidence(4, "run-id", tmp_path, selected.lesson_options, "fixture")

    async def ask(question):
        assert "draft.txt" in question["questions"][0]["question"]
        return {question["questions"][0]["question"]: "Deny"}

    denied = await permission_decision(
        state, selected, "Write", {"file_path": "draft.txt", "content": "x"}, "call-id", ask
    )
    assert isinstance(denied, PermissionResultDeny)
    outside = await permission_decision(
        state, selected, "Write", {"file_path": "../outside.txt", "content": "x"}, "other-id", ask
    )
    assert isinstance(outside, PermissionResultDeny) and state.unsupported
    assert not (tmp_path.parent / "outside.txt").exists()


@pytest.mark.parametrize(
    "behavior,post,pre,passed",
    [
        ("observe", True, True, True),
        ("block", True, True, False),
        ("rewrite", True, True, True),
        ("observe", False, True, False),
        ("rewrite", True, False, True),
    ],
)
async def test_hook_configuration_matches_executed_read(tmp_path, behavior, post, pre, passed):
    seed_workspace(tmp_path, LESSONS[7])
    result = await run_local(
        tmp_path,
        RunRequest(lesson_options={"behavior": behavior, "post_hook": post, "pre_hook": pre}),
        LESSONS[7],
    )
    assert result["experiment_passed"] is passed
    text = result["experiment"]["local_effects"]["read_result"]
    if behavior == "rewrite" and pre:
        assert text == "An alternate owned fixture.\n"
    elif behavior != "block":
        assert text == (tmp_path / "notes.txt").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "strategy,passed", [("same-client", True), ("resume", True), ("fresh", False)]
)
async def test_session_identity_is_distinct_from_recall(tmp_path, strategy, passed):
    result = await run_local(
        tmp_path, RunRequest(lesson_options={"strategy": strategy}), LESSONS[6]
    )
    assert result["experiment_passed"] is passed
    terminals = result["experiment"]["terminal_results"]
    assert len(terminals) == 2
    assert (terminals[0]["session_id"] == terminals[1]["session_id"]) is passed


@pytest.mark.parametrize("variant", ["default", "custom", "preset", "boundary", "project"])
async def test_system_variants_echo_actual_configuration(tmp_path, variant):
    request = lesson_request(
        9,
        {
            "lesson_options": {
                "variant": variant,
                "instruction": "A fixed instruction",
                "context": "A dynamic context",
            }
        },
    )
    options = ClaudeAgentOptions(setting_sources=[])
    echo = configure(options, LESSONS[9], request, tmp_path)
    assert echo["system_prompt"] == options.system_prompt
    assert options.setting_sources == (["project"] if variant == "project" else [])
    if variant == "project":
        assert (tmp_path / "CLAUDE.md").read_text(encoding="utf-8").strip() == "A fixed instruction"
    if variant == "boundary":
        assert "SYSTEM_PROMPT_DYNAMIC_BOUNDARY" in options.system_prompt


@pytest.mark.parametrize("scenario", ["invalid-arguments", "ambiguous-handler"])
async def test_custom_handler_rejections_and_ambiguity_need_review(tmp_path, scenario):
    result = await run_local(tmp_path, RunRequest(scenario=scenario), LESSONS[5])
    assert not result["experiment_passed"]
    if scenario == "invalid-arguments":
        assert result["experiment"]["local_effects"]["handler_count"] == 0


@pytest.mark.parametrize("operation", ["interrupt", "abort"])
async def test_stop_experiment_is_separate_from_schema_acceptance(tmp_path, operation):
    result = await run_local(
        tmp_path,
        RunRequest(scenario="stop-control", lesson_options={"stop_experiment": operation}),
        LESSONS[10],
    )
    assert not result["experiment_passed"]
    comparison = result["experiment"]["local_effects"]["stop_comparison"]
    assert comparison["continued"] is (operation == "interrupt")
    assert ("interrupt" in comparison["control_requests"]) is (operation == "interrupt")


def test_call_matching_requires_correct_run_id_and_result_id(tmp_path):
    state = Evidence(3, "run", tmp_path, {}, "live SDK stream and actual host callbacks")
    state.configured = {"tools": ["Read"]}
    state.initialized = [{"session_id": "session", "tools": ["Read"]}]
    state.terminals = [{"session_id": "session", "subtype": "success", "is_error": False}]
    state.calls = [{"run_id": "run", "id": "call", "name": "Read", "arguments": {}}]
    state.results = [{"run_id": "run", "id": "call", "is_error": False}]
    assert state.report()["experiment_passed"]
    for field, value in [("run_id", "other"), ("id", "other"), ("is_error", True)]:
        altered = copy.deepcopy(state)
        altered.results[0][field] = value
        assert not altered.report()["experiment_passed"]
    duplicate = copy.deepcopy(state)
    duplicate.results.append({"run_id": "run", "id": "call", "is_error": True})
    assert not duplicate.report()["experiment_passed"]


def test_absence_is_not_confused_with_an_unobserved_denial_snapshot(tmp_path):
    state = Evidence(4, "run", tmp_path, {}, "fixture")
    state.terminals = [{"session_id": "session", "subtype": "success", "is_error": False}]
    state.calls = [{"run_id": "run", "id": "call", "name": "Write", "arguments": {}}]
    state.decisions = [
        {
            "run_id": "run",
            "call_id": "call",
            "decision": "deny",
            "supported": True,
            "target": "draft.txt",
            "hash_at_decision": None,
        }
    ]
    assert state.report()["experiment_passed"]
    del state.decisions[0]["hash_at_decision"]
    assert not state.report()["experiment_passed"]


@pytest.mark.parametrize("lesson", [4, 7])
async def test_host_path_guard_stays_enabled_without_the_teaching_hook(tmp_path, lesson):
    from agent_lab.foundations import experiment_hooks
    from agent_lab.hooks import call_hook

    selected = lesson_request(
        lesson, {"lesson_options": {"pre_hook": False} if lesson == 7 else {}}
    )
    state = Evidence(lesson, "run", tmp_path, selected.lesson_options, "fixture")

    async def emit(event):
        pass

    config = experiment_hooks(state, emit)
    output = await call_hook(
        config["PreToolUse"][0].hooks[0],
        {"tool_name": "Read", "tool_input": {"file_path": "../outside.txt"}},
        "call",
    )
    assert output["hookSpecificOutput"]["permissionDecision"] == "deny"


async def test_cancellation_while_waiting_for_permission_leaves_no_write(tmp_path):
    runner = RunService(Settings(data_dir=tmp_path))
    try:
        handle = runner.start(4, RunRequest(lesson_options={"decision": "ask"}))
        events = []
        async for event in runner.events(handle):
            events.append(event)
            if event.kind == "question":
                await runner.cancel(handle)
        assert events[-1].data["status"] == "cancelled"
        assert not runner.active and not handle.questions
        assert not (tmp_path / handle.id / "work" / "draft.txt").exists()
    finally:
        await runner.close()


def test_all_foundation_assessments_have_seven_explained_questions_and_exact_excerpts():
    from agent_lab.foundations import source_sections
    from agent_lab.learning import guide

    for lesson in range(2, 11):
        item = guide(lesson)
        assert len(item.quiz) == 7
        for question in item.quiz:
            assert question.options[question.correct].explanation.startswith("Correct.")
            if question.code:
                compile(question.code, f"lesson-{lesson}-question.py", "exec")
        sections = source_sections(lesson)
        assert len(sections) == 3
        lines = (
            (Path(__file__).resolve().parents[1] / sections[0]["path"])
            .read_text(encoding="utf-8")
            .splitlines()
        )
        for section in sections:
            assert section["code"].splitlines() == lines[section["start"] - 1 : section["end"]]
            assert section["question"]


def test_cli_reads_lesson_options_and_follow_up_from_explicit_inputs(tmp_path, monkeypatch):
    import json
    import sys

    from agent_lab import cli

    source = tmp_path / "options.json"
    source.write_text(json.dumps({"strategy": "resume"}), encoding="utf-8-sig")
    captured = []

    async def run(number, request):
        captured.append((number, request))
        return 0

    monkeypatch.setattr(cli, "run_lesson", run)
    monkeypatch.setattr(sys, "argv", ["agent-lab", "lesson", "6", "--lesson-options-file", str(source), "--follow-up", "What label did I mention?"])
    with pytest.raises(SystemExit) as exit_info:
        cli.main()
    assert exit_info.value.code == 0
    number, request = captured[0]
    assert number == 6 and request.lesson_options == {"strategy": "resume"}
    assert request.follow_up == "What label did I mention?"
    assert request.prompt == LESSONS[6].prompt


def test_sdk_options_are_retained_for_failed_run_inspection():
    from agent_lab.models import Event
    from agent_lab.output import OutputState

    state = OutputState(mode="live")
    state.apply(Event(kind="options", data={"sdk_options": {"max_turns": None, "include_partial_messages": False}}))
    state.apply(Event(kind="done", data={"status": "failed"}))
    assert state.options[0]["sdk_options"]["max_turns"] is None
    assert state.status == "failed"
