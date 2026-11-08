"""Lesson 53 diagnostic timeline, first findings and guarded native controls."""

import asyncio
import json
import uuid
from typing import Any

import httpx
from fastapi import FastAPI
from nicegui import ui

from agent_lab.debug_lab import DebugInput, criterion
from agent_lab.learning import check_evidence
from agent_lab.ui_learning import update


def debugging_panel(application: FastAPI) -> None:
    state: dict[str, Any] = {"loaded": None, "start": None, "frames": [], "task": None,
                             "runId": None, "selected": None, "check": None}
    with ui.card().classes("course-card w-full p-6 gap-3 debugging-lab guide-evidence-context"):
        ui.label("Debug an agent run").classes("text-xl font-bold")
        ui.label("Seven free authored SDK replays use real owned fixtures, trace collection and saved bundles. Native calls are separately labelled and paid.").classes("text-sm")
        with ui.row().classes("w-full gap-3"):
            mode = ui.select({"prepared": "Prepared, free", "live": "Live, paid"},
                             value="prepared", label="Diagnostic mode").props("outlined").classes("w-44")
            scenario = ui.select({name: name.replace("-", " ").title() for name in
                                  ("success", "denied", "missing", "max-turns", "startup", "api-error", "truncated")},
                                 value="success", label="Fault scenario").props("outlined").classes("w-44")
            turns = ui.select({number: str(number) for number in range(1, 6)},
                              value=4, label="Max turns").props("outlined").classes("w-32")
            capture = ui.checkbox("Capture bounded debug log", value=True)
        with ui.row().classes("w-full gap-3"):
            compare_id = ui.input("Compare saved run UUID (optional)").props("outlined").classes("w-72")
            budget = ui.number("Paid budget (USD)", value=1.0, min=0.10, max=1.0,
                               step=0.01).props("outlined").classes("w-44")
            consent = ui.checkbox("I authorize this paid diagnostic", value=False)
        with ui.row().classes("w-full gap-3"):
            source_filter = ui.select({"all": "All sources", "sdk": "SDK", "hook": "Hook",
                                       "host": "Host", "permission": "Permission", "stderr": "Stderr"},
                                      value="all", label="Trace source").props("outlined").classes("w-40")
            call_filter = ui.input("Filter call ID").props("outlined").classes("w-52")
        status = ui.label("Ready")
        ui.label("Reading a bundle, hints, source or visuals makes no provider call.").classes("text-sm text-slate-600")

        @ui.refreshable
        def evidence() -> None:
            loaded = state["loaded"]
            if not loaded:
                ui.label("Run a prepared replay, then inspect the first causal finding and saved trace.")
                return
            bundle = loaded["bundle"]
            ui.label(f"Saved bundle: {loaded['id']} · {bundle['mode']} · {bundle['scenario']} · check: {state['check']}").classes("font-semibold")
            ui.label(f"SHA-256: {loaded['sha256']} · model calls: {bundle['modelCalls']} · reported SDK cost: {bundle['reportedSdkUsd']}").classes("text-sm")
            ui.label(f"Closed: {bundle['closed']} · interrupted: {bundle['interrupted']} · overflow: {bundle['overflow']}")
            if bundle["findings"]:
                first = bundle["findings"][0]
                ui.label(f"First useful finding: row {first['row']} — {first['code']}").classes("font-semibold")
                for finding in bundle["findings"]:
                    ui.button(f"Row {finding['row']}: {finding['code']} — {finding['nextCheck']}",
                              on_click=lambda row=finding["row"]: focus_row(row)).props("flat no-caps")
            else:
                ui.label("No failure finding; inspect the verified Read and successful terminal.")
            if compare := bundle.get("comparison"):
                ui.label(f"Comparison: {', '.join(compare['changed']) or 'no effective change'} · one variable: {compare['oneVariable']}")
                ui.label(compare["limitation"]).classes("text-sm")
            rows = [row for row in bundle["rows"] if
                    (source_filter.value == "all" or row["kind"] == source_filter.value) and
                    (not call_filter.value or call_filter.value in json.dumps(row["data"]))]
            with ui.element("div").classes("w-full overflow-x-auto"):
                ui.table(columns=[{"name": name, "label": name, "field": name}
                                  for name in ("seq", "milliseconds", "kind", "name", "data")],
                         rows=[{"seq": row["seq"], "milliseconds": row["milliseconds"],
                                "kind": row["kind"], "name": row["name"],
                                "data": json.dumps(row["data"], ensure_ascii=False)[:350]} for row in rows],
                         row_key="seq").props("dense").classes("min-w-max")
            with ui.expansion("Saved redacted bundle and bounded log").classes("w-full"):
                ui.code(json.dumps(bundle, indent=2, ensure_ascii=False)[:100000], language="json").classes("w-full")
            ui.label("Prepared SDK events are authored. Redaction is best effort; review before sharing.").classes("text-xs")

        def focus_row(number: int) -> None:
            source_filter.value = "all"
            call_filter.value = ""
            status.set_text(f"Finding points to trace row {number}; filters cleared")
            evidence.refresh()

        with ui.column().classes("w-full gap-2 guide-evidence-target guide-scroll-target"):
            evidence()

        async def request(method: str, path: str, **kwargs: Any) -> httpx.Response:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application),
                                         base_url="http://debugging", timeout=90) as client:
                return await client.request(method, path, **kwargs)

        def input_value(target: str) -> DebugInput | None:
            try:
                parsed = uuid.UUID(compare_id.value.strip()) if compare_id.value and compare_id.value.strip() else None
                return DebugInput.model_validate({"mode": target, "scenario": scenario.value,
                                                  "maxTurns": turns.value, "captureLog": bool(capture.value),
                                                  "consent": bool(consent.value) if target == "live" else False,
                                                  "budget": float(budget.value), "compareId": parsed})
            except (ValueError, TypeError):
                status.set_text("Enter a valid comparison UUID and bounded numeric budget")
                return None

        async def run(target: str) -> None:
            if state["task"] is not None:
                return
            selected = input_value(target)
            if selected is None:
                return
            state["selected"] = selected
            state["loaded"] = None
            state["start"] = None
            state["runId"] = None
            state["frames"] = []
            evidence.refresh()
            status.set_text("Collecting diagnostic trace")

            async def stream() -> None:
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application),
                                             base_url="http://debugging", timeout=90) as client:
                    async with client.stream("POST", "/api/c53/run", json=selected.model_dump(mode="json")) as response:
                        if response.status_code != 200:
                            await response.aread()
                            status.set_text(f"Diagnostic route returned {response.status_code}: {response.json().get('detail')}")
                            return
                        async for line in response.aiter_lines():
                            if not line.startswith("data: "):
                                continue
                            frame = json.loads(line[6:])
                            state["frames"].append(frame)
                            if frame["kind"] == "start":
                                state["start"] = frame
                                state["runId"] = frame["runId"]
                            elif frame["kind"] == "bundle":
                                state["loaded"] = frame["loaded"]
                                state["check"] = frame["check"]

            task = asyncio.create_task(stream())
            state["task"] = task
            try:
                while not task.done() and state["runId"] is None:
                    active = await request("GET", "/api/c53/active")
                    if active.status_code == 200:
                        state["runId"] = active.json()["runId"]
                    else:
                        await asyncio.sleep(0.02)
                await task
                loaded = state["loaded"]
                if loaded:
                    recovered = await request("GET", f"/api/c53/runs/{loaded['id']}")
                    if recovered.status_code != 200 or recovered.json() != loaded:
                        state["check"] = "needs-review"
                        status.set_text("Persisted bundle did not match the streamed digest and content")
                    else:
                        state["loaded"] = recovered.json()
                        passed = criterion(state["start"]["runId"], selected,
                                           loaded["bundle"], recovered.json())
                        state["check"] = "passed" if passed else "needs-review"
                        status.set_text("Saved diagnostic passed" if passed else "Saved diagnostic needs review")
                        if passed and target == "prepared":
                            check = check_evidence(53, {"start": state["start"], "loaded": recovered.json(),
                                                        "selected": selected.model_dump(mode="json")},
                                                   status="completed", mode="offline")
                            update(53, check=check.model_dump())
                    evidence.refresh()
                else:
                    status.set_text("No complete saved response; use Recover after cleanup")
            except asyncio.CancelledError:
                status.set_text("Stopped; recover the saved bundle after cleanup")
            finally:
                state["task"] = None
                consent.value = False

        async def stop() -> None:
            if not state["runId"] or state["task"] is None:
                ui.notify("No diagnostic is active", type="warning")
                return
            await request("POST", "/api/c53/stop", json={"runId": state["runId"]})

        async def recover() -> None:
            if not state["runId"]:
                status.set_text("Run a diagnostic to record its recovery UUID")
                return
            response = await request("GET", f"/api/c53/runs/{state['runId']}")
            if response.status_code != 200:
                status.set_text("Bundle is not saved yet; retry recovery after cleanup")
                return
            state["loaded"] = response.json()
            state["check"] = "needs-review" if response.json()["bundle"]["interrupted"] else state["check"]
            status.set_text("Recovered the persisted redacted bundle")
            evidence.refresh()

        def download() -> None:
            if state["loaded"]:
                ui.download.content(json.dumps(state["loaded"]["bundle"], indent=2, ensure_ascii=False),
                                    filename=f"lesson-53-{state['loaded']['id']}.json")

        with ui.row().classes("w-full gap-2 guide-controls-context"):
            ui.button("Run prepared replay", on_click=lambda: run("prepared"), icon="play_arrow").classes("guide-controls-target")
            paid_button = ui.button("Run paid diagnostic", on_click=lambda: run("live"), icon="paid")
            paid_button.disable()
            ui.button("Stop", on_click=stop, color="secondary")
            ui.button("Recover saved bundle", on_click=recover, icon="restore")
            ui.button("Download redacted bundle", on_click=download, icon="download")

        def invalidate() -> None:
            state["loaded"] = None
            state["check"] = None
            consent.value = False
            status.set_text("Inputs changed; run again for current evidence")
            evidence.refresh()
            paid_button.set_enabled(mode.value == "live" and bool(consent.value) and
                                    scenario.value in {"success", "denied", "missing", "max-turns"})

        for control in (mode, scenario, turns, capture, compare_id, budget):
            control.on_value_change(lambda _: invalidate())
        consent.on_value_change(lambda _: paid_button.set_enabled(
            mode.value == "live" and bool(consent.value) and
            scenario.value in {"success", "denied", "missing", "max-turns"}))
        for control in (source_filter, call_filter):
            control.on_value_change(lambda _: evidence.refresh())
