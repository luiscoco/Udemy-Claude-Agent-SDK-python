"""Lesson 56 free team reducer and explicitly consented native observation panel."""

import asyncio
import json
from typing import Any

import httpx
from fastapi import FastAPI
from nicegui import ui

from agent_lab.teams_lab import ReplayInput
from agent_lab.ui_learning import update


def teams_panel(application: FastAPI) -> None:
    state: dict[str, Any] = {"generation": 0, "commands": [], "walkthrough": [], "report": None,
                             "check": None, "task": None, "native": None, "frames": [],
                             "runId": None, "available": False, "liveEnabled": False}
    with ui.card().classes("course-card w-full p-6 gap-3 teams-lab guide-evidence-context"):
        ui.label("Team messaging workshop").classes("text-xl font-bold")
        ui.label("Free application simulation: ownership, inbox delivery, evidence and cleanup. Native SDK calls below observe named subagents, not interactive teams.").classes("text-sm")
        status = ui.label("Load the fixed walkthrough or choose one command.")

        async def request(method: str, path: str, **kwargs: Any) -> httpx.Response:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application),
                                         base_url="http://teams", timeout=100) as client:
                return await client.request(method, path, **kwargs)

        @ui.refreshable
        def evidence() -> None:
            with ui.column().classes("w-full gap-2 guide-evidence-target guide-scroll-target"):
                report = state["report"]
                if report:
                    team = report["state"]
                    ui.label(f"Simulated commands: {len(report['commands'])} · closed: {team['closed']} · automatic check: {state['check']}").classes("font-semibold")
                    ui.label("Members: " + ", ".join(f"{row['id']} {row['status']}" for row in team["members"]))
                    ui.label("Tasks: " + ", ".join(f"{row['id']} {row['status']} / {row['owner'] or 'unowned'}" for row in team["tasks"]))
                    ui.label("Messages: " + ", ".join(f"{row['id']} {row['status']}" for row in team["messages"]))
                    with ui.expansion("Ordered receipts and exact evidence"):
                        for row in team["receipts"]:
                            ui.label(f"{row['seq']}. {row['command']['type']} — {row['code']} ({'accepted' if row['accepted'] else 'refused'})").classes("break-all")
                        ui.code(json.dumps(team, indent=2), language="json").classes("w-full max-w-full")
                native = state["native"]
                if native:
                    ui.label(f"Native named-subagent check: {native['check']}").classes("font-semibold")
                    summary = native["report"]
                    ui.label(f"SDK queries: {summary['sdkQueries']} · reported cumulative USD: {summary['reportedSdkUsd']} · SendMessage attempted: {summary['sendMessageAttempted']}")
                    ui.label(f"Message rejected: {summary['messagingRejected']} · answer contains 37: {summary['answerContains37']} · delivery verified: {summary['deliveryVerified']} · worker completion verified: {summary['workerCompletionVerified']}")
                    with ui.expansion("Bounded native SDK frames"):
                        ui.code(json.dumps(state["frames"], indent=2, default=str)[:50000], language="json").classes("w-full max-w-full")
                ui.label("A queued or acknowledged message does not complete a task. Native hook attempts, transport results and answer text do not independently establish worker delivery.").classes("text-xs")

        evidence()

        actor = ui.select({"researcher": "Researcher", "reviewer": "Reviewer"}, value="researcher",
                          label="Actor").props("outlined").classes("w-40")
        recipient = ui.select({"researcher": "Researcher", "reviewer": "Reviewer"}, value="reviewer",
                              label="Recipient").props("outlined").classes("w-40")
        task = ui.select({"research": "Research", "review": "Review"}, value="research",
                         label="Task").props("outlined").classes("w-36")
        message_id = ui.input("Message ID", value="custom-1").props("outlined maxlength=40").classes("w-40")
        body = ui.input("Message body", value="12 + 18 + 7 = 37").props("outlined maxlength=500").classes("w-full max-w-md")
        entry = ui.input("Completion evidence", value="12 + 18 + 7 = 37").props("outlined maxlength=500").classes("w-full max-w-md")

        def controls() -> None:
            busy = state["task"] is not None
            next_button.set_enabled(not busy and len(state["commands"]) < len(state["walkthrough"]) and
                                    state["commands"] == state["walkthrough"][:len(state["commands"])])
            full_button.set_enabled(not busy)
            native_button.set_enabled(not busy and state["available"] and state["liveEnabled"])
            stop_button.set_enabled(busy)

        async def replay(commands: list[dict[str, Any]]) -> None:
            generation = state["generation"] + 1
            state["generation"] = generation
            state["task"] = asyncio.current_task()
            controls()
            try:
                parsed = ReplayInput.model_validate({"commands": commands})
            except ValueError:
                status.set_text("Invalid fixed role, message ID, bounded text or command fields")
                state["task"] = None
                controls()
                return
            try:
                response = await request("POST", "/api/c56/replay", json=parsed.model_dump(mode="json"))
                if generation != state["generation"]:
                    return
                if response.status_code != 200:
                    status.set_text(f"Replay rejected: HTTP {response.status_code}")
                    return
                payload = response.json()
                state.update({"commands": parsed.model_dump(mode="json")["commands"],
                              "report": payload["report"], "check": payload["check"], "native": None})
                status.set_text("Simulated team complete" if payload["check"] == "passed" else
                                "Partial team; inspect the latest receipt")
                update(56, check={"status": payload["check"], "detail": payload["criterion"]})
                evidence.refresh()
            finally:
                if generation == state["generation"]:
                    state["task"] = None
                    controls()

        async def next_step() -> None:
            count = len(state["commands"])
            if state["commands"] != state["walkthrough"][:count] or count >= len(state["walkthrough"]):
                status.set_text("Reset team before continuing the canonical walkthrough")
                return
            await replay([*state["commands"], state["walkthrough"][count]])

        async def custom(kind: str) -> None:
            command: dict[str, Any] = {"type": kind, "actor": actor.value}
            if kind in {"claim", "complete"}:
                command["task"] = task.value
            if kind == "send":
                command.update(to=recipient.value, id=message_id.value, body=body.value)
            if kind == "ack":
                command["id"] = message_id.value
            if kind == "complete":
                command["evidence"] = entry.value
            if kind == "cleanup":
                command["actor"] = "lead"
            await replay([*state["commands"], command])

        def reset() -> None:
            state["generation"] += 1
            if state["task"] is not None:
                state["task"].cancel()
            state.update({"commands": [], "report": None, "check": None, "native": None,
                          "frames": [], "runId": None, "task": None})
            consent.value = False
            status.set_text("Team reset; notes and attempts remain saved.")
            evidence.refresh()
            controls()

        def edited() -> None:
            state["generation"] += 1
            if state["task"] is not None:
                state["task"].cancel()
            state.update({"report": None, "check": None, "native": None, "task": None})
            consent.value = False
            status.set_text("Inputs changed; replay the current history for fresh evidence.")
            evidence.refresh()
            controls()

        for control in (actor, recipient, task, message_id, body, entry):
            control.on_value_change(lambda _: edited())
        with ui.row().classes("w-full gap-2"):
            next_button = ui.button("Next walkthrough step", on_click=next_step).classes("guide-controls-target")
            full_button = ui.button("Run full walkthrough", on_click=lambda: replay(state["walkthrough"]))
            ui.button("Reset team", on_click=reset)
        with ui.row().classes("w-full gap-2"):
            for name in ("claim", "send", "deliver", "ack", "complete", "shutdown", "cleanup"):
                ui.button(name.title(), on_click=lambda kind=name: custom(kind))

        ui.separator()
        ui.label("Optional paid SDK observation").classes("text-lg font-bold")
        ui.label("One named calculator subagent, then an attempted SendMessage. Maximum 8 turns, 90 seconds and a $0.15 SDK stop threshold. This is not an interactive native team.").classes("text-sm")
        budget = ui.number("Native budget reservation (USD)", value=1, min=0.15,
                           max=1, step=0.01).props("outlined").classes("w-52")
        consent = ui.checkbox("Authorize this one paid native observation")

        async def native() -> None:
            if not consent.value or not state["available"] or not state["liveEnabled"]:
                status.set_text("Fresh paid consent, live access and the installed executable are required")
                return
            generation = state["generation"] + 1
            state["generation"] = generation
            state.update({"native": None, "frames": [], "runId": None,
                          "task": asyncio.current_task()})
            controls()
            try:
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application),
                                             base_url="http://teams", timeout=110) as client:
                    async def find_run() -> None:
                        for _ in range(120):
                            response = await client.get("/api/c56/active")
                            if response.status_code == 200:
                                state["runId"] = response.json()["runId"]
                                return
                            await asyncio.sleep(0.1)

                    waiter = asyncio.create_task(find_run())
                    async with client.stream("POST", "/api/c56/live", json={
                            "consent": True, "budget": float(budget.value)}) as response:
                        if response.status_code != 200:
                            status.set_text(f"Native request rejected: HTTP {response.status_code}")
                            return
                        async for line in response.aiter_lines():
                            if generation != state["generation"]:
                                return
                            if not line.startswith("data: "):
                                continue
                            frame = json.loads(line[6:])
                            if frame["kind"] == "start":
                                state["runId"] = frame["runId"]
                            elif frame["kind"] == "frame":
                                state["frames"].append(frame["frame"])
                            elif frame["kind"] == "result":
                                state["native"] = frame
                                status.set_text(f"Named SDK observation: {frame['check']}")
                            elif frame["kind"] == "error":
                                status.set_text(f"Native observation needs review: {frame['error']}")
                            evidence.refresh()
                    await waiter
            except asyncio.CancelledError:
                status.set_text("Stopped native observation; partial evidence needs review")
            finally:
                if generation == state["generation"]:
                    state["task"] = None
                    consent.value = False
                    controls()

        async def stop() -> None:
            state["generation"] += 1
            if state["runId"]:
                await request("POST", "/api/c56/stop", json={"runId": state["runId"]})
            if state["task"] is not None:
                state["task"].cancel()
            state.update({"task": None, "native": None, "runId": None})
            consent.value = False
            status.set_text("Stopped; partial native evidence needs review")
            evidence.refresh()
            controls()

        with ui.row().classes("w-full gap-2"):
            native_button = ui.button("Run native observation", on_click=native)
            stop_button = ui.button("Stop", on_click=stop)
        controls()

        async def load_facts() -> None:
            response = await request("GET", "/api/c56/facts")
            if response.status_code == 200:
                facts = response.json()
                state.update({"walkthrough": facts["walkthrough"], "available": facts["executableAvailable"],
                              "liveEnabled": facts["liveEnabled"]})
                controls()

        asyncio.create_task(load_facts())
