"""Learning components: guides, workbook, quizzes, visual guides, tutor and progress.

Progress lives in NiceGUI's per-browser user storage. It stays on this machine and is
never sent to Claude; clearing the browser's cookies starts a fresh record.
"""

import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from nicegui import app, ui

from agent_lab.curriculum import LESSONS, TOPICS
from agent_lab.diagrams import exercise_diagram, legend
from agent_lab.learning import (
    TUTOR_INTENTS,
    CheckResult,
    Question,
    VisualGuide,
    code_tour,
    course,
    guide,
    section_quiz,
    visual_guides_for,
)
from agent_lab.lesson_guide import lesson_url
from agent_lab.models import LessonError
from agent_lab.policy import redact
from agent_lab.progress import KEYS as PROGRESS_KEYS
from agent_lab.progress import MAX_BYTES as PROGRESS_MAX_BYTES
from agent_lab.progress import export_progress, import_progress
from agent_lab.tutor import TUTOR_BUDGET_USD, TutorRequest, TutorService

REVIEW_ITEMS = [
    "I understand the objective and preparation.",
    "I ran the exercise in my chosen mode.",
    "I inspected the stated evidence.",
    "I can explain my challenge result.",
]
TEXT_SIZES = {"small": "Small", "normal": "Normal", "large": "Large", "xlarge": "Extra large"}
MAX_ATTEMPTS = 100
MAX_SAVED_ANSWERS = 20


# ---------------------------------------------------------------- persistence


def _store() -> Any:
    return app.storage.user


def record(lesson_id: int) -> dict[str, Any]:
    saved = _store().get("lessons", {}).get(str(lesson_id), {})
    return {
        "checkpoints": list(saved.get("checkpoints", [False] * len(REVIEW_ITEMS))),
        "notes": saved.get("notes", ""),
        "draft": saved.get("draft", ""),
        "attempts": list(saved.get("attempts", [])),
        "hints": saved.get("hints", 0),
        "answers": dict(saved.get("answers", {})),
        "check": saved.get("check"),
        "tutor": list(saved.get("tutor", [])),
        "last_run": saved.get("last_run", ""),
    }


def update(lesson_id: int, **changes: Any) -> dict[str, Any]:
    # Reassign the top-level key so the persistent store always notices nested changes.
    lessons = dict(_store().get("lessons", {}))
    lessons[str(lesson_id)] = record(lesson_id) | changes
    _store()["lessons"] = lessons
    return lessons[str(lesson_id)]


def completed(lesson_id: int) -> bool:
    return all(record(lesson_id)["checkpoints"])


def preference(name: str, default: str) -> str:
    return str(_store().get(name, default))


def stored(name: str, default: Any) -> Any:
    """A saved value as stored (preference() returns text)."""
    return _store().get(name, default)


def set_preference(name: str, value: Any) -> None:
    _store()[name] = value


# ---------------------------------------------------------------- shared pieces


def card(title: str = "", eyebrow: str = "") -> ui.card:
    container = ui.card().classes("course-card w-full p-6 gap-3")
    with container:
        if eyebrow:
            ui.label(eyebrow.upper()).classes("eyebrow")
        if title:
            ui.label(title).classes("text-xl font-bold")
    return container


def plain(text: str) -> str:
    """Content uses Markdown code spans; plain-text widgets show them without backticks."""
    return text.replace("`", "")


def render_quiz(questions: list[Question], answers: dict[str, int], save: Any) -> None:
    """Answer feedback appears immediately and persists; quizzes are practice, not grades."""
    for number, question in enumerate(questions):
        key = str(number)
        with ui.column().classes("w-full gap-1 quiz-question"):
            ui.markdown(f"**{number + 1}. {question.prompt}**")
            if question.code:
                ui.code(question.code, language="python").classes("w-full")
            labels = {index: plain(option.text) for index, option in enumerate(question.options)}

            @ui.refreshable
            def feedback(question: Question = question, key: str = key) -> None:
                chosen = answers.get(key)
                if chosen is None:
                    return
                right = chosen == question.correct
                ui.markdown(
                    ("Correct. " if right else "Review this. ")
                    + question.options[chosen].explanation.removeprefix("Correct. ")
                ).classes("feedback " + ("feedback-ok" if right else "feedback-bad"))

            def choose(event: Any, key: str = key, refresh: Any = feedback) -> None:
                answers[key] = event.value
                save(dict(answers))
                refresh.refresh()

            ui.radio(labels, value=answers.get(key), on_change=choose)
            feedback()


def score(questions: list[Question], answers: dict[str, int]) -> str:
    right = sum(answers.get(str(n)) == q.correct for n, q in enumerate(questions))
    return f"{right} of {len(questions)} correct"


def image_viewer(src: str, title: str) -> None:
    """Zoom, fit and scroll-to-pan for detailed infographics."""
    zoom = {"value": 100}
    with ui.dialog().props("maximized") as dialog, ui.card().classes("w-full h-full p-0 gap-0"):
        with ui.row().classes("w-full items-center p-3 gap-2 border-b"):
            ui.label(title).classes("text-lg font-bold flex-1 min-w-0")
            label = ui.label("Fit")

            def apply(value: int | None) -> None:
                zoom["value"] = value or 100
                image.style(f"width: {zoom['value']}%; max-width: none" if value else "width: 100%")
                label.set_text(f"{zoom['value']}%" if value else "Fit")

            ui.button(icon="zoom_out", on_click=lambda: apply(max(50, zoom["value"] - 25))).props(
                "flat round aria-label='Zoom out'"
            )
            ui.button("Fit", on_click=lambda: apply(None)).props("flat")
            ui.button(icon="zoom_in", on_click=lambda: apply(min(400, zoom["value"] + 25))).props(
                "flat round aria-label='Zoom in'"
            )
            ui.button(icon="close", on_click=dialog.close).props("flat round aria-label='Close'")
        with ui.element("div").classes("w-full flex-1 overflow-auto bg-slate-100 viewer-pane"):
            image = ui.image(src).props("fit=contain no-spinner").style("width: 100%")
    dialog.open()


def visual_guide_card(item: VisualGuide, compact: bool = False) -> None:
    with card(item.title, item.eyebrow):
        ui.label(item.description).classes("text-slate-600")
        ui.image(item.image).classes("rounded-xl w-full cursor-zoom-in").props(
            f"fit=contain alt='{item.title} visual guide'"
        ).on("click", lambda: image_viewer(item.image, item.title))
        ui.label("Select the image to zoom and pan.").classes("text-xs text-slate-500")
        if compact:
            return
        with ui.grid(columns="repeat(auto-fit, minmax(220px, 1fr))").classes("w-full gap-3"):
            for point in item.points:
                with ui.column().classes("gap-0"):
                    ui.label(point.title).classes("font-semibold")
                    ui.label(point.text).classes("text-sm text-slate-600")
        with ui.expansion(f"Check yourself: {item.question}").classes("w-full"):
            ui.label(item.answer)
        ui.label(item.note).classes("text-sm text-slate-500")
        ui.label(f"Takeaway: {item.takeaway}").classes("font-semibold")
        ui.label(
            "Related lessons: " + ", ".join(f"{n}. {LESSONS[n].title}" for n in item.lessons)
        ).classes("text-sm text-slate-500")


