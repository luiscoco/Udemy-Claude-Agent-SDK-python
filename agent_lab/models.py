"""Validated contracts shared by the browser, API and command-line lessons."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["offline", "live"] = "offline"
    prompt: str = Field(default="", max_length=10000)
    follow_up: str = Field(
        default="Summarize your previous answer in one sentence.", max_length=2000
    )
    max_turns: int = Field(default=4, ge=1, le=12)
    max_budget_usd: float = Field(default=0.10, gt=0, le=1, allow_inf_nan=False)
    scenario: str = Field(default="success", min_length=1, max_length=40)
    lesson_options: dict[str, Any] = Field(default_factory=dict)

    @field_validator("prompt", "follow_up")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class QueryRunRequest(RunRequest):
    """Lesson 1's bounded request; other lessons keep their own limits."""

    model_config = ConfigDict(extra="forbid", strict=True)
    prompt: str = Field(
        default="Explain what an agent loop is in two sentences.", min_length=1, max_length=10000
    )
    max_turns: int = Field(default=1, ge=1, le=1)
    max_budget_usd: float = Field(default=0.05, gt=0, le=0.05, allow_inf_nan=False)
    scenario: Literal["success", "error", "missing-result"] = "success"

    @field_validator("prompt", mode="before")
    @classmethod
    def nonempty_prompt(cls, value: Any) -> Any:
        if isinstance(value, str):
            value = value.strip()
            if not value:
                raise ValueError("Enter a nonempty prompt for lesson 1.")
        return value


class FoundationRunRequest(RunRequest):
    model_config = ConfigDict(extra="forbid", strict=True)
    prompt: str = Field(min_length=1, max_length=10000)

    @field_validator("prompt", "follow_up", mode="before")
    @classmethod
    def trim(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value


def lesson_request(lesson_id: int, value: RunRequest | dict[str, Any]) -> RunRequest:
    """Validate before creating a task; omitted fields get the lesson's defaults."""
    data = value.model_dump(exclude_unset=True) if isinstance(value, RunRequest) else value
    parsed: RunRequest
    if 2 <= lesson_id <= 10:
        from agent_lab.curriculum import get_lesson
        from agent_lab.foundation_models import SCENARIOS, inputs

        data = dict(data)
        data.setdefault("prompt", get_lesson(lesson_id).prompt)
        parsed = FoundationRunRequest.model_validate(data)
        parsed.lesson_options = inputs(lesson_id, parsed.lesson_options).model_dump()
        if parsed.scenario not in SCENARIOS[lesson_id]:
            raise LessonError("Choose a scenario offered by this lesson.")
        if parsed.mode == "live" and parsed.scenario != "success":
            raise LessonError("Recorded negative scenarios are offline experiments only.")
        if lesson_id == 6 and not parsed.follow_up:
            raise LessonError("Enter a nonempty follow-up for the session experiment.")
        return parsed
    parsed = (QueryRunRequest if lesson_id == 1 else RunRequest).model_validate(data)
    if parsed.lesson_options:
        raise LessonError("This lesson does not accept lesson-specific options.")
    if parsed.scenario != "success" and (lesson_id != 1 or parsed.mode != "offline"):
        raise LessonError("Recorded scenarios are available only in lesson 1 offline mode.")
    return parsed


class Event(BaseModel):
    kind: str
    data: dict[str, Any] = Field(default_factory=dict)


class Lesson(BaseModel):
    id: int
    title: str
    topic: str
    objective: str
    prompt: str
    exercise: str
    live_profile: str = "query"
    notes: str = ""
    # Live-run defaults shown in the UI and used by the CLI.
    max_turns: int = 4
    max_budget_usd: float = 0.10


class LessonError(Exception):
    """A host-generated failure whose message is safe to show to the student."""
