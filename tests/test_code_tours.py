import re

import pytest

from agent_lab.curriculum import LESSONS
from agent_lab.learning import code_tour, code_tours, guide, tour_problems


@pytest.mark.parametrize("lesson_id", list(LESSONS))
def test_every_lesson_has_a_reviewed_tour_of_its_current_code(lesson_id):
    # A failure here after editing concept code means: review the tour, fix its line ranges
    # and text, then update its source_sha256.
    assert tour_problems(lesson_id) == [], lesson_id
    assert 3 <= len(code_tour(lesson_id)) <= 5


def test_tour_text_is_plain_spoken_python():
    for lesson_id, tour in code_tours().items():
        for section in tour.sections:
            for text in (section.title, section.text):
                assert not re.search(r"[`*#]|\]\(", text), (lesson_id, text)
                assert not re.search(r"TypeScript|JavaScript|\bnpm\b|\bZod\b", text), (lesson_id, text)
                assert not re.search(r"\b(maxTurns|allowedTools|permissionMode|mcpServers)\b", text)


def test_a_changed_concept_code_hides_its_tour(monkeypatch):
    original = guide(1)
    changed = original.model_copy(update={"concept_code": original.concept_code + "\n# edited"})
    monkeypatch.setattr("agent_lab.learning.guide", lambda lesson_id: changed)
    assert tour_problems(1) == ["the concept code changed after the tour was reviewed"]
    assert code_tour(1) == []
