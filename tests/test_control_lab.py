from pathlib import Path

import pytest

from agent_lab.control_lab import AFTER, BEFORE, control_report, local_control
from agent_lab.foundations import Evidence
from agent_lab.models import LessonError, RunRequest, lesson_request


@pytest.mark.parametrize("options", [{}, {"target_model": "sonnet", "permission_mode": "default"}, {"action": "interrupt"}])
async def test_offline_control_variants_pass(tmp_path: Path, options: dict) -> None:
    report = (await local_control(tmp_path, RunRequest(lesson_options=options)))["experiment"]
    assert report["experiment_passed"] is True
    assert report["same_session"] is True
    assert report["post_close_query_rejected"] is True
    if options.get("action") == "interrupt":
        assert report["interrupt_after_stream_started"] is True
        assert report["turn_results"][0]["is_error"] is True
    else:
        assert report["response_markers"] == [BEFORE, AFTER]
        assert report["control_acknowledged"] is True


@pytest.mark.parametrize("scenario", ["missing-evidence", "wrong-identity", "missing-control", "wrong-model", "after-close"])
async def test_offline_control_negative_scenarios_need_review(tmp_path: Path, scenario: str) -> None:
    report = (await local_control(tmp_path, RunRequest(scenario=scenario)))["experiment"]
    assert report["experiment_passed"] is False
    assert report["expected_check"] == "needs-review"


def test_report_rejects_unobserved_model_switch(tmp_path: Path) -> None:
    state = Evidence(26, "run", tmp_path, {"action": "switch", "target_model": "sonnet", "permission_mode": "plan"}, "fixture")
    state.initialized = [{"session_id": "one"}]
    state.terminals = [{"session_id": "one", "subtype": "success", "is_error": False}]
    turns = [state.terminals[0].copy(), state.terminals[0].copy()]
    report = control_report(state, state.selected, [{"name": "set_model", "acknowledged": True}, {"name": "set_permission_mode", "acknowledged": True}], [["haiku"], ["haiku"]], turns, [BEFORE, AFTER], False, True, True, True)
    assert report["observed_model_matches_target"] is False
    assert report["experiment_passed"] is False


def test_request_rejects_unbounded_and_recorded_live_inputs() -> None:
    with pytest.raises(ValueError):
        lesson_request(26, {"lesson_options": {"target_model": "arbitrary-model"}})
    with pytest.raises(LessonError):
        lesson_request(26, {"mode": "live", "scenario": "wrong-model"})
