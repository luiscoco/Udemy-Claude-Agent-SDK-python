from pathlib import Path

import pytest

from agent_lab.models import LessonError, RunRequest, lesson_request
from agent_lab.retry_lab import KEY, ORDER, local_retry, refund_attempt


def test_idempotent_refund_attempts_apply_one_key() -> None:
    ledger: set[str] = set()
    rows = [refund_attempt("recover", attempt, ledger, ORDER) for attempt in range(1, 4)]
    assert [row["status"] for row in rows] == ["ambiguous-after-write", "transient-timeout", "already-applied"]
    assert [row["is_error"] for row in rows] == [True, True, False]
    assert ledger == {KEY}
    assert [row["writes_applied"] for row in rows] == [1, 1, 1]


@pytest.mark.parametrize("outcome,expected_decisions,effects", [
    ("recover", ["retry", "retry", "confirmed"], 1),
    ("permanent", ["reject"], 0),
    ("exhausted", ["retry", "retry", "exhausted"], 1),
])
async def test_offline_retry_outcomes(tmp_path: Path, outcome: str, expected_decisions: list[str], effects: int) -> None:
    report = (await local_retry(tmp_path, RunRequest(lesson_options={"outcome": outcome})))["experiment"]
    assert report["experiment_passed"] is True
    assert report["call_result_correlated"] is True
    assert [row["decision"] for row in report["decisions"]] == expected_decisions
    assert len(report["ledger_keys"]) == effects
    assert len(report["callbacks"]) <= report["max_attempts"] == 3


@pytest.mark.parametrize("scenario", ["missing-evidence", "wrong-identity", "missing-handler", "unmatched-result", "duplicate-write", "wrong-stop"])
async def test_offline_negative_retry_scenarios_need_review(tmp_path: Path, scenario: str) -> None:
    report = (await local_retry(tmp_path, RunRequest(scenario=scenario)))["experiment"]
    assert report["experiment_passed"] is False
    assert report["expected_check"] == "needs-review"


def test_request_rejects_arbitrary_outcomes_and_live_recorded_scenarios() -> None:
    with pytest.raises(ValueError):
        lesson_request(28, {"lesson_options": {"outcome": "unbounded"}})
    with pytest.raises(LessonError):
        lesson_request(28, {"mode": "live", "scenario": "duplicate-write"})
