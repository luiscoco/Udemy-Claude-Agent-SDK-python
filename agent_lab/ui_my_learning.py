"""My Learning workspace over the existing browser-local learning records."""

import json
from typing import Any

from nicegui import ui

from agent_lab.learning import course
from agent_lab.lesson_guide import learning_guides, lesson_url
from agent_lab.my_learning import (
    QuizAnswer,
    SectionQuizSummary,
    filter_lessons,
    learning_snapshot,
    lesson_link,
    setup_url,
    valid_path,
    workspace_url,
)
from agent_lab.ui_learning import (
    appearance_controls,
    card,
    page_style,
    plain,
    progress_card,
    section_quiz_dialog,
    stored,
)

WORKSPACE_CSS = """
.my-learning { overflow-wrap: anywhere; }
.my-learning .course-title { font-size: clamp(28px, 5vw, 36px); }
.my-learning .q-btn { min-height: 44px; white-space: normal; max-width: 100%; }
.my-learning .q-field { min-width: 0; max-width: 100%; }
.my-learning .q-uploader { width: 100%; max-width: 100%; min-width: 0; }
.my-learning a { display: inline-flex; align-items: center; min-height: 44px; max-width: 100%; }
.my-learning-views { flex-wrap: wrap; max-width: 100%; gap: 4px; }
.my-learning-text { white-space: pre-wrap; max-height: 18rem; overflow: auto; width: 100%; }
@layer overrides {
    .my-learning .q-btn:focus-visible { outline: 3px solid #2563eb !important; outline-offset: 3px; }
    body.body--dark .my-learning .q-btn:focus-visible { outline-color: #93c5fd !important; }
}
@media (max-width: 600px) {
    .my-learning .course-card { padding: 16px; }
}
"""


def _header(title: str) -> None:
    with ui.header().classes("lab-header border-b items-center"):
        ui.link("Claude Agent SDK Lab", "/").classes(
            "text-xl font-bold no-underline text-slate-900 min-w-0 flex-1"
        )
        ui.badge(title, color="secondary").classes("gt-xs")
        appearance_controls()


def _saved_text(title: str, text: str) -> None:
    if text.strip():
        ui.label(title).classes("font-bold")
        # Saved student text is plain text, never executable Markdown/HTML or remote media.
        ui.label(text).classes("my-learning-text").props('tabindex="0"')


def _answers(answers: tuple[QuizAnswer, ...]) -> None:
    for answer in answers:
        option = answer.question.options[answer.chosen]
        with ui.column().classes("w-full gap-1 feedback " + ("feedback-ok" if answer.correct else "feedback-bad")):
            ui.label(plain(answer.question.prompt)).classes("font-bold")
            ui.label(f"Saved answer: {plain(option.text)}")
            ui.label("Correct" if answer.correct else "Review this answer").classes("font-bold")
            ui.label(plain(option.explanation))


def _section_score(quiz: SectionQuizSummary) -> str:
    return f"{quiz.topic}: {sum(a.correct for a in quiz.answers)} correct / {quiz.total} questions; {len(quiz.answers)} answered"


