from copy import deepcopy

import pytest

from agent_lab.curriculum import LESSONS
from agent_lab.learning import course, guide
from agent_lab.my_learning import filter_lessons, learning_snapshot, lesson_link, workspace_url


def test_empty_workspace_is_read_only_and_starts_with_a_real_lesson():
    store = {}
    snapshot = learning_snapshot(store)
    assert store == {}
    assert len(snapshot.lessons) == len(LESSONS)
    assert snapshot.reviewed == snapshot.saved_lessons == snapshot.exercise_checks == 0
    assert snapshot.resume().id == 1
    assert all(row.state == "No saved work" for row in snapshot.lessons)
    assert all(path.reviewed == 0 and path.next_lesson == path.lessons[0] for path in snapshot.paths)


def test_work_checks_quizzes_and_guides_do_not_complete_manual_review():
    store = {
        "lessons": {
            "1": {"answers": {"0": guide(1).quiz[0].correct}, "check": {"status": "passed"}},
            "2": {"checkpoints": [True, False, False, False]},
            "3": {"notes": "A source note", "attempts": [{"text": "My attempt", "hints": 1}]},
            "4": {"checkpoints": [True] * 4},
        },
        "learning_guide_positions": {"5": "source"},
    }
    original = deepcopy(store)
    snapshot = learning_snapshot(store)
    assert snapshot.reviewed == 1 and snapshot.saved_lessons == 5 and snapshot.exercise_checks == 1
    assert snapshot.lessons[0].quiz_correct == 1
    assert snapshot.lessons[0].state == "In progress"
    assert snapshot.lessons[4].state == "In progress"
    assert snapshot.lessons[3].state == "Reviewed"
    assert store == original


@pytest.mark.parametrize("checkpoints", [[], [True], [1] * 4, "true", None, [True] * 5])
def test_only_four_explicit_manual_choices_mean_reviewed(checkpoints):
    assert not learning_snapshot({"lessons": {"1": {"checkpoints": checkpoints}}}).lessons[0].reviewed


def test_path_next_unreviewed_obeys_the_route_and_never_wraps_when_finished():
    path = next(path for path in course().paths if path.id == "application-developer")
    store = {"lessons": {str(number): {"checkpoints": [True] * 4} for number in path.lessons}}
    snapshot = learning_snapshot(store)
    summary = next(row for row in snapshot.paths if row.id == path.id)
    assert summary.reviewed == len(path.lessons) and summary.next_lesson is None
    store["lessons"][str(path.lessons[1])]["checkpoints"][0] = False
    summary = next(row for row in learning_snapshot(store).paths if row.id == path.id)
    assert summary.next_lesson == path.lessons[1]


def test_resume_preserves_valid_path_and_only_opens_a_valid_saved_guide():
    snapshot = learning_snapshot({"last_lesson": 5, "learning_guide_positions": {"5": "evidence"}})
    resume = snapshot.resume()
    assert resume.id == 5
    assert lesson_link(resume, "application-developer", resume_guide=True) == "/?lesson=5&path=application-developer&resume_guide=true"
    other = learning_snapshot({"last_lesson": 2, "learning_guide_positions": {"2": "bad"}}).resume()
    assert lesson_link(other, "application-developer", resume_guide=True) == "/?lesson=2"
    assert workspace_url("application-developer") == "/my-learning?path=application-developer"
    assert workspace_url("../../outside") == "/my-learning"


def test_quiz_results_ignore_stale_or_invalid_choices_and_keep_section_results_separate():
    section = course().section_quizzes[0]
    snapshot = learning_snapshot({
        "lessons": {"1": {"answers": {"0": guide(1).quiz[0].correct, "1": 999, "-1": 0, "2": True}}},
        "sections": {section.id: {"0": section.questions[0].correct}},
    })
    row = snapshot.lessons[0]
    assert len(row.answers) == row.quiz_correct == 1
    assert len(snapshot.section_quizzes[0].answers) == 1
    assert snapshot.reviewed == 0


def test_filters_search_saved_text_and_use_each_activitys_own_state_without_mutating_records():
    store = {"lessons": {
        "2": {"notes": "Validation finding", "draft": "Unsubmitted text"},
        "3": {"attempts": [{"text": "Scoped workspace", "hints": 0}]},
        "5": {"check": {"status": "needs-review", "detail": "Missing evidence"}},
        "6": {"checkpoints": [True] * 4},
    }}
    original = deepcopy(store)
    snapshot = learning_snapshot(store)
    assert [row.id for row in filter_lessons(snapshot, view="Notes", search="FINDING")] == [2]
    assert [row.id for row in filter_lessons(snapshot, view="Attempts", search="scoped")] == [3]
    assert [row.id for row in filter_lessons(snapshot, state="needs-review")] == [5]
    assert [row.id for row in filter_lessons(snapshot, state="reviewed")] == [6]
    assert not filter_lessons(snapshot, path="application-developer", search="Validation finding")
    assert [row.id for row in filter_lessons(snapshot, state="in-progress")] == [2, 3, 5]
    assert store == original


def test_malformed_old_records_are_not_phantom_work_or_errors():
    snapshot = learning_snapshot({
        "last_lesson": True,
        "lessons": {"1": {"notes": {}, "check": {"status": []}, "attempts": [None, {"text": False}], "answers": []}},
        "learning_guide_positions": {"1": {}}, "sections": [],
    })
    assert snapshot.last_lesson is None
    assert snapshot.saved_lessons == 0
    assert snapshot.resume().id == 1


def test_a_fully_reviewed_course_has_no_fabricated_next_lesson():
    snapshot = learning_snapshot({"lessons": {str(number): {"checkpoints": [True] * 4} for number in LESSONS}})
    assert snapshot.reviewed == 75
    assert snapshot.resume() is None
