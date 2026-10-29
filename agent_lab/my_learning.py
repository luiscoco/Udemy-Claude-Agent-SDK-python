"""Read-only views of existing per-browser learning records. No execution or grading."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

from agent_lab.curriculum import LESSONS
from agent_lab.learning import Question, course, guide
from agent_lab.lesson_guide import SECTION_IDS, lesson_url, route_lessons


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ""


@dataclass(frozen=True)
class QuizAnswer:
    question: Question
    chosen: int

    @property
    def correct(self) -> bool:
        return self.chosen == self.question.correct


def quiz_answers(questions: list[Question], saved: Any) -> tuple[QuizAnswer, ...]:
    answers = _mapping(saved)
    return tuple(
        QuizAnswer(question, chosen)
        for index, question in enumerate(questions)
        if type(chosen := answers.get(str(index))) is int and 0 <= chosen < len(question.options)
    )


@dataclass(frozen=True)
class SavedAttempt:
    text: str
    hints: int
    at: str


@dataclass(frozen=True)
class LessonSummary:
    id: int
    title: str
    topic: str
    reviewed: bool
    has_work: bool
    notes: str
    draft: str
    attempts: tuple[SavedAttempt, ...]
    answers: tuple[QuizAnswer, ...]
    quiz_total: int
    check_status: str
    check_detail: str
    last_run: str
    guide_section: str
    tutor_count: int

    @property
    def state(self) -> str:
        return "Reviewed" if self.reviewed else "In progress" if self.has_work else "No saved work"

    @property
    def quiz_correct(self) -> int:
        return sum(answer.correct for answer in self.answers)


@dataclass(frozen=True)
class PathSummary:
    id: str
    title: str
    description: str
    lessons: tuple[int, ...]
    reviewed: int
    next_lesson: int | None


@dataclass(frozen=True)
class SectionQuizSummary:
    id: str
    topic: str
    total: int
    answers: tuple[QuizAnswer, ...]


@dataclass(frozen=True)
class LearningSnapshot:
    lessons: tuple[LessonSummary, ...]
    paths: tuple[PathSummary, ...]
    section_quizzes: tuple[SectionQuizSummary, ...]
    last_lesson: int | None

    @property
    def reviewed(self) -> int:
        return sum(row.reviewed for row in self.lessons)

    @property
    def saved_lessons(self) -> int:
        return sum(row.has_work for row in self.lessons)

    @property
    def exercise_checks(self) -> int:
        return sum(bool(row.check_status) for row in self.lessons)

    def resume(self, path: str = "") -> LessonSummary | None:
        if self.last_lesson is not None:
            return next(row for row in self.lessons if row.id == self.last_lesson)
        eligible = [row for row in self.lessons if row.id in route_lessons(path)]
        return next((row for row in eligible if row.has_work and not row.reviewed), None) or next(
            (row for row in eligible if not row.reviewed), None
        )


def learning_snapshot(store: Mapping[str, Any]) -> LearningSnapshot:
    """Inspect saved data without filling in defaults or changing any storage key."""
    saved = _mapping(store.get("lessons"))
    positions = _mapping(store.get("learning_guide_positions"))
    rows = []
    for number, lesson in LESSONS.items():
        raw = _mapping(saved.get(str(number)))
        checks = raw.get("checkpoints", [])
        marks = checks if isinstance(checks, (list, tuple)) and len(checks) == 4 else []
        reviewed = len(marks) == 4 and all(value is True for value in marks)
        notes, draft = _text(raw.get("notes")), _text(raw.get("draft"))
        raw_attempts = raw.get("attempts", [])
        attempts = tuple(
            SavedAttempt(
                item["text"],
                item.get("hints", 0) if type(item.get("hints")) is int and 0 <= item["hints"] <= 2 else 0,
                _text(item.get("at")),
            )
            for value in (raw_attempts if isinstance(raw_attempts, list) else [])
            if isinstance(value, Mapping) and isinstance((item := value).get("text"), str)
        )
        answers = quiz_answers(guide(number).quiz, raw.get("answers"))
        check = _mapping(raw.get("check"))
        saved_status = _text(check.get("status"))
        check_status = saved_status if saved_status in {"passed", "needs-review"} else ""
        last_run = _text(raw.get("last_run"))
        position = positions.get(str(number))
        section = position if isinstance(position, str) and position in SECTION_IDS else ""
        tutor = raw.get("tutor", [])
        tutor_count = sum(
            isinstance(value, Mapping) and bool(_text(value.get("text")))
            for value in (tutor if isinstance(tutor, list) else [])
        )
        has_work = bool(
            reviewed or any(value is True for value in marks) or notes.strip() or draft.strip()
            or attempts or answers or check_status or last_run.strip() or section or tutor_count
            or (type(raw.get("hints")) is int and raw["hints"] > 0)
        )
        rows.append(LessonSummary(
            number, lesson.title, lesson.topic, reviewed, has_work, notes, draft, attempts, answers,
            len(guide(number).quiz), check_status, _text(check.get("detail")), last_run, section, tutor_count,
        ))
    by_id = {row.id: row for row in rows}
    paths = tuple(
        PathSummary(
            path.id, path.title, path.description, tuple(path.lessons),
            sum(by_id[number].reviewed for number in path.lessons),
            next((number for number in path.lessons if not by_id[number].reviewed), None),
        )
        for path in course().paths
    )
    sections = _mapping(store.get("sections"))
    section_results = tuple(
        SectionQuizSummary(quiz.id, quiz.topic, len(quiz.questions), quiz_answers(quiz.questions, sections.get(quiz.id)))
        for quiz in course().section_quizzes
    )
    last = store.get("last_lesson")
    if isinstance(last, str):
        last = int(last) if last.isdigit() and len(last) <= 2 else None
    last_lesson = last if type(last) is int and last in LESSONS else None
    return LearningSnapshot(tuple(rows), paths, section_results, last_lesson)


def valid_path(path: str) -> str:
    return path if any(item.id == path for item in course().paths) else ""


def workspace_url(path: str = "") -> str:
    return "/my-learning" + ("?" + urlencode({"path": path}) if valid_path(path) else "")


def setup_url(path: str = "") -> str:
    return "/setup" + ("?" + urlencode({"path": path}) if valid_path(path) else "")


def lesson_link(row: LessonSummary, path: str = "", *, resume_guide: bool = False) -> str:
    return lesson_url(row.id, path) + ("&resume_guide=true" if resume_guide and row.guide_section else "")


def filter_lessons(
    snapshot: LearningSnapshot, *, path: str = "", search: str = "", state: str = "all", view: str = "Lessons"
) -> list[LessonSummary]:
    term = search.strip().casefold()[:200]
    eligible = set(route_lessons(valid_path(path)))
    result = []
    for row in snapshot.lessons:
        if row.id not in eligible:
            continue
        if state == "reviewed" and not row.reviewed:
            continue
        if state == "in-progress" and (row.reviewed or not row.has_work):
            continue
        if state == "no-work" and row.has_work:
            continue
        if state == "needs-review" and row.check_status != "needs-review":
            continue
        if view == "Notes" and not (row.notes.strip() or row.draft.strip()):
            continue
        if view == "Quiz results" and not row.answers:
            continue
        if view == "Attempts" and not row.attempts:
            continue
        text = " ".join((str(row.id), row.title, row.topic, row.notes, row.draft, *(item.text for item in row.attempts)))
        if term and term not in text.casefold():
            continue
        result.append(row)
    return result
