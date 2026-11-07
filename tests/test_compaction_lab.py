from pathlib import Path

import pytest

from agent_lab.compaction_lab import bounded_result, compaction_report, local_compaction
from agent_lab.foundations import Evidence, record_call
from agent_lab.models import LessonError, RunRequest, lesson_request


def test_bound_and_marker_are_exact() -> None:
    wide = bounded_result(600, True)
    tight = bounded_result(200, True)
    assert wide["raw_characters"] == tight["raw_characters"] > 600
    assert len(wide["delivered"]) == wide["delivered_characters"]
    assert len(tight["delivered"]) == tight["delivered_characters"]
    assert wide["delivered"].startswith(tight["delivered"][:200])
    assert f"truncated {wide['raw_characters'] - 600}" in wide["marker"]
    assert f"truncated {tight['raw_characters'] - 200}" in tight["marker"]
    assert wide["summary"] == {"completed": list(range(8)), "next": "verify"}


@pytest.mark.parametrize("scenario", ["success", "missing-evidence", "wrong-identity", "missing-handler", "wrong-call", "wrong-bound"])
async def test_offline_scenarios_are_correlated(tmp_path: Path, scenario: str) -> None:
    result = await local_compaction(tmp_path, RunRequest(scenario=scenario))
    report = result["experiment"]
    assert report["experiment_passed"] is (scenario == "success")
    assert report["expected_check"] == ("passed" if scenario == "success" else "needs-review")


async def test_omitting_summary_retains_observation_but_requires_review(tmp_path: Path) -> None:
    result = await local_compaction(tmp_path, RunRequest(lesson_options={"retain_summary": False, "limit": 200}))
    report = result["experiment"]
    assert report["observation_passed"] is True
    assert report["experiment_passed"] is False
    assert report["callbacks"][0]["summary"] is None


def test_cross_run_callback_cannot_satisfy_report(tmp_path: Path) -> None:
    state = Evidence(25, "this-run", tmp_path, {"limit": 600, "retain_summary": True}, "fixture")
    state.initialized = [{"session_id": "one"}]
    state.terminals = [{"session_id": "one", "subtype": "success", "is_error": False}]
    record_call(state, "mcp__context__read_log", {}, "call")
    state.results = [{"id": "call", "run_id": "other-run", "is_error": False}]
    report = compaction_report(state, state.selected, [bounded_result(600, True)], [], ["BOUND_25"], True)
    assert report["experiment_passed"] is False


def test_request_rejects_unbounded_or_live_recorded_inputs() -> None:
    with pytest.raises(ValueError):
        lesson_request(25, {"lesson_options": {"limit": 1000}})
    with pytest.raises(LessonError):
        lesson_request(25, {"mode": "live", "scenario": "wrong-bound"})