# ---------------------------------------------------------------- lesson sections


def lesson_header(lesson_id: int, live_enabled: bool) -> None:
    lesson, item = LESSONS[lesson_id], guide(lesson_id)
    ui.label(f"Course / {lesson.topic} / Lesson {lesson_id}").classes("text-sm text-slate-500")
    ui.label(f"{lesson_id}. {lesson.title}").classes("course-title").props('id="lesson-heading" tabindex="-1"')
    ui.label(lesson.objective).classes("text-lg text-slate-600 guide-goal-target")
    with ui.row().classes("items-center gap-3"):
        ui.badge(
            "Offline simulation · no model calls" if lesson_id == 55 else
            "Offline exercise + optional live SDK" if live_enabled else "Offline exercise",
            color="secondary",
        )
        if completed(lesson_id):
            ui.badge("Reviewed", color="positive").props("outline")
        ui.label("Prerequisites:").classes("text-sm text-slate-500")
        if not item.prerequisites:
            ui.label("None").classes("text-sm")
        for number in item.prerequisites:
            ui.link(f"Lesson {number}", f"/?lesson={number}").classes("text-sm")


def tour_code_html(code: str, start: int, end: int) -> str:
    """The concept code with line numbers and the current section's lines highlighted."""
    from pygments import highlight
    from pygments.formatters import HtmlFormatter
    from pygments.lexers import PythonLexer

    formatter = HtmlFormatter(
        cssclass="tour-code", linenos="inline", hl_lines=list(range(start, end + 1))
    )
    return highlight(code, PythonLexer(stripnl=False), formatter)


def concept_code_card(lesson_id: int, guide_target: str = "guide-example-target") -> None:
    """The SDK code for this lesson's concept, as a developer would write it."""
    item = guide(lesson_id)
    sections = code_tour(lesson_id)
    step: dict[str, int | None] = {"index": None}
    with card("The concept in code", "Python SDK").classes("guide-example-context"):
        code_view = ui.column().classes(f"w-full gap-0 guide-scroll-target {guide_target}").props(
            'tabindex="0" aria-label="Python concept code"'
        )

        @ui.refreshable
        def view() -> None:
            index = step["index"]
            if index is None:
                with code_view:
                    ui.code(item.concept_code, language="python").classes("w-full")
                ui.markdown(item.code_focus)
                if sections:
                    ui.button(
                        "Start code tour", icon="route", on_click=lambda: go(0)
                    ).props("outline")
                return
            section = sections[index]
            with code_view:
                ui.html(tour_code_html(item.concept_code, section.start, section.end), sanitize=False)
            with ui.column().classes("tour-step w-full gap-1"):
                ui.label(
                    f"Step {index + 1} of {len(sections)} · lines {section.start}-{section.end}"
                ).classes("eyebrow")
                ui.label(section.title).classes("text-lg font-bold")
                ui.label(section.text)
            with ui.row().classes("gap-2 items-center"):
                ui.button("Previous step", icon="chevron_left", on_click=lambda: go(index - 1)).props(
                    "flat" + (" disable" if index == 0 else "")
                )
                if index < len(sections) - 1:
                    ui.button("Next step", icon="chevron_right", on_click=lambda: go(index + 1))
                ui.button(
                    "Read aloud",
                    icon="volume_up",
                    on_click=lambda: ui.run_javascript(
                        "speechSynthesis.cancel();"
                        f"speechSynthesis.speak(new SpeechSynthesisUtterance({json.dumps(section.text)}));"
                    ),
                ).props("flat")
                ui.button("End tour", icon="close", on_click=lambda: go(None)).props("flat")
            ui.label(
                "Read aloud uses your browser's voice. The tour explains reviewed code; it does "
                "not show that the code ran."
            ).classes("text-xs text-slate-500")

        def go(index: int | None) -> None:
            ui.run_javascript("window.speechSynthesis && speechSynthesis.cancel()")
            step["index"] = index
            code_view.clear()
            view.refresh()

        view()


def learn_panel(lesson_id: int, tutorial: str, open_run: Any) -> None:
    item = guide(lesson_id)
    with card("Prepare this lesson", "Before you begin").classes("guide-preparation-context"):
        for number, line in enumerate(item.preparation):
            ui.markdown(f"- {line}").classes("guide-preparation-target" if number == 0 else "")
    with card("Understand the concept", "Concept"):
        ui.markdown(item.concept_brief)
        ui.markdown(f"**In this lab:** {item.lab_brief}")
        ui.button("Open exercise", icon="play_arrow", on_click=open_run)
    concept_code_card(lesson_id)
    if tutorial:
        # The concept code card above already shows this section; the file keeps it for readers.
        tutorial = re.sub(r"## The concept in code\n.*?(?=\n## )", "", tutorial, flags=re.S)
        with card("Lesson tutorial", "Read"):
            with ui.expansion("Read the full Python tutorial", value=True).classes("w-full"):
                ui.markdown(tutorial).classes("nicegui-markdown")
    workbook(lesson_id)
    with card(f"Lesson {lesson_id} knowledge check", "Check your understanding"):
        saved = record(lesson_id)
        render_quiz(item.quiz, saved["answers"], lambda answers: update(lesson_id, answers=answers))
        topic = LESSONS[lesson_id].topic
        if section_quiz(topic):
            ui.button(
                f"Open the {topic} section quiz", on_click=lambda: section_quiz_dialog(topic)
            ).props("outline")


