from pathlib import Path

import pytest

from agent_lab.models import LessonError, RunRequest, lesson_request
from agent_lab.todo_lab import TASKS, local_todos, proposals, todo_items, validate_todos


def test_validator_rejects_invalid_transitions_and_shapes() -> None:
    ledger = dict.fromkeys(TASKS, "pending")
    valid = {"todos": todo_items(proposals("valid")[0])}
    assert validate_todos(ledger, valid)[0] is True
    for sequence in ("skip", "parallel"):
        assert validate_todos(ledger, {"todos": todo_items(proposals(sequence)[0])})[0] is False
    assert validate_todos(ledger, None)[0] is False
    assert validate_todos(ledger, {"todos": [{"content": [], "status": "pending"}]})[0] is False
    duplicate = {"todos": [valid["todos"][0]] * 3}
    assert validate_todos(ledger, duplicate)[0] is False
    assert ledger == dict.fromkeys(TASKS, "pending")


@pytest.mark.parametrize("sequence,accepted,posts", [
    ("valid", [True, True, True], 3),
    ("skip", [False], 0),
    ("parallel", [False], 0),
    ("reopen", [True, True, False], 2),
])
async def test_offline_todo_sequences_commit_only_accepted(tmp_path: Path, sequence: str, accepted: list[bool], posts: int) -> None:
    report = (await local_todos(tmp_path, RunRequest(lesson_options={"sequence": sequence})))["experiment"]
    assert report["experiment_passed"] is True
    assert [row["allowed"] for row in report["pre_tool_events"]] == accepted
    assert len(report["post_tool_events"]) == posts
    assert report["call_result_correlated"] is True
    assert report["ledger_verified"] is True
    assert sum(status == "in_progress" for status in report["ledger"].values()) <= 1


@pytest.mark.parametrize("scenario", ["missing-evidence", "wrong-identity", "missing-hook", "unmatched-call", "wrong-ledger", "extra-post"])
async def test_recorded_todo_negative_scenarios_need_review(tmp_path: Path, scenario: str) -> None:
    report = (await local_todos(tmp_path, RunRequest(scenario=scenario)))["experiment"]
    assert report["experiment_passed"] is False
    assert report["expected_check"] == "needs-review"


def test_request_rejects_unsupported_sequence_and_live_fixture() -> None:
    with pytest.raises(ValueError):
        lesson_request(30, {"lesson_options": {"sequence": "arbitrary"}})
    with pytest.raises(LessonError):
        lesson_request(30, {"mode": "live", "scenario": "wrong-ledger"})
