"""Readable lane observations and a separate metadata-only inspector."""

from typing import Any

from nicegui import ui

from agent_lab.output import render_value


def comparison_cards(experiment: dict) -> None:
    with ui.column().classes("w-full gap-3 thinking-comparison"):
        ui.label("Requested settings and observed results").classes("text-lg font-bold")
        ui.label(
            "Unknown is not zero. Aliases, requested settings and observed effort do not prove hidden reasoning or fallback."
        ).classes("text-sm text-slate-600")
        with ui.element("div").classes("grid w-full grid-cols-1 md:grid-cols-2 gap-3"):
            for lane in experiment.get("lanes", []):
                requested = lane.get("requested", {})
                metrics = lane.get("metrics", {})
                with ui.card().classes("w-full min-w-0 p-4 thinking-lane"):
                    ui.label("Lane " + lane["lane"]).classes("text-lg font-bold")
                    ui.label("Requested model: " + str(requested.get("model"))).classes(
                        "break-all w-full"
                    )
                    ui.label(
                        f"Thinking: {requested.get('thinking', {}).get('type')} · Requested effort: {requested.get('effort') or 'omitted'}"
                    ).classes("break-words w-full")
                    ui.label("Thinking options: " + str(requested.get("thinking", {}))).classes(
                        "break-all w-full text-sm"
                    )
                    ui.label(
                        "Reported models: "
                        + (", ".join(lane.get("reported_models", [])) or "Unknown")
                    ).classes("break-all w-full")
                    ui.label(
                        "Observed Stop effort: " + str(lane.get("observed_effort") or "Unknown")
                    ).classes("font-semibold w-full")
                    for key, label in (
                        ("sdk_duration_ms", "SDK latency (ms)"),
                        ("input_tokens", "Input tokens"),
                        ("output_tokens", "Output tokens"),
                        ("cost_usd", "Reported cost (USD)"),
                    ):
                        value = metrics.get(key)
                        ui.label(f"{label}: {'Unknown' if value is None else value}")
                    ui.label(
                        "Lane evidence established"
                        if lane.get("experiment_passed")
                        else "Lane evidence incomplete"
                    ).classes("font-semibold")


def model_inspector(sessions: Any) -> None:
    with ui.expansion("Model metadata (no prompt)").classes("w-full"):
        ui.label(
            "This optional probe reads CLI initialization metadata. It never sends a user message and does not establish model access or applied behavior."
        ).classes("text-sm text-slate-600")
        result = ui.column().classes("w-full")

        async def inspect() -> None:
            button.disable()
            try:
                metadata = await sessions.metadata.inspect()
                result.clear()
                with result:
                    render_value(metadata)
            finally:
                button.enable()

        button = ui.button("Inspect model metadata", on_click=inspect)