def workbook(lesson_id: int) -> None:
    item, saved = guide(lesson_id), record(lesson_id)
    with card("Your review", "Workbook"):
        for index, text in enumerate(REVIEW_ITEMS):

            def tick(event: Any, index: int = index) -> None:
                marks = record(lesson_id)["checkpoints"]
                marks[index] = event.value
                update(lesson_id, checkpoints=marks)
                if all(marks):
                    ui.notify("Lesson marked as reviewed.", type="positive")

            ui.checkbox(text, value=saved["checkpoints"][index], on_change=tick)
        ui.textarea(
            "Private notes",
            value=saved["notes"],
            on_change=lambda e: update(lesson_id, notes=(e.value or "")[:20000]),
        ).props("outlined autogrow maxlength=20000").classes("w-full")
        ui.label("Challenge").classes("text-lg font-bold mt-2 guide-practice-context")
        ui.markdown(item.challenge)
        hints = ui.column().classes("w-full gap-1")

        @ui.refreshable
        def show_hints() -> None:
            shown = record(lesson_id)["hints"]
            for number, text in enumerate(item.hints[:shown]):
                ui.markdown(f"**{'Small' if number == 0 else 'Detailed'} hint:** {text}")
            if shown < len(item.hints):
                ui.button(
                    f"Show {'small' if shown == 0 else 'detailed'} hint",
                    on_click=lambda: (update(lesson_id, hints=shown + 1), show_hints.refresh()),
                ).props("outline")

        with hints:
            show_hints()
        with ui.expansion("Reference explanation").classes("w-full"):
            ui.markdown(item.reference)
        draft = (
            ui.textarea(
                "Your explanation and evidence",
                value=saved["draft"],
                on_change=lambda e: update(lesson_id, draft=(e.value or "")[:10000]),
            )
            .props("outlined autogrow maxlength=10000")
            .classes("w-full guide-practice-target guide-scroll-target")
        )

        @ui.refreshable
        def attempts() -> None:
            rows = record(lesson_id)["attempts"]
            ui.label(f"{len(rows)} saved attempts · saved text is not graded").classes(
                "text-sm text-slate-500"
            )
            for row in reversed(rows[-3:]):
                with ui.expansion(f"Attempt saved {row['at'][:16].replace('T', ' ')}").classes(
                    "w-full"
                ):
                    ui.label(row["text"]).classes("whitespace-pre-wrap")

        def save_attempt() -> None:
            text = (draft.value or "").strip()
            rows = record(lesson_id)["attempts"]
            if not text:
                ui.notify("Write your explanation first.", type="warning")
                return
            if len(rows) >= MAX_ATTEMPTS:
                ui.notify("This lesson already has 100 saved attempts.", type="warning")
                return
            rows.append(
                {
                    "text": text,
                    "hints": record(lesson_id)["hints"],
                    "at": datetime.now(UTC).isoformat(),
                }
            )
            update(lesson_id, attempts=rows)
            attempts.refresh()

        ui.button("Save attempt", icon="save", on_click=save_attempt)
        attempts()


def walkthrough_panel(lesson_id: int) -> None:
    item = guide(lesson_id)
    if lesson_id == 58:
        with card("Lesson 58 discovery walkthrough", "Search, admit, refund and verify"):
            ui.image("/assets/lesson-58-lab-walkthrough.svg").props('alt="ToolSearch reference precedes exact refund admission and owned ledger verification"').classes("w-full")
    if lesson_id == 57:
        with card("Lesson 57 integration walkthrough", "Two worker commits, serial picks and retained conflict"):
            ui.image("/assets/lesson-57-lab-walkthrough.svg").props('alt="Two worktrees run worker checks before the host cherry-picks serially or retains a conflict"').classes("w-full")
    if lesson_id == 56:
        with card("Lesson 56 team walkthrough", "Sixteen commands, five deliberate refusals"):
            ui.image("/assets/lesson-56-lab-walkthrough.svg").props('alt="Researcher and reviewer step through claims, message delivery, exact evidence, shutdown and cleanup"').classes("w-full")
    if lesson_id == 55:
        with card("Lesson 55 simulated canary", "Observe gates, then rehearse promotion and rollback"):
            ui.image("/assets/lesson-55-lab-walkthrough.svg").props('alt="Fixed candidate assessment leads through checked, canary, promoted and rolled back states"').classes("w-full")
    if lesson_id == 54:
        with card("Lesson 54 catalog walkthrough", "Direct calls, scripted cursor loop, guarded native comparison"):
            ui.image("/assets/lesson-54-lab-walkthrough.svg").props('alt="Direct valid and invalid calls, vague replay, focused cursor loop and paid comparison"').classes("w-full")
    if lesson_id == 53:
        with card("Lesson 53 debugging walkthrough", "Replay, inspect, reload and compare"):
            ui.image("/assets/lesson-53-lab-walkthrough.svg").props('alt="Choose a fault, inspect its first finding, reload its saved bundle, then compare one changed variable"').classes("w-full")
    if lesson_id == 52:
        with card("Lesson 52 evaluation walkthrough", "Cases, calibration and baseline gate"):
            ui.image("/assets/lesson-52-lab-walkthrough.svg").props('alt="Run fixed cases, inspect checks, calibrate, compare, and review promotion"').classes("w-full")
    if lesson_id == 51:
        with card("Lesson 51 offline walkthrough", "Sixteen assertions and six public replays"):
            ui.image("/assets/lesson-51-lab-walkthrough.svg").props('alt="Run all cases, inspect assertions, challenge mutation, replay fixtures"').classes("w-full")
    if lesson_id == 50:
        with card("Lesson 50 support desk walkthrough", "Scoped effects and CRM close"):
            ui.image("/assets/lesson-50-lab-walkthrough.svg").props("fit=contain").classes("w-full")
    if lesson_id == 49:
        with card("Lesson 49 headless walkthrough", "Processes, CI codes and local worker"):
            ui.image("/assets/lesson-49-lab-walkthrough.svg").props("fit=contain").classes("w-full")
    if lesson_id == 48:
        with card("Lesson 48 security walkthrough", "Fixed probes and independent effects"):
            ui.image("/assets/lesson-48-lab-walkthrough.svg").props("fit=contain").classes("w-full")
    if lesson_id == 47:
        with card("Lesson 47 orchestration walkthrough", "Worker evidence and dependent work"):
            ui.image("/assets/lesson-47-lab-walkthrough.svg").props(
                'alt="Owned CSV, matched worker lifecycle, host verdict, then handoff or dependent skip"'
            ).classes("w-full")
    if lesson_id == 46:
        with card("Lesson 46 cache walkthrough", "Four measured actions"):
            ui.image("/assets/lesson-46-lab-walkthrough.svg").props(
                'alt="Four cache actions lead to two-turn counter and hook evidence"'
            ).classes("w-full")
    if lesson_id == 45:
        with card("Lesson 45 cloud walkthrough", "Five owned actions"):
            ui.image("/assets/lesson-45-lab-walkthrough.svg").props(
                'alt="Catalog, Same, Auth, Models and Failure cloud-format actions"'
            ).classes("w-full")
    if lesson_id == 44:
        with card("Lesson 44 telemetry walkthrough", "Six collector actions"):
            ui.image("/assets/lesson-44-lab-walkthrough.svg").props(
                'alt="Six-step OTLP telemetry lab from signals through collector authentication"'
            ).classes("w-full")
    if lesson_id == 43:
        with card("Lesson 43 walkthrough map", "Owned remote MCP fixture"):
            ui.image("/assets/lesson-43-lab-walkthrough.svg").props(
                'alt="Seven-step remote MCP walkthrough from auth through live evidence and rotation limits"'
            ).classes("w-full")
    with card("Lab walkthrough", "Step by step"):
        ui.markdown(item.lab_brief)
        with ui.timeline(side="right").classes("w-full"):
            for number, step in enumerate(item.steps, 1):
                ui.timeline_entry(plain(step.text), title=f"{number}. {step.title}")
    with card("What to inspect", "Evidence"):
        ui.markdown(item.inspect)
        ui.label("Expected result").classes("font-semibold")
        ui.markdown(item.expected)
        ui.label("Automatic check").classes("font-semibold")
        ui.markdown(item.evidence_criterion)
    with card("If something goes wrong", "Recovery"):
        for line in item.recovery:
            ui.markdown(f"- {line}")


