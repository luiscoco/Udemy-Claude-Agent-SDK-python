"""Written learning tours and route navigation, separate from exercise execution."""

import json
from functools import cache
from typing import Literal
from urllib.parse import urlencode

from pydantic import Field, model_validator

from agent_lab.curriculum import LESSONS
from agent_lab.learning import CONTENT, Strict, course

SectionId = Literal["goal", "preparation", "example", "controls", "evidence", "source", "practice"]
SECTION_IDS = ("goal", "preparation", "example", "controls", "evidence", "source", "practice")


class GuideSection(Strict):
    id: SectionId
    title: str = Field(min_length=1, max_length=80)
    tab: Literal["Learn", "Run the exercise", "Python source"]
    target: str = Field(pattern=r"^[.#][a-z][a-z0-9-]*$")
    context: str = Field(pattern=r"^[.#][a-z][a-z0-9-]*$")
    text: str = Field(min_length=1, max_length=2000)
    action: str = Field(min_length=1, max_length=1000)
    student_action: bool


class LearningGuide(Strict):
    lesson: int = Field(ge=1, le=75)
    sections: list[GuideSection] = Field(min_length=7, max_length=7)

    @model_validator(mode="after")
    def complete(self) -> "LearningGuide":
        if tuple(section.id for section in self.sections) != SECTION_IDS:
            raise ValueError("A guide must contain the seven sections in teaching order.")
        return self


@cache
def learning_guides() -> dict[int, LearningGuide]:
    rows = json.loads((CONTENT / "learning_guides.json").read_text(encoding="utf-8"))
    guides = [LearningGuide.model_validate(row) for row in rows]
    if len({guide.lesson for guide in guides}) != len(guides):
        raise ValueError("Learning guide lesson numbers must be unique.")
    return {guide.lesson: guide for guide in guides}


def route_id(path: str, lesson: int) -> str:
    """Keep a named route only when it actually contains the selected lesson."""
    return next((p.id for p in course().paths if p.id == path and lesson in p.lessons), "")


def route_lessons(path: str = "") -> list[int]:
    return next((list(p.lessons) for p in course().paths if p.id == path), sorted(LESSONS))


def adjacent_lesson(lesson: int, offset: Literal[-1, 1], path: str = "") -> int | None:
    lessons = route_lessons(route_id(path, lesson))
    index = lessons.index(lesson) + offset
    return lessons[index] if 0 <= index < len(lessons) else None


def lesson_url(lesson: int, path: str = "") -> str:
    if lesson not in LESSONS:
        raise ValueError("Unknown lesson.")
    query = {"lesson": str(lesson)}
    if valid_path := route_id(path, lesson):
        query["path"] = valid_path
    return "/?" + urlencode(query)
