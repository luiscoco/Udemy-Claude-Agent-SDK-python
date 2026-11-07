"""Lesson 23 owned-plugin discovery and invocation evidence."""

import pytest
from pydantic import ValidationError

from agent_lab.config import Settings
from agent_lab.foundation_models import SCENARIOS
from agent_lab.learning import check_evidence, guide
from agent_lab.models import LessonError, RunRequest, lesson_request
from agent_lab.runtime import RunService


async def observed(tmp_path, options=None, scenario="success"):
    runner = RunService(Settings(data_dir=tmp_path))
    events = [
        event async for event in runner.events(
            runner.start(23, RunRequest(lesson_options=options or {}, scenario=scenario))
        )
    ]
    proof = next(event.data["result"] for event in events if event.kind == "evidence")
    return proof, events


@pytest.mark.parametrize(
    "options,marker,discovered,skill_call",
    [
        ({}, "PLUGIN_EXPLAIN_23", True, False),
        ({"action": "quiz"}, "PLUGIN_QUIZ_23", True, False),
        ({"action": "skill"}, "PLUGIN_SKILL_23", None, True),
        ({"enabled": False}, None, False, False),
    ],
)
async def test_owned_plugin_cases_have_correlated_offline_fixtures(tmp_path, options, marker, discovered, skill_call):
    proof, events = await observed(tmp_path, options)
    report = proof["experiment"]
    assert proof["experiment_passed"] and report["observation_passed"]
    assert report["command_discovered"] is discovered
    assert report["skill_call_correlated"] is skill_call
    if marker:
        assert report["observed_answer"] == marker
    else:
        assert report["observed_answer"] != report["marker_label"]
    assert report["plugin_files_unchanged"] and report["connection_closed"]
    assert events[-1].data["status"] == "completed"
    assert check_evidence(23, proof, status="completed").status == "passed"
    assert check_evidence(23, proof, status="completed", mode="live").status == "needs-review"


@pytest.mark.parametrize("scenario", SCENARIOS[23])
async def test_recorded_plugin_negative_scenarios_need_review(tmp_path, scenario):
    proof, _ = await observed(tmp_path, scenario=scenario)
    assert proof["experiment_passed"] is (scenario == "success")
    assert proof["experiment"]["expected_check"] == (
        "passed" if scenario == "success" else "needs-review"
    )


def test_plugin_inputs_and_fixed_prompt_are_bounded():
    for options in ({"action": "outside"}, {"path": "other-plugin"}, {"enabled": "yes"}):
        with pytest.raises(ValidationError):
            lesson_request(23, RunRequest(lesson_options=options))
    with pytest.raises(LessonError):
        lesson_request(23, RunRequest(lesson_options={"action": "skill", "enabled": False}))
    with pytest.raises(LessonError):
        lesson_request(23, RunRequest(prompt="Load my other plugin"))
    with pytest.raises(LessonError):
        lesson_request(23, RunRequest(mode="live", scenario="wrong-marker"))
    assert len(guide(23).quiz) == 7
