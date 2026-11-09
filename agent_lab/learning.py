"""Learning content and checks shared by the UI and API: guides, quizzes, paths and tutor."""

from functools import cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agent_lab.curriculum import LESSONS

CONTENT = Path(__file__).resolve().parent / "content"
STEP_TITLES = [
    "Understand the goal",
    "Prepare your exercise",
    "Run one example",
    "Verify the evidence",
    "Try the challenge",
]
TUTOR_INTENTS = {
    "explain": "Explain this exercise",
    "concepts": "Concepts to learn",
    "steps": "Steps to complete it",
    "hint": "Give me a hint",
    "expected": "Expected result and why",
    "code": "Show me the code",
}


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Option(Strict):
    text: str = Field(min_length=1)
    explanation: str = Field(min_length=1)


class Question(Strict):
    prompt: str = Field(min_length=1)
    options: list[Option] = Field(min_length=2, max_length=4)
    correct: int = Field(ge=0)
    lesson: int | None = None
    code: str | None = None
    source: str | None = None

    @model_validator(mode="after")
    def correct_in_range(self) -> "Question":
        if self.correct >= len(self.options):
            raise ValueError("correct must index an option")
        return self


class Step(Strict):
    title: str
    text: str = Field(min_length=1)


class EvidenceCheck(Strict):
    key: str = Field(min_length=1)
    rule: Literal["present", "truthy", "equals"]
    value: Any = None


class ConceptPoint(Strict):
    title: str = Field(min_length=1, max_length=60)
    text: str = Field(min_length=1, max_length=240)


class Misconception(Strict):
    claim: str = Field(min_length=1, max_length=160)
    correction: str = Field(min_length=1, max_length=300)


class LessonGuide(Strict):
    id: int = Field(ge=1, le=75)
    prerequisites: list[int]
    concept_brief: str
    lab_brief: str
    preparation: list[str] = Field(min_length=1)
    steps: list[Step] = Field(min_length=5, max_length=5)
    inspect: str
    expected: str
    evidence_criterion: str
    evidence_checks: list[EvidenceCheck] = Field(min_length=1, max_length=3)
    challenge: str
    hints: list[str] = Field(min_length=2, max_length=2)
    reference: str
    recovery: list[str] = Field(min_length=1)
    quiz: list[Question] = Field(min_length=2, max_length=7)
    # The lesson's concept as real SDK code: shown in Learn, Python source and the infographic.
    concept_code: str = Field(min_length=1)
    code_focus: str = Field(min_length=1)
    concept_points: list[ConceptPoint] = Field(min_length=3, max_length=3)
    misconception: Misconception

    @model_validator(mode="after")
    def consistent(self) -> "LessonGuide":
        if [step.title for step in self.steps] != STEP_TITLES:
            raise ValueError(f"lesson {self.id}: steps must be titled {STEP_TITLES}")
        if any(not 1 <= number < self.id for number in self.prerequisites):
            raise ValueError(f"lesson {self.id}: prerequisites must be earlier lessons")
        return self


class Point(Strict):
    title: str
    text: str


class VisualGuide(Strict):
    id: str
    title: str
    eyebrow: str
    description: str
    image: str
    lessons: list[int]
    question: str
    answer: str
    note: str
    takeaway: str
    points: list[Point]


class LearningPath(Strict):
    id: str
    title: str
    description: str
    outcome: str
    lessons: list[int] = Field(min_length=1)


class SectionQuiz(Strict):
    id: str
    topic: str
    questions: list[Question] = Field(min_length=1)


class Course(Strict):
    source: str
    paths: list[LearningPath]
    section_quizzes: list[SectionQuiz]
    visual_guides: list[VisualGuide]


class CheckResult(Strict):
    status: Literal["passed", "needs-review"]
    detail: str


@cache
def guides() -> dict[int, LessonGuide]:
    import json

    rows = json.loads((CONTENT / "lessons.json").read_text(encoding="utf-8"))
    return {guide.id: guide for guide in (LessonGuide.model_validate(row) for row in rows)}


@cache
def course() -> Course:
    return Course.model_validate_json((CONTENT / "course.json").read_text(encoding="utf-8"))