def install_my_learning_pages() -> None:
    @ui.page("/my-learning")
    def my_learning(path: str = "") -> None:
        page_style()
        ui.add_css(WORKSPACE_CSS)
        _header("MY LEARNING")
        snapshot = learning_snapshot({key: stored(key, None) for key in (
            "lessons", "sections", "last_lesson", "learning_guide_positions",
        )})
        selected = valid_path(path)
        page_state: dict[str, Any] = {"view": "Lessons", "limit": 12, "path": selected}
        attempt_limits: dict[int, int] = {}
        section_scores: dict[str, ui.label] = {}
        section_buttons: dict[str, ui.button] = {}
        with ui.column().classes("my-learning w-full max-w-6xl mx-auto py-4 md:p-8 gap-5"):
            ui.link("Back to course", "/").classes("font-bold")
            ui.label("My Learning").classes("course-title").props('role="heading" aria-level="1"')
            ui.label("Your progress and saved work.").classes("text-lg text-slate-600")
            resume = snapshot.resume(selected)
            if resume and (snapshot.last_lesson is not None or snapshot.saved_lessons):
                with card("Continue learning", "Last visited lesson" if snapshot.last_lesson else "Saved work"):
                    ui.label(f"Lesson {resume.id}: {resume.title}").classes("text-lg font-bold")
                    ui.label(f"Manual status: {resume.state}")
                    if resume.guide_section:
                        section = next(s for s in learning_guides()[resume.id].sections if s.id == resume.guide_section)
                        ui.label(f"Saved guide section: {section.title}")
                    with ui.row().classes("w-full gap-2"):
                        if resume.guide_section:
                            ui.button("Resume Learning Guide", icon="explore", on_click=lambda: ui.navigate.to(
                                lesson_link(resume, page_state["path"], resume_guide=True)
                            ))
                        ui.button(f"Continue lesson {resume.id}", icon="play_arrow", on_click=lambda: ui.navigate.to(
                            lesson_link(resume, page_state["path"])
                        )).props("outline" if resume.guide_section else "")
            elif not snapshot.saved_lessons:
                with card("Start your learning journey", "Your first step"):
                    with ui.row().classes("w-full gap-2"):
                        ui.button("Start lesson 1", icon="play_arrow", on_click=lambda: ui.navigate.to(lesson_url(1, page_state["path"])))
                        ui.button("Review setup", icon="settings", on_click=lambda: ui.navigate.to(setup_url(page_state["path"]))).props("outline")
                    ui.label("Learn the Python concept, run its offline exercise, and inspect the evidence.")
                    ui.label("1. Read Learn and Python source.  2. Run the offline exercise.  3. Save notes and review the checklist when ready.")

            with ui.grid(columns="repeat(auto-fit, minmax(min(100%, 210px), 1fr))").classes("w-full gap-3"):
                for title, value, detail in (
                    ("Manual review", f"{snapshot.reviewed} of 75", "Only your four checklist choices count."),
                    ("Saved work", f"{snapshot.saved_lessons} lesson{'s' if snapshot.saved_lessons != 1 else ''}", "Notes, answers, attempts, checks or guide positions."),
                    ("Exercise checks", f"{snapshot.exercise_checks} lesson{'s' if snapshot.exercise_checks != 1 else ''}", "Saved checks are separate from manual review."),
                ):
                    with card(title):
                        ui.label(value).classes("text-2xl font-bold")
                        ui.label(detail).classes("text-sm text-slate-600")
            with card("Manual checklist progress"):
                ui.linear_progress(snapshot.reviewed / 75, show_value=False).props("rounded size=10px")
                ui.label(f"{snapshot.reviewed} of 75 lessons manually reviewed")

            ui.label(
                "Your notes, answers and checklist choices stay in this browser. "
                "Export progress for backup or transfer. Visiting a page never marks a lesson reviewed."
            ).classes("text-sm text-slate-600")

            ui.label("Learning paths").classes("text-xl font-bold").props('role="heading" aria-level="2"')
            with ui.grid(columns="repeat(auto-fit, minmax(min(100%, 260px), 1fr))").classes("w-full gap-3"):
                for item in snapshot.paths:
                    with card(item.title):
                        ui.label(item.description)
                        ui.linear_progress(item.reviewed / len(item.lessons), show_value=False).props("rounded")
                        ui.label(f"{item.reviewed} of {len(item.lessons)} manually reviewed")
                        if item.next_lesson is not None:
                            ui.link(f"Next unreviewed lesson {item.next_lesson}", lesson_url(item.next_lesson, item.id)).classes("font-bold")
                        else:
                            ui.label("All lessons in this path are manually reviewed.")
                        ui.link("View this path", workspace_url(item.id))

            ui.label("Your learning workspace").classes("text-xl font-bold").props('role="heading" aria-level="2"')
            ui.label("Practice quiz answers and exercise checks are independent of manual lesson review.").classes("text-sm text-slate-600")
            with ui.row().classes("w-full items-start gap-3"):
                path_choice = ui.select({"": "All lessons", **{p.id: p.title for p in course().paths}},
                                        value=selected, label="Learning path").props("outlined dense").classes("w-full sm:w-64")
                search = ui.input("Find lessons or saved text", placeholder="Lesson, topic, note or attempt").props(
                    "outlined dense clearable debounce=200 maxlength=200"
                ).classes("w-full sm:flex-1")
                status = ui.select({"all": "All statuses", "in-progress": "In progress", "reviewed": "Reviewed",
                                    "no-work": "No saved work", "needs-review": "Exercise needs review"},
                                   value="all", label="Manual / exercise status").props("outlined dense").classes("w-full sm:w-64")
            views = ui.toggle(["Lessons", "Notes", "Quiz results", "Attempts"], value="Lessons").classes("my-learning-views").props('role="group" aria-label="Saved work view"')

            @ui.refreshable
            def results() -> None:
                rows = filter_lessons(snapshot, path=path_choice.value or "", search=search.value or "",
                                      state=status.value, view=page_state["view"])
                ui.label(f"{len(rows)} matching lesson{'s' if len(rows) != 1 else ''}").props('role="status" aria-live="polite"')
                if not rows:
                    ui.label("No saved work matches these filters." if page_state["view"] != "Lessons" else "No lessons match these filters.")
                for row in rows[:page_state["limit"]]:
                    with card(f"{row.id}. {row.title}", row.topic).classes("my-learning-lesson"):
                        with ui.row().classes("w-full items-center gap-2"):
                            ui.badge(row.state, color="positive" if row.reviewed else "secondary" if row.has_work else "grey")
                            ui.label(f"Practice quiz: {row.quiz_correct} correct / {row.quiz_total} questions; {len(row.answers)} answered")
                            ui.label(f"Saved attempts: {len(row.attempts)}")
                        ui.label(f"Exercise check: {row.check_status or 'not recorded'}")
                        if row.guide_section:
                            title = next(s.title for s in learning_guides()[row.id].sections if s.id == row.guide_section)
                            ui.label(f"Saved guide section: {title}")
                        view = page_state["view"]
                        if view == "Notes":
                            _saved_text("Private notes", row.notes)
                            _saved_text("Unsubmitted explanation", row.draft)
                        elif view == "Quiz results":
                            _answers(row.answers)
                        elif view == "Attempts":
                            limit = attempt_limits.get(row.id, 5)
                            for attempt in tuple(reversed(row.attempts))[:limit]:
                                ui.label(f"Saved {attempt.at or 'without a timestamp'}; {attempt.hints} hints used").classes("text-sm")
                                _saved_text("Your saved explanation", attempt.text)
                            if len(row.attempts) > limit:
                                def more_attempts(number: int = row.id) -> None:
                                    attempt_limits[number] = attempt_limits.get(number, 5) + 5
                                    results.refresh()
                                ui.button(f"Show more attempts for lesson {row.id}", on_click=more_attempts).props("outline")
                        else:
                            ui.label(f"Private notes: {'saved' if row.notes.strip() else 'none'}; saved tutor answers: {row.tutor_count}")
                            if row.check_detail:
                                ui.label(row.check_detail).classes("text-sm")
                            if row.last_run:
                                with ui.expansion("Saved run summary").classes("w-full"):
                                    _saved_text("Last saved run", row.last_run)
                        with ui.row().classes("w-full gap-2"):
                            ui.link(f"Open lesson {row.id}", lesson_link(row, path_choice.value or "")).classes("font-bold")
                            if row.guide_section:
                                ui.link(f"Resume guide for lesson {row.id}", lesson_link(row, path_choice.value or "", resume_guide=True))
                if len(rows) > page_state["limit"]:
                    def more() -> None:
                        page_state["limit"] += 12
                        results.refresh()
                    ui.button("Show more lessons", icon="expand_more", on_click=more).props("outline")
                if page_state["view"] == "Quiz results":
                    with card("Section quiz practice", "Separate assessment results"):
                        for quiz in snapshot.section_quizzes:
                            section_scores[quiz.id] = ui.label(_section_score(quiz))
                            section_buttons[quiz.id] = ui.button(
                                f"Open {quiz.topic} section quiz",
                                on_click=lambda topic=quiz.topic, number=quiz.id: section_quiz_dialog(
                                    topic, on_close=lambda: refresh_quiz_results(number)
                                ),
                            ).props("flat")

            def refresh_quiz_results(quiz_id: str) -> None:
                nonlocal snapshot
                snapshot = learning_snapshot({key: stored(key, None) for key in (
                    "lessons", "sections", "last_lesson", "learning_guide_positions",
                )})
                # Keep the launch button in place so the dialog can restore keyboard focus.
                if page_state["view"] == "Quiz results":
                    for quiz in snapshot.section_quizzes:
                        label = section_scores.get(quiz.id)
                        if label is not None:
                            label.set_text(_section_score(quiz))
                    button = section_buttons.get(quiz_id)
                    if button is not None:
                        ui.run_javascript(
                            f"document.getElementById({json.dumps(button.html_id)})?.focus({{preventScroll: true}})"
                        )

            def refresh() -> None:
                page_state["limit"] = 12
                page_state["view"] = views.value
                results.refresh()

            def change_path() -> None:
                # The selected path stays in the URL; no persistence keys are added or replaced.
                page_state["path"] = path_choice.value or ""
                setup_link.props(f'href="{setup_url(page_state["path"])}"')
                ui.run_javascript("history.replaceState(null, '', " + json.dumps(workspace_url(path_choice.value or "")) + ")")
                refresh()

            results()
            path_choice.on_value_change(change_path)
            search.on_value_change(refresh)
            status.on_value_change(refresh)
            views.on_value_change(refresh)
            with ui.row().classes("w-full gap-4"):
                ui.link("Study Coach", "/coach")
                ui.link("Evaluation Studio", "/studio")
                ui.link("Publishing Studio", "/publish")
                setup_link = ui.link("Review setup", setup_url(selected))
            progress_card()

    @ui.page("/setup")
    def setup(path: str = "") -> None:
        page_style()
        ui.add_css(WORKSPACE_CSS)
        _header("SETUP")
        with ui.column().classes("my-learning w-full max-w-4xl mx-auto py-4 md:p-8 gap-5"):
            ui.link("Back to My Learning", workspace_url(path))
            ui.label("Prepare your Python learning workspace").classes("course-title").props('role="heading" aria-level="1"')
            with card("Start offline"):
                ui.label("From the project folder, install the locked dependencies and start the course:")
                ui.code("uv sync --locked\nuv run agent-lab serve", language="shell").classes("w-full")
                ui.label("Open the address printed by the server. If it is already running, use that instance.")
                ui.label("Choose Offline Python exercise. Local exercises need no model API key and make no paid model call.")
                ui.link("Open lesson 1", lesson_url(1, path)).classes("font-bold")
            with card("Optional live exercises"):
                ui.label("Configure your provider credentials and LAB_ENABLE_LIVE=true in your local .env, then restart the server. Live calls can incur charges; inspect the lesson's limits before starting one.")
                ui.label("Opening My Learning, a guide or this setup page never enables live mode or starts a run.")
            with card("Keep your work"):
                ui.label("Notes, answers and checklist choices belong to this browser. Use Export progress in My Learning for backups and transfers. There is no account or cloud synchronization.")
                ui.link("Open My Learning", workspace_url(path)).classes("font-bold")
