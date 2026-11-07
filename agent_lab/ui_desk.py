"""Lesson 50 browser controls for the synthetic scoped support desk."""

import asyncio
from typing import Any

import httpx
from fastapi import FastAPI
from nicegui import ui

from agent_lab.config import Settings


def desk_panel(application: FastAPI, settings: Settings) -> None:
    selected_conversation: dict[str, str | None] = {"id": None}
    pending_data: dict[str, Any] = {}
    active: dict[str, asyncio.Task[httpx.Response] | None] = {"task": None}
    report: dict[str, Any] = {}
    snapshot: dict[str, Any] = {}

    with ui.card().classes("course-card w-full p-6 gap-3 desk-lab guide-evidence-context"):
        ui.label("Synthetic support desk").classes("text-xl font-bold")
        ui.label("Ada and Bo are classroom records. Customer selection is not authentication; refunds only change the owned lesson ledger.").classes("text-sm text-slate-600")
        with ui.row().classes("w-full gap-3"):
            customer = ui.select({"ada": "Ada Example", "bo": "Bo Example"},
                                 value="ada", label="Host customer").props("outlined").classes("w-44")
            mode = ui.select({"local": "Local authored lifecycle", **({"live": "Live Agent SDK"}
                             if settings.enable_live else {})}, value="local", label="Mode").props("outlined").classes("w-48")
            intent = ui.select({"orders": "Orders", "ticket": "Ticket", "refund": "Refund"},
                               value="orders", label="Intent").props("outlined").classes("w-36")
            scenario = ui.select({"normal": "Normal", "missing": "Missing evidence",
                                  "foreign": "Foreign call", "failed": "Failed"},
                                 value="normal", label="Local scenario").props("outlined").classes("w-44")
            scenario.bind_visibility_from(mode, "value", lambda value: value == "local")
        message = ui.textarea("Customer message", value="Please inspect my orders.").props(
            "outlined autogrow maxlength=500").classes("w-full")
        consent = ui.checkbox("Authorize this bounded paid SDK query", value=False)
        consent.bind_visibility_from(mode, "value", lambda value: value == "live")
        conversation = ui.select({}, label="Resume an open conversation or start a new one",
                                 value=None).props("outlined clearable").classes("w-full")
        current = ui.label("New conversation").classes("text-sm text-slate-600")
        status = ui.label("Ready")

        @ui.refreshable
        def evidence() -> None:
            if report:
                ui.label(f"Bounded check: {'passed' if report.get('experiment_passed') else 'needs review'}").classes("font-semibold")
                ui.label(f"Source: {report.get('source')} · mode: {report.get('mode')}").classes("text-sm")
                if report.get("calls"):
                    rows = [{"tool": row.get("tool"), "call": row.get("id")}
                            for row in report["calls"]]
                    ui.table(columns=[{"name": key, "label": key.title(), "field": key}
                                      for key in ("tool", "call")], rows=rows, row_key="call")
            if snapshot:
                for key in ("orders", "tickets", "refunds", "audit"):
                    ui.label(f"{key.title()}: {len(snapshot.get(key, []))}").classes("text-sm")
                if snapshot.get("refunds"):
                    ui.label("Refund calls: " + ", ".join(row["call"] for row in snapshot["refunds"]))

        with ui.column().classes("w-full gap-3 guide-evidence-target guide-scroll-target"):
            evidence()

        async def request(method: str, path: str, **kwargs: Any) -> httpx.Response:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application),
                                         base_url="http://desk", timeout=185) as client:
                return await client.request(method, path, **kwargs)

        async def refresh() -> None:
            response = await request("GET", "/api/c50/state", params={"customer": customer.value})
            if response.status_code != 200:
                return
            snapshot.clear()
            snapshot.update(response.json())
            options = {row["id"]: row["id"] for row in snapshot["conversations"]
                       if row["status"] == "open" and row["mode"] == mode.value}
            conversation.set_options(options)
            if selected_conversation["id"] in options:
                conversation.set_value(selected_conversation["id"])
            else:
                selected_conversation["id"] = None
                conversation.set_value(None)
            evidence.refresh()

        async def settle(choice: str) -> None:
            if not pending_data:
                return
            body = {key: pending_data[key] for key in
                    ("runId", "conversationId", "callId", "approvalToken")}
            response = await request("POST", "/api/c50/approve", json=body | {"choice": choice})
            if response.status_code != 200:
                ui.notify("Approval was already settled or did not match", type="warning")
            pending_data.clear()
            approval_panel.set_visibility(False)

        with ui.column().classes("w-full bg-amber-50 p-3 rounded") as approval_panel:
            proposal = ui.label("Synthetic proposal pending")
            with ui.row():
                ui.button("Approve", on_click=lambda: settle("approve"))
                ui.button("Deny", on_click=lambda: settle("deny"), color="negative")
        approval_panel.set_visibility(False)

        async def send() -> None:
            if active["task"] is not None:
                return
            if mode.value == "live" and not consent.value:
                ui.notify("Confirm this bounded paid query", type="warning")
                return
            body: dict[str, Any] = {"customer": customer.value, "mode": mode.value,
                                    "intent": intent.value, "message": message.value,
                                    "scenario": scenario.value if mode.value == "local" else "normal",
                                    "consent": bool(consent.value)}
            if conversation.value:
                body["conversationId"] = conversation.value
            consent.set_value(False)
            status.set_text("Running support query")
            active["task"] = asyncio.create_task(request("POST", "/api/c50/chat", json=body))
            try:
                while active["task"] is not None and not active["task"].done():
                    if intent.value == "refund" and not pending_data:
                        pending = await request("GET", "/api/c50/pending",
                                                params={"customer": customer.value})
                        if pending.status_code == 200:
                            pending_data.update(pending.json())
                            proposal.set_text(f"{pending_data['orderId']}: {pending_data['amountCents']} synthetic cents")
                            approval_panel.set_visibility(True)
                    await asyncio.sleep(0.1)
                task = active["task"]
                assert task is not None
                result = await task
                if result.status_code != 200:
                    ui.notify(f"Support route returned {result.status_code}", type="negative")
                    status.set_text("Needs review")
                    return
                report.clear()
                report.update(result.json())
                selected_conversation["id"] = report.get("conversation")
                current.set_text("Conversation: " + str(selected_conversation["id"]))
                status.set_text("Passed" if report.get("experiment_passed") else "Needs review")
                await refresh()
            except asyncio.CancelledError:
                status.set_text("Stopped")
            finally:
                active["task"] = None
                pending_data.clear()
                approval_panel.set_visibility(False)

        async def close() -> None:
            identifier = conversation.value or selected_conversation["id"]
            if not identifier:
                ui.notify("Select an open conversation", type="warning")
                return
            if mode.value == "live" and not consent.value:
                ui.notify("Confirm this bounded paid CRM close", type="warning")
                return
            response = await request("POST", "/api/c50/close", json={
                "mode": mode.value, "consent": bool(consent.value),
                "customer": customer.value, "conversationId": identifier})
            consent.set_value(False)
            if response.status_code == 200:
                report.clear()
                report.update(response.json())
                status.set_text("CRM closed" if report.get("experiment_passed") else "Needs review")
                await refresh()
            else:
                ui.notify(f"CRM route returned {response.status_code}", type="negative")

        async def evaluate() -> None:
            response = await request("POST", "/api/c50/evals", json={})
            if response.status_code == 200:
                report.clear()
                report.update(response.json())
                status.set_text("Local evaluations passed" if report.get("experiment_passed") else "Needs review")
                evidence.refresh()

        async def stop() -> None:
            if pending_data:
                await request("POST", "/api/c50/stop", json={"runId": pending_data["runId"]})
            elif active["task"] is not None:
                active["task"].cancel()

        async def reset() -> None:
            response = await request("POST", "/api/c50/reset", json={"confirm": True})
            if response.status_code == 200:
                selected_conversation["id"] = None
                report.clear()
                current.set_text("New conversation")
                status.set_text("Synthetic desk reset")
                await refresh()

        def new_conversation() -> None:
            selected_conversation["id"] = None
            conversation.set_value(None)
            current.set_text("New conversation")

        with ui.row().classes("w-full gap-2 guide-controls-context"):
            ui.button("Send support request", on_click=send, icon="send").classes("guide-controls-target")
            ui.button("Close to CRM", on_click=close, icon="done")
            ui.button("Local evaluations", on_click=evaluate, icon="fact_check")
            ui.button("Stop", on_click=stop, color="secondary")
            ui.button("New conversation", on_click=new_conversation)
            ui.button("Inspect", on_click=refresh)
            ui.button("Reset synthetic desk", on_click=reset, color="warning")
        def selection_changed() -> None:
            new_conversation()
            consent.set_value(False)
            asyncio.create_task(refresh())

        customer.on_value_change(lambda _: selection_changed())
        mode.on_value_change(lambda _: selection_changed())
        intent.on_value_change(lambda _: consent.set_value(False))
        message.on_value_change(lambda _: consent.set_value(False))
        conversation.on_value_change(lambda event: selected_conversation.update(id=event.value))
        ui.timer(0.1, refresh, once=True)
