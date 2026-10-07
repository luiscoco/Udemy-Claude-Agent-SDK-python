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

    @field_validator("prompt", "follow_up")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


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
