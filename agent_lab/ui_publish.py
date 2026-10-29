"""The Agent Publishing Studio milestone page. Every action goes through the student's publisher.py."""

import base64
import html
import re
from typing import Any

from fastapi import HTTPException
from fastapi.responses import Response
from nicegui import app, ui

from agent_lab.config import ROOT
from agent_lab.models import LessonError
from agent_lab.publishing_studio import (
    MAX_ANSWERS,
    NO_SOURCE,
    STAGE_FUNCTIONS,
    PublishingService,
    load_publisher,
    prompt_library,
    publisher_path,
    stage_of,
)
from agent_lab.ui_learning import appearance_controls, card, page_style, preference
from agent_lab.ui_learning import set_preference as remember

STAGES = {
    1: "M15 Ask, select and read prepared answers",
    2: "M16 Validate requests and add a consented live answer",
    3: "M17 Attach sources and see exactly what was extracted",
    4: "M18 Plan a document or infographic from one selected answer",
    5: "M19 Build Word and PDF files from one validated plan",
    6: "M20 Build SVG and PNG infographics",
    7: "M21 Optional documentation MCP and the full workflow",
    8: "M22 Style infographics from a PNG visual reference",
}
PUBLISH_CSS = """
.step-compose { border-top: 5px solid #2563eb !important; }
.step-review { border-top: 5px solid #0f766e !important; }
.step-publish { border-top: 5px solid #d97706 !important; }
.artifact-preview { width: 100%; border: 1px solid #cbd5e1; border-radius: 12px; background: #fff; overflow: hidden; }
.artifact-preview img { width: 100%; height: auto; display: block; }
.doc-frame { width: 100%; height: 560px; border: 0; background: #fff; display: block; }
.swatch { width: 3.5rem; height: 2.25rem; border-radius: 8px; border: 1px solid #94a3b8; }
.code-label { font-size: 0.75rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; }
.answer-view .q-code, .answer-view pre { max-width: 100%; overflow-x: auto; }
.break-all { overflow-wrap: anywhere; }
"""
FENCE = re.compile(r"^\s*```\s*([\w+#.-]*)[^\n`]*$")


class StageLocked(Exception):
    pass


def locked(stage: int) -> StageLocked:
    names = ", ".join(f"`{name}`" for name in STAGE_FUNCTIONS.get(stage, ()))
    return StageLocked(
        f"Implement stage {stage} ({names}) in mini_projects/publishing_studio/publisher.py, "
        f"then set STAGE = {stage}."
    )


def segments(text: str) -> list[tuple[str, str, str]]:
    """Split an answer into prose and fenced code for display: (kind, language, text)."""
    lines = text.replace("\r\n", "\n").split("\n")
    parts: list[tuple[str, str, str]] = []
    prose: list[str] = []
    index = 0
    while index < len(lines):
        opening = FENCE.match(lines[index])
        end = (
            next((j for j in range(index + 1, len(lines)) if lines[j].strip() == "```"), None)
            if opening
            else None
        )
        if opening and end is not None:
            parts.append(("text", "", "\n".join(prose)))
            prose = []
            parts.append(("code", opening.group(1).lower() or "text", "\n".join(lines[index + 1 : end])))
            index = end + 1
            continue
        prose.append(lines[index])
        index += 1
    parts.append(("text", "", "\n".join(prose)))
    return [part for part in parts if part[2].strip()]


