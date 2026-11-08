"""Mobile Lesson 54 direct catalog calls and prepared/native profile comparison."""

import asyncio
import json
from typing import Any

import httpx
from fastapi import FastAPI
from nicegui import ui

from agent_lab.learning import check_evidence
from agent_lab.ui_learning import update


def tool_design_panel(application: FastAPI) -> None:
    state: dict[str, Any] = {"reports": [], "frames": [], "runId": None, "task": None,
                             "check": None, "direct": None}
    with ui.card().classes("course-card w-full p-6 gap-3 tool-design-lab guide-evidence-context"):
        ui.label("Design tools the model uses well").classes("text-xl font-bold")
        ui.label("Both profiles read the same immutable synthetic catalog. Vague lookup is broad; focused tools filter, paginate and fetch stable IDs.").classes("text-sm")
        with ui.row().classes("w-full gap-3 guide-controls-context"):
            mode = ui.select({"prepared": "Prepared, free", "live": "Live, paid"},
                             value="prepared", label="Mode").props("outlined").classes("w-40")
            profile = ui.select({"vague": "Vague lookup", "focused": "Focused catalog"},
                                value="focused", label="Profile").props("outlined").classes("w-40")
            format_choice = ui.select({"concise": "Concise", "detailed": "Detailed"},
                                      value="concise", label="Format").props("outlined").classes("w-40")
        with ui.row().classes("w-full gap-3"):
            tool = ui.select({"catalog_search": "catalog_search", "catalog_get": "catalog_get"},
                             value="catalog_search", label="Direct tool").props("outlined").classes("w-44")
            budget = ui.number("Paid comparison budget (USD)", value=0.5, min=0.5,
                               max=1.0, step=0.01).props("outlined").classes("w-52")
            consent = ui.checkbox("Authorize this bounded paid run")
        raw_input = ui.textarea("Direct JSON arguments", value='{"category":"camping","maxPriceCents":3000,"pageSize":1,"format":"concise"}').props("outlined autogrow").classes("w-full")
        status = ui.label("Select a profile, call a tool, or run the prepared consumer.").classes("text-sm")

        @ui.refreshable
        def evidence() -> None:
            with ui.column().classes("w-full gap-2 guide-evidence-target guide-scroll-target"):
                direct = state["direct"]
                if direct is not None:
                    row = direct.get("receipt", {})
                    ui.label(f"Direct {row.get('tool')}: {'OK' if row.get('ok') else row.get('errorCode')}").classes("font-semibold")
                    ui.label(f"Handler executed: {row.get('executed')} · UTF-8 envelope bytes: {row.get('envelopeBytes')} · handler ms: {row.get('handlerMs')}")
                    ui.code(json.dumps(row.get("payload", {}), indent=2, ensure_ascii=False), language="json").classes("w-full max-w-full")
                    ui.label("Direct calls inspect arguments and effects; they do not award the lesson check.")
                for report in state["reports"]:
                    summary = report["summary"]
                    ui.separator()
                    ui.label(f"{report['mode']} / {report['profile']} / {report['format']}").classes("font-semibold")
                    ui.label(f"Calls {summary['calls']} · successful handlers {summary['successfulExecutions']} · errors {summary['errors']} · UTF-8 envelope bytes {summary['envelopeBytes']}")
                    ui.label(f"Search IDs {', '.join(summary['searchIds']) or 'none'} · detail IDs {', '.join(summary['detailIds']) or 'none'} · model calls {summary['modelCalls']} · SDK cost {summary['reportedSdkUsd'] if summary['reportedSdkUsd'] is not None else 'unknown'}")
                    ui.label(f"Fixture unchanged: {report['beforeSha256'] == report['afterSha256']} · closed: {report['closed']} · interrupted: {report['interrupted']}")
                    with ui.expansion("Actual handler receipts and correlated timeline"):
                        for row in report["receipts"]:
                            ui.label(f"{row['tool']} · {row['callId']} · {row['envelopeBytes']} bytes · {row['returnedIds']}").classes("break-all")
                        ui.code(json.dumps(report["frames"], indent=2, ensure_ascii=False)[:50000], language="json").classes("w-full max-w-full")
                if state["check"]:
                    ui.label(f"Automatic check: {state['check']}").classes("font-semibold")
                ui.label("Bytes measure serialized handler envelopes, not tokens, transport or full model context. Timing excludes model and transport. Prepared pagination is scripted; one native success does not prove general tool quality.").classes("text-xs")

        evidence()

        async def request(method: str, path: str, **kwargs: Any) -> httpx.Response:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application),
                                         base_url="http://catalog", timeout=90) as client:
                return await client.request(method, path, **kwargs)

        async def direct_call() -> None:
            try:
                arguments = json.loads(raw_input.value)
                if not isinstance(arguments, dict):
                    raise ValueError("JSON object required")
            except (ValueError, TypeError):
                status.set_text("Enter a JSON object with fixed tool arguments")
                return
            response = await request("POST", "/api/c54/call", json={"profile": profile.value,
                               "tool": tool.value, "input": arguments})
            if response.status_code != 200:
                status.set_text(f"Direct call rejected: HTTP {response.status_code}")
            else:
                state["direct"] = response.json()
                row = state["direct"]["receipt"]
                status.set_text("Direct handler receipt recorded" if row["ok"] else
                                f"{row['errorCode']}: {row['payload'].get('recovery')}")
            evidence.refresh()

        async def one(selected_profile: str) -> dict[str, Any] | None:
            body = {"mode": mode.value, "profile": selected_profile, "format": format_choice.value,
                    "consent": bool(consent.value), "budget": float(budget.value)}
            state["runId"] = None
            async def stream() -> dict[str, Any] | None:
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application),
                                             base_url="http://catalog", timeout=90) as client:
                    async with client.stream("POST", "/api/c54/run", json=body) as response:
                        if response.status_code != 200:
                            status.set_text(f"Run rejected: HTTP {response.status_code}")
                            return None
                        result = None
                        async for line in response.aiter_lines():
                            if not line.startswith("data: "):
                                continue
                            frame = json.loads(line[6:])
                            state["frames"].append(frame)
                            if frame["kind"] == "start":
                                state["runId"] = frame["runId"]
                            if frame["kind"] == "result":
                                result = frame
                        return result
            task = asyncio.create_task(stream())
            state["task"] = task
            try:
                while not task.done() and state["runId"] is None:
                    active = await request("GET", "/api/c54/active")
                    if active.status_code == 200:
                        state["runId"] = active.json()["runId"]
                    else:
                        await asyncio.sleep(0.02)
                return await task
            finally:
                state["task"] = None

        async def run(compare: bool = False) -> None:
            if state["task"] is not None:
                return
            if mode.value == "live" and (not consent.value or float(budget.value) < (0.5 if compare else 0.25)):
                status.set_text("Fresh paid consent and the reserved comparison budget are required")
                return
            state["reports"] = []
            state["frames"] = []
            state["check"] = None
            evidence.refresh()
            status.set_text("Running the selected catalog consumer")
            try:
                for selected_profile in (("vague", "focused") if compare else (profile.value,)):
                    result = await one(selected_profile)
                    if result is None:
                        break
                    report = result["report"]
                    state["reports"].append(report)
                    state["check"] = result["check"] if selected_profile == "focused" else "observation only"
                    evidence.refresh()
                    if mode.value == "live":
                        cost = report["summary"]["reportedSdkUsd"]
                        if cost is None or cost > 0.25 or report["interrupted"]:
                            status.set_text("Paid comparison stopped after unknown, over-ceiling or interrupted first result")
                            break
                    if result["check"] == "passed" and mode.value == "prepared" and selected_profile == "focused":
                        check = check_evidence(54, {"report": report}, status="completed", mode="offline")
                        update(54, check=check.model_dump())
                else:
                    status.set_text("Comparison complete" if compare else "Consumer run complete")
            finally:
                consent.value = False

        async def stop() -> None:
            if state["runId"] and state["task"] is not None:
                await request("POST", "/api/c54/stop", json={"runId": state["runId"]})
                status.set_text("Stopping owned run; partial evidence needs review")

        with ui.row().classes("w-full gap-2 guide-controls-context"):
            ui.button("Call selected tool", on_click=direct_call, icon="call").classes("guide-controls-target")
            ui.button("Run selected consumer", on_click=lambda: run(False), icon="play_arrow")
            ui.button("Compare profiles", on_click=lambda: run(True), icon="compare_arrows")
            ui.button("Stop", on_click=stop, color="secondary")

        def invalidate() -> None:
            state["reports"] = []
            state["frames"] = []
            state["check"] = None
            consent.value = False
            evidence.refresh()
            status.set_text("Inputs changed; run again for current evidence")

        def profile_changed() -> None:
            tool.set_options({name: name for name in
                              ({"lookup": "lookup"} if profile.value == "vague" else
                               {"catalog_search": "catalog_search", "catalog_get": "catalog_get"})})
            tool.value = "lookup" if profile.value == "vague" else "catalog_search"
            raw_input.value = ('{"q":"camping"}' if profile.value == "vague" else
                               '{"category":"camping","maxPriceCents":3000,"pageSize":1,"format":"' + format_choice.value + '"}')
            invalidate()

        profile.on_value_change(lambda _: profile_changed())
        for control in (mode, format_choice, tool, raw_input, budget):
            control.on_value_change(lambda _: invalidate())
