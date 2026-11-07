"""Lesson 51 browser controls for free host assertions and synthetic replay."""

import asyncio
import json
from typing import Any

import httpx
from fastapi import FastAPI
from nicegui import ui


def offline_panel(application: FastAPI) -> None:
    report: dict[str, Any] = {}
    frames: list[dict[str, Any]] = []
    running: dict[str, asyncio.Task[httpx.Response] | None] = {"task": None}
    current: dict[str, str | None] = {"run": None}

    with ui.card().classes("course-card w-full p-6 gap-3 offline-lab guide-evidence-context"):
        ui.label("Offline host testing lab").classes("text-xl font-bold")
        ui.label("Synthetic SDK-style envelopes exercise real host contracts. Model calls and actual billing remain zero.").classes("text-sm text-slate-600")
        with ui.row().classes("w-full gap-3"):
            group = ui.select({"all": "All 16 assertions", "contracts": "Contracts (6)",
                               "store": "Store (2)", "replay": "Replay (8)"},
                              value="all", label="Case group").props("outlined").classes("w-52")
            scenario = ui.select({name: name.replace("-", " ").title() for name in
                                  ("success", "budget", "api-error", "invalid", "truncated", "malformed-tool")},
                                 value="success", label="Synthetic replay").props("outlined").classes("w-52")
        mutation = ui.checkbox("Mutation challenge: change only the denial policy", value=False)
        status = ui.label("Ready")
        facts = ui.label("Free host suite; no live mode or key required.").classes("text-sm text-slate-600")

        @ui.refreshable
        def evidence() -> None:
            if not report:
                ui.label("Run all 16 unmodified assertions for the lesson check. Partial groups, mutation and replay are separate observations.")
                return
            ui.label("Complete-suite check: " + ("passed" if report.get("experiment_passed") else "needs review")).classes("font-semibold")
            ui.label(f"Action: {report.get('action')} · status: {report.get('status')} · model calls: {report.get('modelCalls', 0)} · actual billed: $0").classes("text-sm")
            if summary := report.get("summary"):
                ui.label(f"Assertions: {summary['passed']}/{summary['total']} passed; {summary['failed']} failed").classes("font-semibold")
            if rows := report.get("assertions"):
                table_rows = [{"case": row["caseId"], "group": row["group"],
                               "passed": "yes" if row["passed"] else "no",
                               "detail": row["detail"]} for row in rows]
                with ui.element("div").classes("w-full overflow-x-auto"):
                    ui.table(columns=[{"name": key, "label": key.title(), "field": key}
                                      for key in ("case", "group", "passed", "detail")],
                             rows=table_rows, row_key="case").classes("min-w-max")
            if report.get("action") == "replay":
                ui.label(f"Host status: {report.get('status')} · simulated cost: {report.get('simulatedCostUsd') if report.get('simulatedCostUsd') is not None else 'unknown'} USD · actual billed: $0").classes("font-semibold")
                ui.label(f"Real scoped handler executions: {report.get('handlerCount')} · fake query closed: {report.get('closed')}")
                with ui.expansion("Captured synthetic fixture and host observations"):
                    ui.code(json.dumps({"fixture": report.get("fixture"),
                                        "handler": report.get("handler"),
                                        "frames": frames[:40]}, indent=2), language="json").classes("w-full")

        with ui.column().classes("w-full gap-2 guide-evidence-target guide-scroll-target"):
            evidence()

        async def request(method: str, path: str, **kwargs: Any) -> httpx.Response:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application),
                                         base_url="http://offline", timeout=30) as client:
                return await client.request(method, path, **kwargs)

        async def operate(path: str, payload: dict[str, Any]) -> None:
            if running["task"] is not None:
                return
            report.clear()
            frames.clear()
            evidence.refresh()
            status.set_text("Running free host code")
            task = asyncio.create_task(request("POST", path, json=payload))
            running["task"] = task
            try:
                while not task.done():
                    if current["run"] is None:
                        observed = await request("GET", "/api/c51/active")
                        if observed.status_code == 200:
                            current["run"] = observed.json()["runId"]
                    await asyncio.sleep(0.02)
                response = await task
                if response.status_code != 200:
                    status.set_text(f"Offline route returned {response.status_code}")
                    return
                for line in response.text.splitlines():
                    if line.startswith("data: "):
                        frames.append(json.loads(line[6:]))
                complete = next((row for row in reversed(frames) if row.get("kind") == "complete"), None)
                if complete is None:
                    status.set_text("Offline stream ended without completion")
                    return
                report.update(complete["report"])
                status.set_text("Passed" if report.get("experiment_passed") else
                                "Expected mutation failure" if payload.get("mutation") else
                                "Observation ready")
                evidence.refresh()
            except asyncio.CancelledError:
                status.set_text("Stopped")
            finally:
                current["run"] = None
                running["task"] = None

        async def run() -> None:
            await operate("/api/c51/run", {"group": group.value, "mutation": bool(mutation.value)})

        async def replay() -> None:
            await operate("/api/c51/replay", {"scenario": scenario.value})

        async def stop() -> None:
            if current["run"] is None:
                ui.notify("No offline operation is active", type="warning")
                return
            await request("POST", "/api/c51/stop", json={"runId": current["run"]})

        async def show_facts() -> None:
            response = await request("GET", "/api/c51/facts")
            if response.status_code == 200:
                facts.set_text(response.json()["scope"] + " · 16 fixed cases · zero model calls")

        with ui.row().classes("w-full gap-2 guide-controls-context"):
            ui.button("Run offline host suite", on_click=run, icon="fact_check").classes("guide-controls-target")
            ui.button("Replay synthetic stream", on_click=replay, icon="play_arrow")
            ui.button("Stop", on_click=stop, color="secondary")
            ui.button("Free facts", on_click=show_facts)

        def invalidate() -> None:
            report.clear()
            status.set_text("Inputs changed; run again for evidence")
            evidence.refresh()

        group.on_value_change(lambda _: invalidate())
        scenario.on_value_change(lambda _: invalidate())
        mutation.on_value_change(lambda _: invalidate())
