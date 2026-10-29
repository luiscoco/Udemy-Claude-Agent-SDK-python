
import json

import pytest
from pydantic import ValidationError

from agent_lab.config import ROOT
from agent_lab.curriculum import LESSONS
from agent_lab.exercises import EXERCISES
from agent_lab.learning import course, guide
from agent_lab.lesson_guide import (
    SECTION_IDS,
    LearningGuide,
    adjacent_lesson,
    learning_guides,
    lesson_url,
    route_id,
)


def test_every_lesson_contains_the_seven_sections_and_explicit_student_actions():
    tours = learning_guides()
    assert set(tours) == set(LESSONS)
    assert sum(len(tour.sections) for tour in tours.values()) == 525
    for number, tour in tours.items():
        assert tour.lesson == number
        assert tuple(section.id for section in tour.sections) == SECTION_IDS
        assert {section.id for section in tour.sections if section.student_action} == {
            "controls", "evidence", "practice",
        }


@pytest.mark.parametrize("number", range(2, 76))
def test_expanded_guide_uses_its_own_preparation_code_evidence_and_challenge(number):
    item = guide(number)
    sections = {section.id: section for section in learning_guides()[number].sections}
    assert LESSONS[number].objective in sections["goal"].text
    for line in item.preparation:
        assert line.replace("`", "") in sections["preparation"].text
    assert item.code_focus.replace("`", "") in sections["example"].text
    assert item.lab_brief.replace("`", "") in sections["controls"].text
    assert item.inspect.replace("`", "") in sections["evidence"].text
    assert item.expected.replace("`", "") in sections["evidence"].text
    assert item.evidence_criterion.replace("`", "") in sections["evidence"].action
    assert EXERCISES[LESSONS[number].exercise].__name__ + "()" in sections["source"].action
    assert item.challenge.replace("`", "") == sections["practice"].text


@pytest.mark.parametrize("change", ["missing", "duplicate", "unsafe-selector"])
def test_bad_tour_content_is_rejected_before_rendering(change):
    row = learning_guides()[1].model_dump()
    if change == "missing":
        row["sections"].pop()
    elif change == "duplicate":
        row["sections"][-1]["id"] = "goal"
    else:
        row["sections"][0]["target"] = "body, #anything"
    with pytest.raises(ValidationError):
        LearningGuide.model_validate(row)


def test_route_navigation_follows_the_selected_route_in_both_directions():
    assert adjacent_lesson(1, 1, "application-developer") == 3
    assert adjacent_lesson(3, -1, "application-developer") == 1
    assert adjacent_lesson(1, -1, "application-developer") is None
    for path in course().paths:
        assert adjacent_lesson(path.lessons[-1], 1, path.id) is None
    assert lesson_url(3, "application-developer") == "/?lesson=3&path=application-developer"
    assert route_id("application-developer", 2) == ""
    assert lesson_url(2, "application-developer") == "/?lesson=2"
    assert lesson_url(1, "unknown") == "/?lesson=1"
    assert adjacent_lesson(1, 1, "unknown") == 2
    with pytest.raises(ValueError):
        lesson_url(99)


def test_reference_inventory_tracks_all_current_lessons_without_certifying_parity():
    inventory = json.loads((ROOT / "docs/reference-parity.json").read_text(encoding="utf-8"))
    assert len(inventory["lessons"]) == 75
    assert {row["id"] for row in inventory["lessons"]} == set(LESSONS)
    assert len(inventory["reference"]["commit"]) == 40
    for row in inventory["lessons"]:
        lesson = LESSONS[row["id"]]
        assert row["title"] == lesson.title and row["live_profile"] == lesson.live_profile
        assert row["reference_parity"] == "not-certified"
        assert row["written_guide"] == "written"
        assert row["reference_contract"].startswith(f"docs/prompts/l{row['id']:02}-")
        assert len(row["reference_blob_sha"]) == 40 and row["foundation_component"]
