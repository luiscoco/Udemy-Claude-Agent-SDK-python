
import json

import pytest
from pydantic import ValidationError

from agent_lab.config import ROOT
from agent_lab.curriculum import LESSONS
from agent_lab.learning import course
from agent_lab.lesson_guide import (
    SECTION_IDS,
    LearningGuide,
    adjacent_lesson,
    learning_guides,
    lesson_url,
    route_id,
)


def test_pilot_contains_the_seven_real_sections_and_explicit_student_actions():
    tours = learning_guides()
    assert set(tours) == {1}  # Other lessons are pending, never falsely presented as reviewed.
    tour = tours[1]
    assert tuple(section.id for section in tour.sections) == SECTION_IDS
    assert {section.id for section in tour.sections if section.student_action} == {
        "controls", "evidence", "practice",
    }
    assert all(section.target != section.context or section.id == "source" for section in tour.sections)


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
        assert row["written_guide"] == ("written-pilot" if row["id"] in learning_guides() else "pending")
        assert row["reference_contract"].startswith(f"docs/prompts/l{row['id']:02}-")
        assert len(row["reference_blob_sha"]) == 40 and row["foundation_component"]
