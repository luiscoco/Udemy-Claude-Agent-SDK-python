"""The Study Coach milestone page. Every action goes through the student's coach.py."""

from typing import Any

from nicegui import ui

from agent_lab.config import ROOT
from agent_lab.curriculum import LESSONS, TOPICS
from agent_lab.exercises import exercise_location
from agent_lab.learning import course, guide
from agent_lab.models import LessonError
from agent_lab.study_coach import (
    INTRO_CONCEPTS,
    SHORTCUTS,
    STAGE_FUNCTIONS,
    CoachService,
    coach_path,
    fixture_plan,
    load_coach,
    shortcut_question,
    stage_of,
)
from agent_lab.ui_learning import (
    appearance_controls,
    card,
    page_style,
    plain,
    preference,
    stored,
)
from agent_lab.ui_learning import set_preference as remember

STAGES = {
    1: "Start the app and identify the prepared response",
    2: "Validate questions and accept only completed answers",
    3: "Choose fixture or live mode, keeping credentials on the server",
    4: "Keep the conversation identity across follow-ups",
    5: "Validate a structured study plan",
    6: "Recover a saved turn without duplicate requests",
    7: "Verify and present the finished project",
}
RECOVERY = {
    "reuse": "Reuse the saved answer. No new request is sent.",
    "wait": "The turn is still running on the server. Inspect it again shortly.",
    "new-turn": "The turn failed for certain. Asking again is safe.",
    "inspect": "The outcome is uncertain. Check before sending anything else; "
    "this conversation stays blocked.",
}


class StageLocked(Exception):
    pass


def locked(stage: int) -> StageLocked:
    names = ", ".join(f"`{name}`" for name in STAGE_FUNCTIONS.get(stage, ()))
    return StageLocked(
        f"Implement stage {stage} ({names}) in mini_projects/study_coach/coach.py, "
        f"then set STAGE = {stage}."
    )