def infographic(lesson_id: int) -> None:
    """A per-lesson Python infographic built from the lesson's own content."""
    lesson, item = LESSONS[lesson_id], guide(lesson_id)
    with ui.element("div").classes("infographic w-full"):
        with ui.element("div").classes("ig-header"):
            ui.label(f"LESSON {lesson_id:02}").classes("ig-badge")
            with ui.column().classes("gap-0 min-w-0"):
                ui.label(lesson.title).classes("ig-title")
                ui.label(lesson.objective).classes("ig-objective")
        with ui.element("div").classes("ig-grid ig-three"):
            for number, point in enumerate(item.concept_points, 1):
                with ui.element("div").classes("ig-panel"):
                    ui.label(f"{number}. {plain(point.title)}").classes("ig-panel-title")
                    ui.markdown(point.text).classes("ig-panel-text")
        with ui.element("div").classes("ig-grid ig-two"):
            with ui.element("div").classes("ig-panel ig-code"):
                ui.label("The concept in Python").classes("ig-panel-title")
                ui.code(item.concept_code, language="python").classes("w-full")
                ui.markdown(item.code_focus).classes("ig-panel-text")
            with ui.column().classes("gap-3"):
                with ui.element("div").classes("ig-panel"):
                    ui.label("Evidence in this lesson").classes("ig-panel-title")
                    ui.markdown(item.evidence_criterion).classes("ig-panel-text")
                    for check in item.evidence_checks:
                        ui.label(f"\u2713 {check.key}").classes("ig-check")
                with ui.element("div").classes("ig-panel ig-myth"):
                    ui.label("Common misconception").classes("ig-panel-title")
                    ui.markdown(f"*{item.misconception.claim}*").classes("ig-panel-text")
                    ui.label("Not true.").classes("ig-not-true")
                    ui.markdown(item.misconception.correction).classes("ig-panel-text")
        ui.label(
            f"Lesson {lesson_id:02} \u00b7 {lesson.topic} \u00b7 Python edition, "
            "generated from the lesson content"
        ).classes("ig-footer")


def visual_panel(lesson_id: int) -> None:
    related = visual_guides_for(lesson_id)
    if lesson_id == 58:
        with card("Tool search concept map", "Lesson 58"):
            ui.image("/assets/lesson-58-concept-map.svg").props('alt="64 tool catalog is compared with local estimates and native context measurements"').classes("w-full")
    if lesson_id == 57:
        with card("Worktree coordination concept map", "Lesson 57"):
            ui.image("/assets/lesson-57-concept-map.svg").props('alt="Shared Git history connects isolated worker checkouts, host validation and serial integration"').classes("w-full")
    if lesson_id == 56:
        with card("Team coordination concept map", "Lesson 56"):
            ui.image("/assets/lesson-56-concept-map.svg").props('alt="Ownership, inbox delivery and exact evidence are independent team coordination gates"').classes("w-full")
    if lesson_id == 55:
        with card("SDK compatibility gate concept map", "Lesson 55"):
            ui.image("/assets/lesson-55-concept-map.svg").props('alt="Installed inventory and four independent synthetic contract gates feed eligibility"').classes("w-full")
    if lesson_id == 54:
        with card("Catalog tool contract concept map", "Lesson 54"):
            ui.image("/assets/lesson-54-concept-map.svg").props('alt="One immutable catalog feeds vague and focused tool contracts, then a correlated evidence gate"').classes("w-full")
    if lesson_id == 53:
        with card("Diagnostic evidence concept map", "Lesson 53"):
            ui.image("/assets/lesson-53-concept-map.svg").props('alt="Owned run evidence and SDK call IDs flow through causal findings and bounded persisted redaction"').classes("w-full")
    if lesson_id == 52:
        with card("Evaluation concept map", "Lesson 52"):
            ui.image("/assets/lesson-52-concept-map.svg").props('alt="Business facts and judge verdicts flow into statistical comparison"').classes("w-full")
    if lesson_id == 51:
        with card("Offline host testing concept map", "Lesson 51"):
            ui.image("/assets/lesson-51-concept-map.svg").props('alt="Fixed envelopes enter real host consumer and produce zero billed cost"').classes("w-full")
    if lesson_id == 50:
        with card("Support desk concept map", "Lesson 50"):
            ui.image("/assets/lesson-50-concept-map.svg").props("fit=contain").classes("w-full")
    if lesson_id == 49:
        with card("Headless evidence concept map", "Lesson 49"):
            ui.image("/assets/lesson-49-concept-map.svg").props("fit=contain").classes("w-full")
    if lesson_id == 48:
        with card("Security boundaries concept map", "Lesson 48"):
            ui.image("/assets/lesson-48-concept-map.svg").props("fit=contain").classes("w-full")
    if lesson_id == 47:
        with card("Orchestration concept map", "Lesson 47"):
            ui.image("/assets/lesson-47-concept-map.svg").props(
                'alt="Native lead, manager and analyst tree beside host-controlled regional fan-out"'
            ).classes("w-full")
    if lesson_id == 46:
        with card("Prompt cache concept map", "Lesson 46"):
            ui.image("/assets/lesson-46-concept-map.svg").props(
                'alt="A cache breakpoint requests reuse while response counters prove a read"'
            ).classes("w-full")
    if lesson_id == 45:
        with card("Cloud provider concept map", "Lesson 45"):
            ui.image("/assets/lesson-45-concept-map.svg").props(
                'alt="Five native provider configurations reach an owned proxy and fixed upstream"'
            ).classes("w-full")
    if lesson_id == 44:
        with card("OpenTelemetry concept map", "Lesson 44"):
            ui.image("/assets/lesson-44-concept-map.svg").props(
                'alt="Native SDK telemetry exports reach the collector as metrics logs and traces"'
            ).classes("w-full")
    if lesson_id == 43:
        with card("Remote MCP concept map", "Lesson 43"):
            ui.image("/assets/lesson-43-concept-map.svg").props(
                'alt="Remote MCP authentication, transports, tool and resource evidence, and reconnect versus rotation"'
            ).classes("w-full")
    with card("Lesson infographic", "Python"):
        infographic(lesson_id)
    with card("How this exercise is built", "Generated from the code"):
        ui.label(
            "This diagram is drawn from the exercise's own source, so it always matches what "
            "Run the exercise executes."
        ).classes("text-sm text-slate-600")
        with ui.element("div").classes("w-full overflow-x-auto"):
            ui.mermaid(exercise_diagram(lesson_id)).classes("exercise-diagram")
        with ui.row().classes("gap-2"):
            for kind, label in legend(lesson_id).items():
                ui.label(label).classes(f"legend-chip legend-{kind}")
    with card("Concept summary", "Visual guide"):
        ui.markdown(guide(lesson_id).concept_brief)
        if not related:
            ui.label(
                "No visual guide is mapped to this lesson yet. These course-wide guides apply to every lesson."
            ).classes("text-slate-500")
    for item in related or course().visual_guides:
        visual_guide_card(item, compact=not related)


