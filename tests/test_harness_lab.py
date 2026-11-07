"""Lesson 24 structured proposals remain untrusted until the host gate passes."""

from copy import deepcopy

import pytest
from pydantic import ValidationError

from agent_lab.config import Settings
from agent_lab.foundation_models import SCENARIOS
from agent_lab.harness_lab import PROPOSALS, host_gate
from agent_lab.learning import check_evidence, guide
from agent_lab.models import LessonError, RunRequest, lesson_request
from agent_lab.runtime import RunService


async def observed(tmp_path, options=None, scenario="success"):
    runner = RunService(Settings(data_dir=tmp_path))
    events = [
        event async for event in runner.events(
            runner.start(24, RunRequest(lesson_options=options or {}, scenario=scenario))
        )
    ]
    proof = next(event.data["result"] for event in events if event.kind == "evidence")
    return proof, events


@pytest.mark.parametrize(
    "options,verdict,workers",
    [
        ({}, "accepted", ["T1", "T2"]),
        ({"approve": False}, "accepted", []),
        ({"proposal": "duplicate"}, "duplicate-owner", []),
        ({"proposal": "cycle"}, "dependency-cycle", []),
        ({"proposal": "outside"}, "outside-owned-scope", []),
    ],
)
async def test_host_gate_controls_actual_worker_effects(tmp_path, options, verdict, workers):
    proof, events = await observed(tmp_path, options)
    report = proof["experiment"]
    assert proof["experiment_passed"] and report["observation_passed"]
    assert report["host_verdict"] == verdict
    assert report["workers_started"] == workers
    assert set(report["written_hashes"]) == ({"src/tags.py", "src/search.py"} if workers else set())
    work = tmp_path / events[0].data["run_id"] / "work"
    assert (work / "src" / "tags.py").is_file() is bool(workers)
    assert (work / "src" / "search.py").is_file() is bool(workers)
    assert report["connection_closed"] and events[-1].data["status"] == "completed"
    assert check_evidence(24, proof, status="completed").status == "passed"
    assert check_evidence(24, proof, status="completed", mode="live").status == "needs-review"


@pytest.mark.parametrize("scenario", SCENARIOS[24])
async def test_recorded_negative_harness_scenarios_need_review(tmp_path, scenario):
    proof, _ = await observed(tmp_path, scenario=scenario)
    assert proof["experiment_passed"] is (scenario == "success")
    assert proof["experiment"]["expected_check"] == (
        "passed" if scenario == "success" else "needs-review"
    )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p["tasks"][0].update(files=["src/../src/tags.py"]),
        lambda p: p["tasks"][0].update(files=["src/../../.env.py"]),
        lambda p: p["tasks"][1].update(files=["src/tags.py"]),
        lambda p: p["tasks"][1].update(depends_on=["T9"]),
        lambda p: p["tasks"][0].update(id="T2"),
        lambda p: p.update(extra=True),
    ],
)
def test_host_gate_rejects_unexpected_or_unsafe_proposals(tmp_path, mutate):
    proposal = deepcopy(PROPOSALS["valid"])
    mutate(proposal)
    plan, verdict = host_gate(proposal, tmp_path)
    assert plan is None and verdict != "accepted"


def test_harness_inputs_and_fixed_prompt_are_bounded():
    for options in ({"proposal": "arbitrary"}, {"path": "outside"}, {"approve": "yes"}):
        with pytest.raises(ValidationError):
            lesson_request(24, RunRequest(lesson_options=options))
    with pytest.raises(LessonError):
        lesson_request(24, RunRequest(prompt="Run my plan"))
    with pytest.raises(LessonError):
        lesson_request(24, RunRequest(mode="live", scenario="wrong-worker"))
    assert len(guide(24).quiz) == 7