def install_publish_page(service: PublishingService) -> None:
    @app.get("/publish/artifacts/{artifact_id}")
    def download_artifact(artifact_id: str) -> Response:
        try:
            record, data = service.artifact(artifact_id)
        except (ValueError, OSError) as exc:
            raise HTTPException(status_code=404, detail="Unknown artifact.") from exc
        return Response(
            data,
            media_type=record["mime"],
            headers={
                "Content-Disposition": f'attachment; filename="{record["filename"]}"',
                "X-Content-Type-Options": "nosniff",
                "Content-Security-Policy": "default-src 'none'; img-src data:; style-src 'unsafe-inline'",
            },
        )

    @app.get("/publish/project.zip")
    def download_project() -> Response:
        return Response(
            service.project_zip(),
            media_type="application/zip",
            headers={"Content-Disposition": 'attachment; filename="publishing_studio.zip"'},
        )

    @ui.page("/publish")
    async def publish_page() -> None:
        page_style()
        ui.add_css(PUBLISH_CSS)
        library = prompt_library()
        state: dict[str, Any] = {
            "implementation": preference("publisher_implementation", "learner"),
            "answer": next(reversed(service.answers), None),
            "bundle": None,
            "files": [],
            "reference": None,
        }
        live_enabled = service.settings.enable_live

        def publisher() -> Any:
            return load_publisher(state["implementation"])

        def need(stage: int) -> Any:
            module = publisher()
            if stage_of(module) < stage:
                raise locked(stage)
            return module

        def warn(exc: Exception) -> None:
            if isinstance(exc, NotImplementedError):
                ui.notify(f"{exc}. See mini_projects/publishing_studio/prompts/.")
            else:
                ui.notify(str(exc), type="info" if isinstance(exc, StageLocked) else "warning")

        failures = (StageLocked, NotImplementedError, ValueError, PermissionError, LessonError)

        with ui.header().classes("lab-header border-b items-center"):
            ui.link("Claude Agent SDK Lab", "/").classes(
                "text-xl font-bold no-underline text-slate-900 min-w-0 flex-1"
            )
            ui.badge("PUBLISHING STUDIO", color="accent").classes("gt-xs")
            appearance_controls()

        with ui.column().classes("w-full max-w-6xl mx-auto p-4 md:p-8 gap-5"):
            # ---------------------------------------------------------- status
            with card("Agent Publishing Studio", "Milestone project"):
                ui.label(
                    "Ask, select, build, download: turn one saved answer into Word, PDF, SVG and "
                    "PNG files. This page runs your mini_projects/publishing_studio/publisher.py, "
                    "so every stage you finish unlocks a feature."
                ).classes("text-slate-600")

                @ui.refreshable
                def status() -> None:
                    current = stage_of(publisher())
                    path = publisher_path(state["implementation"]).relative_to(ROOT).as_posix()
                    ui.label(f"{path} is at stage {current} of 8").classes("font-semibold")
                    for number, text in STAGES.items():
                        with ui.row().classes("items-center gap-2 no-wrap"):
                            done = number <= current
                            ui.icon("check_circle" if done else "lock").props(
                                f"color={'positive' if done else 'grey'}"
                            )
                            ui.label(text).classes("text-sm")

                def choose(event: Any) -> None:
                    state["implementation"] = event.value
                    remember("publisher_implementation", event.value)
                    reload_code()

                ui.toggle(
                    {"learner": "Your publisher.py", "reference": "Reference"},
                    value=state["implementation"],
                    on_change=choose,
                )
                status()
                ui.markdown(
                    "Check your stages: `uv run agent-lab publish check` · Compare the reference: "
                    "`uv run agent-lab publish check --reference` (it never marks your work done)."
                ).classes("text-sm")
                with ui.row().classes("gap-2"):
                    ui.button("Reload my code", icon="refresh", on_click=lambda: reload_code()).props(
                        "flat"
                    )
                    ui.link("Download project ZIP", "/publish/project.zip").props("download").classes(
                        "self-center"
                    )

            # ---------------------------------------------------------- 1. ask
            with card("1 · Ask", "Compose").classes("step-compose"):
                with ui.row().classes("w-full gap-3"):
                    section = ui.select(
                        {s["id"]: s["title"] for s in library},
                        value=library[0]["id"],
                        label="Prompt library section",
                    ).classes("w-full sm:w-72")
                    suggestion = ui.select({}, label="Suggested prompt (fills the box)").classes(
                        "w-full sm:flex-1 min-w-0"
                    )

                def fill_suggestions() -> None:
                    chosen = next(s for s in library if s["id"] == section.value)
                    suggestion.set_options(dict(enumerate(chosen["prompts"])), value=None)

                section.on_value_change(fill_suggestions)
                fill_suggestions()
                prompt = (
                    ui.textarea("Your prompt", value=library[0]["prompts"][0])
                    .props("outlined autogrow maxlength=4000")
                    .classes("w-full")
                )
                suggestion.on_value_change(
                    lambda event: event.value is not None
                    and prompt.set_value(
                        next(s for s in library if s["id"] == section.value)["prompts"][event.value]
                    )
                )
                models = publisher().MODELS
                with ui.row().classes("w-full gap-3 items-center"):
                    model = ui.select(models, value=next(iter(models)), label="Model").classes(
                        "w-full sm:w-80"
                    )
                    mode = ui.toggle(
                        {"prepared": "Prepared (free sample)", "live": "Live SDK answer"},
                        value="prepared",
                    )
                with (
                    ui.column()
                    .classes("w-full gap-2")
                    .bind_visibility_from(mode, "value", lambda value: value == "live")
                ):
                    if not live_enabled:
                        ui.label(
                            "Live answers are off: set ANTHROPIC_API_KEY and LAB_ENABLE_LIVE=true in .env, then restart."
                        ).classes("text-sm text-amber-700")
                    with ui.row().classes("gap-3 items-center"):
                        budget = ui.select(
                            {0.2: "$0.20", 0.5: "$0.50", 1.0: "$1.00", 2.0: "$2.00"},
                            value=0.2,
                            label="Spending cap for this call",
                        ).classes("w-56")
                        source = ui.toggle(
                            {"none": "No external source", "docs": "Official Claude documentation MCP"},
                            value="none",
                        )
                    consent = ui.checkbox("I authorize one paid SDK answer up to $0.20.")
                    mcp_consent = ui.checkbox(
                        "I authorize the connection to the official documentation MCP for this answer."
                    ).bind_visibility_from(source, "value", lambda value: value == "docs")

                    def budget_changed() -> None:
                        consent.set_value(False)  # a new cap needs a new authorization
                        consent.set_text(f"I authorize one paid SDK answer up to ${budget.value:.2f}.")

                    budget.on_value_change(budget_changed)
                    source.on_value_change(lambda: mcp_consent.set_value(False))

                ui.label("Sources (stage 3) and a PNG style reference (stage 8)").classes(
                    "font-semibold mt-2"
                )

                async def uploaded(event: Any) -> None:
                    try:
                        module = need(3)
                        record = service.upload(
                            module, event.file.name, await event.file.read(), len(state["files"])
                        )
                    except failures as exc:
                        warn(exc)
                        return
                    finally:
                        uploader.reset()
                    if record["kind"] == "png":
                        state["reference"] = record["id"]
                        reference_view.refresh()
                        ui.notify(f"{record['name']} is the visual reference for infographics.")
                    else:
                        state["files"].append(record["id"])
                        attachments.refresh()

                uploader = (
                    ui.upload(
                        label="TXT, MD, CSV, DOCX or text PDF (up to 3, 5 MB each); one PNG reference",
                        on_upload=uploaded,
                        on_rejected=lambda: ui.notify(
                            "Rejected: upload TXT, MD, CSV, DOCX, PDF or PNG files up to 5 MB.",
                            type="warning",
                        ),
                        auto_upload=True,
                        multiple=True,
                        max_file_size=5_000_000,
                    )
                    .props('accept=".txt,.md,.markdown,.csv,.docx,.pdf,.png" flat bordered')
                    .classes("w-full max-w-xl")
                )

                @ui.refreshable
                def attachments() -> None:
                    if not state["files"]:
                        ui.label("No source files attached to the next answer.").classes(
                            "text-sm text-slate-500"
                        )
                        return
                    for file_id in list(state["files"]):
                        item = service.uploads.get(file_id)
                        if item is None:
                            state["files"].remove(file_id)
                            continue
                        with ui.expansion(
                            f"{item['name']} · {item['chars']:,} characters extracted",
                            icon="description",
                        ).classes("w-full border rounded"):
                            ui.label(item["preview"] + ("…" if item["chars"] > 240 else "")).classes(
                                "text-sm whitespace-pre-wrap break-all"
                            )

                            def detach(file_id: str = file_id) -> None:
                                state["files"].remove(file_id)
                                attachments.refresh()

                            ui.button("Remove", icon="close", on_click=detach).props("flat dense")

                attachments()
                send = ui.button("Send", icon="send").props("color=primary")

            # ---------------------------------------------------------- 2. select
            with card("2 · Select", "Review").classes("step-review"):
                history = ui.select({}, label=f"Saved answers (latest {MAX_ANSWERS})").classes("w-full")

                def history_options() -> None:
                    options = {
                        key: f"{item['created'][11:19]} · {item['origin'].upper()} · {item['prompt'][:70]}"
                        for key, item in reversed(service.answers.items())
                    }
                    history.set_options(options, value=state["answer"] if state["answer"] in options else None)

                def selected(event: Any) -> None:
                    if event.value and event.value != state["answer"]:
                        state["answer"] = event.value
                        state["bundle"] = None  # an old artifact never describes a new answer
                        refresh_answer()

                history.on_value_change(selected)

                @ui.refreshable
                def answer_view() -> None:
                    item = service.answers.get(state["answer"] or "")
                    if item is None:
                        ui.label("Send a prompt, then select its answer here.").classes("text-slate-500")
                        return
                    live = item["origin"] == "live"
                    with ui.row().classes("gap-2 items-center"):
                        ui.badge(
                            "LIVE SDK ANSWER" if live else "PREPARED SAMPLE",
                            color="primary" if live else "secondary",
                        )
                        if live:
                            ui.badge(item["subtype"], color="positive" if item["complete"] else "negative")
                        else:
                            ui.label("Fixed teaching sample · zero model calls").classes("text-sm")
                    cost = item["cost_usd"]
                    files = ", ".join(f["name"] for f in item["files"]) or "none"
                    ui.label(
                        f"Answer {item['id'][:8]} · {item['model']} · turns {item['turns']} · cost "
                        f"{f'${cost:.4f}' if cost is not None else 'unknown'} · MCP calls "
                        f"{item['mcp_tool_calls']} · {item['source']} · files: {files}"
                    ).classes("text-sm text-slate-500 break-all").props(f"data-answer={item['id']}")
                    ui.label(f"Prompt: {item['prompt']}").classes("text-sm break-all")
                    with ui.column().classes("answer-view w-full gap-2"):
                        for kind, language, text in segments(item["answer"]):
                            if kind == "code":
                                ui.label(f"Code · {language}").classes("code-label text-slate-500")
                                ui.code(text, language=language).classes("w-full")
                            else:
                                ui.markdown(text).classes("response-prose w-full")

                history_options()
                answer_view()

            # ---------------------------------------------------------- 3. build
            with card("3 · Build", "Publish").classes("step-publish"):

                @ui.refreshable
                def build_source() -> None:
                    item = service.answers.get(state["answer"] or "")
                    ui.label(
                        f"Source: answer {item['id'][:8]} ({item['origin']}, sha256 {item['sha256'][:12]}…)"
                        if item
                        else "Source: select an answer first."
                    ).classes("text-sm font-semibold break-all")

                build_source()
                with ui.row().classes("w-full gap-3 items-center"):
                    kind = ui.toggle(
                        {"document": "Word + PDF document", "infographic": "SVG + PNG infographic"},
                        value="document",
                    )
                    planning = ui.toggle(
                        {"prepared": "Prepared plan (free)", "live": "Live plan (paid)"},
                        value="prepared",
                    )
                conversion = (
                    ui.input("Conversion request (optional), for example: a one-page beginner handout")
                    .props("outlined maxlength=500")
                    .classes("w-full")
                )
                with (
                    ui.column()
                    .classes("w-full gap-2")
                    .bind_visibility_from(planning, "value", lambda value: value == "live")
                ):
                    with ui.row().classes("gap-3"):
                        plan_model = ui.select(models, value=next(iter(models)), label="Planning model").classes(
                            "w-full sm:w-80"
                        )
                        plan_budget = ui.select(
                            {0.2: "$0.20", 0.5: "$0.50", 1.0: "$1.00", 2.0: "$2.00"},
                            value=0.2,
                            label="Planning spending cap",
                        ).classes("w-56")
                    plan_consent = ui.checkbox(
                        "I authorize one paid planning call up to $0.20 (separate from the answer)."
                    )

                    def plan_budget_changed() -> None:
                        plan_consent.set_value(False)
                        plan_consent.set_text(
                            f"I authorize one paid planning call up to ${plan_budget.value:.2f} (separate from the answer)."
                        )

                    plan_budget.on_value_change(plan_budget_changed)

                @ui.refreshable
                def reference_view() -> None:
                    reference = service.references.get(state["reference"] or "")
                    if reference is None:
                        ui.label(
                            "Stage 8: upload a PNG under Ask to style infographics after it."
                        ).classes("text-sm text-slate-500")
                        return
                    ui.label(f"Visual reference: {reference['name']} ({reference['width']} × {reference['height']})").classes(
                        "font-semibold break-all"
                    )
                    data = base64.b64encode(service.reference_png(reference["id"])).decode("ascii")
                    with ui.row().classes("w-full gap-4 items-start"):
                        ui.image(f"data:image/png;base64,{data}").classes("w-full max-w-xs rounded border")
                        with ui.column().classes("gap-2"):
                            with ui.row().classes("gap-3"):
                                for name, color in reference["palette"].items():
                                    with ui.column().classes("items-center gap-1"):
                                        ui.element("div").classes("swatch").style(f"background:{color}")
                                        ui.label(f"{name} {color}").classes("text-xs")
                            ui.label("Prepared planning samples pixels; it does not identify objects.").classes(
                                "text-xs text-slate-500"
                            )

                            def clear_reference() -> None:
                                state["reference"] = None
                                reference_view.refresh()

                            ui.button("Stop using this reference", icon="close", on_click=clear_reference).props(
                                "flat dense"
                            )

                with ui.column().classes("w-full gap-2").bind_visibility_from(
                    kind, "value", lambda value: value == "infographic"
                ):
                    reference_view()
                    with ui.row().classes("w-full gap-6"):
                        with ui.column().classes("w-full sm:w-64 gap-0"):
                            ui.label("Horizontal focus").classes("text-sm")
                            focus_x = ui.slider(min=0, max=100, value=78).props("label")
                        with ui.column().classes("w-full sm:w-64 gap-0"):
                            ui.label("Vertical focus").classes("text-sm")
                            focus_y = ui.slider(min=0, max=100, value=35).props("label")
                build_button = ui.button("Build files", icon="build").props("color=accent")
                building = ui.spinner(size="lg").classes("hidden")

            # ---------------------------------------------------------- 4. download
            with card("4 · Download", "Publish").classes("step-publish"):

                @ui.refreshable
                def downloads() -> None:
                    bundle = service.bundles.get(state["bundle"] or "")
                    if bundle is None:
                        ui.label("Build files from the selected answer to preview and download them.").classes(
                            "text-slate-500"
                        )
                        return
                    reference = f" · styled from {bundle['reference']}" if bundle["reference"] else ""
                    ui.label(
                        f"{bundle['title']} · {bundle['planning'].upper()} planning{reference} · from answer "
                        f"{bundle['answer_id'][:8]} (sha256 {bundle['answer_sha256'][:12]}…)"
                    ).classes("font-semibold break-all")
                    ui.label(
                        "Preview for human layout and factual review: check it before you share the files."
                    ).classes("text-sm text-amber-700")
                    with ui.element("div").classes("artifact-preview"):
                        if bundle["kind"] == "document":
                            ui.html(
                                f'<iframe class="doc-frame" sandbox="" title="Document preview" '
                                f'srcdoc="{html.escape(service.preview(bundle))}"></iframe>',
                                sanitize=False,
                            )
                        else:
                            svg_id = bundle["artifact_ids"][0]
                            ui.image(f"/publish/artifacts/{svg_id}").props("no-spinner").classes("w-full")
                    for artifact_id in bundle["artifact_ids"]:
                        record = service.artifacts[artifact_id]
                        with ui.row().classes("w-full items-center gap-3 border-t pt-2"):
                            ui.link(
                                f"Download {record['format'].upper()}", f"/publish/artifacts/{artifact_id}"
                            ).props("download").classes("font-semibold")
                            ui.label(
                                f"{record['mime']} · {record['bytes']:,} bytes · {record['planning']} plan · "
                                f"{record['created']}"
                            ).classes("text-sm")
                            ui.label(f"SHA-256 {record['sha256']}").classes("text-xs text-slate-500 break-all")

                downloads()

            with card("Artifact history", "Latest 40 files"):

                @ui.refreshable
                def artifact_history() -> None:
                    rows = [
                        {
                            "title": bundle["title"][:50],
                            "kind": bundle["kind"],
                            "planning": bundle["planning"],
                            "answer": bundle["answer_id"][:8],
                            "created": bundle["created"],
                        }
                        for bundle in reversed(service.bundles.values())
                    ]
                    if not rows:
                        ui.label("No files built yet.").classes("text-slate-500")
                        return
                    ui.table(
                        columns=[{"name": k, "label": k.title(), "field": k, "align": "left"} for k in rows[0]],
                        rows=rows,
                    ).classes("w-full").props("flat bordered dense")

                artifact_history()

        # -------------------------------------------------------------- actions
        def refresh_answer() -> None:
            history_options()
            answer_view.refresh()
            build_source.refresh()
            downloads.refresh()

        def reload_code() -> None:
            status.refresh()
            ui.notify("Reloaded publisher.py.")

        async def start() -> None:
            send.disable()
            try:
                module = publisher()
                if stage_of(module) >= 2:
                    request = module.parse_answer_request(
                        prompt.value or "", model.value, mode.value, budget.value, bool(consent.value)
                    )
                elif mode.value == "live":
                    raise locked(2)
                else:
                    request = {"prompt": (prompt.value or "").strip(), "model": model.value}
                if mode.value == "prepared":
                    label = (
                        module.source_settings(source.value, "prepared")["label"]
                        if stage_of(module) >= 7
                        else NO_SOURCE["label"]
                    )
                    answer = service.prepared_answer(request["prompt"], request["model"], state["files"], label)
                else:
                    if stage_of(module) >= 7:
                        settings = module.source_settings(source.value, "live", bool(mcp_consent.value))
                    elif source.value == "none":
                        settings = NO_SOURCE
                    else:
                        raise locked(7)
                    ui.notify("Running one authorized SDK answer…")
                    answer = await service.live_answer(
                        module,
                        request,
                        state["files"],
                        settings,
                        consent=bool(consent.value),
                        mcp_consent=bool(mcp_consent.value),
                    )
            except failures as exc:
                warn(exc)
                return
            finally:
                send.enable()
                consent.set_value(False)  # consent covers one call
                mcp_consent.set_value(False)
            state["answer"] = answer["id"]
            state["bundle"] = None
            state["files"] = []
            attachments.refresh()
            refresh_answer()
            ui.notify("Answer saved and selected.", type="positive")

        async def build() -> None:
            if not state["answer"]:
                ui.notify("Select an answer first.", type="warning")
                return
            build_button.disable()
            building.classes(remove="hidden")
            try:
                module = need(5 if kind.value == "document" else 6)
                reference = state["reference"] if stage_of(module) >= 8 else None
                bundle = await service.create_artifacts(
                    module,
                    state["answer"],
                    kind.value,
                    conversion.value or "",
                    planning.value,
                    consent=bool(plan_consent.value),
                    budget=plan_budget.value,
                    model=plan_model.value,
                    reference_id=reference,
                    focus=(float(focus_x.value), float(focus_y.value)),
                )
            except failures as exc:
                warn(exc)
                return
            finally:
                build_button.enable()
                building.classes(add="hidden")
                plan_consent.set_value(False)
            state["bundle"] = bundle["id"]
            downloads.refresh()
            artifact_history.refresh()
            ui.notify("Files built. Review the preview before sharing.", type="positive")

        send.on_click(start)
        build_button.on_click(build)