def guide(lesson_id: int) -> LessonGuide:
    try:
        return guides()[lesson_id]
    except KeyError as exc:
        raise ValueError(f"Unknown lesson: {lesson_id}") from exc


class TourSection(Strict):
    title: str = Field(min_length=1, max_length=60)
    start: int = Field(ge=1)
    end: int = Field(ge=1)
    text: str = Field(min_length=1, max_length=450)


class CodeTour(Strict):
    """A reviewed walkthrough of one lesson's concept code, bound to that exact code."""

    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    sections: list[TourSection] = Field(min_length=3, max_length=5)


def code_sha256(code: str) -> str:
    import hashlib

    return hashlib.sha256(code.replace("\r\n", "\n").encode("utf-8")).hexdigest()


@cache
def code_tours() -> dict[int, CodeTour]:
    import json

    path = CONTENT / "code_tours.json"
    rows = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    return {int(key): CodeTour.model_validate(value) for key, value in rows.items()}


def tour_problems(lesson_id: int) -> list[str]:
    """Why a lesson's tour cannot be shown; an empty list means it matches the code."""
    tour = code_tours().get(lesson_id)
    if tour is None:
        return ["no reviewed tour"]
    code = guide(lesson_id).concept_code
    if tour.source_sha256 != code_sha256(code):
        return ["the concept code changed after the tour was reviewed"]
    count, problems, last = len(code.replace("\r\n", "\n").split("\n")), [], 0
    for section in tour.sections:
        if not last < section.start <= section.end <= count:
            problems.append(
                f"{section.title}: lines {section.start}-{section.end} are out of order"
            )
        last = section.end
    return problems


def code_tour(lesson_id: int) -> list[TourSection]:
    """Sections to narrate, or none: a stale tour must never describe different code."""
    return [] if tour_problems(lesson_id) else list(code_tours()[lesson_id].sections)


def section_quiz(topic: str) -> SectionQuiz | None:
    return next((quiz for quiz in course().section_quizzes if quiz.topic == topic), None)


def visual_guides_for(lesson_id: int) -> list[VisualGuide]:
    return [item for item in course().visual_guides if lesson_id in item.lessons]