def run_summary(state: Any, check: CheckResult) -> str:
    """What the tutor may see of the latest run: short and redacted, never raw traces."""
    parts = [
        f"Mode: {state.mode}. Status: {state.status}.",
        f"Automatic check: {check.status} ({check.detail})",
    ]
    if state.error:
        parts.append(f"Error: {state.error[:400]}")
    if state.response_texts:
        parts.append("Claude's answer: " + state.response_texts[-1][:1500])
    if state.evidence is not None:
        evidence = json.dumps(redact(state.evidence), default=str, ensure_ascii=False)
        parts.append("Exercise evidence: " + evidence[:3000])
    return "\n".join(parts)[:6000]


def check_card(lesson_id: int, result: CheckResult | None) -> None:
    item = guide(lesson_id)
    with card("Automatic check", "Evidence"):
        ui.markdown(item.evidence_criterion)
        if result is None:
            ui.label("Run the exercise to check its evidence.").classes("text-slate-500")
            return
        passed = result.status == "passed"
        with ui.row().classes("items-center gap-2"):
            ui.icon(
                "check_circle" if passed else "report", color="positive" if passed else "warning"
            )
            ui.label("Check passed" if passed else "Needs review").classes("font-bold")
        ui.markdown(result.detail)
        ui.label(
            "The automatic check covers the bounded evidence criterion shown above. Your own review in the Learn tab stays separate."
            if lesson_id <= 45 else
            "The automatic check covers local evidence only. Your own review in the Learn tab stays separate."
        ).classes("text-xs text-slate-500")


def tutor_panel(lesson_id: int, tutor: TutorService, source: str) -> None:
    live = tutor.settings.enable_live
    with card("AI Tutor", "Ask about this lesson"):
        ui.label(
            "Prepared answers are written from this lesson's content and cost nothing. "
            "Live answers send this lesson's context and your question to Claude."
        ).classes("text-slate-600")
        mode = ui.toggle(
            {"prepared": "Prepared answer", "live": "Live Claude answer"}, value="prepared"
        )
        intent = ui.select(TUTOR_INTENTS, value="explain", label="What do you need?").classes(
            "w-72"
        )
        question = (
            ui.textarea(
                "Your question (live only)", placeholder="Why does the handler validate again?"
            )
            .props("outlined autogrow maxlength=2000")
            .classes("w-full")
            .bind_enabled_from(mode, "value", lambda value: value == "live")
        )
        model = (
            ui.select([tutor.settings.model], value=tutor.settings.model, label="Model")
            .classes("w-72")
            .bind_visibility_from(mode, "value", lambda value: value == "live")
        )
        consent = ui.checkbox(
            f"I authorize one paid request (budget threshold {TUTOR_BUDGET_USD:.2f} USD, one turn, no tools)."
        ).bind_visibility_from(mode, "value", lambda value: value == "live")
        if not live:
            # The option stays visible so students can find it; it explains how to turn it on.
            ui.label(
                "Live answers are turned off. Set ANTHROPIC_API_KEY and LAB_ENABLE_LIVE=true in "
                ".env, then restart the app."
            ).classes("text-sm text-amber-700").bind_visibility_from(
                mode, "value", lambda value: value == "live"
            )
        latest = record(lesson_id)["last_run"]
        include_run = ui.checkbox("Include my latest run of this lesson", value=bool(latest))
        include_run.set_visibility(bool(latest))
        ask = ui.button("Ask the tutor", icon="school").bind_enabled_from(
            mode, "value", lambda value: value == "prepared" or live
        )
        status = ui.label("")

    with card("Answer"):
        answer_box = ui.column().classes("w-full")
        with answer_box:
            ui.label("Choose what you need and ask the tutor.").classes("text-slate-500")
        last: dict[str, Any] = {}
        save_button = ui.button("Save this answer", icon="bookmark").props("outline")
        save_button.set_visibility(False)

    @ui.refreshable
    def saved_answers() -> None:
        rows = record(lesson_id)["tutor"]
        if not rows:
            return
        with card(f"Saved answers ({len(rows)})"):
            for index, row in enumerate(reversed(rows)):
                title = f"{TUTOR_INTENTS.get(row['intent'], row['intent'])} · {row['mode']}"
                with ui.expansion(
                    title + (f" · {row['question'][:60]}" if row["question"] else "")
                ).classes("w-full"):
                    ui.markdown(row["text"]).classes("response-prose")

                    def remove(position: int = len(rows) - 1 - index) -> None:
                        kept = record(lesson_id)["tutor"]
                        kept.pop(position)
                        update(lesson_id, tutor=kept)
                        saved_answers.refresh()

                    ui.button("Delete", icon="delete", on_click=remove).props("flat color=negative")

    saved_answers()

    async def load_models() -> None:
        if live:
            model.set_options(await tutor.models(), value=tutor.settings.model)

    async def run() -> None:
        request = TutorRequest(
            mode=mode.value,
            intent=intent.value,
            question=question.value or "",
            model=model.value,
            consent=bool(consent.value),
            latest_run=record(lesson_id)["last_run"] if include_run.value else "",
        )
        ask.disable()
        status.set_text("Asking Claude…" if request.mode == "live" else "")
        try:
            answer = await tutor.answer(lesson_id, request, source)
        except (PermissionError, ValueError, LessonError) as exc:
            ui.notify(str(exc), type="warning")
            status.set_text("")
            return
        except Exception as exc:
            ui.notify(f"{type(exc).__name__}: the tutor request failed.", type="negative")
            status.set_text("")
            return
        finally:
            ask.enable()
            consent.set_value(False)  # Consent covers exactly one request.
        last.clear()
        last.update(answer.model_dump())
        answer_box.clear()
        with answer_box:
            ui.badge(
                "LIVE CLAUDE ANSWER" if answer.mode == "live" else "PREPARED ANSWER",
                color="primary" if answer.mode == "live" else "secondary",
            )
            ui.markdown(answer.text).classes("response-prose w-full min-w-0")
            if answer.mode == "live":
                ui.label(
                    f"Model {answer.model} · ${answer.cost_usd or 0:.4f} reported cost"
                ).classes("text-xs text-slate-500")
        status.set_text("")
        save_button.set_visibility(True)

    def save() -> None:
        rows = record(lesson_id)["tutor"]
        rows.append(last | {"at": datetime.now(UTC).isoformat()})
        update(lesson_id, tutor=rows[-MAX_SAVED_ANSWERS:])
        save_button.set_visibility(False)
        saved_answers.refresh()

    ask.on_click(run)
    save_button.on_click(save)
    ui.timer(0.1, load_models, once=True)


