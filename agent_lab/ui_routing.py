"""Lesson 59 fixed routing controls and visible provenance."""

import json
from typing import Any

import httpx
from fastapi import FastAPI
from nicegui import ui

from agent_lab.routing_lab import STRATEGIES, TASKS
from agent_lab.ui_learning import update


def routing_panel(application: FastAPI) -> None:
    state: dict[str, Any] = {"generation": 0, "busy": False, "report": None}
    with ui.card().classes("course-card w-full max-w-full p-6 gap-3 guide-evidence-context"):
        ui.label("Model routing: thirteen fixed tasks").classes("text-xl font-bold")
        ui.label("Compare independently graded answers and cost per correct answer. Prepared costs and durations are authored teaching fixtures.")
        mode = ui.select({"prepared": "Prepared teaching fixtures", "live": "Native SDK observation"},
                         value="prepared", label="Mode").classes("w-full max-w-sm")
        strategy = ui.select({name: name for name in STRATEGIES}, value="rules",
                             label="Strategy").classes("w-full max-w-sm")
        ui.label("Selected tasks")
        tasks = {task.id: ui.checkbox(f"{task.id} · intended {task.tier}", value=task.id == "invoice")
                 for task in TASKS}
        budget = ui.number("Native budget USD", value=1, min=.1, max=1, step=.1).classes("w-full max-w-sm")
        consent = ui.checkbox("Authorize this bounded paid native run")
        special_consent = ui.checkbox("Authorize one paid expert or alias observation")
        model_consent = ui.checkbox("Authorize one silent native model-list control")
        status = ui.label("Choose a task and run one strategy.")

        @ui.refreshable
        def evidence() -> None:
            report = state["report"]
            with ui.column().classes("w-full max-w-full guide-evidence-target guide-scroll-target"):
                if report is None:
                    ui.label("No current routing report.")
                    return
                if "metrics" in report:
                    for name, metric in report["metrics"].items():
                        ui.label(f"{name}: {metric['accepted']}/{metric['tasks']} accepted; cost per correct {metric['costPerCorrectUsd']} USD; classifier cost {metric['classifierCostUsd']} USD")
                ui.code(json.dumps(report, indent=2, default=str)[:90000], language="json").classes("w-full max-w-full overflow-auto")

        evidence()

        def edited() -> None:
            if state["busy"]:
                return
            state["generation"] += 1
            state["report"] = None
            consent.value = False
            special_consent.value = False
            model_consent.value = False
            status.set_text("Controls changed; previous check invalidated.")
            evidence.refresh()

        for control in (mode, strategy, budget, *tasks.values()):
            control.on_value_change(lambda _: edited())

        def select_all() -> None:
            if state["busy"] or mode.value != "prepared":
                return
            for checkbox in tasks.values():
                checkbox.value = True
            edited()

        def select_invoice() -> None:
            if state["busy"]:
                return
            for task_id, checkbox in tasks.items():
                checkbox.value = task_id == "invoice"
            edited()

        async def run(compare: bool) -> None:
            if state["busy"]:
                return
            selected = [task_id for task_id, checkbox in tasks.items() if checkbox.value]
            if not selected:
                status.set_text("Select at least one fixed task.")
                return
            if mode.value == "live" and (compare or len(selected) > 3):
                status.set_text("Native runs allow one strategy and at most three tasks.")
                return
            state["busy"] = True
            stop_button.set_enabled(mode.value == "live")
            generation = state["generation"]
            payload = {"mode": mode.value, "strategies": list(STRATEGIES) if compare else [strategy.value],
                       "taskIds": selected, "consent": bool(consent.value), "budget": float(budget.value)}
            try:
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application),
                                             base_url="http://routing", timeout=255) as client:
                    response = await client.post("/api/c59/run", json=payload)
                report = response.json()
                if state["generation"] != generation:
                    return
                state["report"] = report
                check = report.get("check", {})
                status.set_text(f"{response.status_code}: {check.get('status', report.get('detail', 'ready'))}")
                if check.get("status") == "pass":
                    update(59, check={"status": "passed", "detail": check["criterion"]})
                evidence.refresh()
            except Exception as exc:
                status.set_text(f"Routing failed: {type(exc).__name__}")
            finally:
                state["busy"] = False
                stop_button.set_enabled(False)

        async def stop() -> None:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application),
                                         base_url="http://routing", timeout=10) as client:
                active = await client.get("/api/c59/active")
                if active.status_code == 200:
                    response = await client.post("/api/c59/stop", json=active.json())
                    status.set_text("Stop requested" if response.status_code == 202 else "Stop was not accepted")
                else:
                    status.set_text("No active native run")

        async def special(kind: str) -> None:
            if state["busy"]:
                return
            state["busy"] = True
            generation = state["generation"]
            payload = {"mode": mode.value, "consent": bool(special_consent.value),
                       "budget": max(.3, float(budget.value))}
            try:
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application),
                                             base_url="http://routing", timeout=255) as client:
                    response = await client.post(f"/api/c59/{kind}", json=payload)
                if state["generation"] != generation:
                    return
                state["report"] = response.json()
                status.set_text(f"{kind}: {state['report'].get('status', response.status_code)}; separate observation only")
                evidence.refresh()
            except Exception as exc:
                status.set_text(f"{kind} failed: {type(exc).__name__}")
            finally:
                state["busy"] = False
                special_consent.value = False

        async def models() -> None:
            if state["busy"]:
                return
            state["busy"] = True
            generation = state["generation"]
            path = "/api/c59/models?native=1&consent=1" if model_consent.value else "/api/c59/models"
            try:
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application),
                                             base_url="http://routing", timeout=25) as client:
                    response = await client.get(path)
                if state["generation"] != generation:
                    return
                state["report"] = response.json()
                status.set_text(f"Model list: {state['report'].get('source', response.status_code)}")
                evidence.refresh()
            except Exception as exc:
                status.set_text(f"Model control failed: {type(exc).__name__}")
            finally:
                state["busy"] = False
                model_consent.value = False

        with ui.row().classes("w-full flex-wrap gap-2 guide-controls-target"):
            ui.button("Select all tasks", on_click=select_all).bind_enabled_from(mode, "value", lambda value: value == "prepared")
            ui.button("Select invoice only", on_click=select_invoice)
            ui.button("Run selected strategy", on_click=lambda: run(False))
            ui.button("Compare all prepared strategies", on_click=lambda: run(True)).bind_enabled_from(mode, "value", lambda value: value == "prepared")
            ui.button("Configured / native models", on_click=models)
            ui.button("Observe expert delegation", on_click=lambda: special("delegate"))
            ui.button("Observe alias resolution", on_click=lambda: special("resolution"))
            stop_button = ui.button("Stop active native run", on_click=stop)
            stop_button.set_enabled(False)
        ui.label("Native SDK cost is a reported query-pipeline estimate, not a provider invoice. Configured model IDs and teaching rates are not account entitlement or live prices.").classes("text-xs")
