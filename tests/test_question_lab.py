import pytest
from claude_agent_sdk.types import PermissionResultAllow, PermissionResultDeny

from agent_lab.config import Settings
from agent_lab.foundation_models import SCENARIOS
from agent_lab.models import LessonError, RunRequest, lesson_request
from agent_lab.question_lab import (
    execute_question,
    local_question,
    question_input,
    question_options,
    validate_question,
)


def test_exact_question_boundary_and_sdk_options(tmp_path):
    valid = question_input()
    assert validate_question(valid)
    for mutation in (
        lambda item: item["questions"][0].update(header="Other"),
        lambda item: item["questions"][0].update(options=item["questions"][0]["options"][:1]),
        lambda item: item["questions"][0].update(priority="high"),
    ):
        candidate = question_input()
        mutation(candidate)
        assert not validate_question(candidate)
    options = question_options(tmp_path, tmp_path / "config", RunRequest(), Settings(), lambda *_: None)
    assert options.tools == ["AskUserQuestion"]
    assert options.allowed_tools == []
    assert options.can_use_tool is not None


@pytest.mark.parametrize("answer", ["Concise", "Detailed"])
@pytest.mark.parametrize("scenario", SCENARIOS[31])
async def test_question_scenarios_have_bounded_outcomes(tmp_path, answer, scenario):
    proof = await local_question(tmp_path, RunRequest(lesson_options={"answer": answer}, scenario=scenario))
    report = proof["experiment"]
    assert report["experiment_passed"] is (scenario == "success")
    assert report["expected_check"] == ("passed" if scenario == "success" else "needs-review")
    assert report["connection_closed"]
    assert report["simulated_answer"] == answer


async def test_callback_routes_exact_answer_and_denies_wrong_tool(tmp_path, monkeypatch):
    import agent_lab.question_lab as question_lab

    captured = []
    original = question_lab.question_options

    def wrap(root, config, request, settings, callback):
        captured.append(callback)
        return original(root, config, request, settings, callback)

    monkeypatch.setattr(question_lab, "question_options", wrap)
    async def ignore(_):
        pass

    await execute_question(tmp_path, RunRequest(lesson_options={"answer": "Detailed"}), Settings(), ignore)
    allowed = await captured[0]("AskUserQuestion", question_input(), None)
    denied = await captured[0]("Bash", {"command": "pwd"}, None)
    assert isinstance(allowed, PermissionResultAllow)
    assert allowed.updated_input["answers"] == {"Which teaching style?": "Detailed"}
    assert isinstance(denied, PermissionResultDeny)


def test_live_rejects_recorded_scenarios_and_changed_prompt():
    with pytest.raises(LessonError):
        lesson_request(31, RunRequest(mode="live", scenario="missing-callback"))
    with pytest.raises(LessonError):
        lesson_request(31, RunRequest(prompt="different"))