def check_evidence(
    lesson_id: int,
    evidence: dict[str, Any] | None,
    *,
    status: str,
    mode: str = "offline",
    responded: bool = False,
) -> CheckResult:
    """Compare a finished run with the lesson criterion. This is not a grade of the student."""
    if status != "completed":
        return CheckResult(
            status="needs-review",
            detail=f"The run ended as {status}. Read the first error, fix it and run again.",
        )
    if not isinstance(evidence, dict):
        return CheckResult(status="needs-review", detail="No local exercise evidence was produced.")
    if lesson_id == 57:
        from agent_lab.worktrees_lab import grade

        report = evidence.get("report")
        passed = isinstance(report, dict) and report.get("mode") == ("live" if mode == "live" else "prepared") and grade(report)
        return CheckResult(status="passed" if passed else "needs-review",
                           detail="Owned Git worker commits, host Node tests, serial integration and clean removal are required.")
    if lesson_id == 56:
        from agent_lab.teams_lab import ReplayInput, grade

        report = evidence.get("report")
        try:
            selected = ReplayInput.model_validate({"commands": report["commands"]})
            passed = mode == "offline" and grade(selected, report)
        except (KeyError, TypeError, ValueError):
            passed = False
        return CheckResult(status="passed" if passed else "needs-review",
                           detail="Application team reducer verified exact ownership, acknowledgment and cleanup; native observations remain separate.")
    if lesson_id == 55:
        from agent_lab.upgrading_lab import RunInput, criterion

        report = evidence.get("report")
        try:
            selected = RunInput.model_validate({"scenario": report["scenario"]})
            passed = mode == "offline" and criterion(selected, report)
        except (KeyError, TypeError, ValueError):
            passed = False
        return CheckResult(status="passed" if passed else "needs-review",
                           detail="Synthetic offline gates matched the fixed candidate and installed inventory.")
    if lesson_id == 54:
        from agent_lab.tool_design_lab import DesignInput, grade

        report = evidence.get("report")
        try:
            selected = DesignInput.model_validate({"mode": report["mode"], "profile": report["profile"],
                                                   "format": report["format"]})
            passed = mode == "offline" and selected.mode == "prepared" and grade(selected, report)
        except (KeyError, TypeError, ValueError):
            passed = False
        return CheckResult(status="passed" if passed else "needs-review",
                           detail="Explicit tool-contract run completed without handler errors; fixture/live scope retained.")
    if lesson_id == 53:
        from agent_lab.debug_lab import DebugInput, criterion

        start, loaded, selected = (evidence.get(key) for key in ("start", "loaded", "selected"))
        try:
            parsed = DebugInput.model_validate(selected)
            passed = (mode == "offline" and parsed.mode == "prepared" and
                      isinstance(start, dict) and isinstance(loaded, dict) and
                      loaded.get("source") == "persisted-file-reload" and
                      isinstance(loaded.get("sha256"), str) and len(loaded["sha256"]) == 64 and
                      criterion(start["runId"], parsed, loaded["bundle"], loaded))
        except (KeyError, TypeError, ValueError):
            passed = False
        return CheckResult(status="passed" if passed else "needs-review",
                           detail=("Saved prepared bundle correlates run identity, rows and causal findings."
                                   if passed else "Reload a complete matching diagnostic bundle and inspect its trace."))
    if lesson_id == 52:
        from agent_lab.evals_core import synthetic_criterion

        baseline, candidate, comparison = (evidence.get(key) for key in ("baseline", "candidate", "comparison"))
        passed = (mode == "offline" and all(isinstance(item, dict) for item in
                                            (baseline, candidate, comparison)) and
                  synthetic_criterion(baseline, candidate, comparison))
        return CheckResult(status="passed" if passed else "needs-review",
                           detail=("Correlated synthetic baseline/candidate trial evidence passed with zero calls."
                                   if passed else "Complete authored synthetic reports and a recomputed passing comparison are required."))
    if lesson_id == 51:
        from agent_lab.offline_lab import evaluate_suite

        passed = mode == "offline" and evaluate_suite(evidence)
        return CheckResult(status="passed" if passed else "needs-review",
                           detail=("The complete unmodified 16-case host suite passed with zero model calls."
                                   if passed else "Complete unmodified host-suite evidence is required; partial, replay and mutation observations are separate."))
    if lesson_id == 1 and evidence.get("successful_result") is not True:
        return CheckResult(
            status="needs-review",
            detail="A final successful SDK result was not established. Inspect the terminal subtype and is_error; assistant text alone does not prove success. The recorded error and missing-result scenarios intentionally need review.",
        )
    if 2 <= lesson_id <= 49:
        experiment = evidence.get("experiment", {})
        passed = evidence.get("experiment_passed") is True and isinstance(experiment, dict) and experiment.get("experiment_passed") is True
        if mode == "live" and lesson_id <= 40 and isinstance(experiment, dict) and experiment.get("source") != "live SDK stream and actual host callbacks":
            passed = False
        if mode == "live" and lesson_id == 41 and isinstance(experiment, dict) and experiment.get("source_label") != "real Python SDK client and provider-backed CLI":
            passed = False
        if mode == "live" and lesson_id == 42 and isinstance(experiment, dict) and experiment.get("source_label") != "provider-backed SDK web tool calls and host hook observations":
            passed = False
        if mode == "live" and lesson_id == 43 and isinstance(experiment, dict) and experiment.get("source_label") != "provider-backed SDK remote MCP tool and resource calls":
            passed = False
        if mode == "live" and lesson_id == 44 and isinstance(experiment, dict) and experiment.get("source_label") != "native SDK subprocess":
            passed = False
        if mode == "live" and lesson_id == 45 and isinstance(experiment, dict) and experiment.get("source_label") != "native SDK subprocess":
            passed = False
        if mode == "live" and lesson_id == 46 and isinstance(experiment, dict) and experiment.get("source_label") != "native SDK subprocess":
            passed = False
        if mode == "live" and lesson_id == 47 and isinstance(experiment, dict) and experiment.get("source_label") != "native SDK and host checks":
            passed = False
        if mode == "live" and lesson_id == 48 and isinstance(experiment, dict) and experiment.get("source_label") != "native SDK subprocess":
            passed = False
        if mode == "live" and lesson_id == 49 and isinstance(experiment, dict) and experiment.get("source_label") != "native CLI and SDK":
            passed = False
        return CheckResult(
            status="passed" if passed else "needs-review",
            detail=("Live SDK evidence. " if mode == "live" else "Local experiment with labelled SDK fixtures. ")
            + (experiment.get("check_scope", "Required experiment evidence is missing.") if isinstance(experiment, dict) else "Required experiment evidence is missing.")
            + (" The bounded criterion passed." if passed else " The bounded criterion was not established; inspect the evidence.")
            + " Your manual review remains separate.",
        )
    failures = []
    for check in guide(lesson_id).evidence_checks:
        if check.key not in evidence:
            failures.append(f"`{check.key}` is missing")
        elif check.rule == "truthy" and not evidence[check.key]:
            failures.append(f"`{check.key}` is empty or false")
        elif check.rule == "equals" and evidence[check.key] != check.value:
            failures.append(f"`{check.key}` is {evidence[check.key]!r}, expected {check.value!r}")
    if failures:
        return CheckResult(status="needs-review", detail="; ".join(failures) + ".")
    if lesson_id == 1:
        return CheckResult(
            status="passed",
            detail=("The live SDK stream" if mode == "live" else "The recorded fixture stream")
            + " ended with a final result/success and is_error false. This checks the run outcome, not answer quality or your manual review.",
        )
    if mode == "live" and not responded:
        return CheckResult(
            status="needs-review",
            detail="The local evidence passed, but no Claude response or structured result arrived.",
        )
    detail = "The local evidence meets the lesson criterion."
    if mode == "live":
        detail += " Claude also returned a response; judge its content yourself."
    return CheckResult(status="passed", detail=detail)


