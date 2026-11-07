"""Owned CLAUDE.md comparisons and strict lesson 22 evidence."""

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
            runner.start(22, RunRequest(lesson_options=options or {}, scenario=scenario))
        )
    ]
    proof = next(event.data["result"] for event in events if event.kind == "evidence")
    return proof, events


@pytest.mark.parametrize(
    "source,system_mode,rule,answer",
    [
        ("project", "preset", "alpha", "PROJECT_ALPHA_22"),
        ("project", "preset", "beta", "PROJECT_BETA_22"),
        ("project", "custom", "alpha", "PROJECT_ALPHA_22"),
        ("project", "custom", "beta", "PROJECT_BETA_22"),
        ("none", "preset", "alpha", "UNKNOWN"),
        ("none", "custom", "beta", "UNKNOWN"),
    ],
)
async def test_owned_memory_behavior_comparisons(tmp_path, source, system_mode, rule, answer):
    proof, events = await observed(tmp_path, {"source": source, "system_mode": system_mode, "rule": rule})
    report = proof["experiment"]
    assert proof["experiment_passed"]
    assert report["observed_answer"] == answer
    assert report["configured"]["setting_sources"] == (["project"] if source == "project" else [])
    assert report["configured"]["auto_memory_disabled"]
    assert report["project_file_unchanged"] and report["auto_memory_files"] == []
    assert report["calls"] == [] and report["connection_closed"]
    assert events[-1].data["status"] == "completed"
    assert check_evidence(22, proof, status="completed").status == "passed"
    assert check_evidence(22, proof, status="completed", mode="live").status == "needs-review"


@pytest.mark.parametrize("scenario", SCENARIOS[22])
async def test_recorded_negative_memory_scenarios_need_review(tmp_path, scenario):
    proof, _ = await observed(tmp_path, scenario=scenario)
    assert proof["experiment_passed"] is (scenario == "success")
    assert proof["experiment"]["expected_check"] == (
        "passed" if scenario == "success" else "needs-review"
    )


def test_memory_input_boundary_and_fixed_question():
    for values in ({"source": "user"}, {"rule": "secrets"}, {"path": "outside"}):
        with pytest.raises(ValidationError):
            lesson_request(22, RunRequest(lesson_options=values))
    with pytest.raises(LessonError):
        lesson_request(22, RunRequest(prompt="Which private files exist?"))
    with pytest.raises(LessonError):
        lesson_request(22, RunRequest(mode="live", scenario="wrong-answer"))
    assert len(guide(22).quiz) == 7
