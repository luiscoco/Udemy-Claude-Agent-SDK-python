import pytest

from agent_lab.config import Settings
from agent_lab.foundation_models import SCENARIOS
from agent_lab.models import LessonError, RunRequest, lesson_request
from agent_lab.plan_lab import local_plan_mode, plan_options, plan_prompt


def test_plan_options_start_in_plan_mode_without_model_tools(tmp_path):
    options = plan_options(tmp_path, tmp_path / "config", RunRequest(), Settings())
    assert options.permission_mode == "plan"
    assert options.tools == []
    assert options.allowed_tools == []
    assert options.setting_sources == []
    assert "duplicate" in plan_prompt("duplicate") or "src/tags.py" in plan_prompt("duplicate")


@pytest.mark.parametrize("selection", [{}, {"approve": False}, {"proposal": "duplicate"}])
async def test_approved_review_and_rejected_paths(tmp_path, selection):
    proof = await local_plan_mode(tmp_path, RunRequest(lesson_options=selection))
    report = proof["experiment"]
    assert report["experiment_passed"]
    assert report["mode_sequence_verified"]
    assert report["terminal_sessions_verified"]
    if selection:
        assert report["workers_started"] == []
        assert not (tmp_path / "src" / "tags.py").exists()
    else:
        assert set(report["workers_started"]) == {"T1", "T2"}
        assert (tmp_path / "src" / "tags.py").exists()


@pytest.mark.parametrize("scenario", [key for key in SCENARIOS[32] if key != "success"])
async def test_negative_scenarios_need_review(tmp_path, scenario):
    proof = await local_plan_mode(tmp_path, RunRequest(scenario=scenario))
    assert not proof["experiment_passed"]
    assert proof["experiment"]["expected_check"] == "needs-review"
    if scenario in {"missing-evidence", "wrong-identity", "missing-proposal"}:
        assert not (tmp_path / "src" / "tags.py").exists()


def test_live_rejects_synthetic_negative_and_changed_prompt():
    with pytest.raises(LessonError):
        lesson_request(32, RunRequest(mode="live", scenario="missing-switch"))
    with pytest.raises(LessonError):
        lesson_request(32, RunRequest(prompt="different"))
