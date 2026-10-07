"""NiceGUI browser UI. Students author application code entirely in Python."""

import asyncio
import inspect
import json
from typing import Any

from fastapi import FastAPI
from nicegui import app as nice_app
from nicegui import ui

from agent_lab.config import ROOT
from agent_lab.curriculum import LESSONS, TOPICS
from agent_lab.exercises import EXERCISES
from agent_lab.models import Event, RunRequest
from agent_lab.output import OutputState, render_output
from agent_lab.policy import redact
from agent_lab.runtime import RunHandle, RunService


def install_ui(application: FastAPI, runner: RunService) -> None:
    if (ROOT / "public").is_dir():
        nice_app.add_static_files("/assets", str(ROOT / "public"))

    @ui.page("/")
    async def home(lesson: int = 0) -> None:
        ui.colors(primary="#7c3aed", secondary="#0f766e", accent="#f59e0b")
        ui.add_css("""
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
        """)
        client = ui.context.client
        handle: RunHandle | None = None
        consumer: asyncio.Task[Any] | None = None
        drawer: Any

        with ui.header().classes("bg-white text-slate-900 border-b items-center"):
            ui.button(icon="menu", on_click=lambda: drawer.toggle()).props("flat color=primary")
            ui.link("Claude Agent SDK Lab", "/").classes(
                "text-xl font-bold no-underline text-slate-900 min-w-0 flex-1"
            )
            ui.space()
            ui.badge("PYTHON EDITION", color="secondary")
        with (
            ui.left_drawer(value=None)
            .props("width=320 breakpoint=1000")
            .classes("lesson-menu") as drawer
        ):
            ui.label("75 practical lessons").classes("text-lg font-bold px-2")
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
                            ui.link(f"{item.id}. {item.title}", f"/?lesson={item.id}").classes(
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
                with ui.card().classes("course-card w-full p-8"):
                    ui.label("Build agents with Python").classes("course-title")
                    ui.label(
                        "Learn the official Claude Agent SDK through runnable Python exercises, then connect your agents to FastAPI and NiceGUI."
                    ).classes("text-lg text-slate-600")
                    ui.label(
                        "Offline exercises run local Python code without API costs. Live mode starts the real SDK and reports its messages and usage."
                    )
                    ui.button("Start lesson 1", on_click=lambda: ui.navigate.to("/?lesson=1"))
                return
            current = LESSONS[lesson]
            ui.label(f"{current.topic} / Lesson {lesson}").classes("text-sm text-slate-500")
            ui.label(f"{lesson}. {current.title}").classes("course-title")
            ui.label(current.objective).classes("text-lg text-slate-600")
            if current.notes:
                with ui.card().classes("course-card w-full bg-amber-50"):
                    ui.label(current.notes)
            with ui.tabs().classes("w-full") as tabs:
                learn_tab = ui.tab("Learn")
                run_tab = ui.tab("Run the exercise")
                source_tab = ui.tab("Python source")
            with ui.tab_panels(tabs, value=run_tab).classes("w-full bg-transparent"):
                with ui.tab_panel(learn_tab).classes("p-0"):
                    documents = list(ROOT.glob(f"Tab{lesson}-*.md"))
                    if documents:
                        ui.markdown(documents[0].read_text(encoding="utf-8")).classes(
                            "bg-white p-6 rounded-xl"
                        )
                with ui.tab_panel(source_tab).classes("p-0"):
                    ui.label("This is the host exercise used by the UI, CLI, and API.")
                    ui.code(
                        inspect.getsource(EXERCISES[current.exercise]), language="python"
                    ).classes("w-full")
                    ui.label(
                        "SDK integration: agent_lab/sdk.py · Task lifecycle: agent_lab/runtime.py"
                    )
                with ui.tab_panel(run_tab).classes("p-0"):
                    with ui.card().classes("course-card w-full p-6"):
                        modes = {"offline": "Offline Python exercise"}
                        if runner.settings.enable_live:
                            modes["live"] = "Live Agent SDK"
                        mode = ui.toggle(modes, value="offline")
                        prompt = (
                            ui.textarea("Agent prompt (live mode only)", value=current.prompt)
                            .props("outlined autogrow")
                            .classes("w-full")
                            .bind_enabled_from(mode, "value", lambda value: value == "live")
                        )
                        follow_up = (
                            ui.input(
                                "Follow-up for conversation lessons", value=RunRequest().follow_up
                            )
                            .props("outlined")
                            .classes("w-full")
                            .bind_enabled_from(mode, "value", lambda value: value == "live")
                        )
                        with ui.row().classes("w-full items-center"):
                            turns = (
                                ui.number("Maximum turns", value=4, min=1, max=12, precision=0)
                                .props("outlined dense")
                                .classes("w-48")
                            )
                            budget = (
                                ui.number(
                                    "Budget threshold (USD)", value=0.10, min=0.01, max=1, step=0.01
                                )
                                .props("outlined dense")
                                .classes("w-48")
                            )
                        if not runner.settings.enable_live:
                            ui.label(
                                "Live mode is disabled. Enable LAB_ENABLE_LIVE in .env after configuring your API key."
                            ).classes("text-sm text-slate-500")
                        with ui.row().classes("items-center"):
                            run_button = ui.button("Run exercise", icon="play_arrow")
                            cancel_button = ui.button("Cancel", icon="stop", color="secondary")
                            cancel_button.disable()
                            status = ui.label("Ready")
                    with ui.card().classes("course-card w-full p-6"):
                        ui.label("Response and results").classes("text-xl font-bold")
                        output_state = OutputState()

                        @ui.refreshable
                        def output() -> None:
                            render_output(output_state, current.exercise, handle.id if handle else None)

                        output()
                        with ui.expansion("Diagnostics — raw events", icon="code").classes("w-full"):
                            ui.label("For debugging and SDK lessons. These events are not the agent’s answer.").classes("text-sm text-slate-500")
                            log = ui.log(max_lines=500).classes(
                                "w-full h-64 bg-slate-950 text-slate-100 rounded-xl"
                            )

                        async def show_question(data: dict[str, Any]) -> None:
                            if handle is None:
                                return
                            choices = []
                            with ui.dialog() as dialog, ui.card().classes("w-full max-w-xl"):
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
            with ui.row().classes("w-full justify-between"):
                if lesson > 1:
                    ui.link("← Previous lesson", f"/?lesson={lesson - 1}")
                if lesson < 75:
                    ui.link("Next lesson →", f"/?lesson={lesson + 1}")

    ui.run_with(
        application,
        title="Python Claude Agent SDK Lab",
        favicon="🐍",
        dark=False,
        show_welcome_message=False,
    )
