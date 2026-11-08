"""Offline Lesson 55 candidate gates and stateless simulated promotion flow."""

import asyncio
import json
from typing import Any

import httpx
from fastapi import FastAPI
from nicegui import ui

from agent_lab.ui_learning import update


def upgrading_panel(application: FastAPI) -> None:
    state: dict[str, Any] = {"generation": 0, "report": None, "stage": "baseline", "task": None,
                             "check": None, "inventory": None}
    with ui.card().classes("course-card w-full p-6 gap-3 upgrading-lab guide-evidence-context"):
        ui.label("Offline simulation · no model calls").classes("text-xl font-bold")
        ui.label("Compare a fixed synthetic candidate with actual installed Python SDK inventory. These gates do not install or deploy anything.")
        scenario = ui.select({name: name.replace("-", " ").title() for name in (
            "compatible", "removed-export", "renamed-result", "permission-drift", "quality-regression",
            "cost-regression", "latency-regression", "missing-evidence", "error-result")},
            value="compatible", label="Synthetic candidate").props("outlined").classes("w-full max-w-md")
        status = ui.label("Run compatibility gates to inspect this candidate.").classes("text-sm")

        async def request(path: str, body: dict[str, Any] | None = None) -> httpx.Response:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application),
                                         base_url="http://upgrading", timeout=30) as client:
                return await client.request("POST" if body is not None else "GET", path, json=body)

        @ui.refreshable
        def evidence() -> None:
            with ui.column().classes("w-full gap-2 guide-evidence-target guide-scroll-target"):
                inventory = state["inventory"]
                if inventory:
                    ui.label(f"Observed Python SDK: {inventory['installedVersion']} · declared {inventory['declaredPin']} · lock {inventory['lockedVersion']}")
                    ui.label(f"Inventory consistent: {inventory['consistent']} · dependency SHA-256: {inventory['dependencySha256']}").classes("break-all text-xs")
                report = state["report"]
                if report:
                    ui.label(f"Candidate: {report['candidate']} · {report['decision']} · simulated state: {state['stage']}").classes("font-semibold")
                    for gate in report["gates"]:
                        with ui.expansion(f"{gate['name']}: {'pass' if gate['passed'] else 'fail'}"):
                            ui.label(gate["explanation"])
                            ui.code(json.dumps(gate["observed"], indent=2), language="json").classes("w-full")
                            ui.label("Recovery: " + gate["recovery"])
                    ui.label(f"Automatic diagnostic: {state['check']}").classes("font-semibold")
                    ui.label("Passing an incompatible fixture means its failure was correctly blocked; it does not make that candidate safe.").classes("text-xs")
                ui.label("Synthetic metrics and authored adapter records are not real candidate benchmarks, native transcripts, billing or deployment evidence.").classes("text-xs")

        evidence()

        def controls() -> None:
            busy = state["task"] is not None
            run_button.set_enabled(not busy)
            stop_button.set_enabled(busy)
            canary_button.set_enabled(not busy and state["stage"] == "checked" and
                                      bool(state["report"] and state["report"]["eligible"]))
            promote_button.set_enabled(not busy and state["stage"] == "canary" and
                                       bool(state["report"] and state["report"]["eligible"]))
            rollback_button.set_enabled(not busy and state["stage"] in {"canary", "promoted"})

        def changed() -> None:
            state["generation"] += 1
            if state["task"] is not None:
                state["task"].cancel()
            state.update({"task": None, "report": None, "stage": "baseline", "check": None})
            status.set_text("Candidate changed; run fresh gates before simulation.")
            evidence.refresh()
            controls()

        async def run_gates() -> None:
            generation = state["generation"] + 1
            state["generation"] = generation
            selected = scenario.value
            state.update({"report": None, "stage": "baseline", "check": None,
                          "task": asyncio.current_task()})
            status.set_text("Assessing fixed offline contracts…")
            controls()
            try:
                response = await request("/api/c55/run", {"scenario": selected})
                if generation != state["generation"] or selected != scenario.value:
                    return
                if response.status_code != 200:
                    status.set_text(f"Offline assessment rejected: HTTP {response.status_code}")
                    return
                payload = response.json()
                state["report"] = payload["report"]
                state["stage"] = "checked"
                state["check"] = payload["check"]
                status.set_text("Compatible fixture eligible" if state["report"]["eligible"] else
                                "Incompatible fixture blocked by concrete gate evidence")
                update(55, check={"status": payload["check"], "detail": payload["criterion"]})
                evidence.refresh()
            except asyncio.CancelledError:
                status.set_text("Stopped; incomplete evidence cannot pass.")
            finally:
                if generation == state["generation"]:
                    state["task"] = None
                    controls()

        async def move(action: str) -> None:
            generation = state["generation"]
            selected = scenario.value
            stage = state["stage"]
            response = await request("/api/c55/transition", {"scenario": selected, "state": stage,
                                                              "action": action})
            if generation != state["generation"] or selected != scenario.value:
                return
            if response.status_code != 200:
                status.set_text(f"Transition blocked: HTTP {response.status_code}")
                return
            result = response.json()
            state["stage"] = result["newState"]
            state["report"] = result["assessment"]
            status.set_text(f"Simulated state: {state['stage']}")
            evidence.refresh()
            controls()

        def stop() -> None:
            state["generation"] += 1
            if state["task"] is not None:
                state["task"].cancel()
            state.update({"task": None, "report": None, "stage": "baseline", "check": None})
            status.set_text("Stopped; incomplete evidence cannot pass.")
            evidence.refresh()
            controls()

        scenario.on_value_change(lambda _: changed())
        with ui.row().classes("w-full gap-2"):
            run_button = ui.button("Run compatibility gates", on_click=run_gates).classes("guide-controls-target")
            canary_button = ui.button("Start simulated canary", on_click=lambda: move("start-canary"))
            promote_button = ui.button("Promote simulation", on_click=lambda: move("promote"))
            rollback_button = ui.button("Roll back simulation", on_click=lambda: move("rollback"))
            stop_button = ui.button("Stop", on_click=stop)
        controls()

        async def load_inventory() -> None:
            response = await request("/api/c55/facts")
            if response.status_code == 200:
                state["inventory"] = response.json()["inventory"]
                evidence.refresh()

        asyncio.create_task(load_inventory())
