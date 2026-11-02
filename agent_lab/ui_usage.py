"""Usage observations and an explicitly operated session meter."""

from typing import Any

from nicegui import ui

from agent_lab.models import LessonError, lesson_request
from agent_lab.output import render_value
from agent_lab.runtime import BusyError
from agent_lab.usage_sessions import UsageSession, UsageSessions


def usage_cards(experiment: dict) -> None:
    final = experiment.get("final", {})
    usage = final.get("usage", {})
    with ui.column().classes("w-full gap-3 usage-accounting"):
        ui.label("Final usage and reported cost").classes("text-lg font-bold")
        for key, label, source in (
            ("total_cost_usd", "Final reported cost (USD)", final),
            ("input_tokens", "Final input tokens", usage),
            ("output_tokens", "Final output tokens", usage),
        ):
            value = source.get(key)
            ui.label(f"{label}: {'Unknown' if value is None else value}").classes(
                "w-full break-words font-semibold"
            )
        ui.label("Terminal subtype: " + str(final.get("subtype") or "Unknown"))
        ui.label(
            "Message usage is intermediate; per-model aggregates and final totals are separate reports. Unknown is not zero. Budgets do not predict exact prices."
        ).classes("w-full text-slate-600")
        render_value(experiment.get("messages", []), "Assistant messages grouped by message ID")
        render_value(final.get("model_usage"), "Final per-model usage (SDK model_usage)")
        render_value(experiment.get("meter", {}), "Cumulative cost meter")


def usage_session_controls(registry: UsageSessions, client: Any, read_request: Any) -> None:
    session: UsageSession | None = None
    busy = False
    with ui.column().classes("w-full gap-3 usage-session"):
        ui.label("Session meter (completed results)").classes("text-lg font-bold")
        ui.label(
            "Open a separate connection, send up to four messages, inspect usage or context, then End. This does not complete the automatic exercise check. Live sends each require authorization."
        ).classes("text-sm text-slate-600")
        prompt = (
            ui.textarea("Meter message", value="Explain cumulative usage briefly.")
            .props("outlined rows=3 maxlength=10000")
            .classes("w-full")
        )
        consent = ui.checkbox(
            "I authorize this paid session/message using the selected limits.", value=False
        )
        feedback = ui.label("No usage session yet.").classes("w-full break-words")

        async def action(name: str) -> None:
            nonlocal session, busy
            if busy:
                return
            busy = True
            try:
                if name == "open":
                    if session and not session.closed:
                        raise LessonError("End the current usage session first.")
                    request = lesson_request(15, read_request())
                    if request.mode == "live" and not consent.value:
                        raise PermissionError("Authorize the paid usage session first.")
                    session = await registry.open(request)
                    result = session.snapshot()
                else:
                    if session is None:
                        raise LessonError("Open a usage session first.")
                    if name == "send":
                        if session.request.mode == "live" and not consent.value:
                            raise PermissionError("Authorize this paid message first.")
                        result = await registry.command(session, "send", prompt.value)
                    elif name == "context":
                        result = await registry.command(session, "context")
                    elif name == "usage":
                        result = session.snapshot()
                    else:
                        result = await registry.end(session)
                consent.value = False
                with client:
                    feedback.set_text(
                        f"Mode: {session.request.mode} | Messages: {session.sends}/4 | Connection closed: {session.connection_closed}"
                    )
                    output.clear()
                    with output:
                        render_value(result)
            except (LessonError, PermissionError, ValueError, BusyError) as exc:
                feedback.set_text(str(exc))
            finally:
                busy = False

        with ui.row().classes("w-full flex-wrap"):
            for label, name in (
                ("Open usage session", "open"),
                ("Send meter message", "send"),
                ("Inspect session usage", "usage"),
                ("Inspect session context", "context"),
                ("End usage session", "end"),
            ):

                async def click(action_name: str = name) -> None:
                    await action(action_name)

                ui.button(label, on_click=click)

        output = ui.column().classes("w-full")

        async def disconnect() -> None:
            if session:
                await registry.end(session)

        client.on_disconnect(disconnect)
