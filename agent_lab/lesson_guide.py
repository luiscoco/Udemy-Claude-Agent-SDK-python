"""Written learning tours and route navigation, separate from exercise execution."""

import json
from functools import cache
from typing import Literal
from urllib.parse import urlencode

from pydantic import Field, model_validator

from agent_lab.curriculum import LESSONS
from agent_lab.learning import CONTENT, Strict, code_tour, course, guide

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
    """Use curated overrides where supplied; expand the other lessons from their content.

    This keeps the approved lesson 1 wording while binding every other tour to the
    current lesson preparation, concept code, host exercise, evidence and challenge.
    Loading a written guide never runs an exercise or calls the SDK.
    """
    rows = json.loads((CONTENT / "learning_guides.json").read_text(encoding="utf-8"))
    overrides = [LearningGuide.model_validate(row) for row in rows]
    if len({item.lesson for item in overrides}) != len(overrides):
        raise ValueError("Learning guide lesson numbers must be unique.")
    by_lesson = {item.lesson: item for item in overrides}
    if 1 not in by_lesson or not set(by_lesson) <= set(LESSONS):
        raise ValueError("Learning guides need lesson 1's section template and valid lesson numbers.")
    return {
        number: by_lesson[number] if number in by_lesson else _expand_guide(number, by_lesson[1])
        for number in LESSONS
    }


def _prose(text: str) -> str:
    """Guide labels are plain text; strip Markdown code-span markers, not code content."""
    return text.replace("`", "")


def _expand_guide(number: int, template: LearningGuide) -> LearningGuide:
    from agent_lab.exercises import EXERCISES

    lesson, item = LESSONS[number], guide(number)
    function = EXERCISES[lesson.exercise].__name__
    source_sections = "; ".join(section.title for section in code_tour(number))
    wording = {
        "goal": (
            f"{lesson.objective} {_prose(item.concept_brief)}",
            f"Read lesson {number}'s objective. {_prose(item.steps[0].text)}",
        ),
        "preparation": (
            " ".join(_prose(line) for line in item.preparation),
            f"Check the preparation for {lesson.title} before running anything. "
            "Start with Offline Python exercise. Optional live instructions are separate; "
            "the guide never changes your mode or authorizes a paid call.",
        ),
        "example": (
            f"{_prose(item.code_focus)} The outline frames the actual Python example. "
            "Scroll inside it to read the full code; displaying the example does not execute it.",
            f"Follow these code-tour sections: {source_sections}. "
            "Trace the inputs and result before continuing; Start code tour offers a line-by-line explanation.",
        ),
        "controls": (
            f"{_prose(item.lab_brief)} The guide never clicks Run, changes inputs or authorizes a paid call.",
            f"{_prose(item.steps[2].text)} Keep Offline Python exercise selected and run it yourself "
            "when ready. Wait for Completed before inspecting the result; consult the lesson's "
            "recovery instructions if the run fails.",
        ),
        "evidence": (
            f"Inspect: {_prose(item.inspect)} Expected: {_prose(item.expected)} "
            "Long results can be scrolled inside the red frame.",
            f"{_prose(item.evidence_criterion)} Check the LOCAL PYTHON RESULT source. "
            "A local check does not prove a live model response or complete your manual review checklist.",
        ),
        "source": (
            f"The outlined concept code explains {lesson.title}. {_prose(item.code_focus)} "
            "The expandable host exercise below it is the implementation used by the offline browser, CLI and API.",
            f"Expand How the offline lab checks this concept and find {function}() "
            f"in agent_lab/exercises.py. Compare it with the concept example: {_prose(item.lab_brief)}",
        ),
        "practice": (
            _prose(item.challenge),
            "Work in a scratch copy. Use the lesson's hints if needed, then write and save your "
            "own explanation and evidence. Finish tour returns to this lesson's heading; "
            "Next lesson follows your selected route when another lesson remains. "
            "Tour controls never submit your explanation or change your manual review checklist.",
        ),
    }
    return LearningGuide(
        lesson=number,
        sections=[
            GuideSection.model_validate(
                section.model_dump() | {"text": wording[section.id][0], "action": wording[section.id][1]}
            )
            for section in template.sections
        ],
    )


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
