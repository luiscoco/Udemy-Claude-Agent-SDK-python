"""Cumulative stage checks. Positive and negative cases for every contract."""

import json
import uuid

import pytest

CONVERSATION = str(uuid.uuid4())


def test_stage_1_starts_at_a_valid_stage(coach):
    assert isinstance(coach.STAGE, int) and 1 <= coach.STAGE <= 7


# M02: validate input; accept only confirmed answers


@pytest.mark.stage(2)
def test_prepare_question_trims_valid_input(coach):
    assert coach.prepare_question("  What does query() return?  ") == "What does query() return?"
    assert coach.prepare_question("x" * 2000) == "x" * 2000


@pytest.mark.stage(2)
@pytest.mark.parametrize("value", ["", "   \n\t", "x" * 2001, None, 42, ["question"]])
def test_prepare_question_rejects_blank_oversized_or_non_text(coach, value):
    with pytest.raises(ValueError):
        coach.prepare_question(value)


@pytest.mark.stage(2)
def test_accept_answer_returns_only_completed_text(coach):
    assert coach.accept_answer({"status": "completed", "text": "## Done"}) == "## Done"


@pytest.mark.stage(2)
@pytest.mark.parametrize(
    "result",
    [
        {"status": "running", "text": "partial dra"},
        {"status": "failed", "text": "error"},
        {"status": "completed", "text": "   "},
        {"status": "completed"},
        {"text": "no status"},
    ],
)
def test_accept_answer_rejects_drafts_failures_and_empty_text(coach, result):
    with pytest.raises(ValueError):
        coach.accept_answer(result)


# M03: choose a mode and a conversation without touching credentials


@pytest.mark.stage(3)
def test_create_tutor_request_for_new_and_existing_conversations(coach):
    assert coach.create_tutor_request(" Explain hooks ", "fixture") == {
        "question": "Explain hooks",
        "mode": "fixture",
        "conversation_id": None,
    }
    request = coach.create_tutor_request("Follow up", "live", CONVERSATION)
    assert request["conversation_id"] == CONVERSATION and request["mode"] == "live"


@pytest.mark.stage(3)
@pytest.mark.parametrize(
    ("question", "mode", "conversation_id"),
    [
        ("Explain hooks", "paid", None),
        ("Explain hooks", "LIVE", None),
        ("   ", "fixture", None),
        ("Explain hooks", "fixture", "not-a-uuid"),
        ("Explain hooks", "fixture", CONVERSATION.upper()),
        ("Explain hooks", "fixture", 42),
    ],
)
def test_create_tutor_request_rejects_bad_modes_questions_and_ids(
    coach, question, mode, conversation_id
):
    with pytest.raises(ValueError):
        coach.create_tutor_request(question, mode, conversation_id)


# M04: application identity stays separate from the provider's


@pytest.mark.stage(4)
def test_continue_conversation_adopts_then_keeps_the_uuid(coach):
    assert coach.continue_conversation(None, CONVERSATION) == CONVERSATION
    assert coach.continue_conversation(CONVERSATION, CONVERSATION) == CONVERSATION


@pytest.mark.stage(4)
@pytest.mark.parametrize(
    ("current", "returned"),
    [(None, None), (None, "session-abc"), (CONVERSATION, str(uuid.uuid4())), (CONVERSATION, None)],
)
def test_continue_conversation_rejects_missing_invalid_or_switched_ids(coach, current, returned):
    with pytest.raises(ValueError):
        coach.continue_conversation(current, returned)


# M05: a structured plan must meet the exact request


def plan(*minutes):
    return {
        "days": [
            {"day": n, "topic": f"Lesson {n}", "minutes": used} for n, used in enumerate(minutes, 1)
        ]
    }


@pytest.mark.stage(5)
def test_validate_plan_accepts_exact_days_within_the_limit(coach):
    assert coach.validate_plan(plan(30, 45, 1), 3, 45) == []
    assert coach.validate_plan(json.dumps(plan(20, 20)), 2, 20) == []


@pytest.mark.stage(5)
@pytest.mark.parametrize(
    ("candidate", "days", "minutes", "mentions"),
    [
        (plan(30, 90), 2, 60, "Day 2"),
        (plan(30), 2, 60, "Expected 2 days"),
        (plan(0), 1, 60, "Day 1"),
        (plan(30.5), 1, 60, "Day 1"),
        ({"days": [{"day": 2, "topic": "x", "minutes": 5}]}, 1, 60, "Row 1"),
        ({"days": [{"day": 1, "topic": "", "minutes": 5}]}, 1, 60, "topic"),
        ({"days": [{"day": 1, "topic": "x" * 201, "minutes": 5}]}, 1, 60, "topic"),
        ({"days": [{"day": 1, "topic": "x", "minutes": 5, "extra": 1}]}, 1, 60, "Row 1"),
        ({"days": [], "notes": "extra"}, 1, 60, "only a days list"),
        (["not", "an", "object"], 1, 60, "only a days list"),
        ("Sure! Day 1: hooks", 1, 60, "JSON"),
        (plan(30), 0, 60, "Days"),
        (plan(30), 1, 121, "minutes"),
        (plan(30), True, 60, "Days"),
    ],
)
def test_validate_plan_rejects_with_a_readable_reason(coach, candidate, days, minutes, mentions):
    errors = coach.validate_plan(candidate, days, minutes)
    assert errors and any(mentions.lower() in error.lower() for error in errors), errors


# M06: inspect saved work before deciding


@pytest.mark.stage(6)
@pytest.mark.parametrize(
    ("turn", "action"),
    [
        ({"status": "completed", "text": "Saved answer"}, "reuse"),
        ({"status": "running", "text": ""}, "wait"),
        ({"status": "failed", "text": ""}, "new-turn"),
        ({"status": "uncertain", "text": ""}, "inspect"),
        ({"status": "completed", "text": "  "}, "inspect"),
        ({"status": "paused"}, "inspect"),
        (None, "inspect"),
    ],
)
def test_recover_turn_never_resubmits_uncertain_work(coach, turn, action):
    assert coach.recover_turn(turn) == action
