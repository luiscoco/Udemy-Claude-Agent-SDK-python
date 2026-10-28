import re

import pytest

from agent_lab.curriculum import LESSONS
from agent_lab.diagrams import components, exercise_diagram, legend, text


@pytest.mark.parametrize("lesson_id", LESSONS)
def test_every_lesson_has_a_well_formed_diagram(lesson_id):
    diagram = exercise_diagram(lesson_id)
    assert diagram.startswith("flowchart LR")
    # Every edge connects nodes that the diagram defines.
    defined = set(re.findall(r"^\s+(\w+)[\[\(\{]", diagram, re.MULTILINE))
    for source, target in re.findall(r"^\s+(\w+) --> (\w+)$", diagram, re.MULTILINE):
        assert {source, target} <= defined, (lesson_id, source, target)
    # Labels may contain the line break <br/> the generator adds, and nothing else risky.
    labels = [label.replace("<br/>", " ") for label in re.findall(r'"([^"]*)"', diagram)]
    assert labels and not any(set(label) & set("<>{}|`") for label in labels)
    assert legend(lesson_id)


@pytest.mark.parametrize(
    ("lesson_id", "expected", "absent"),
    [
        (7, {"Hook callbacks", "Path policy"}, set()),
        (19, {"SDK session functions", "Child process"}, set()),
        # client.query() is a method call, not the module-level query() function.
        (26, {"ClaudeSDKClient", "Scripted CLI fixture"}, {"SDK query()"}),
        (12, {"SDK query()", "Scripted CLI fixture"}, set()),
        (66, {"Local HTTP server", "WebSocket client"}, set()),
        (9, {"Host Python logic"}, set()),
    ],
)
def test_components_are_detected_from_the_exercise_code(lesson_id, expected, absent):
    found = {part.label for part in components(lesson_id)}
    assert expected <= found and not absent & found


def test_labels_cannot_break_mermaid_syntax():
    assert text('a "quoted" <b>{x}|y`') == "a quoted bxy"
