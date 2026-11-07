from types import SimpleNamespace

import pytest

from agent_lab.elicitation_lab import (
    ACCEPT_CONTENT,
    FORM_MESSAGE,
    known_request,
    local_elicitation,
)
from agent_lab.foundation_models import SCENARIOS
from agent_lab.models import LessonError, RunRequest, lesson_request


def test_only_owned_form_shape_is_known():
    known = SimpleNamespace(message=FORM_MESSAGE, requestedSchema={"properties": dict.fromkeys(ACCEPT_CONTENT)})
    assert known_request(known)
    assert not known_request(SimpleNamespace(message="Other", requestedSchema=known.requestedSchema))
    assert not known_request(SimpleNamespace(message=FORM_MESSAGE, requestedSchema={"properties": {"name": {}}}))


@pytest.mark.parametrize("action", ["accept", "decline", "cancel"])
async def test_actual_python_mcp_server_outcomes(tmp_path, action):
    proof = await local_elicitation(tmp_path, RunRequest(lesson_options={"action": action}))
    report = proof["experiment"]
    assert report["experiment_passed"]
    assert report["callback_verified"]
    assert report["server_outcome_verified"]
    outcome = report["mcp_server_outcomes"][0]
    assert outcome["booked"] is (action == "accept")
    if action == "accept":
        assert outcome["external_calendar"] is False
    else:
        assert outcome["state"] == action


@pytest.mark.parametrize("scenario", [key for key in SCENARIOS[33] if key != "success"])
async def test_recorded_mismatches_need_review(tmp_path, scenario):
    proof = await local_elicitation(tmp_path, RunRequest(scenario=scenario))
    assert not proof["experiment_passed"]
    assert proof["experiment"]["expected_check"] == "needs-review"


def test_live_rejects_synthetic_scenarios_and_changed_prompt():
    with pytest.raises(LessonError):
        lesson_request(33, RunRequest(mode="live", scenario="wrong-action"))
    with pytest.raises(LessonError):
        lesson_request(33, RunRequest(prompt="different"))