def section_quiz_dialog(topic: str, on_close: Callable[[], None] | None = None) -> None:
    quiz = section_quiz(topic)
    if quiz is None:
        return
    answers = dict(_store().get("sections", {}).get(quiz.id, {}))

    def save(values: dict[str, int]) -> None:
        sections = dict(_store().get("sections", {}))
        sections[quiz.id] = values
        _store()["sections"] = sections

    with ui.dialog() as dialog, ui.card().classes("w-full max-w-3xl p-6 gap-3"):
        ui.label(f"{topic} section quiz").classes("text-xl font-bold")
        render_quiz(quiz.questions, answers, save)
        ui.button("Close", on_click=dialog.close)
    if on_close is not None:
        dialog.on("hide", on_close)
    dialog.open()


# ---------------------------------------------------------------- home page


def next_in_path(lessons: list[int]) -> int:
    return next((n for n in lessons if not completed(n)), lessons[0])


def progress_card() -> None:
    """Move progress between browsers: export a JSON file, or replace progress from one."""
    with card("Your progress", "Backup and transfer"):
        ui.label(
            "Progress is stored in this browser only. Export it to keep a backup or to "
            "continue in another browser; importing replaces the progress stored here."
        ).classes("text-sm text-slate-600")

        def export() -> None:
            ui.download.content(
                export_progress(_store()), "agent-lab-progress.json", "application/json"
            )

        async def received(event: Any) -> None:
            try:
                data = import_progress(await event.file.read())
            except ValueError as exc:
                ui.notify(str(exc), type="warning")
                return
            reviewed = sum(all(row["checkpoints"]) for row in data["lessons"].values())
            with ui.dialog() as dialog, ui.card().classes("p-6 gap-3"):
                ui.label("Replace your progress?").classes("text-lg font-bold")
                ui.label(
                    f"The file has {len(data['lessons'])} lessons with saved work, "
                    f"{reviewed} of them reviewed. Your current progress in this browser "
                    "will be replaced. This cannot be undone."
                )

                def replace() -> None:
                    for key in PROGRESS_KEYS:
                        _store()[key] = data[key]
                    dialog.close()
                    ui.navigate.reload()

                with ui.row().classes("gap-2"):
                    ui.button("Replace progress", on_click=replace).props("color=negative")
                    ui.button("Cancel", on_click=dialog.close).props("flat")
            dialog.open()
            upload.reset()

        with ui.row().classes("gap-3 items-center"):
            ui.button("Export progress", icon="download", on_click=export).props("outline")
            upload = (
                ui.upload(
                    label="Import progress (.json)",
                    auto_upload=True,
                    max_file_size=PROGRESS_MAX_BYTES,
                    on_upload=received,
                    on_rejected=lambda: ui.notify(
                        "Choose a progress export under 2 MB.", type="warning"
                    ),
                )
                .props("accept=.json flat bordered")
                .classes("max-w-xs")
            )


def home_page() -> None:
    done = [n for n in LESSONS if completed(n)]
    last = int(preference("last_lesson", "0") or 0)
    with card():
        ui.label("Build agents with Python").classes("course-title")
        ui.label(
            "Learn the official Claude Agent SDK through runnable Python exercises, then connect your agents to FastAPI and NiceGUI."
        ).classes("text-lg text-slate-600")
        ui.label(
            "Offline exercises run local Python code without API costs. Live mode starts the real SDK and reports its messages and usage."
        )
        ui.linear_progress(len(done) / len(LESSONS), show_value=False).props("rounded size=10px")
        ui.label(f"{len(done)} of {len(LESSONS)} lessons reviewed").classes(
            "text-sm text-slate-500"
        )
        with ui.row().classes("gap-3"):
            if last in LESSONS:
                ui.button(
                    f"Continue lesson {last}",
                    icon="play_arrow",
                    on_click=lambda: ui.navigate.to(f"/?lesson={last}"),
                )
            ui.button("Start with lesson 1", on_click=lambda: ui.navigate.to("/?lesson=1")).props(
                "outline" if last in LESSONS else ""
            )
    progress_card()
    ui.link("Open My Learning", "/my-learning").classes("text-lg font-bold")
    ui.label("Milestone projects").classes("text-xl font-bold mt-4")
    ui.markdown(
        "Three apps you build yourself, in this order: **understand** concepts in the Study "
        "Coach, **evaluate** runs in the Evaluation Studio, then **publish** reviewed answers. "
        "Their counts measure different activities (concept cards, evaluation cases, prompt "
        "suggestions), so do not add them up. A finished stage is your code passing its checks, "
        "not a lesson marked complete. The procedure is in `docs/milestone-projects.md`."
    ).classes("text-slate-600")
    projects = [
        (
            "1 · Understand: Study Coach",
            "7 stages · 80 concept cards",
            "Validated questions, live conversations that resume the SDK session, structured "
            "study plans and safe recovery; start-here cards and recognition checks.",
            "Open the Study Coach",
            "school",
            "/coach",
        ),
        (
            "2 · Evaluate: Agent Evaluation Studio",
            "7 stages · 170 cases",
            "Honest run summaries, instruction variants, bounded live runs with MCP, reviews, "
            "evidence export and a release decision.",
            "Open the Evaluation Studio",
            "fact_check",
            "/studio",
        ),
        (
            "3 · Publish: Agent Publishing Studio",
            "8 stages · 173 prompts",
            "Turn a saved SDK answer into Word, PDF, SVG and PNG files: consented live answers, "
            "uploaded sources, validated plans, highlighted code and a PNG style reference.",
            "Open the Publishing Studio",
            "auto_stories",
            "/publish",
        ),
    ]
    with ui.grid(columns="repeat(auto-fit, minmax(260px, 1fr))").classes("w-full gap-4"):
        for title, eyebrow, text, button, icon, page in projects:
            with card(title, eyebrow):
                ui.label(text).classes("flex-1")
                ui.button(button, icon=icon, on_click=lambda page=page: ui.navigate.to(page))

    ui.label("Learning paths").classes("text-xl font-bold mt-4")
    with ui.grid(columns="repeat(auto-fit, minmax(260px, 1fr))").classes("w-full gap-4"):
        for path in course().paths:
            finished = sum(completed(n) for n in path.lessons)
            with card(path.title, f"{len(path.lessons)} lessons"):
                ui.label(path.description)
                ui.label(path.outcome).classes("text-sm text-slate-500")
                ui.linear_progress(finished / len(path.lessons), show_value=False).props("rounded")
                ui.label(f"{finished} of {len(path.lessons)} reviewed").classes("text-sm")
                target = next_in_path(path.lessons)
                ui.button(
                    f"Open lesson {target}",
                    on_click=lambda t=target, p=path.id: ui.navigate.to(lesson_url(t, p)),
                ).props("outline")

    ui.label("Course sections").classes("text-xl font-bold mt-4")
    with ui.grid(columns="repeat(auto-fit, minmax(260px, 1fr))").classes("w-full gap-4"):
        for topic, ids in TOPICS.items():
            finished = sum(completed(n) for n in ids)
            with card(topic, f"{len(ids)} lessons"):
                ui.label(
                    ", ".join(LESSONS[n].title for n in ids[:4]) + ("…" if len(ids) > 4 else "")
                ).classes("text-sm text-slate-600")
                ui.linear_progress(finished / len(ids), show_value=False).props("rounded")
                with ui.row().classes("gap-2"):
                    ui.button(
                        f"Lesson {ids[0]}",
                        on_click=lambda n=ids[0]: ui.navigate.to(f"/?lesson={n}"),
                    ).props("outline")
                    if section_quiz(topic):
                        ui.button(
                            "Section quiz", on_click=lambda t=topic: section_quiz_dialog(t)
                        ).props("flat")

    ui.label("Visual guides").classes("text-xl font-bold mt-4")
    with ui.grid(columns="repeat(auto-fit, minmax(260px, 1fr))").classes("w-full gap-4"):
        for item in course().visual_guides:
            visual_guide_card(item, compact=True)


