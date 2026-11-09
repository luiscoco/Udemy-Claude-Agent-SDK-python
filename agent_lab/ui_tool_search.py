"""Lesson 58 catalog and native discovery controls."""

import json
from typing import Any

import httpx
from fastapi import FastAPI
from nicegui import ui

from agent_lab.ui_learning import update


def tool_search_panel(application: FastAPI) -> None:
    state: dict[str, Any] = {"generation": 0, "result": None, "busy": False}
    with ui.card().classes("course-card w-full max-w-full p-6 gap-3 guide-evidence-context"):
        ui.label("Tool search across 64 tools").classes("text-xl font-bold")
        ui.label("Compare a local search and character estimate with native ToolSearch and silent SDK context usage.")
        metadata = ui.select({"clear": "Clear refund metadata", "vague": "Vague billing operation"},
                             value="clear", label="Metadata").classes("w-full max-w-sm")
        mode = ui.select({"true": "Deferred", "false": "Eager", "auto": "Auto",
                          "auto:1": "Auto 1%"}, value="true", label="Search mode").classes("w-full max-w-sm")
        auto_percent = ui.number("Auto threshold percent", value=10, min=0, max=100,
                                 step=1).classes("w-full max-w-sm")
        pin = ui.checkbox("Always load the refund tool")
        query = ui.input("Query", value="refund duplicate charge").classes("w-full max-w-lg")
        budget = ui.number("Native budget USD", value=1, min=0.15, max=1,
                           step=0.01).classes("w-full max-w-sm")
        local_consent = ui.checkbox("Authorize one paid native discovery")
        measure_consent = ui.checkbox("Authorize one native silent context measurement")
        status = ui.label("Choose controls and run a local check.")

        @ui.refreshable
        def evidence() -> None:
            with ui.column().classes("w-full max-w-full guide-evidence-target guide-scroll-target"):
                if state["result"] is not None:
                    ui.code(json.dumps(state["result"], indent=2, default=str)[:90000],
                            language="json").classes("w-full max-w-full overflow-auto")
                else:
                    ui.label("Run a local search, plan or refund to inspect evidence here.")

        evidence()

        def edited() -> None:
            if state["busy"]:
                return
            state["generation"] += 1
            state["result"] = None
            local_consent.value = False
            measure_consent.value = False
            status.set_text("Controls changed; previous check invalidated.")
            evidence.refresh()

        for control in (metadata, mode, auto_percent, pin, query, budget):
            control.on_value_change(lambda _: edited())

        async def post(path: str, payload: dict[str, Any]) -> Any:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application),
                                         base_url="http://tool-search", timeout=105) as client:
                response = await client.post(path, json=payload)
                return response.json() if response.status_code == 200 else {"http": response.status_code,
                                                                               "detail": response.json()}

        async def stop() -> None:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application),
                                         base_url="http://tool-search", timeout=10) as client:
                active = await client.get("/api/c58/active")
                if active.status_code != 200:
                    status.set_text("No active native operation")
                    return
                reply = await client.post("/api/c58/stop", json=active.json())
                status.set_text("Stop requested" if reply.status_code == 202 else "Stop request was not accepted")

        def config() -> dict[str, Any]:
            search_mode = f"auto:{int(auto_percent.value)}" if mode.value == "auto" else mode.value
            return {"metadata": metadata.value, "searchMode": search_mode,
                    "alwaysLoad": pin.value}

        async def action(kind: str) -> None:
            if state["busy"]:
                return
            state["busy"] = True
            stop_button.set_enabled(True)
            generation = state["generation"]
            try:
                payload = config()
                if kind == "search":
                    payload["query"] = query.value
                elif kind == "plan":
                    payload["contextWindow"] = 200000
                elif kind == "run":
                    payload.update({"mode": "prepared", "query": query.value})
                elif kind == "native":
                    payload.update({"mode": "live", "query": query.value,
                                    "consent": local_consent.value, "budget": float(budget.value)})
                else:
                    payload["consent"] = measure_consent.value
                route = "run" if kind == "native" else "measure" if kind == "measure" else kind
                report = await post(f"/api/c58/{route}", payload)
                if state["generation"] != generation:
                    return
                state["result"] = report
                status.set_text(f"{kind}: {report.get('check', report.get('kind', 'ready'))}")
                if kind in {"run", "native"} and report.get("check") == "pass":
                    update(58, check={"status": "passed", "detail": "Owned refund ledger and discovery evidence verified."})
                evidence.refresh()
            except Exception as exc:
                status.set_text(f"{kind} failed: {type(exc).__name__}")
            finally:
                state["busy"] = False
                stop_button.set_enabled(False)

        with ui.row().classes("w-full flex-wrap gap-2 guide-controls-target"):
            ui.button("Local search", on_click=lambda: action("search"))
            ui.button("Estimate load", on_click=lambda: action("plan"))
            ui.button("Prepared refund", on_click=lambda: action("run"))
            ui.button("Native discovery", on_click=lambda: action("native"))
            ui.button("Measure native context", on_click=lambda: action("measure"))
            stop_button = ui.button("Stop active native run", on_click=stop)
            stop_button.set_enabled(False)
        ui.label("Local scores and character estimates are not SDK ranking or billed tokens. Silent measurement sends zero model input turns; control traffic may still occur.").classes("text-xs")
