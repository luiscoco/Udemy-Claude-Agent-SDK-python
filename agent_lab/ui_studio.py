"""The Agent Evaluation Studio milestone page. Every action goes through the student's studio.py."""

from typing import Any

from nicegui import ui

from agent_lab.config import ROOT
from agent_lab.evaluation_studio import (
    STAGE_FUNCTIONS,
    StudioService,
    catalog,
    load_studio,
    stage_of,
    studio_path,
)
from agent_lab.models import LessonError
from agent_lab.ui_learning import appearance_controls, card, page_style, preference
from agent_lab.ui_learning import set_preference as remember

STAGES = {
    1: "M08 Browse the roadmap of evaluation cases",
    2: "M09 Summarize a run honestly: answer, timeline and result",
    3: "M10 Compare baseline and guided instructions",
    4: "M11 Add one bounded, authorized live run",
    5: "M12 Add external knowledge with scoped MCP settings",
    6: "M13 Record reviews and export evidence",
    7: "M14 Decide a release from two regression suites",
}
SCENARIOS = {
    "success": "Completed run",
    "max_turns": "Turn limit reached",
    "max_turns_then_stream_error": "Turn limit, then a stream error",
}


class StageLocked(Exception):
    pass


def locked(stage: int) -> StageLocked:
    names = ", ".join(f"`{name}`" for name in STAGE_FUNCTIONS.get(stage, ()))
    return StageLocked(
        f"Implement stage {stage} ({names}) in mini_projects/evaluation_studio/studio.py, "
        f"then set STAGE = {stage}."
    )


