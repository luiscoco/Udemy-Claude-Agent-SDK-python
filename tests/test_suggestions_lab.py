"""Lesson 38's queued-turn and suggestion evidence boundaries."""

from pathlib import Path

import pytest

from agent_lab.config import Settings
from agent_lab.models import RunRequest
from agent_lab.suggestions_lab import SuggestionSession, local_suggestions


async def test_prepared_two_turn_suggestion_and_edited_send(tmp_path: Path) -> None:
    proof = await local_suggestions(tmp_path / "work", RunRequest(lesson_options={"edited": True}))
    report = proof["experiment"]
    assert proof["experiment_passed"]
    assert len(report["inputs"]) == len(report["results"]) == 3
    assert report["inputs"][2]["text"].endswith("Include one example.")
    assert report["edited_submission"]
    assert report["observed_attributed_suggestion"]
    assert report["normal_end"] and report["connection_closed"]


@pytest.mark.parametrize("scenario", ["missing-evidence", "wrong-identity", "missing-suggestion",
                                       "foreign-suggestion", "failed-result", "duplicate-result",
                                       "misordered-result", "interrupted"])
async def test_prepared_negative_evidence(tmp_path: Path, scenario: str) -> None:
    proof = await local_suggestions(tmp_path / "work", RunRequest(scenario=scenario))
    assert not proof["experiment_passed"]
    assert proof["experiment"]["expected_check"] == "needs-review"


@pytest.mark.parametrize("variant", ["omitted", "disabled", "env-off", "setting-off", "plan"])
async def test_suppressed_variants_do_not_claim_suggestion(tmp_path: Path, variant: str) -> None:
    proof = await local_suggestions(tmp_path / "work", RunRequest(lesson_options={"variant": variant}))
    assert not proof["experiment_passed"]
    assert not proof["experiment"]["observed_attributed_suggestion"]


def test_send_rejects_blank_oversized_fourth_and_closed(tmp_path: Path) -> None:
    chat = SuggestionSession(tmp_path, tmp_path / "config", Settings(), "offline")
    with pytest.raises(ValueError):
        chat.send(" ")
    with pytest.raises(ValueError):
        chat.send("x" * 2001)
    for number in range(3):
        assert chat.send(f"turn {number}")["order"] == number + 1
    with pytest.raises(ValueError):
        chat.send("fourth")
    chat.end()
    with pytest.raises(ValueError):
        chat.send("after end")
