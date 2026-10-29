import asyncio
import os
import subprocess
import sys
import uuid

import pytest

from agent_lab.config import ROOT, Settings
from agent_lab.models import LessonError
from agent_lab.study_coach import (
    PROJECT,
    SHORTCUTS,
    CoachService,
    fixture_plan,
    load_coach,
    prepared_answer,
    shortcut_question,
    stage_of,
)


def run_stage_checks(implementation):
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(PROJECT)],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=os.environ | {"COACH_IMPLEMENTATION": implementation},
        timeout=120,
    )


def test_reference_passes_every_stage_and_the_learner_file_loads():
    reference = run_stage_checks("reference")
    assert reference.returncode == 0 and "skipped" not in reference.stdout, reference.stdout
    # The learner file is the student's work in progress: the course suite only checks that
    # it loads. Students verify it themselves with `uv run agent-lab coach check`.
    assert 1 <= stage_of(load_coach("learner")) <= 7


def test_prepared_answers_come_from_the_lesson_content():
    assert "query(" in prepared_answer(1, "code", "q")
    assert "Common belief" in prepared_answer(1, "failure", "q")
    assert prepared_answer(None, None, "How do hooks work?").startswith("### A first step")
    for kind in SHORTCUTS:
        assert "query()" in shortcut_question(kind, 1)
        assert prepared_answer(1, kind, "q").startswith("### Lesson 1: query()")


def test_fixture_plans_pass_and_fail_the_reference_validator():
    reference = load_coach("reference")
    assert reference.validate_plan(fixture_plan([1, 3, 5], 3, 30, invalid=False), 3, 30) == []
    errors = reference.validate_plan(fixture_plan([1, 3, 5], 3, 30, invalid=True), 3, 30)
    assert errors and errors[0].startswith("Day 2")


async def wait(service, turn_id):
    for _ in range(200):
        turn = service.public_turn(turn_id)
        if turn["status"] != "running":
            return turn
        await asyncio.sleep(0.05)
    raise AssertionError("turn did not finish")


async def test_fixture_conversation_keeps_identity_and_shows_the_earlier_question(tmp_path):
    service = CoachService(Settings(data_dir=tmp_path))
    first = service.submit("What does query() return?", "fixture", None, lesson_id=1, kind="code")
    assert (await wait(service, first["turn_id"]))["status"] == "completed"
    follow = service.submit("And the result?", "fixture", first["conversation_id"], lesson_id=1)
    turn = await wait(service, follow["turn_id"])
    assert follow["conversation_id"] == first["conversation_id"]
    assert "Earlier you asked: What does query() return?" in turn["text"]


async def test_mode_cannot_change_inside_a_conversation(tmp_path, monkeypatch):
    service = CoachService(Settings(data_dir=tmp_path, enable_live=True))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fixture-not-a-real-key")
    first = service.submit("Explain hooks.", "fixture", None)
    await wait(service, first["turn_id"])
    with pytest.raises(ValueError, match="changing mode"):
        service.submit("Explain more.", "live", first["conversation_id"], consent=True)


def test_live_turns_need_live_access_and_consent(tmp_path, monkeypatch):
    with pytest.raises(PermissionError, match="disabled"):
        CoachService(Settings(data_dir=tmp_path)).submit("Hi there", "live", None, consent=True)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fixture-not-a-real-key")
    service = CoachService(Settings(data_dir=tmp_path, enable_live=True))
    with pytest.raises(PermissionError, match="authorize"):
        service.submit("Hi there", "live", None)


def test_a_restart_marks_running_turns_uncertain_and_blocks_the_conversation(tmp_path):
    service = CoachService(Settings(data_dir=tmp_path))
    conversation = str(uuid.uuid4())
    service.conversations[conversation] = {
        "mode": "fixture",
        "turns": ["t1"],
        "session_id": None,
        "blocked": False,
    }
    service.turns["t1"] = {
        "id": "t1",
        "conversation_id": conversation,
        "question": "q",
        "mode": "fixture",
        "status": "running",
        "draft": "half an ans",
        "text": "",
        "error": "",
    }
    service._save()
    restarted = CoachService(Settings(data_dir=tmp_path))
    assert restarted.public_turn("t1")["status"] == "uncertain"
    with pytest.raises(LessonError, match="uncertain"):
        restarted.submit("Continue?", "fixture", conversation)


def stub_query(monkeypatch, seen, fail=False):
    import claude_agent_sdk
    from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock

    async def fake_query(prompt, options):
        seen.append(options.resume)
        if fail:
            raise ConnectionError("network dropped after sending")
        yield AssistantMessage(content=[TextBlock(text="Live answer.")], model="m")
        yield ResultMessage(
            subtype="success",
            duration_ms=1,
            duration_api_ms=1,
            is_error=False,
            num_turns=1,
            session_id="sdk-session-1",
            total_cost_usd=0.001,
            result="Live answer.",
        )

    monkeypatch.setattr(claude_agent_sdk, "query", fake_query)
    monkeypatch.setattr("agent_lab.doctor.resolve_cli_path", lambda settings: "claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fixture-not-a-real-key")


async def test_live_follow_ups_resume_the_server_held_session(tmp_path, monkeypatch):
    seen: list = []
    stub_query(monkeypatch, seen)
    service = CoachService(Settings(data_dir=tmp_path, enable_live=True))
    first = service.submit("Explain hooks.", "live", None, consent=True, lesson_id=7)
    assert (await wait(service, first["turn_id"]))["text"] == "Live answer."
    second = service.submit("And PostToolUse?", "live", first["conversation_id"], consent=True)
    await wait(service, second["turn_id"])
    assert seen == [None, "sdk-session-1"]
    assert "session_id" not in service.public_turn(second["turn_id"])


async def test_a_failed_live_call_is_uncertain_and_never_retried(tmp_path, monkeypatch):
    seen: list = []
    stub_query(monkeypatch, seen, fail=True)
    service = CoachService(Settings(data_dir=tmp_path, enable_live=True))
    started = service.submit("Explain hooks.", "live", None, consent=True)
    turn = await wait(service, started["turn_id"])
    assert turn["status"] == "uncertain" and len(seen) == 1
    assert load_coach("reference").recover_turn(turn) == "inspect"


def test_start_here_cards_are_valid_python_with_answerable_checks():
    import ast

    from agent_lab.study_coach import INTRO_CONCEPTS

    assert [card["id"] for card in INTRO_CONCEPTS] == ["llm", "agent", "harness", "sdk", "first-query"]
    for card in INTRO_CONCEPTS:
        ast.parse(card["code"])
        check = card["check"]
        assert 0 <= check["correct"] < len(check["choices"]) and check["why"]


def test_every_lesson_cites_its_real_exercise_source():
    from agent_lab.config import ROOT
    from agent_lab.curriculum import LESSONS
    from agent_lab.exercises import exercise_location

    for lesson in LESSONS.values():
        path, start, end = exercise_location(lesson.exercise)
        lines = (ROOT / path).read_text(encoding="utf-8").splitlines()[start - 1 : end]
        assert any(f"def {lesson.exercise}(" in line for line in lines[:3]) or any(
            line.startswith("@exercise") for line in lines[:3]
        ), (lesson.id, path, start)
