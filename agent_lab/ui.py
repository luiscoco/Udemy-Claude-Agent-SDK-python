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
from agent_lab.foundation_models import SCENARIOS
from agent_lab.foundations import source_sections
from agent_lab.learning import CheckResult, check_evidence, course
from agent_lab.lesson_guide import adjacent_lesson, learning_guides, lesson_url, route_id
from agent_lab.models import Event, LessonError, RunRequest
from agent_lab.my_learning import workspace_url
from agent_lab.output import OutputState, render_output
from agent_lab.policy import redact
from agent_lab.publishing_studio import PublishingService
from agent_lab.runtime import RunHandle, RunService
from agent_lab.study_coach import CoachService
from agent_lab.tutor import TutorService
from agent_lab.ui_coach import install_coach_page
from agent_lab.ui_foundations import experiment_controls
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
            ui.button(icon="menu", on_click=lambda: drawer.toggle()).props(
                "flat color=primary aria-label='Open lesson navigation'"
            )
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
            with ui.row().classes(
                "w-full items-center gap-3 guide-lesson-actions"
            ) as lesson_actions:
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
                    ui.label("Python source for this concept").classes(
                        "text-xl font-bold guide-source-context"
                    )
                    concept_code_card(lesson, guide_target="guide-source-target")
                    with ui.expansion(
                        "How the offline lab checks this concept", icon="science"
                    ).classes("w-full course-card"):
                        ui.label(
                            "The host exercise run by Run the exercise, the CLI and the API."
                        ).classes("text-sm text-slate-500")
                        ui.code(source, language="python").classes("w-full")
                        if 2 <= lesson <= 15:
                            for section in source_sections(lesson):
                                with ui.expansion(section["title"]).classes(
                                    "w-full foundation-source-excerpt"
                                ):
                                    ui.label(
                                        f"{section['path']}: {section['start']}–{section['end']}"
                                    ).classes("font-semibold")
                                    ui.code(section["code"], language="python").classes("w-full")
                                    ui.label(section["question"]).classes("font-semibold")
                            ui.link(
                                "Read the shared evidence evaluator", "/agent_lab/streaming.py" if lesson == 12 else "/agent_lab/thinking.py" if lesson == 14 else "/agent_lab/usage.py" if lesson == 15 else "/agent_lab/foundations.py"
                            )
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
                                "Prompt"
                                if lesson <= 15
                                else "Prompt (optional)"
                                if offline_prompt
                                else "Agent prompt (live mode)",
                                placeholder=current.prompt,
                                value=current.prompt if lesson <= 15 else "",
                            )
                            .props("outlined autogrow clearable")
                            .classes("w-full")
                            .bind_enabled_from(
                                mode, "value", lambda value: value == "live" or offline_prompt
                            )
                        )
                        if lesson <= 15:
                            ui.label(
                                "Offline experiments validate your prompt and run local host code with labelled SDK fixtures; they do not call Claude."
                            ).classes("text-sm text-slate-600")
                        elif offline_prompt:
                            ui.label(
                                "This offline exercise also uses your prompt. Leave it empty to use the example."
                            ).classes("text-sm text-slate-500")
                        follow_up = (
                            ui.input(
                                "Script follow-up" if lesson == 12 else "Follow-up for conversation lessons", value=RunRequest().follow_up
                            )
                            .props("outlined")
                            .classes("w-full")
                            .bind_enabled_from(
                                mode, "value", lambda value: value == "live" or offline_follow_up
                            )
                        )
                        if lesson <= 15 and lesson not in {6, 12}:
                            follow_up.set_visibility(False)
                        read_lesson_options = experiment_controls(lesson, mode)
                        scenario = (
                            ui.select(
                                SCENARIOS.get(
                                    lesson,
                                    {
                                        "success": "Success",
                                        "error": "SDK error",
                                        "missing-result": "Missing final result",
                                    },
                                ),
                                value="success",
                                label="Recorded scenario",
                            )
                            .props("outlined")
                            .classes("w-full")
                        )
                        scenario.bind_visibility_from(
                            mode, "value", lambda value: lesson <= 15 and value == "offline"
                        )
                        with ui.row().classes("w-full items-center"):
                            turns = (
                                ui.number(
                                    "Maximum turns",
                                    value=current.max_turns,
                                    min=1,
                                    max=1 if lesson == 1 else 12,
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
                                    max=0.05 if lesson == 1 else 1,
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
                            run_button = ui.button("Run exercise", icon="play_arrow").classes(
                                "guide-controls-target"
                            )
                            cancel_button = ui.button("Cancel", icon="stop", color="secondary")
                            cancel_button.disable()
                            status = ui.label("Ready")
                        if lesson == 13:
                            from agent_lab.ui_mcp import mcp_workshop_controls

                            mcp_workshop_controls(application.state.mcp_workshops, client)
                        if lesson == 14:
                            from agent_lab.ui_thinking import model_inspector

                            model_inspector(application.state.thinking_sessions)
                        if lesson == 15:
                            from agent_lab.ui_usage import usage_session_controls

                            usage_session_controls(application.state.usage_sessions, client, lambda: {
                                "mode": mode.value, "prompt": prompt.value,
                                "max_turns": int(turns.value), "max_budget_usd": budget.value,
                                "scenario": scenario.value, "lesson_options": read_lesson_options(),
                            })
                        stream_buttons = []
                        if lesson == 12:
                            with ui.column().classes("w-full gap-3 stream-session-controls"):
                                ui.label("Open input session").classes("text-lg font-bold")
                                stream_status = ui.label("Choose manual mode above, then Run exercise to open a session.").classes("break-words w-full")
                                stream_lifecycle = ui.label().classes("font-semibold w-full")
                                stream_identity = ui.label().classes("text-sm font-mono whitespace-pre-wrap break-all w-full")
                                stream_settings = ui.label().classes("text-sm break-words w-full")
                                stream_message = ui.textarea("Message to queue", value=RunRequest().follow_up).props("outlined rows=3 maxlength=10000").classes("w-full")

                                async def stream_action(action: str, value: str = "") -> None:
                                    if handle is None or runner.active.get(handle.id) is not handle or handle.input_stream is None:
                                        ui.notify("Open a new manual input session first.", type="warning")
                                        return
                                    session = handle.input_stream
                                    try:
                                        if not session.ready or session.input_closed or not session.manual_mode:
                                            raise LessonError("This session is no longer open for input.")
                                        if action == "send":
                                            session.push(stream_message.value or "")
                                        elif action == "end":
                                            session.end()
                                        else:
                                            await session.command(action, value)
                                        await session.publish()
                                    except LessonError as exc:
                                        ui.notify(str(exc), type="warning")

                                with ui.row().classes("w-full gap-2"):
                                    stream_buttons.append(ui.button("Queue message", icon="queue", on_click=lambda: stream_action("send")))
                                    stream_buttons.append(ui.button("End input", icon="done_all", on_click=lambda: stream_action("end")))
                                stream_model = ui.select({"haiku": "haiku", "sonnet": "sonnet"}, value="haiku", label="Runtime model").props("outlined").classes("w-full")
                                stream_buttons.append(ui.button("Apply runtime model", on_click=lambda: stream_action("model", stream_model.value)))
                                stream_permission = ui.select({"default": "Default", "plan": "Plan"}, value="default", label="Runtime permission mode").props("outlined").classes("w-full")
                                stream_buttons.append(ui.button("Apply permission mode", on_click=lambda: stream_action("permission", stream_permission.value)))
                                ui.label("These controls target this page's active run only. End input drains the queue; Cancel aborts. Acknowledgement is separate from model behavior or permission effects.").classes("text-sm text-slate-600")
                                for button in stream_buttons:
                                    button.disable()
                    with ui.card().classes("course-card w-full p-6 guide-evidence-context"):
                        evidence_view = ui.column().classes(
                            "w-full gap-3 guide-evidence-target guide-scroll-target"
                        )
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

                                async def cancel_question() -> None:
                                    if handle:
                                        await runner.cancel(handle)
                                    dialog.close()

                                ui.button("Cancel run", icon="stop", on_click=cancel_question).props("outline")
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
                                    if event.kind == "input_stream" and lesson == 12:
                                        state = event.data
                                        stream_status.set_text(
                                            f"Submitted {state['submitted_count']} · Yielded {state['yielded_count']} · Successful results {state['successful_results']} · Queued {state['queued_count']}"
                                        )
                                        stream_lifecycle.set_text(f"Input {'closed' if state['input_closed'] else 'open'} · Connection {'closed' if state['connection_closed'] else 'open'}")
                                        stream_identity.set_text(f"Application handle: {state['application_handle']}\nSDK identity: {state['sdk_identity'] or 'not observed'}")
                                        stream_settings.set_text(f"Acknowledged model: {state['acknowledged_settings'].get('model', 'no runtime change')} · Acknowledged permission mode: {state['acknowledged_settings'].get('permission', 'no runtime change')}")
                                        for button in stream_buttons:
                                            button.set_enabled(state["ready"] and state["manual_mode"])
                                    if output_state.apply(event):
                                        output.refresh()
                                    if event.kind == "done":
                                        status.set_text(event.data["status"].capitalize())
                                        record_check(event.data["status"])
                            finally:
                                run_button.enable()
                                cancel_button.disable()
                                for button in stream_buttons:
                                    button.disable()

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
                                    max_turns=turns.value,
                                    max_budget_usd=budget.value,
                                    lesson_options=read_lesson_options(),
                                    scenario=scenario.value
                                    if mode.value == "offline"
                                    else "success",
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
                route_name = next(
                    (p.title for p in course().paths if p.id == active_path), "All lessons"
                )
                ui.label(f"Route: {route_name}").classes("text-sm text-slate-500")
                if target := adjacent_lesson(lesson, 1, active_path):
                    ui.link("Next lesson →", lesson_url(target, active_path)).classes(
                        "font-semibold"
                    )
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
