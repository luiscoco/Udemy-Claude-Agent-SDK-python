"""NiceGUI browser UI. Students author application code entirely in Python."""

import asyncio
import json
import secrets
from typing import Any

from fastapi import FastAPI
from nicegui import app as nice_app
from nicegui import ui

from agent_lab.config import ROOT
from agent_lab.curriculum import LESSONS, TOPICS
from agent_lab.evaluation_studio import StudioService
from agent_lab.exercises import exercise_context, exercise_source, exercise_uses
from agent_lab.learning import CheckResult, check_evidence, course
from agent_lab.lesson_guide import adjacent_lesson, learning_guides, lesson_url, route_id
from agent_lab.models import Event, RunRequest
from agent_lab.my_learning import workspace_url
from agent_lab.output import OutputState, render_output
from agent_lab.policy import redact
from agent_lab.publishing_studio import PublishingService
from agent_lab.runtime import RunHandle, RunService
from agent_lab.study_coach import CoachService
from agent_lab.tutor import TutorService
from agent_lab.ui_coach import install_coach_page
from agent_lab.ui_guide import INITIAL_LESSON_START, LessonGuidePanel
from agent_lab.ui_learning import (
    appearance_controls,
    check_card,
    completed,
    concept_code_card,
    home_page,
    learn_panel,
    lesson_header,
    page_style,
    record,
    run_summary,
    set_preference,
    tutor_panel,
    update,
    visual_panel,
    walkthrough_panel,
)
from agent_lab.ui_my_learning import install_my_learning_pages
from agent_lab.ui_publish import install_publish_page
from agent_lab.ui_studio import install_studio_page


def storage_secret(runner: RunService) -> str:
    """Signs the browser id cookie for per-browser progress; created once per installation."""
    path = runner.settings.data_dir / "storage-secret"
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(secrets.token_urlsafe(32), encoding="utf-8")
    return path.read_text(encoding="utf-8").strip()