# ---------------------------------------------------------------- appearance


APPEARANCE_CSS = """
    .eyebrow { font-size: 14px !important; letter-spacing: .08em; font-weight: 700; color: #7c3aed; }
    .response-prose h2 { font-size: 1.45em; line-height: 1.3; }
    .response-prose h3 { font-size: 1.2em; line-height: 1.3; }
    .feedback { padding: 8px 12px; border-radius: 8px; }
    .exercise-diagram { min-width: 640px; }
    .q-table__container { max-width: 100%; }
    .q-table__middle { overflow-x: auto; }
    .infographic { border: 1px solid #c9d8f0; border-radius: 16px; padding: 18px; background: #f6f9fe; display: flex; flex-direction: column; gap: 14px; }
    .ig-header { display: flex; gap: 16px; align-items: center; }
    .ig-badge { background: #1e3a6e; color: #fff; font-weight: 800; letter-spacing: .04em; padding: 10px 16px; border-radius: 10px; white-space: nowrap; font-size: 20px !important; }
    .ig-title { font-size: 28px !important; font-weight: 800; color: #12264d; line-height: 1.2; }
    .ig-objective { font-size: 17px !important; color: #3a4a66; font-style: italic; }
    .ig-grid { display: grid; gap: 12px; }
    .ig-three { grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); }
    .ig-two { grid-template-columns: minmax(0, 3fr) minmax(0, 2fr); }
    @media (max-width: 900px) { .ig-two { grid-template-columns: minmax(0, 1fr); } .ig-header { flex-direction: column; align-items: flex-start; } }
    .ig-panel { background: #fff; border: 1px solid #c9d8f0; border-radius: 12px; padding: 12px 14px; min-width: 0; }
    .ig-panel-title { font-weight: 800; color: #12264d; font-size: 18px !important; margin-bottom: 4px; }
    .ig-panel-text, .ig-panel-text p { font-size: 16px !important; line-height: 1.5; color: #2b3a55; }
    .ig-check { font-size: 15px !important; color: #146c43; font-weight: 600; }
    .ig-code pre, .ig-code code { white-space: pre-wrap !important; overflow-wrap: anywhere; font-size: 14px !important; }
    .ig-myth { border-color: #f5b38a; background: #fff7f1; }
    .ig-not-true { color: #c2410c; font-weight: 800; font-size: 16px !important; }
    .ig-footer { font-size: 13px !important; color: #6b7a96; }
    body.body--dark .infographic { background: #161a2b; border-color: #2d3a5c; }
    body.body--dark .ig-panel { background: #1b1f33; border-color: #2d3a5c; }
    body.body--dark .ig-title, body.body--dark .ig-panel-title { color: #dbe6ff; }
    body.body--dark .ig-objective, body.body--dark .ig-panel-text, body.body--dark .ig-panel-text p { color: #b9c3dd; }
    body.body--dark .ig-myth { background: #2a1d17; border-color: #8a4b2a; }
    body.body--dark .ig-check { color: #6ee7b7; }
    body.body--dark .text-amber-700 { color: #fbbf24 !important; }
    body.body--dark .exercise-diagram .flowchart-link { stroke: #c4c1d9 !important; }
    body.body--dark .exercise-diagram marker path { fill: #c4c1d9 !important; stroke: #c4c1d9 !important; }
    .legend-chip { font-size: 14px !important; padding: 2px 10px; border-radius: 999px; border: 1px solid; color: #1f1d2e; }
    .legend-sdk { background: #ede9fe; border-color: #7c3aed; }
    .legend-fixture { background: #fef3c7; border-color: #d97706; }
    .legend-host { background: #e0f2fe; border-color: #0284c7; }
    .legend-process { background: #fce7f3; border-color: #db2777; }
    .legend-external { background: #dcfce7; border-color: #16a34a; }
    .legend-data { background: #f1f5f9; border-color: #64748b; }
    .feedback-ok { background: #ecfdf5; color: #065f46; }
    .feedback-bad { background: #fff7ed; color: #9a3412; }
    .q-notification {
        --q-info: #163a63; --q-negative: #7f1d1d; --q-positive: #14532d;
        --q-warning: #fef3c7; --q-primary: #ffffff;
        background: #1e293b; color: #ffffff;
        max-width: min(860px, calc(100vw - 32px)); padding: 16px 20px;
        border: 1px solid #64748b; border-radius: 12px;
    }
    .q-notification.bg-info { border-color: #93c5fd; }
    .q-notification.bg-negative { border-color: #fca5a5; }
    .q-notification.bg-positive { border-color: #86efac; }
    .q-notification.bg-warning { --q-primary: #422006; color: #422006; border-color: #b45309; }
    .q-notification__wrapper, .q-notification__content { min-width: 0; }
    .q-notification__message {
        font-size: 20px !important; font-weight: 600; line-height: 1.6;
        white-space: normal; overflow-wrap: anywhere;
    }
    .q-notification__icon { color: inherit !important; font-size: 28px; }
    .q-notification__actions .q-btn { color: inherit !important; font-size: 18px; min-height: 44px; }
    @media (max-width: 600px) {
        .q-notification__wrapper { flex-direction: column; align-items: stretch; }
        .q-notification__actions { align-self: flex-end; padding-left: 0; }
    }
    body.lab-text-large .q-notification__message { font-size: 22px !important; }
    body.lab-text-xlarge .q-notification__message { font-size: 24px !important; }
    body.lab-text-small .q-page-container { zoom: .9; }
    body.lab-text-large .q-page-container { zoom: 1.12; }
    body.lab-text-xlarge .q-page-container { zoom: 1.25; }
    .q-header.lab-header { background: #fff; color: #1f1d2e; }
    .q-header.lab-header a { color: #1f1d2e; }
    body.body--dark { background: #12121a; color: #e7e6f0; }
    body.body--dark .q-header.lab-header { background: #1b1a26; color: #e7e6f0; }
    body.body--dark .q-header.lab-header a { color: #e7e6f0; }
    body.body--dark .q-drawer { background: #1b1a26; border-color: #2d2b3d; }
    body.body--dark .lesson-menu a { color: #cfcbe6; }
    body.body--dark .course-card { border-color: #2d2b3d; background: #1b1a26; }
    body.body--dark .bg-white { background: #1b1a26 !important; }
    body.body--dark .bg-amber-50 { background: #3a2f12 !important; }
    body.body--dark .bg-red-50 { background: #3b1414 !important; }
    body.body--dark .text-red-800 { color: #fecaca !important; }
    body.body--dark .bg-slate-100 { background: #0f0f16 !important; }
    body.body--dark .text-slate-500, body.body--dark .text-slate-600,
    body.body--dark .text-slate-700 { color: #a9a6bf !important; }
    body.body--dark .text-slate-900 { color: #e7e6f0 !important; }
    body.body--dark .eyebrow { color: #c4b5fd; }
    body.body--dark .feedback-ok { background: #0b3b2c; color: #a7f3d0; }
    body.body--dark .feedback-bad { background: #43230b; color: #fed7aa; }
"""


