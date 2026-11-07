"""Lesson 21 host effects, discovery controls and evidence correlation."""

import pytest
from pydantic import ValidationError

from agent_lab.config import Settings
from agent_lab.curriculum import get_lesson
from agent_lab.exercises import seed_workspace
from agent_lab.foundation_models import SCENARIOS
from agent_lab.foundations import Evidence, record_call
from agent_lab.learning import check_evidence, guide
from agent_lab.models import LessonError, RunRequest, lesson_request
from agent_lab.runtime import RunService
from agent_lab.slash_commands import MARKERS, command_report, prepare


async def record(tmp_path, options=None, scenario="success"):
    runner = RunService(Settings(data_dir=tmp_path))
    events = [
        e async for e in runner.events(
            runner.start(21, RunRequest(lesson_options=options or {}, scenario=scenario))
        )
    ]
    proof = next(e.data["result"] for e in events if e.kind == "evidence")
    return proof, events


@pytest.mark.parametrize("template", ["summary", "quiz"])
async def test_owned_templates_and_correlated_offline_fixture(tmp_path, template):
    proof, events = await record(tmp_path, {"template": template})
    report = proof["experiment"]
    assert proof["experiment_passed"]
    assert report["command_inventory"] == ["lesson-summary"]
    assert report["read_correlated"] and report["marker_observed"]
    assert report["marker_label"] == MARKERS[template]
    assert report["fixture_hashes_unchanged"] and report["connection_closed"]
    assert events[-1].data["status"] == "completed"
    assert check_evidence(21, proof, status="completed", mode="offline").status == "passed"
    assert check_evidence(21, proof, status="completed", mode="live").status == "needs-review"


async def test_no_project_control_observes_absence_and_needs_review(tmp_path):
    proof, _ = await record(tmp_path, {"source": "none"})
    report = proof["experiment"]
    assert report["command_inventory"] == []
    assert report["observation_passed"] and not report["experiment_passed"]
    assert check_evidence(21, proof, status="completed").status == "needs-review"


@pytest.mark.parametrize("scenario", SCENARIOS[21])
async def test_recorded_negative_scenarios_do_not_pass(tmp_path, scenario):
    proof, _ = await record(tmp_path, scenario=scenario)
    assert proof["experiment_passed"] is (scenario == "success")


@pytest.mark.parametrize("damage", ["inventory", "result", "marker", "identity", "hash"])
def test_report_recomputes_correlations_from_raw_observations(tmp_path, damage):
    root = tmp_path / "work"
    seed_workspace(root, get_lesson(21))
    root = root.resolve()
    before = prepare(root, "summary")
    state = Evidence(21, "run", root, {"source": "project", "template": "summary"}, "fixture")
    state.configured = {"setting_sources": ["project"]}
    state.initialized = [{"session_id": "owned"}]
    state.terminals = [{"session_id": "owned", "subtype": "success", "is_error": False}]
    record_call(state, "Read", {"file_path": str(root / "notes.txt")}, "call")
    state.results = [{"id": "call", "run_id": "run", "is_error": False}]
    inventory, texts, after = ["lesson-summary"], [MARKERS["summary"]], dict(before)
    assert command_report(state, state.selected, inventory, texts, before, after, True, "/lesson-summary")["experiment_passed"]
    if damage == "inventory":
        inventory.clear()
    elif damage == "result":
        state.results[0]["id"] = "foreign"
    elif damage == "marker":
        texts.clear()
    elif damage == "identity":
        state.terminals[0]["session_id"] = "foreign"
    else:
        after["note"] = "changed"
    assert not command_report(state, state.selected, inventory, texts, before, after, True, "/lesson-summary")["experiment_passed"]


def test_strict_inputs_and_live_negative_preflight():
    with pytest.raises(ValidationError):
        lesson_request(21, RunRequest(lesson_options={"source": "user"}))
    with pytest.raises(ValidationError):
        lesson_request(21, RunRequest(lesson_options={"template": "../../secret"}))
    with pytest.raises(ValidationError):
        lesson_request(21, RunRequest(lesson_options={"path": "outside"}))
    with pytest.raises(LessonError):
        lesson_request(21, RunRequest(mode="live", scenario="missing-command"))
    assert len(guide(21).quiz) == 7