def install_coach_page(service: CoachService) -> None:
    @ui.page("/coach")
    async def coach_page(lesson: int = 1) -> None:
        page_style()
        state: dict[str, Any] = {
            "implementation": preference("coach_implementation", "learner"),
            "lesson": lesson if lesson in LESSONS else 1,
            "conversation": None,
            "kind": None,
            "last_turn": None,
            "plan": None,
        }

        def coach() -> Any:
            return load_coach(state["implementation"])

        def run(action: Any) -> Any:
            """Calls into the student's code: a TODO becomes a clear next step, not a crash."""
            try:
                return action()
            except NotImplementedError as exc:
                ui.notify(f"{exc}. See the stage prompt in mini_projects/study_coach/prompts/.")
            except StageLocked as exc:
                ui.notify(str(exc), type="info", close_button="Dismiss", timeout=0)
            except (ValueError, PermissionError, LessonError) as exc:
                ui.notify(str(exc), type="warning")
            return None

        with ui.header().classes("lab-header border-b items-center"):
            ui.link("Claude Agent SDK Lab", "/").classes(
                "text-xl font-bold no-underline text-slate-900 min-w-0 flex-1"
            )
            ui.badge("STUDY COACH", color="secondary").classes("gt-xs")
            appearance_controls()

        with ui.column().classes("w-full max-w-6xl mx-auto p-4 md:p-8 gap-5"):
            # ---------------------------------------------------------- project status
            with card("Study Coach", "Milestone project"):
                ui.label(
                    "Build a study coach one stage at a time. This page runs your own "
                    "mini_projects/study_coach/coach.py, so every stage you finish unlocks a feature."
                ).classes("text-slate-600")

                @ui.refreshable
                def status() -> None:
                    module = coach()
                    current = stage_of(module)
                    path = coach_path(state["implementation"]).relative_to(ROOT).as_posix()
                    ui.label(f"{path} is at stage {current} of 7").classes("font-semibold")
                    for number, text in STAGES.items():
                        with ui.row().classes("items-center gap-2 no-wrap"):
                            ui.icon("check_circle" if number <= current else "lock").props(
                                f"color={'positive' if number <= current else 'grey'}"
                            )
                            ui.label(f"M0{number}: {text}").classes("text-sm")

                def choose(event: Any) -> None:
                    state["implementation"] = event.value
                    remember("coach_implementation", event.value)
                    status.refresh()

                ui.toggle(
                    {"learner": "Your coach.py", "reference": "Reference"},
                    value=state["implementation"],
                    on_change=choose,
                )
                status()
                ui.markdown(
                    "Check your stages: `uv run agent-lab coach check` · Compare the reference: "
                    "`uv run agent-lab coach check --reference` (it never marks your work done)."
                ).classes("text-sm")
                ui.button("Reload my code", icon="refresh", on_click=status.refresh).props("flat")

            # ---------------------------------------------------------- concept browser
            routes = {"all": "All lessons"} | {path.id: path.title for path in course().paths}
            sections = {"all": "All sections"} | {topic: topic for topic in TOPICS}
            intros = {f"intro:{item['id']}": item for item in INTRO_CONCEPTS}
            state["concept"] = f"lesson:{state['lesson']}"

            def visible_lessons() -> list[int]:
                ids = list(LESSONS)
                if route.value != "all":
                    ids = next(p.lessons for p in course().paths if p.id == route.value)
                if section.value != "all":
                    ids = [n for n in ids if n in TOPICS[section.value]]
                return ids or [state["lesson"]]

            def visible() -> list[str]:
                ids = visible_lessons()
                # The "Start here" cards lead every view that includes lesson 1.
                return (list(intros) if 1 in ids else []) + [f"lesson:{n}" for n in ids]

            def title_of(key: str) -> str:
                if key in intros:
                    return f"Start here · {intros[key]['title']}"
                number = int(key.split(":")[1])
                return f"{number}. {LESSONS[number].title}"

            with card("Concept guide", "Choose what to study"):
                with ui.row().classes("w-full gap-3"):
                    route = ui.select(routes, value="all", label="Route").classes("w-64")
                    section = ui.select(sections, value="all", label="Section").classes("w-64")
                picker = ui.select({}, label="Concept").classes("w-full")

                @ui.refreshable
                def score() -> None:
                    checks = stored("coach_checks", {})
                    ui.label(
                        f"Recognition checks: {sum(checks.values())} correct of {len(checks)} "
                        "answered. Practice only: they never mark a course lesson complete."
                    ).classes("text-sm text-slate-500")

                score()

                def refresh_picker() -> None:
                    keys = visible()
                    picker.set_options({key: title_of(key) for key in keys})
                    if state["concept"] not in keys:
                        state["concept"] = keys[0]
                    picker.set_value(state["concept"])

                def step(offset: int) -> None:
                    keys = visible()
                    index = keys.index(state["concept"]) if state["concept"] in keys else 0
                    picker.set_value(keys[(index + offset) % len(keys)])

                with ui.row().classes("gap-2"):
                    ui.button("Previous concept", icon="chevron_left", on_click=lambda: step(-1))
                    ui.button("Next concept", icon="chevron_right", on_click=lambda: step(1))

                def recognition(
                    question: str, choices: list[str], correct: int, why: list[str]
                ) -> None:
                    key = state["concept"]
                    ui.label("Recognition check").classes("font-semibold mt-2")
                    ui.markdown(question)
                    previous = stored("coach_checks", {}).get(key)
                    feedback = ui.markdown(
                        ""
                        if previous is None
                        else f"*Last answer: {'correct' if previous else 'review this'}.*"
                    )

                    def answer(event: Any) -> None:
                        right = event.value == correct
                        feedback.set_content(
                            ("Correct. " if right else "Review this. ") + why[event.value]
                        )
                        remember("coach_checks", stored("coach_checks", {}) | {key: right})
                        score.refresh()

                    ui.radio(dict(enumerate(choices)), on_change=answer)

                @ui.refreshable
                def concept() -> None:
                    key = state["concept"]
                    if key in intros:
                        intro = intros[key]
                        ui.label(f"Start here: {intro['title']}").classes("text-xl font-bold")
                        ui.markdown(intro["explanation"])
                        ui.code(intro["code"], language="python").classes("w-full")
                        ui.label(
                            "A simplified teaching snippet; lesson 1 runs the real exercise."
                        ).classes("text-xs text-slate-500")
                        check = intro["check"]
                        recognition(
                            check["question"],
                            check["choices"],
                            check["correct"],
                            [check["why"]] * len(check["choices"]),
                        )
                        ui.link("Open lesson 1 in the course", "/?lesson=1")
                        return
                    number = state["lesson"]
                    item = guide(number)
                    ui.label(f"Lesson {number}: {LESSONS[number].title}").classes(
                        "text-xl font-bold"
                    )
                    for point in item.concept_points:
                        ui.markdown(f"**{point.title}.** {point.text}")
                    ui.code(item.concept_code, language="python").classes("w-full")
                    exercise = LESSONS[number].exercise
                    path, start, end = exercise_location(exercise)
                    ui.markdown(
                        f"Lab source: `{path}`, lines {start}-{end} (exercise `{exercise}`); "
                        "the lesson's Python source tab shows it in full."
                    ).classes("text-sm text-slate-500")
                    ui.markdown(
                        f"*Common misconception:* {item.misconception.claim} "
                        f"**Not true.** {item.misconception.correction}"
                    )
                    question = item.quiz[0]
                    recognition(
                        question.prompt,
                        [plain(option.text) for option in question.options],
                        question.correct,
                        [option.explanation.removeprefix("Correct. ") for option in question.options],
                    )
                    ui.link(f"Open lesson {number} in the course", f"/?lesson={number}")

                def pick(event: Any) -> None:
                    if event.value:
                        state["concept"] = event.value
                        # Intro cards belong to lesson 1, so shortcuts and live context use it.
                        state["lesson"] = (
                            1 if event.value in intros else int(event.value.split(":")[1])
                        )
                        concept.refresh()

                def filters_changed() -> None:
                    refresh_picker()
                    concept.refresh()

                picker.on_value_change(pick)
                route.on_value_change(filters_changed)
                section.on_value_change(filters_changed)
                refresh_picker()
                concept()

            # ---------------------------------------------------------- ask the coach
            with card("Ask the coach", "Conversation"):
                ui.label("Shortcuts fill the question box; nothing is sent until you ask.").classes(
                    "text-sm text-slate-500"
                )
                with ui.row().classes("gap-2"):
                    for kind, (label, _) in SHORTCUTS.items():

                        def fill(kind: str = kind) -> None:
                            question.set_value(shortcut_question(kind, state["lesson"]))
                            # After set_value: its change event clears the kind for typed text.
                            state["kind"] = kind

                        ui.button(label, on_click=fill).props("outline rounded dense color=accent")
                question = (
                    ui.textarea("Your question", on_change=lambda: state.update(kind=None))
                    .props("outlined autogrow maxlength=2000")
                    .classes("w-full")
                )
                mode = ui.toggle(
                    {"fixture": "Prepared example", "live": "Live agent"}, value="fixture"
                )
                live = service.settings.enable_live
                if not live:
                    ui.label(
                        "Live answers are off: set ANTHROPIC_API_KEY and LAB_ENABLE_LIVE=true in .env, then restart."
                    ).classes("text-sm text-amber-700").bind_visibility_from(
                        mode, "value", lambda value: value == "live"
                    )
                consent = ui.checkbox(
                    "I authorize one paid question (0.05 USD threshold, one turn, no tools)."
                ).bind_visibility_from(mode, "value", lambda value: value == "live")
                with ui.row().classes("gap-2 items-center"):
                    ask = ui.button("Ask", icon="send")
                    ui.button(
                        "New conversation", icon="add_comment", on_click=lambda: new_conversation()
                    )
                    conversation_label = ui.label("").classes("text-sm text-slate-500")

                @ui.refreshable
                def transcript() -> None:
                    if not state["conversation"]:
                        ui.label("No conversation yet.").classes("text-slate-500")
                        return
                    module = coach()
                    for turn in service.history(state["conversation"]):
                        ui.markdown(f"**You:** {turn['question']}")
                        if turn["status"] == "running":
                            ui.badge("RUNNING", color="warning")
                            ui.markdown(turn["draft"] or "…").classes("response-prose opacity-70")
                            continue
                        try:
                            # Only a completed answer replaces the streamed draft.
                            ui.markdown(module.accept_answer(turn)).classes("response-prose")
                        except NotImplementedError:
                            ui.label("Implement accept_answer (stage 2) to show answers.")
                        except ValueError as exc:
                            ui.badge(turn["status"].upper(), color="negative")
                            ui.label(f"{exc} {turn['error']}").classes("text-sm")

                def new_conversation() -> None:
                    state["conversation"] = None
                    conversation_label.set_text("")
                    transcript.refresh()

                def poll() -> None:
                    transcript.refresh()
                    turn = state["last_turn"] and service.public_turn(state["last_turn"])
                    if not turn or turn["status"] != "running":
                        timer.deactivate()

                timer = ui.timer(0.3, poll, active=False)

                def submit() -> None:
                    module = coach()
                    current = stage_of(module)
                    if current < 2:
                        raise locked(2)
                    text = module.prepare_question(question.value or "")
                    if current >= 3:
                        keep = state["conversation"] if current >= 4 else None
                        request = module.create_tutor_request(text, mode.value, keep)
                        text, conversation = request["question"], request["conversation_id"]
                    elif mode.value == "live":
                        raise locked(3)
                    else:
                        conversation = None
                    started = service.submit(
                        text,
                        mode.value,
                        conversation,
                        consent=bool(consent.value),
                        lesson_id=state["lesson"],
                        kind=state["kind"],
                    )
                    consent.set_value(False)  # consent covers one question
                    returned = started["conversation_id"]
                    if current >= 4:
                        returned = module.continue_conversation(state["conversation"], returned)
                    state["conversation"], state["last_turn"] = returned, started["turn_id"]
                    conversation_label.set_text(
                        f"Conversation {returned[:8]}… · turn {started['turn_id'][:8]}…"
                    )
                    recover_id.set_value(started["turn_id"])
                    transcript.refresh()
                    timer.activate()

                ask.on_click(lambda: run(submit))
                transcript()

            # ---------------------------------------------------------- recovery
            with card("Recover a saved turn", "Stage 6"):
                ui.label(
                    "Inspecting a turn reads what the server saved. It never calls the model "
                    "or starts another turn."
                ).classes("text-sm text-slate-600")
                recover_id = ui.input("Turn id").props("outlined").classes("w-full")
                decision = ui.markdown("")

                def inspect_turn() -> None:
                    module = coach()
                    if stage_of(module) < 6:
                        raise locked(6)
                    turn = service.public_turn((recover_id.value or "").strip())
                    action = module.recover_turn(turn)
                    detail = f"\n\n{turn['text']}" if action == "reuse" else ""
                    decision.set_content(
                        f"**{action}**: {RECOVERY.get(action, 'Unknown action.')}{detail}"
                    )

                ui.button(
                    "Inspect saved turn", icon="manage_search", on_click=lambda: run(inspect_turn)
                )

            # ---------------------------------------------------------- study plan
            with card("Create a study plan", "Stage 5"):
                with ui.row().classes("gap-3"):
                    days = ui.number("Days", value=3, min=1, max=7, precision=0).classes("w-32")
                    minutes = ui.number(
                        "Minutes per day", value=30, min=5, max=120, precision=0
                    ).classes("w-40")
                plan_view = ui.column().classes("w-full")

                def show_plan(plan: Any, label: str) -> None:
                    module = coach()
                    if stage_of(module) < 5:
                        raise locked(5)
                    errors = module.validate_plan(
                        plan, int(days.value or 0), int(minutes.value or 0)
                    )
                    plan_view.clear()
                    with plan_view:
                        ui.label(label).classes("font-semibold")
                        if errors:
                            ui.badge("REJECTED", color="negative")
                            for error in errors:
                                ui.label(f"• {error}").classes("text-red-700")
                        else:
                            ui.badge("ACCEPTED", color="positive")
                        rows = plan.get("days", []) if isinstance(plan, dict) else []
                        if rows and all(isinstance(row, dict) for row in rows):
                            ui.table(
                                columns=[
                                    {"name": k, "label": k.title(), "field": k, "align": "left"}
                                    for k in ("day", "topic", "minutes")
                                ],
                                rows=rows,
                            ).classes("w-full").props("flat bordered")
                        elif not isinstance(plan, dict):
                            ui.code(str(plan)[:2000]).classes("w-full")

                def prepared(invalid: bool) -> None:
                    plan = fixture_plan(
                        visible_lessons(), int(days.value or 1), int(minutes.value or 5), invalid
                    )
                    show_plan(plan, "Prepared invalid plan" if invalid else "Prepared plan")

                async def live_plan() -> None:
                    try:
                        if stage_of(coach()) < 5:
                            raise locked(5)
                        if not plan_consent.value:
                            raise PermissionError(
                                "Confirm that you authorize one paid plan request."
                            )
                        plan_consent.set_value(False)  # consent covers one request
                        plan = await service.live_plan(
                            visible_lessons(), int(days.value or 1), int(minutes.value or 5)
                        )
                    except (StageLocked, ValueError, PermissionError, LessonError) as exc:
                        ui.notify(str(exc), type="warning")
                        return
                    # The same validator judges live and prepared plans.
                    run(lambda: show_plan(plan, "Live plan from Claude"))

                with ui.row().classes("gap-2"):
                    ui.button("Create study plan", on_click=lambda: run(lambda: prepared(False)))
                    ui.button(
                        "Try invalid prepared plan", on_click=lambda: run(lambda: prepared(True))
                    ).props("outline")
                    ui.button(
                        "Ask Claude for a plan", icon="auto_awesome", on_click=live_plan
                    ).props("outline").set_enabled(live)
                plan_consent = ui.checkbox(
                    "I authorize one paid plan request (0.05 USD threshold)."
                )
                plan_consent.set_visibility(live)