BASE_CSS = """
    html { font-size: 18px; }
    body { background: #f5f5fa; color: #222238; font-size: 18px; line-height: 1.6; }
    .text-xs { font-size: 16px !important; line-height: 1.5 !important; }
    .text-sm { font-size: 18px !important; line-height: 1.5 !important; }
    .text-lg { font-size: 22px !important; line-height: 1.5 !important; }
    .text-xl { font-size: 26px !important; line-height: 1.4 !important; }
    .q-btn, .q-tab__label, .q-item__label, .q-expansion-item__container > .q-item { font-size: 18px; }
    .q-field__native, .q-field__input { font-size: 18px; line-height: 1.5; }
    .q-field__label { font-size: 20px; }
    .q-badge { font-size: 15px; line-height: 1.4; }
    .q-table th, .q-table td { font-size: 18px; }
    .nicegui-markdown { font-size: 20px; line-height: 1.75; }
    .nicegui-markdown pre, .nicegui-code, .nicegui-code pre,
    .nicegui-markdown code, .nicegui-code code { font-size: 17px !important; }
    .nicegui-log { font-size: 16px; line-height: 1.6; }
    .course-card { border: 1px solid #e6e3ee; border-radius: 16px; box-shadow: none; min-width: 0; max-width: 100%; overflow-wrap: anywhere; }
    .course-card .q-btn-toggle { flex-wrap: wrap; max-width: 100%; }
    .lesson-menu a { color: #44415b; text-decoration: none; display: block; padding: 7px 0; }
    .lesson-menu a:hover { color: #7c3aed; }
    .course-title { font-size: 36px; font-weight: 750; line-height: 1.2; }
    .q-drawer { background: #fff; border-right: 1px solid #e6e3ee; }
    .response-prose { font-size: 20px; line-height: 1.75; overflow-wrap: anywhere; }
    .response-prose pre { overflow-x: auto; max-width: 100%; padding: 16px; border-radius: 10px; }
    .response-prose table { display: block; overflow-x: auto; max-width: 100%; }
    .response-prose h1, .response-prose h2, .response-prose h3 { margin-top: 1em; font-weight: 700; }
"""


def tour_css() -> str:
    """Pygments colors for the code tour; the code box stays light in both themes."""
    from pygments.formatters import HtmlFormatter

    return HtmlFormatter(style="default").get_style_defs(".tour-code") + """
    .tour-code { background: #f8fafc; color: #1e293b; border: 1px solid #cbd5e1; border-radius: 12px;
                 padding: 12px; overflow-x: auto; max-width: 100%; }
    .tour-code pre { margin: 0; font-size: 0.9rem; line-height: 1.5; background: transparent; }
    .tour-code .hll { background: #fde68a; }
    .tour-code .linenos { color: #64748b; background: transparent; padding-right: 0.75rem; user-select: none; }
    .tour-step { border-left: 4px solid #f59e0b; padding-left: 0.75rem; }
    """


def page_style() -> None:
    """Colors and styles shared by every page of the course."""
    ui.colors(primary="#7c3aed", secondary="#0f766e", accent="#f59e0b")
    ui.add_css(BASE_CSS + APPEARANCE_CSS + tour_css())


def appearance_controls() -> None:
    """Theme and text size, remembered for this browser."""
    dark = ui.dark_mode()
    theme = preference("theme", "light")
    dark.set_value({"light": False, "dark": True}.get(theme))
    size = preference("text_size", "normal")
    ui.query("body").classes(f"lab-text-{size}")

    def set_theme(value: str) -> None:
        set_preference("theme", value)
        dark.set_value({"light": False, "dark": True}.get(value))

    def set_size(value: str) -> None:
        ui.query("body").classes(
            remove=" ".join(f"lab-text-{name}" for name in TEXT_SIZES), add=f"lab-text-{value}"
        )
        set_preference("text_size", value)

    with ui.button(icon="tune").props("flat round color=primary aria-label='Appearance'"):
        with ui.menu().classes("p-4"), ui.column().classes("gap-2"):
            ui.label("Appearance").classes("font-bold")
            ui.toggle(
                {"light": "Light", "dark": "Dark", "auto": "System"},
                value=theme,
                on_change=lambda e: set_theme(e.value),
            )
            ui.select(
                TEXT_SIZES, value=size, label="Text size", on_change=lambda e: set_size(e.value)
            )