def install_studio_page(service: StudioService) -> None:
    @ui.page("/studio")
    async def studio_page() -> None:
        page_style()
        cases, sections, variants = catalog()["cases"], catalog()["sections"], catalog()["variants"]
        state: dict[str, Any] = {
            "implementation": preference("studio_implementation", "learner"),
            "case": cases[0]["id"],
            "run": None,
        }
        live_enabled = service.settings.enable_live

        def studio() -> Any:
            return load_studio(state["implementation"])

        def need(stage: int) -> Any:
            module = studio()
            if stage_of(module) < stage:
                raise locked(stage)
            return module

        def run(action: Any) -> Any:
            """Calls into the student's code: a TODO becomes a clear next step, not a crash."""
            try:
                return action()
            except NotImplementedError as exc:
                ui.notify(f"{exc}. See mini_projects/evaluation_studio/prompts/.")
            except StageLocked as exc:
                ui.notify(str(exc), type="info")
            except (ValueError, PermissionError, LessonError) as exc:
                ui.notify(str(exc), type="warning")
            return None

        with ui.header().classes("lab-header border-b items-center"):
            ui.link("Claude Agent SDK Lab", "/").classes(
                "text-xl font-bold no-underline text-slate-900 min-w-0 flex-1"
            )
            ui.badge("EVALUATION STUDIO", color="secondary").classes("gt-xs")
            appearance_controls()

        with ui.column().classes("w-full max-w-6xl mx-auto p-4 md:p-8 gap-5"):
            # ---------------------------------------------------------- status
            with card("Agent Evaluation Studio", "Milestone project"):
                ui.label(
                    f"Evaluate an SDK tutor on {len(cases)} cases in {len(sections)} sections. "
                    "This page runs your mini_projects/evaluation_studio/studio.py, so every "
                    "stage you finish unlocks a feature."
                ).classes("text-slate-600")

                @ui.refreshable
                def status() -> None:
                    current = stage_of(studio())
                    path = studio_path(state["implementation"]).relative_to(ROOT).as_posix()
                    ui.label(f"{path} is at stage {current} of 7").classes("font-semibold")
                    for number, text in STAGES.items():
                        with ui.row().classes("items-center gap-2 no-wrap"):
                            done = number <= current
                            ui.icon("check_circle" if done else "lock").props(
                                f"color={'positive' if done else 'grey'}"
                            )
                            ui.label(text).classes("text-sm")

                def choose(event: Any) -> None:
                    state["implementation"] = event.value
                    remember("studio_implementation", event.value)
                    status.refresh()

                ui.toggle(
                    {"learner": "Your studio.py", "reference": "Reference"},
                    value=state["implementation"],
                    on_change=choose,
                )
                status()
                ui.markdown(
                    "Check your stages: `uv run agent-lab studio check` · Compare the reference: "
                    "`uv run agent-lab studio check --reference` (it never marks your work done)."
                ).classes("text-sm")
                ui.button("Reload my code", icon="refresh", on_click=status.refresh).props("flat")

            # ---------------------------------------------------------- roadmap
            with card("Roadmap", "Choose a case"):
                section = ui.select(
                    {s["id"]: f"{s['title']} · {s['level']}" for s in sections},
                    value=sections[0]["id"],
                    label="Section",
                ).classes("w-full")
                picker = ui.select({}, label="Case").classes("w-full")

                def in_section() -> list[dict]:
                    return [c for c in cases if c["section"] == section.value]

                def refresh_cases() -> None:
                    items = in_section()
                    picker.set_options({c["id"]: f"{c['number']}. {c['title']}" for c in items})
                    if state["case"] not in {c["id"] for c in items}:
                        state["case"] = items[0]["id"]
                    picker.set_value(state["case"])

                def step(offset: int) -> None:
                    index = next(i for i, c in enumerate(cases) if c["id"] == state["case"])
                    target = cases[(index + offset) % len(cases)]
                    state["case"] = target["id"]
                    section.set_value(target["section"])
                    refresh_cases()
                    detail.refresh()

                with ui.row().classes("gap-2"):
                    ui.button("Previous case", icon="chevron_left", on_click=lambda: step(-1))
                    ui.button("Next case", icon="chevron_right", on_click=lambda: step(1))

                @ui.refreshable
                def detail() -> None:
                    item = next(c for c in cases if c["id"] == state["case"])
                    guide = next(s for s in sections if s["id"] == item["section"])["guide"]
                    ui.label(f"{item['number']}. {item['title']}").classes("text-xl font-bold")
                    ui.markdown(f"**Question:** {item['question']}")
                    ui.markdown(f"**Context (task data, not instructions):** {item['context']}")
                    ui.label("Review criteria").classes("font-semibold")
                    for criterion in item["criteria"]:
                        ui.label(f"• {criterion}").classes("text-sm")
                    source = {"docs": "official docs MCP", "project": "a trusted project MCP"}.get(
                        item["resource"], "no external source"
                    )
                    ui.label(f"Suggested source: {source}").classes("text-sm text-slate-500")
                    ui.link("Official guide for this section", guide, new_tab=True)

                def picked(event: Any) -> None:
                    if event.value:
                        state["case"] = event.value
                        detail.refresh()

                def section_changed() -> None:
                    refresh_cases()
                    detail.refresh()

                picker.on_value_change(picked)
                section.on_value_change(section_changed)
                refresh_cases()
                detail()

            # ---------------------------------------------------------- run
            with card("Run the case", "Prepared or live"):
                with ui.row().classes("gap-3 items-center"):
                    variant = ui.toggle({key: key.title() for key in variants}, value="guided")
                    mode = ui.toggle(
                        {"prepared": "Prepared fixture", "live": "Live SDK run"}, value="prepared"
                    )
                scenario = (
                    ui.select(SCENARIOS, value="success", label="Prepared scenario")
                    .classes("w-full max-w-xs")
                    .bind_visibility_from(mode, "value", lambda value: value == "prepared")
                )
                with (
                    ui.column()
                    .classes("w-full gap-2")
                    .bind_visibility_from(mode, "value", lambda value: value == "live")
                ):
                    if not live_enabled:
                        ui.label(
                            "Live runs are off: set ANTHROPIC_API_KEY and LAB_ENABLE_LIVE=true in .env, then restart."
                        ).classes("text-sm text-amber-700")
                    with ui.row().classes("gap-3"):
                        depth = ui.select(
                            ["brief", "guided", "worked"], value="guided", label="Depth"
                        ).classes("w-36")
                        turns = ui.select([1, 3, 5, 8, 12], value=1, label="Max turns").classes(
                            "w-32"
                        )
                        budget = ui.select(
                            [0.05, 0.15, 0.3, 0.5], value=0.05, label="Budget USD"
                        ).classes("w-36")
                    question = (
                        ui.input("Optional question override")
                        .props("outlined maxlength=2000")
                        .classes("w-full")
                    )
                    source = ui.toggle(
                        {"none": "No source", "docs": "Official docs MCP", "custom": "Custom MCP"},
                        value="none",
                    )
                    with (
                        ui.row()
                        .classes("gap-3")
                        .bind_visibility_from(source, "value", lambda value: value == "custom")
                    ):
                        mcp_name = ui.input("Server name").classes("w-40")
                        mcp_url = ui.input("Public HTTPS URL").classes("w-full max-w-xs")
                        mcp_tools = ui.input("Tools (comma separated)").classes("w-64")
                    specialist = ui.checkbox(
                        "Specialist reviewer subagent (needs 5+ turns and 0.15 USD)"
                    )
                    consent = ui.checkbox("I authorize one paid SDK run within these bounds.")
                    mcp_consent = ui.checkbox(
                        "I authorize the external MCP connection for this run."
                    ).bind_visibility_from(source, "value", lambda value: value != "none")
                with ui.row().classes("gap-2"):
                    run_button = ui.button("Run", icon="play_arrow")
                    ui.button(
                        "Compare baseline and guided", icon="compare", on_click=lambda: run(compare)
                    ).props("outline")
                compare_view = ui.column().classes("w-full")

            with card("Result", "Answer and timeline"):

                @ui.refreshable
                def result() -> None:
                    current = state["run"]
                    if not current:
                        ui.label("Run a case to see its answer, result and timeline.").classes(
                            "text-slate-500"
                        )
                        return
                    with ui.row().classes("gap-2 items-center"):
                        ui.badge(
                            "LIVE SDK RUN" if current["run_mode"] == "live" else "PREPARED FIXTURE",
                            color="primary" if current["run_mode"] == "live" else "secondary",
                        )
                        ui.badge(
                            current["subtype"],
                            color="negative" if current["is_error"] else "positive",
                        )
                        ui.label(
                            f"{current['duration_ms']} ms · turns {current['turns']} · cost "
                            f"{current['cost_usd'] if current['cost_usd'] is not None else 'n/a'} · "
                            f"MCP calls {current['mcp_tool_calls']} · specialist calls {current['specialist_calls']} · "
                            f"{current['source']}"
                        ).classes("text-sm text-slate-500")
                    ui.markdown(current["answer"]).classes("response-prose w-full")
                    ui.table(
                        columns=[
                            {"name": "label", "label": "Event", "field": "label", "align": "left"},
                            {
                                "name": "detail",
                                "label": "Detail",
                                "field": "detail",
                                "align": "left",
                            },
                        ],
                        rows=current["events"],
                    ).classes("w-full").props("flat bordered dense")

                result()

            with card("Review this run", "Stage 6"):

                @ui.refreshable
                def review() -> None:
                    current = state["run"]
                    if not current:
                        ui.label("Run a case first.").classes("text-slate-500")
                        return
                    boxes = [ui.checkbox(text) for text in current["criteria"]]
                    note = (
                        ui.textarea("Reviewer note")
                        .props("outlined maxlength=1000")
                        .classes("w-full")
                    )
                    saved = service.reviews.get(current["id"])
                    if saved:
                        ui.label(
                            f"Saved: {'passed' if saved['passed'] else 'needs work'} ({saved['kind']})"
                        )

                    def save() -> None:
                        record = service.save_review(
                            need(6), current["id"], [bool(b.value) for b in boxes], note.value or ""
                        )
                        ui.notify(
                            f"Review saved: {'passed' if record['passed'] else 'needs work'}."
                        )
                        review.refresh()
                        history.refresh()

                    with ui.row().classes("gap-2"):
                        ui.button("Save review", icon="rate_review", on_click=lambda: run(save))
                        ui.button(
                            "Export evidence", icon="download", on_click=lambda: run(export)
                        ).props("outline")

                def export() -> None:
                    markdown = need(6).export_evidence(list(service.reviews.values()))
                    ui.download.content(markdown, "evaluation-evidence.md", "text/markdown")

                review()

            def start() -> None:
                if mode.value == "prepared":
                    state["run"] = service.prepared_run(
                        need(2), state["case"], variant.value, scenario.value
                    )
                    refresh_run()
                    return
                ui.timer(0.01, live, once=True)

            async def live() -> None:
                try:
                    module = need(5)
                    options = module.parse_run_options(
                        depth.value,
                        turns.value,
                        budget.value,
                        bool(specialist.value),
                        question.value or "",
                    )
                    mcp = module.mcp_settings(
                        source.value,
                        mcp_name.value or "",
                        mcp_url.value or "",
                        mcp_tools.value or "",
                    )
                    run_button.disable()
                    state["run"] = await service.live_run(
                        module,
                        state["case"],
                        variant.value,
                        options,
                        mcp,
                        consent=bool(consent.value),
                        mcp_consent=bool(mcp_consent.value),
                    )
                except (
                    StageLocked,
                    NotImplementedError,
                    ValueError,
                    PermissionError,
                    LessonError,
                ) as exc:
                    ui.notify(str(exc), type="warning")
                    return
                finally:
                    run_button.enable()
                    consent.set_value(False)  # consent covers one run
                    mcp_consent.set_value(False)
                refresh_run()

            def refresh_run() -> None:
                result.refresh()
                review.refresh()
                history.refresh()

            def compare() -> None:
                module = need(3)
                compare_view.clear()
                with (
                    compare_view,
                    ui.grid(columns="repeat(auto-fit, minmax(280px, 1fr))").classes("w-full gap-3"),
                ):
                    for key, text in variants.items():
                        outcome = service.prepared_run(module, state["case"], key)
                        with ui.card().classes("course-card p-4 gap-2"):
                            ui.label(key.title()).classes("font-bold")
                            ui.code(module.build_system_prompt(text, depth.value, "none")).classes(
                                "w-full"
                            )
                            ui.markdown(outcome["answer"]).classes("response-prose")
                history.refresh()

            run_button.on_click(lambda: run(start))

            # ---------------------------------------------------------- history
            with card("Run history", f"Latest {40}"):

                @ui.refreshable
                def history() -> None:
                    rows = [
                        {
                            "case": run_["case_title"],
                            "variant": run_["variant"],
                            "kind": run_["run_mode"],
                            "subtype": run_["subtype"],
                            "review": (service.reviews.get(run_["id"]) or {}).get("passed", "-"),
                        }
                        for run_ in reversed(list(service.runs.values()))
                    ]
                    if not rows:
                        ui.label("No runs yet.").classes("text-slate-500")
                        return
                    ui.table(
                        columns=[
                            {"name": k, "label": k.title(), "field": k, "align": "left"}
                            for k in rows[0]
                        ],
                        rows=rows,
                    ).classes("w-full").props("flat bordered dense")

                history()

            # ---------------------------------------------------------- suites
            with card("Regression suites", "Stage 7"):
                ui.label(
                    "A suite runs every case as a prepared fixture: free and deterministic. "
                    "It never makes hidden paid calls and is not a live validation."
                ).classes("text-sm text-slate-600")
                with ui.row().classes("gap-3 items-center"):
                    suite_name = ui.input("Suite name", value="guided-v1").classes("w-48")
                    suite_variant = ui.toggle(
                        {key: key.title() for key in variants}, value="guided"
                    )

                    def build_suite() -> None:
                        suite = service.run_suite(
                            need(2), suite_variant.value, suite_name.value or ""
                        )
                        failures = sum(r["subtype"] != "success" for r in suite["results"].values())
                        ui.notify(
                            f"Suite {suite['name']}: {len(suite['results'])} cases, {failures} not successful."
                        )
                        suites.refresh()

                    ui.button(
                        "Run prepared suite",
                        icon="playlist_play",
                        on_click=lambda: run(build_suite),
                    )

                @ui.refreshable
                def suites() -> None:
                    names = list(service.suites)
                    if len(names) < 2:
                        ui.label(f"{len(names)} suite(s) saved. Save two to compare them.").classes(
                            "text-slate-500"
                        )
                        return
                    baseline = ui.select(names, value=names[-2], label="Baseline").classes("w-56")
                    candidate = ui.select(names, value=names[-1], label="Candidate").classes("w-56")
                    explanations = (
                        ui.textarea("Explain each regression (one per line: case-id: reason)")
                        .props("outlined")
                        .classes("w-full")
                    )
                    verdict = ui.markdown("")

                    def decide() -> None:
                        module = need(7)
                        notes = {}
                        for line in (explanations.value or "").splitlines():
                            if ":" in line:
                                key, reason = line.split(":", 1)
                                notes[key.strip()] = reason.strip()

                        def outcomes(name: str) -> dict[str, dict[str, Any]]:
                            results = service.suites[name]["results"]
                            return {
                                key: {"subtype": value["subtype"], "passed": value["passed"]}
                                for key, value in results.items()
                            }

                        decision = module.release_decision(
                            outcomes(baseline.value), outcomes(candidate.value), notes
                        )
                        verdict.set_content(
                            f"**{'Ready to release' if decision['ready'] else 'Not ready'}** · "
                            f"regressions: {', '.join(decision['regressions']) or 'none'} · "
                            f"unexplained: {', '.join(decision['unexplained']) or 'none'} · "
                            f"missing: {', '.join(decision['missing']) or 'none'}"
                        )

                    ui.button("Decide release", icon="gavel", on_click=lambda: run(decide))

                suites()