def install_ui(application: FastAPI, runner: RunService, tutor: TutorService) -> None:
    if (ROOT / "public").is_dir():
        nice_app.add_static_files("/assets", str(ROOT / "public"))
    install_coach_page(CoachService(runner.settings))
    install_studio_page(StudioService(runner.settings))
    install_publish_page(PublishingService(runner.settings))
    install_my_learning_pages()

    @ui.page("/")
    async def home(lesson: int = 0, path: str = "", resume_guide: bool = False) -> None:
        page_style()
        active_path = route_id(path, lesson) if lesson in LESSONS else ""
        client = ui.context.client
        handle: RunHandle | None = None
        consumer: asyncio.Task[Any] | None = None
        drawer: Any

        with ui.header().classes("lab-header border-b items-center"):
            ui.button(icon="menu", on_click=lambda: drawer.toggle()).props("flat color=primary aria-label='Open lesson navigation'")
            ui.link("Claude Agent SDK Lab", "/").classes(
                "text-xl font-bold no-underline text-slate-900 min-w-0 flex-1"
            )
            ui.badge("PYTHON EDITION", color="secondary").classes("gt-xs")
            ui.link("My Learning", workspace_url(active_path)).classes("gt-xs font-bold")
            appearance_controls()
        with (
            ui.left_drawer(value=None)
            .props("width=320 breakpoint=1000")
            .classes("lesson-menu") as drawer
        ):
            ui.label("75 practical lessons").classes("text-lg font-bold px-2")
            ui.link("My Learning", workspace_url(active_path)).classes("font-bold px-2")
            search = (
                ui.input("Find a lesson", placeholder="Sessions, MCP, permissions…")
                .props("outlined dense clearable")
                .classes("w-full")
            )
            navigation = ui.column().classes("w-full gap-1")

            @ui.refreshable
            def menu() -> None:
                term = (search.value or "").lower()
                for topic, ids in TOPICS.items():
                    matches = [
                        LESSONS[number]
                        for number in ids
                        if not term or term in f"{number} {LESSONS[number].title}".lower()
                    ]
                    if not matches:
                        continue
                    with ui.expansion(topic, value=bool(term) or lesson in ids).classes("w-full"):
                        for item in matches:
                            mark = " ✓" if completed(item.id) else ""
                            ui.link(
                                f"{item.id}. {item.title}{mark}", lesson_url(item.id, active_path)
                            ).classes(
                                "text-sm"
                                + (" font-bold text-purple-700" if item.id == lesson else "")
                            )

            with navigation:
                menu()
            search.on_value_change(lambda: menu.refresh())

        with ui.column().classes("w-full max-w-6xl mx-auto p-4 md:p-8 gap-5"):
            banner = ROOT / "public" / "ClaudeAgentsSDK_LandingPage.png"
            if banner.exists() and lesson not in LESSONS:
                ui.image("/assets/ClaudeAgentsSDK_LandingPage.png").classes(
                    "rounded-2xl w-full max-w-2xl mx-auto"
                ).props("fit=contain")
            if lesson not in LESSONS:
                home_page()
                return
            current = LESSONS[lesson]
            set_preference("last_lesson", lesson)
            source = exercise_source(current.exercise)
            lesson_header(lesson, runner.settings.enable_live)
            with ui.row().classes("w-full items-center gap-3 guide-lesson-actions") as lesson_actions:
                pass
            if current.notes:
                with ui.card().classes("course-card w-full bg-amber-50"):
                    ui.label(current.notes)
            with ui.tabs().props("mobile-arrows outside-arrows").classes("w-full") as tabs:
                learn_tab = ui.tab("Learn", icon="menu_book")
                walkthrough_tab = ui.tab("Lab walkthrough", icon="route")
                visual_tab = ui.tab("Visual guide", icon="image")
                run_tab = ui.tab("Run the exercise", icon="play_circle")
                source_tab = ui.tab("Python source", icon="code")
                tutor_tab = ui.tab("AI Tutor", icon="school")
            with ui.tab_panels(tabs, value=learn_tab).classes("w-full bg-transparent"):
                with ui.tab_panel(learn_tab).classes("p-0 flex flex-col gap-5"):
                    documents = list(ROOT.glob(f"Tab{lesson}-*.md"))
                    tutorial = documents[0].read_text(encoding="utf-8") if documents else ""
                    learn_panel(lesson, tutorial, lambda: tabs.set_value(run_tab))
                with ui.tab_panel(walkthrough_tab).classes("p-0 flex flex-col gap-5"):
                    walkthrough_panel(lesson)
                with ui.tab_panel(visual_tab).classes("p-0 flex flex-col gap-5"):
                    visual_panel(lesson)
                with ui.tab_panel(source_tab).classes("p-0 flex flex-col gap-5"):
                    ui.label("Python source for this concept").classes("text-xl font-bold guide-source-context")
                    concept_code_card(lesson, guide_target="guide-source-target")
                    with ui.expansion(
                        "How the offline lab checks this concept", icon="science"
                    ).classes("w-full course-card"):
                        ui.label(
                            "The host exercise run by Run the exercise, the CLI and the API."
                        ).classes("text-sm text-slate-500")
                        ui.code(source, language="python").classes("w-full")
                        ui.label(
                            "SDK integration: agent_lab/sdk.py · Task lifecycle: agent_lab/runtime.py"
                        ).classes("text-sm text-slate-500")
                with ui.tab_panel(tutor_tab).classes("p-0 flex flex-col gap-5"):
                    tutor_panel(lesson, tutor, exercise_context(current.exercise))
                with ui.tab_panel(run_tab).classes("p-0 flex flex-col gap-5"):
                    with ui.card().classes("course-card w-full p-6"):
                        modes = {"offline": "Offline Python exercise"}
                        if runner.settings.enable_live:
                            modes["live"] = "Live Agent SDK"
                        mode = ui.toggle(modes, value="offline")
                        # Empty means "use the example": live runs fall back to the lesson
                        # prompt, and offline exercises see only what the student typed.
                        offline_prompt = exercise_uses(current.exercise, "prompt")
                        offline_follow_up = exercise_uses(current.exercise, "follow_up")
                        prompt = (
                            ui.textarea(
                                "Prompt (optional)"
                                if offline_prompt
                                else "Agent prompt (live mode)",
                                placeholder=current.prompt,
                            )
                            .props("outlined autogrow clearable")
                            .classes("w-full")
                            .bind_enabled_from(
                                mode, "value", lambda value: value == "live" or offline_prompt
                            )
                        )
                        if offline_prompt:
                            ui.label(
                                "This offline exercise also uses your prompt. Leave it empty to use the example."
                            ).classes("text-sm text-slate-500")
                        follow_up = (
                            ui.input(
                                "Follow-up for conversation lessons", value=RunRequest().follow_up
                            )
                            .props("outlined")
                            .classes("w-full")
                            .bind_enabled_from(
                                mode, "value", lambda value: value == "live" or offline_follow_up
                            )
                        )
                        with ui.row().classes("w-full items-center"):
                            turns = (
                                ui.number(
                                    "Maximum turns",
                                    value=current.max_turns,
                                    min=1,
                                    max=12,
                                    precision=0,
                                )
                                .props("outlined dense")
                                .classes("w-48")
                            )
                            budget = (
                                ui.number(
                                    "Budget threshold (USD)",
                                    value=current.max_budget_usd,
                                    min=0.01,
                                    max=1,
                                    step=0.01,
                                )
                                .props("outlined dense")
                                .classes("w-48")
                            )
                        if not runner.settings.enable_live:
                            ui.label(
                                "Live mode is disabled. Enable LAB_ENABLE_LIVE in .env after configuring your API key."
                            ).classes("text-sm text-slate-500")
                        with ui.row().classes("items-center guide-controls-context"):
                            run_button = ui.button("Run exercise", icon="play_arrow").classes("guide-controls-target")
                            cancel_button = ui.button("Cancel", icon="stop", color="secondary")
                            cancel_button.disable()
                            status = ui.label("Ready")
                    with ui.card().classes("course-card w-full p-6 guide-evidence-context"):
                        evidence_view = ui.column().classes("w-full gap-3 guide-evidence-target guide-scroll-target")
                        with evidence_view:
                            ui.label("Response and results").classes("text-xl font-bold")
                        output_state = OutputState()

                        @ui.refreshable
                        def output() -> None:
                            render_output(
                                output_state, current.exercise, handle.id if handle else None
                            )

                        with evidence_view:
                            output()
                        with ui.expansion("Diagnostics — raw events", icon="code").classes(
                            "w-full"
                        ):
                            ui.label(
                                "For debugging and SDK lessons. These events are not the agent’s answer."
                            ).classes("text-sm text-slate-500")
                            log = ui.log(max_lines=500).classes(
                                "w-full h-64 bg-slate-950 text-slate-100 rounded-xl"
                            )

                        async def show_question(data: dict[str, Any]) -> None:
                            if handle is None:
                                return
                            choices = []
                            # consume() runs as a background task, so enter the page's slot explicitly.
                            with (
                                client,
                                ui.dialog() as dialog,
                                ui.card().classes("w-full max-w-xl"),
                            ):
                                ui.label("The agent needs your answer").classes("text-xl font-bold")
                                for question in data["questions"]:
                                    ui.label(question["question"])
                                    labels = [item["label"] for item in question["options"]]
                                    picker: Any
                                    if question.get("multiSelect"):
                                        picker = ui.select(labels, multiple=True, value=[])
                                    else:
                                        picker = ui.radio(labels)
                                    free_text = ui.input("Or enter your own answer")
                                    choices.append((question["question"], picker, free_text))

                                def submit() -> None:
                                    if handle is None:
                                        return
                                    answers = {}
                                    for key, picker, free_text in choices:
                                        value = free_text.value or picker.value
                                        if not value:
                                            ui.notify("Answer every question.", type="warning")
                                            return
                                        answers[key] = (
                                            ", ".join(value) if isinstance(value, list) else value
                                        )
                                    try:
                                        runner.answer(
                                            handle.id, handle.token, data["question_id"], answers
                                        )
                                    except (ValueError, PermissionError) as exc:
                                        ui.notify(str(exc), type="warning")
                                    dialog.close()

                                ui.button("Send answer", on_click=submit)
                            dialog.open()

                        async def consume() -> None:
                            if handle is None:
                                return
                            active_handle = handle
                            try:
                                async for event in runner.events(active_handle):
                                    data = redact(dict(event.data))
                                    data.pop("control_token", None)
                                    log.push(
                                        f"{event.kind.upper()}  {json.dumps(data, ensure_ascii=False)}"
                                    )
                                    if event.kind == "question":
                                        await show_question(event.data)
                                    if output_state.apply(event):
                                        output.refresh()
                                    if event.kind == "done":
                                        status.set_text(event.data["status"].capitalize())
                                        record_check(event.data["status"])
                            finally:
                                run_button.enable()
                                cancel_button.disable()

                        async def run() -> None:
                            nonlocal handle, consumer, output_state
                            log.clear()
                            output_state = OutputState(mode=mode.value)
                            output.refresh()
                            try:
                                body = RunRequest(
                                    mode=mode.value,
                                    prompt=prompt.value or "",
                                    follow_up=follow_up.value or "",
                                    max_turns=int(turns.value),
                                    max_budget_usd=budget.value,
                                )
                                handle = runner.start(lesson, body)
                            except Exception as exc:
                                status.set_text("Could not start")
                                log.push(f"ERROR  {exc}")
                                output_state.apply(Event(kind="error", data={"message": str(exc)}))
                                output_state.status = "failed"
                                output.refresh()
                                ui.notify(str(exc), type="negative")
                                return
                            run_button.disable()
                            cancel_button.enable()
                            status.set_text("Running")
                            consumer = asyncio.create_task(consume())

                        async def cancel() -> None:
                            if handle:
                                await runner.cancel(handle)
                            if consumer:
                                await consumer

                        run_button.on_click(run)
                        cancel_button.on_click(cancel)
                        client.on_disconnect(cancel)

                    saved_check = record(lesson)["check"]
                    check_result = CheckResult(**saved_check) if saved_check else None

                    @ui.refreshable
                    def checks() -> None:
                        check_card(lesson, check_result)

                    checks()

                    def record_check(status_value: str) -> None:
                        nonlocal check_result
                        check_result = check_evidence(
                            lesson,
                            output_state.evidence,
                            status=status_value,
                            mode=output_state.mode,
                            responded=bool(output_state.response_texts or output_state.results),
                        )
                        update(
                            lesson,
                            check=check_result.model_dump(),
                            last_run=run_summary(output_state, check_result),
                        )
                        checks.refresh()

            with lesson_actions:
                if tour := learning_guides().get(lesson):
                    panel = LessonGuidePanel(tour, tabs, active_path)
                    if resume_guide:
                        ui.timer(0.15, panel.resume_saved, once=True)
                route_name = next((p.title for p in course().paths if p.id == active_path), "All lessons")
                ui.label(f"Route: {route_name}").classes("text-sm text-slate-500")
                if target := adjacent_lesson(lesson, 1, active_path):
                    ui.link("Next lesson →", lesson_url(target, active_path)).classes("font-semibold")
            with ui.row().classes("w-full justify-between"):
                if previous := adjacent_lesson(lesson, -1, active_path):
                    ui.link("← Previous lesson", lesson_url(previous, active_path))
                if following := adjacent_lesson(lesson, 1, active_path):
                    ui.link("Next lesson →", lesson_url(following, active_path))
            ui.timer(0.15, lambda: ui.run_javascript(INITIAL_LESSON_START), once=True)

    ui.run_with(
        application,
        title="Python Claude Agent SDK Lab",
        favicon="🐍",
        dark=None,
        show_welcome_message=False,
        storage_secret=storage_secret(runner),
    )