def tutor_context(lesson_id: int) -> dict[str, Any]:
    lesson, item = LESSONS[lesson_id], guide(lesson_id)
    return {
        "id": lesson_id,
        "title": lesson.title,
        "objective": lesson.objective,
        "concept": item.concept_brief,
        "lab": item.lab_brief,
        "steps": [step.text for step in item.steps],
        "inspect": item.inspect,
        "expected": item.expected,
        "challenge": item.challenge,
        "hints": item.hints,
        "notes": lesson.notes,
        "concept_code": item.concept_code,
        "code_focus": item.code_focus,
    }


def prepared_answer(lesson_id: int, intent: str, latest_run: str = "") -> str:
    """An offline, grounded tutor answer built only from this lesson's authored content."""
    if intent not in TUTOR_INTENTS:
        raise ValueError(f"Unknown tutor intent: {intent}")
    context = tutor_context(lesson_id)
    heading = f"## Lesson {lesson_id}: {context['title']}"
    if intent == "concepts":
        body = f"### Concepts to learn\n\n{context['concept']}\n\n### What the exercise teaches\n\n{context['objective']}"
    elif intent == "steps":
        steps = "\n".join(f"{n}. {text}" for n, text in enumerate(context["steps"], 1))
        body = f"### Steps to complete the exercise\n\n{steps}\n\n### Expected behavior\n\n{context['expected']}"
    elif intent == "hint":
        body = f"### First hint\n\n{context['hints'][0]}\n\nRun the exercise once and inspect the results before asking for the detailed hint in the Learn tab."
    elif intent == "expected":
        body = f"### Expected result\n\n{context['expected']}\n\n### Evidence to inspect\n\n{context['inspect']}\n\nAn offline run shows local Python evidence. It does not prove that a live Claude call succeeded."
    elif intent == "code":
        body = (
            f"### The concept in code\n\n```python\n{context['concept_code']}\n```\n\n"
            f"{context['code_focus']}\n\nThe Python source tab also shows the offline lab "
            "that checks this concept."
        )
    else:
        body = f"### Exercise goal\n\n{context['objective']}\n\n### What happens\n\n{context['lab']}\n\n### What to inspect\n\n{context['inspect']}"
    if latest_run and intent in {"explain", "expected"}:
        body += f"\n\n### Your latest run\n\n{latest_run}"
    if context["notes"]:
        body += f"\n\n> Note: {context['notes']}"
    return f"{heading}\n\n{body}"
