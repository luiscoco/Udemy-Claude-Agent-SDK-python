"""Lesson 57 owned Git workshop panel."""

import asyncio
import json
from typing import Any

import httpx
from fastapi import FastAPI
from nicegui import ui

from agent_lab.ui_learning import update


def worktrees_panel(application: FastAPI) -> None:
    state: dict[str, Any] = {"generation": 0, "task": None, "runId": None,
                             "report": None, "events": [], "check": None, "liveEnabled": False}
    with ui.card().classes("course-card w-full max-w-full p-6 gap-3 worktrees-lab guide-evidence-context"):
        ui.label("Parallel worktrees workshop").classes("text-xl font-bold")
        ui.label("Two workers edit isolated checkouts. The host tests, commits and integrates their exact files. Worktrees share Git state and do not provide an OS sandbox.").classes("text-sm")
        status = ui.label("Choose Independent or Conflict, then run the local Git workshop.")

        async def request(method: str, path: str, **kwargs: Any) -> httpx.Response:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application),
                                         base_url="http://worktrees", timeout=110) as client:
                return await client.request(method, path, **kwargs)

        @ui.refreshable
        def evidence() -> None:
            report = state["report"]
            with ui.column().classes("w-full max-w-full gap-2 guide-evidence-target guide-scroll-target"):
                if report:
                    ui.label(f"Run {report['runId']} · {report['mode']} · {report['scenario']} · {report['status']} · {state['check']}").classes("font-semibold break-all")
                    ui.label(f"Base commit: {report.get('baseSHA', 'unavailable')}").classes("break-all")
                    for worker in report["workers"]:
                        ui.label(f"{worker['name']}: {worker.get('branch')} · original {worker.get('workerSHA', 'none')} · test exit {worker.get('test', {}).get('exit', 'none')}").classes("break-all")
                    for pick in report["integration"]:
                        ui.label(f"Integrated {pick['worker']}: {pick['integratedSHA']} · parent {pick['parentSHA']}").classes("break-all")
                    if report.get("conflict"):
                        ui.label(f"Conflict: {report['conflict']['unmerged']} · pick aborted: {report['conflict']['aborted']} · original worktrees retained").classes("text-orange-700")
                    ui.label(f"Combined tests: {len(report['combinedTests'])} · clean removals: {len(report['cleanup'])} · observed worktrees: {report.get('worktreeCount', 'unknown')}")
                    for error in report["errors"]:
                        ui.label(error).classes("text-red-700 break-all")
                    with ui.expansion("Ordered events and retained evidence"):
                        ui.code(json.dumps(report, indent=2)[:90000], language="json").classes("w-full max-w-full overflow-auto")
                elif state["events"]:
                    for row in state["events"][-12:]:
                        ui.label(f"{row['seq']}. {row['kind']} {row.get('name', '')}").classes("break-all")
                ui.label("A successful SDK response is only worker evidence; exact source bytes, Node assertions, Git commits and clean integration decide the check. SDK budget thresholds are not prepaid spending caps.").classes("text-xs")

        evidence()
        mode = ui.select({"prepared": "Prepared local Git", "live": "Live two SDK workers"},
                         value="prepared", label="Mode").props("outlined").classes("w-full max-w-sm")
        scenario = ui.select({"independent": "Independent integration", "conflict": "Deliberate conflict"},
                             value="independent", label="Scenario").props("outlined").classes("w-full max-w-sm")
        budget = ui.number("Live budget reservation (USD)", value=1, min=0.16, max=1,
                           step=0.01).props("outlined").classes("w-full max-w-sm")
        consent = ui.checkbox("Authorize this one paid two-worker run")

        def controls() -> None:
            busy = state["task"] is not None
            for field in (mode, scenario, budget, consent):
                field.set_enabled(not busy)
            run_button.set_enabled(not busy)
            stop_button.set_enabled(busy)
            recover_button.set_enabled(not busy and state["runId"] is not None)

        def edited() -> None:
            if state["task"] is not None:
                return
            state["generation"] += 1
            state.update({"report": None, "check": None, "events": [], "runId": None})
            consent.value = False
            status.set_text("Configuration changed; prior check invalidated. Run again for fresh evidence.")
            evidence.refresh()
            controls()

        for field in (mode, scenario, budget):
            field.on_value_change(lambda _: edited())

        async def recover(award: bool = False) -> None:
            run_id = state["runId"]
            if run_id is None:
                return
            response = await request("GET", f"/api/c57/runs/{run_id}", headers={"Cache-Control": "no-store"})
            if response.status_code != 200:
                status.set_text(f"Retained report not yet available: HTTP {response.status_code}")
                return
            payload = response.json()
            report = payload["report"]
            if report["runId"] != run_id:
                status.set_text("Report identity mismatch")
                return
            state["report"] = report
            state["check"] = report["check"] if award else "needs-review"
            status.set_text("Owned report verified" if award else "Retained evidence recovered; no new check awarded")
            if award:
                update(57, check={"status": report["check"], "detail": "Owned Git commits, host tests, serial picks and clean removal verified."})
            evidence.refresh()

        async def run() -> None:
            if mode.value == "live" and (not state["liveEnabled"] or not consent.value):
                status.set_text("Live access and fresh paid consent are required")
                return
            generation = state["generation"] + 1
            state["generation"] = generation
            state.update({"task": asyncio.current_task(), "runId": None,
                          "report": None, "check": None, "events": []})
            controls()
            streamed: dict[str, Any] | None = None
            async def find_active() -> None:
                for _ in range(120):
                    if generation != state["generation"]:
                        return
                    response = await request("GET", "/api/c57/active")
                    if response.status_code == 200:
                        state["runId"] = response.json()["runId"]
                        return
                    await asyncio.sleep(0.1)

            finder = asyncio.create_task(find_active())
            try:
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application),
                                             base_url="http://worktrees", timeout=110) as client:
                    async with client.stream("POST", "/api/c57/run", json={
                        "mode": mode.value, "scenario": scenario.value,
                        "consent": bool(consent.value), "budget": float(budget.value)}) as response:
                        if response.status_code != 200:
                            status.set_text(f"Run rejected: HTTP {response.status_code}")
                            return
                        async for line in response.aiter_lines():
                            if generation != state["generation"]:
                                return
                            if not line.startswith("data: "):
                                continue
                            frame = json.loads(line[6:])
                            if frame["kind"] == "start":
                                state["runId"] = frame["runId"]
                                status.set_text(f"Running owned {frame['scenario']} workshop")
                            elif frame["kind"] == "progress":
                                state["events"].append(frame["event"])
                            elif frame["kind"] == "result":
                                streamed = frame["report"]
                            elif frame["kind"] == "error":
                                status.set_text(f"Run needs review: {frame['error']}")
                            evidence.refresh()
                if streamed is not None and state["runId"] == streamed["runId"]:
                    retained = await request("GET", f"/api/c57/runs/{state['runId']}",
                                             headers={"Cache-Control": "no-store"})
                    if retained.status_code == 200 and retained.json()["report"] == streamed:
                        await recover(award=True)
                    else:
                        status.set_text("Stream and owned report differ; needs review")
            except asyncio.CancelledError:
                status.set_text("Stopped; recover retained partial evidence when ready")
            finally:
                finder.cancel()
                if generation == state["generation"]:
                    state["task"] = None
                    consent.value = False
                    controls()

        async def stop() -> None:
            run_id = state["runId"]
            state["generation"] += 1
            if run_id:
                await request("POST", "/api/c57/stop", json={"runId": run_id})
            if state["task"] is not None:
                state["task"].cancel()
            state.update({"task": None, "report": None, "check": "needs-review"})
            consent.value = False
            status.set_text("Stop requested; wait for owned report, then Recover")
            evidence.refresh()
            controls()

        with ui.row().classes("w-full max-w-full gap-2 flex-wrap guide-controls-target"):
            run_button = ui.button("Run worktree lab", on_click=run)
            stop_button = ui.button("Stop", on_click=stop)
            recover_button = ui.button("Recover retained report", on_click=lambda: recover(False))
        controls()

        async def load_facts() -> None:
            response = await request("GET", "/api/c57/facts")
            if response.status_code == 200:
                state["liveEnabled"] = response.json()["liveEnabled"]

        asyncio.create_task(load_facts())
