"""Completed Study Coach host contracts for all seven stages.

Check your work:      uv run agent-lab coach check
Compare a reference:  uv run agent-lab coach check --reference   (never marks your work done)

Each stage prompt is in mini_projects/study_coach/prompts/. The Study Coach page
(http://127.0.0.1:8080/coach) runs this file, so every stage you finish unlocks a feature.
"""

import json
import uuid
from collections.abc import Mapping
from typing import Any, TypeGuard

# All contracts are implemented; `agent-lab coach check` verifies every stage.
STAGE = 7
MAX_QUESTION = 2000
MODES = ("fixture", "live")


def prepare_question(value: object) -> str:
    """M02: return the trimmed question.

    Raise ValueError for non-text, blank, or longer than MAX_QUESTION characters.
    """
    if not isinstance(value, str):
        raise ValueError("The question must be text.")
    question = value.strip()
    if not question:
        raise ValueError("Write a question first.")
    if len(question) > MAX_QUESTION:
        raise ValueError(f"Keep the question under {MAX_QUESTION} characters.")
    return question


def accept_answer(result: Mapping[str, Any]) -> str:
    """M02: return result["text"] only when result["status"] == "completed" and the
    text is nonempty; otherwise raise ValueError. A streamed draft never counts."""
    if result.get("status") != "completed":
        raise ValueError("The answer is not complete, so it cannot replace the draft.")
    text = result.get("text")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("The completed answer is empty.")
    return text


def _is_conversation_id(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return str(uuid.UUID(value)) == value
    except ValueError:
        return False


def create_tutor_request(
    question: object, mode: object, conversation_id: object = None
) -> dict[str, Any]:
    """M03: return {"question", "mode", "conversation_id"}.

    Allow only the modes in MODES, validate the question with prepare_question, and
    accept conversation_id only when it is None or a canonical UUID string.
    """
    if mode not in MODES:
        raise ValueError("Mode must be fixture or live.")
    if conversation_id is not None and not _is_conversation_id(conversation_id):
        raise ValueError("The conversation id must be an application UUID.")
    return {
        "question": prepare_question(question),
        "mode": mode,
        "conversation_id": conversation_id,
    }


def continue_conversation(current_id: str | None, returned_id: object) -> str:
    """M04: for a new conversation (current_id is None) accept a valid returned UUID;
    for an existing one, the returned id must equal current_id. Raise ValueError otherwise."""
    if not _is_conversation_id(returned_id):
        raise ValueError("The server did not return a valid conversation id.")
    if current_id is not None and returned_id != current_id:
        raise ValueError("The server answered a different conversation.")
    return str(returned_id)


def _whole(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool)


def validate_plan(plan: object, days: object, minutes: object) -> list[str]:
    """M05: return a list of readable errors (empty when valid).

    Limits: days 1-7 and minutes 5-120, both whole numbers. The plan (a dict, or a JSON
    string from the model) must be {"days": [...]} with exactly `days` rows, each
    {"day", "topic", "minutes"}: day counts 1, 2, 3..., topic is 1-200 characters, and
    minutes is a whole number from 1 to the daily limit.
    """
    errors = []
    if not (_whole(days) and 1 <= days <= 7):
        errors.append("Days must be a whole number from 1 to 7.")
    if not (_whole(minutes) and 5 <= minutes <= 120):
        errors.append("Daily minutes must be a whole number from 5 to 120.")
    if errors:
        return errors
    assert _whole(days) and _whole(minutes)
    if isinstance(plan, str):
        try:
            plan = json.loads(plan)
        except json.JSONDecodeError:
            return ["The plan is not valid JSON."]
    if not isinstance(plan, dict) or set(plan) != {"days"} or not isinstance(plan["days"], list):
        return ["The plan must be an object with only a days list."]
    rows = plan["days"]
    if len(rows) != days:
        errors.append(f"Expected {days} days, got {len(rows)}.")
    for number, row in enumerate(rows, 1):
        if not isinstance(row, dict) or set(row) != {"day", "topic", "minutes"}:
            errors.append(f"Row {number} must have exactly day, topic and minutes.")
            continue
        if not _whole(row["day"]) or row["day"] != number:
            errors.append(f"Row {number} is numbered {row['day']!r}; days must count 1, 2, 3...")
        topic = row["topic"]
        if not isinstance(topic, str) or not topic.strip() or len(topic) > 200:
            errors.append(f"Day {number} needs a topic of 1 to 200 characters.")
        used = row["minutes"]
        if not (_whole(used) and 1 <= used <= minutes):
            errors.append(f"Day {number} uses {used!r} minutes; allowed is 1 to {minutes}.")
    return errors


def recover_turn(turn: object) -> str:
    """M06: decide what to do with a saved turn, without calling the model.

    Return "reuse" for a completed nonempty answer, "wait" for running, "new-turn" for a
    confirmed failure, and "inspect" for anything uncertain or unrecognised.
    """
    if not isinstance(turn, Mapping):
        return "inspect"
    status, text = turn.get("status"), turn.get("text")
    if status == "completed" and isinstance(text, str) and text.strip():
        return "reuse"
    if status == "running":
        return "wait"
    if status == "failed":
        return "new-turn"
    return "inspect"
