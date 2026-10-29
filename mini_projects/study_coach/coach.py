"""Your Study Coach host contracts. Implement one stage at a time, then raise STAGE.

Check your work:      uv run agent-lab coach check
Compare a reference:  uv run agent-lab coach check --reference   (never marks your work done)

Each stage prompt is in mini_projects/study_coach/prompts/. The Study Coach page
(http://127.0.0.1:8080/coach) runs this file, so every stage you finish unlocks a feature.
"""

from collections.abc import Mapping
from typing import Any

# Raise this after each stage passes; tests for later stages are skipped until you do.
STAGE = 1
MAX_QUESTION = 2000
MODES = ("fixture", "live")


def prepare_question(value: object) -> str:
    """M02: return the trimmed question.

    Raise ValueError for non-text, blank, or longer than MAX_QUESTION characters.
    """
    raise NotImplementedError("TODO M02: implement prepare_question")


def accept_answer(result: Mapping[str, Any]) -> str:
    """M02: return result["text"] only when result["status"] == "completed" and the
    text is nonempty; otherwise raise ValueError. A streamed draft never counts."""
    raise NotImplementedError("TODO M02: implement accept_answer")


def create_tutor_request(
    question: object, mode: object, conversation_id: object = None
) -> dict[str, Any]:
    """M03: return {"question", "mode", "conversation_id"}.

    Allow only the modes in MODES, validate the question with prepare_question, and
    accept conversation_id only when it is None or a canonical UUID string.
    """
    raise NotImplementedError("TODO M03: implement create_tutor_request")


def continue_conversation(current_id: str | None, returned_id: object) -> str:
    """M04: for a new conversation (current_id is None) accept a valid returned UUID;
    for an existing one, the returned id must equal current_id. Raise ValueError otherwise."""
    raise NotImplementedError("TODO M04: implement continue_conversation")


def validate_plan(plan: object, days: object, minutes: object) -> list[str]:
    """M05: return a list of readable errors (empty when valid).

    Limits: days 1-7 and minutes 5-120, both whole numbers. The plan (a dict, or a JSON
    string from the model) must be {"days": [...]} with exactly `days` rows, each
    {"day", "topic", "minutes"}: day counts 1, 2, 3..., topic is 1-200 characters, and
    minutes is a whole number from 1 to the daily limit.
    """
    raise NotImplementedError("TODO M05: implement validate_plan")


def recover_turn(turn: object) -> str:
    """M06: decide what to do with a saved turn, without calling the model.

    Return "reuse" for a completed nonempty answer, "wait" for running, "new-turn" for a
    confirmed failure, and "inspect" for anything uncertain or unrecognised.
    """
    raise NotImplementedError("TODO M06: implement recover_turn")
