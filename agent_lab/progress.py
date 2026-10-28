"""Export and import a learner's progress as a validated JSON file.

Progress lives in per-browser storage. Exporting lets a student move it to another
browser or keep a backup; importing treats the file as untrusted input and accepts
only the exact shape the app writes.
"""

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

FORMAT: Final = "agent-lab-progress"
VERSION: Final = 1
MAX_BYTES = 2_000_000
KEYS = ("lessons", "sections", "theme", "text_size", "last_lesson")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Attempt(Strict):
    text: str = Field(max_length=10000)
    hints: int = Field(ge=0, le=2)
    at: str = Field(max_length=40)


class Check(Strict):
    status: Literal["passed", "needs-review"]
    detail: str = Field(max_length=2000)


class SavedAnswer(Strict):
    mode: Literal["prepared", "live"]
    intent: str = Field(max_length=40)
    question: str = Field(max_length=2000)
    text: str = Field(max_length=20000)
    model: str | None = Field(default=None, max_length=120)
    cost_usd: float | None = None
    at: str = Field(max_length=40)


class LessonRecord(Strict):
    checkpoints: list[bool] = Field(default_factory=lambda: [False] * 4, min_length=4, max_length=4)
    notes: str = Field(default="", max_length=20000)
    draft: str = Field(default="", max_length=10000)
    attempts: list[Attempt] = Field(default_factory=list, max_length=100)
    hints: int = Field(default=0, ge=0, le=2)
    answers: dict[str, int] = Field(default_factory=dict, max_length=10)
    check: Check | None = None
    tutor: list[SavedAnswer] = Field(default_factory=list, max_length=20)
    last_run: str = Field(default="", max_length=6000)


class Progress(Strict):
    lessons: dict[str, LessonRecord] = Field(default_factory=dict)
    sections: dict[str, dict[str, int]] = Field(default_factory=dict, max_length=20)
    theme: Literal["light", "dark", "auto"] = "light"
    text_size: Literal["small", "normal", "large", "xlarge"] = "normal"
    last_lesson: int = Field(default=0, ge=0, le=75)

    @field_validator("lessons")
    @classmethod
    def lesson_numbers(cls, value: dict[str, LessonRecord]) -> dict[str, LessonRecord]:
        if any(not key.isdigit() or not 1 <= int(key) <= 75 for key in value):
            raise ValueError("Lesson keys must be lesson numbers from 1 to 75.")
        return value


class ProgressFile(Strict):
    format: Literal["agent-lab-progress"]
    version: Literal[1]
    exported_at: str = Field(max_length=40)
    progress: Progress


def export_progress(store: Mapping[str, Any]) -> bytes:
    """Serialize only the known progress keys, validated, so the file always re-imports."""
    progress = Progress.model_validate({key: store[key] for key in KEYS if key in store})
    document = ProgressFile(
        format=FORMAT,
        version=VERSION,
        exported_at=datetime.now(UTC).isoformat(timespec="seconds"),
        progress=progress,
    )
    return document.model_dump_json(indent=1).encode("utf-8")


def import_progress(content: bytes) -> dict[str, Any]:
    """Return storage-ready progress, or raise ValueError with a student-readable reason."""
    if len(content) > MAX_BYTES:
        raise ValueError("The file is larger than 2 MB, so it is not a progress export.")
    try:
        document = ProgressFile.model_validate(json.loads(content.decode("utf-8")))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("The file is not valid JSON.") from exc
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(part) for part in first["loc"])
        raise ValueError(f"This is not a valid progress export ({where}: {first['msg']}).") from exc
    return document.progress.model_dump()
