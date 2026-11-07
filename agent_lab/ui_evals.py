"""Lesson 52 browser lab for synthetic reports, calibration and optional paid trials."""

import asyncio
import json
from typing import Any

import httpx
from fastapi import FastAPI
from nicegui import ui

from agent_lab.learning import check_evidence
from agent_lab.ui_learning import update


def evals_panel(application: FastAPI) -> None:
    state: dict[str, Any] = {"report": None, "calibration": None, "baseline": None,
                             "pairwise": None, "recent": [], "task": None, "run": None}

    with ui.card().classes("course-card w-full p-6 gap-3 evals-lab guide-evidence-context"):
        ui.label("Evaluation and regression lab").classes("text-xl font-bold")
        ui.label("Three fixed Ada support cases. Synthetic scores are authored fixture data; live trials use isolated host effects and SDK receipts.").classes("text-sm")
        with ui.row().classes("w-full gap-3"):
            mode = ui.select({"synthetic": "Synthetic, free", "live": "Live, paid"},
                             value="synthetic", label="Evaluation mode").props("outlined").classes("w-44")
            variant = ui.select({"baseline": "Baseline", "cold-tone": "Cold tone",
                                 "false-refund": "False refund", "fix-findings": "Fix findings"},
                                value="baseline", label="Candidate variant").props("outlined").classes("w-44")
            trials = ui.select({1: "1 per case", 2: "2 per case", 3: "3 per case"},
                               value=3, label="Trials").props("outlined").classes("w-40")
            judge = ui.select({"heuristic": "Keyword heuristic", "model": "Model judge"},
                              value="heuristic", label="Judge").props("outlined").classes("w-48")
        with ui.row().classes("w-full gap-3"):
            budget = ui.number("Paid budget (USD)", value=1.0, min=0.08, max=1.0, step=0.01).props("outlined").classes("w-44")
            consent = ui.checkbox("I authorize this paid evaluation", value=False)
        status = ui.label("Ready")
        ui.label("Synthetic report interpretation makes no model call.").classes("text-sm text-slate-600")

        @ui.refreshable
        def evidence() -> None:
            response = state["report"]
            if not any(state[key] for key in ("report", "calibration", "baseline", "pairwise")):
                ui.label("Run a comparison to inspect case, rubric, business and cost evidence.")
            if response:
                comparison = response["comparison"]
                candidate = response["candidate"]
                ui.label(f"Comparison: {comparison['status']} · mode: {candidate['mode']} · judge: {candidate['judge']}").classes("font-semibold")
                ui.label(f"Model calls: {candidate['modelCalls']} · actual billed estimate: {candidate['actualBilledUsd']} USD · complete: {candidate['complete']}")
                ui.label(f"Run ID: {candidate['id']}").classes("text-sm")
                if review := response.get("review"):
                    ui.label(f"Promotion eligible: {review['eligible']} · reviewed hash: {review['reviewHash']}").classes("text-sm")
                rows = [{"key": f"{item['caseId']}:{item['index']}", "case": item["caseId"], "trial": item["index"],
                         "scope": item["business"]["scope"], "effect": item["business"]["effect"],
                         "money": item["business"]["money"], "reply": item["reply"][:180],
                         "agentCost": item["agentCost"], "judgeCost": item["judgeCost"]}
                        for item in candidate["rows"]]
                with ui.element("div").classes("w-full overflow-x-auto"):
                    ui.table(columns=[{"name": name, "label": name, "field": name}
                                      for name in ("case", "trial", "scope", "effect", "money", "reply", "agentCost", "judgeCost")],
                             rows=rows, row_key="key").classes("min-w-max")
                if comparison["metrics"]:
                    with ui.expansion("24 case and criterion differences").classes("w-full"):
                        with ui.element("div").classes("w-full overflow-x-auto"):
                            ui.table(columns=[{"name": key, "label": key, "field": key}
                                              for key in ("case", "criterion", "baseline", "candidate", "status")],
                                     rows=[{"key": f"{row['caseId']}:{row['criterion']}",
                                            "case": row["caseId"], "criterion": row["criterion"],
                                            "baseline": f"{row['baseline']['passed']}/{row['baseline']['total']}",
                                            "candidate": f"{row['candidate']['passed']}/{row['candidate']['total']}",
                                            "status": row["status"]} for row in comparison["metrics"]],
                                     row_key="key").classes("min-w-max")
                with ui.expansion("Full report and uncertainty").classes("w-full"):
                    ui.code(json.dumps(response, indent=2)[:100000], language="json").classes("w-full")
            if calibration := state["calibration"]:
                summary = calibration["summary"]
                ui.label(f"Heuristic calibration: {summary['decisions']} decisions · κ {summary['kappa']:.3f} · lenient errors {summary['lenientErrors']} · advisory trust {summary['advisoryTrusted']}").classes("font-semibold")
                ui.label("The invented Friday shipment and funds-sent claim are known semantic misses. This does not calibrate the model judge.").classes("text-sm")
                with ui.expansion("All 40 human and heuristic decisions"):
                    ui.code(json.dumps(calibration["rows"], indent=2), language="json")
            if baseline := state["baseline"]:
                ui.label(f"Selected baseline: {baseline['mode']}/{baseline['judge']} · {'present' if baseline['report'] else 'missing'}")
                ui.label(f"Reviewed digest: {baseline['reviewHash']}").classes("text-sm")
            if pair := state["pairwise"]:
                ui.label(f"Pairwise AB: {pair['ab']['winner']} · BA: {pair['ba']['winner']} · consistent: {pair['consistent']}")

        with ui.column().classes("w-full gap-2 guide-evidence-target guide-scroll-target"):
            evidence()

        async def request(method: str, path: str, **kwargs: Any) -> httpx.Response:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application),
                                         base_url="http://evals", timeout=190) as client:
                return await client.request(method, path, **kwargs)

        def options() -> dict[str, Any]:
            return {"mode": mode.value, "variant": variant.value, "trials": trials.value,
                    "judge": judge.value, "consent": bool(consent.value), "budget": budget.value}

        async def operate(path: str, payload: dict[str, Any]) -> dict[str, Any] | None:
            if state["task"] is not None:
                return None
            status.set_text("Running evaluation")
            task = asyncio.create_task(request("POST", path, json=payload))
            state["task"] = task
            try:
                while not task.done():
                    if state["run"] is None:
                        observed = await request("GET", "/api/c52/active")
                        if observed.status_code == 200:
                            state["run"] = observed.json()["runId"]
                    await asyncio.sleep(0.05)
                result = await task
                if result.status_code != 200:
                    status.set_text(f"Evaluation route returned {result.status_code}: {result.json().get('detail')}")
                    return None
                return result.json()
            except asyncio.CancelledError:
                status.set_text("Stopped; partial live report retained when available")
                return None
            finally:
                state["task"] = None
                state["run"] = None

        async def run(target: str) -> None:
            if target == "live" and mode.value == "synthetic":
                mode.value = "live"
                judge.value = "model"
            selected = options()
            if target in {"demo", "synthetic"}:
                selected["mode"], selected["judge"], selected["consent"] = "synthetic", "heuristic", False
            else:
                selected["mode"] = "live"
            result = await operate("/api/c52/demo" if target == "demo" else "/api/c52/run", selected)
            if result is None:
                return
            state["report"] = result
            if result.get("review"):
                state["recent"] = ([result["candidate"]["id"]] + state["recent"])[:2]
                left.value = state["recent"][0]
                if len(state["recent"]) > 1:
                    right.value = state["recent"][1]
            status.set_text("Synthetic check passed" if result.get("experiment_passed") else
                            "Comparison ready: " + result["comparison"]["status"])
            if result.get("experiment_passed"):
                check = check_evidence(52, result, status="completed", mode="offline")
                update(52, check=check.model_dump())
            consent.value = False
            evidence.refresh()

        async def calibrate() -> None:
            result = await operate("/api/c52/calibrate", {})
            if result:
                state["calibration"] = result
                status.set_text("Heuristic calibration ready")
                evidence.refresh()

        async def show_baseline() -> None:
            result = await request("GET", "/api/c52/baseline", params={"mode": mode.value, "judge": judge.value})
            if result.status_code == 200:
                state["baseline"] = result.json()
                evidence.refresh()

        async def stop() -> None:
            if state["run"] is None:
                ui.notify("No evaluation is active", type="warning")
                return
            await request("POST", "/api/c52/stop", json={"runId": state["run"]})

        with ui.row().classes("w-full gap-2 guide-controls-context"):
            ui.button("Run synthetic comparison", on_click=lambda: run("synthetic"), icon="fact_check").classes("guide-controls-target")
            ui.button("Preview free demo", on_click=lambda: run("demo"), icon="visibility")
            ui.button("Run paid evaluation", on_click=lambda: run("live"), icon="paid")
            ui.button("Calibrate heuristic", on_click=calibrate, icon="tune")
            ui.button("Inspect baseline", on_click=show_baseline, icon="inventory")
            ui.button("Stop", on_click=stop, color="secondary")

        with ui.expansion("Promote a retained run after review").classes("w-full"):
            promotion_note = ui.input("Review note (8–200 characters)").props("outlined").classes("w-full")
            confirm = ui.checkbox("I reviewed the eligible report and digest", value=False)

            async def promote() -> None:
                response = state["report"]
                if not response or not response.get("review"):
                    ui.notify("Run and review a retained report first", type="warning")
                    return
                result = await operate("/api/c52/promote", {"runId": response["candidate"]["id"],
                                                       "expectedHash": response["review"]["reviewHash"],
                                                       "confirm": bool(confirm.value), "note": promotion_note.value or ""})
                if result:
                    status.set_text("Scoped baseline promoted")
                    confirm.value = False

            ui.button("Promote reviewed baseline", on_click=promote)

        with ui.expansion("Compare two retained replies AB and BA").classes("w-full"):
            left = ui.input("Left run UUID").props("outlined").classes("w-full")
            right = ui.input("Right run UUID").props("outlined").classes("w-full")
            pair_case = ui.select({"orders": "Orders", "ticket": "Ticket",
                                   "denied-refund": "Denied refund"}, value="orders",
                                  label="Pairwise case").props("outlined")

            async def pairwise() -> None:
                result = await operate("/api/c52/pairwise", {"left": left.value,
                                                       "right": right.value, "caseId": pair_case.value})
                if result:
                    state["pairwise"] = result
                    status.set_text("Local AB/BA preference ready")
                    evidence.refresh()

            ui.button("Compare retained replies", on_click=pairwise)

        def invalidate() -> None:
            state["report"] = None
            consent.value = False
            status.set_text("Inputs changed; run again for current evidence")
            evidence.refresh()

        for control in (mode, variant, trials, judge, budget):
            control.on_value_change(lambda _: invalidate())
