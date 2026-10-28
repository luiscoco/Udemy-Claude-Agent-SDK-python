"""Readable run results shared by every lesson; transport traces stay separate."""

from dataclasses import dataclass, field
from typing import Any

from nicegui import ui

from agent_lab.models import Event
from agent_lab.policy import redact


@dataclass
class OutputState:
    mode: str = "offline"
    status: str = "ready"
    evidence: dict[str, Any] | None = None
    answers: list[str] = field(default_factory=list)
    current_answer: str = ""
    partial: str = ""
    results: list[tuple[str, Any]] = field(default_factory=list)
    error: str = ""
    cost: float = 0
    turns: int = 0

    @property
    def response_texts(self) -> list[str]:
        pending = "\n\n".join(part for part in (self.current_answer, self.partial) if part)
        return self.answers + ([pending] if pending else [])

    def apply(self, event: Event) -> bool:
        """Return whether an event changed the student-facing output."""
        data = redact(event.data)
        if event.kind == "started":
            self.mode = data["mode"]
            self.status = "running"
        elif event.kind == "evidence":
            self.evidence = data["result"]
        elif event.kind == "message" and not data.get("parent_tool_use_id"):
            if data.get("message_class") == "AssistantMessage":
                # Complete blocks replace streamed previews; thinking/tool calls are traces.
                text = "\n\n".join(
                    block["text"]
                    for block in data.get("content", [])
                    if isinstance(block, dict) and isinstance(block.get("text"), str)
                )
                if not text:
                    return False
                self.current_answer = "\n\n".join(
                    part for part in (self.current_answer, text) if part
                )
                self.partial = ""
            elif data.get("message_class") == "StreamEvent":
                delta = data.get("event", {}).get("delta", {})
                if delta.get("type") != "text_delta":
                    return False
                self.partial += delta.get("text", "")
            else:
                return False
        elif event.kind == "result":
            text = self.current_answer or self.partial
            if not text and isinstance(data.get("result"), str) and not data.get("is_error"):
                text = data["result"]
            if text:
                self.answers.append(text)
            self.current_answer = self.partial = ""
            self.cost += data.get("total_cost_usd") or 0
            self.turns += data.get("num_turns") or 0
            if data.get("structured_output") is not None:
                self.results.append(("Structured response", data["structured_output"]))
        elif event.kind in {"validated", "agent_result", "verification", "team_result"}:
            title = {
                "validated": "Validated response",
                "agent_result": f"Agent: {data.get('role', 'worker')}",
                "verification": "Acceptance checks",
                "team_result": "Team outcome",
            }[event.kind]
            if event.kind != "validated" or not any(value == data for _, value in self.results):
                self.results.append((title, data))
        elif event.kind == "error":
            self.error = data.get("message", "The run failed.")
        elif event.kind == "done":
            self.status = data["status"]
        else:
            return False
        return True


def title_for(key: str) -> str:
    return key.replace("_", " ").capitalize()


def display_value(value: Any) -> str:
    if value is None:
        return "Not available"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value)


def render_value(value: Any, label: str = "", depth: int = 0) -> None:
    """Render heterogeneous lesson evidence as fields, tables, lists and code."""
    if label:
        ui.label(label).classes("font-semibold text-slate-700 mt-2")
    if isinstance(value, dict):
        # Encoded images belong in the image viewer, never in a table or a trace-like field.
        if value.get("type") == "image":
            ui.label("Image created in the lesson workspace.").classes("text-slate-600")
            return
        scalars = {key: item for key, item in value.items() if not isinstance(item, (dict, list))}
        if scalars:
            with ui.column().classes("w-full gap-2"):
                for key, item in scalars.items():
                    if key in {"session_id", "run_id", "control_token"}:
                        continue
                    with ui.row().classes("w-full items-start gap-1 sm:gap-3 flex-col sm:flex-row"):
                        ui.label(title_for(key)).classes("sm:w-36 sm:shrink-0 text-sm text-slate-500")
                        if key in {"source", "code"} and isinstance(item, str) and "\n" in item:
                            ui.code(item, language="python").classes("min-w-0 flex-1 max-w-full")
                        else:
                            ui.label(display_value(item)).classes(
                                "min-w-0 break-words whitespace-pre-wrap flex-1"
                            )
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                if depth >= 2 or key in {"schema", "option_fields", "journal", "ledger"}:
                    with ui.expansion(title_for(key)).classes("w-full"):
                        render_value(item, depth=depth + 1)
                else:
                    render_value(item, title_for(key), depth + 1)
    elif isinstance(value, list):
        if not value:
            ui.label("None").classes("text-sm text-slate-500")
        elif all(
            isinstance(row, dict) and all(not isinstance(v, (dict, list)) for v in row.values())
            for row in value
        ):
            keys = list(
                dict.fromkeys(
                    key
                    for row in value
                    for key in row
                    if key not in {"session_id", "run_id", "control_token"}
                )
            )
            if keys:
                ui.table(
                    columns=[
                        {"name": key, "label": title_for(key), "field": key, "align": "left"}
                        for key in keys
                    ],
                    rows=[
                        {"_row": i, **{key: display_value(row.get(key)) for key in keys}}
                        for i, row in enumerate(value)
                    ],
                    row_key="_row",
                ).classes("w-full max-w-full").props("wrap-cells flat bordered")
        else:
            for number, item in enumerate(value, 1):
                if isinstance(item, (dict, list)):
                    render_value(item, f"Item {number}", depth + 1)
                else:
                    ui.label(f"• {display_value(item)}").classes(
                        "break-words whitespace-pre-wrap max-w-full"
                    )
    else:
        ui.label(display_value(value)).classes("break-words whitespace-pre-wrap max-w-full")


def render_output(state: OutputState, exercise: str, run_id: str | None) -> None:
    if state.status == "ready":
        ui.label("Your results will appear here when you run the exercise.").classes(
            "text-slate-500"
        )
        return
    if state.error:
        with ui.row().classes(
            "w-full bg-red-50 text-red-800 rounded-lg p-4 items-start flex-nowrap"
        ):
            ui.icon("error_outline")
            ui.label(state.error).classes("break-words min-w-0")
    if state.mode == "live":
        for number, text in enumerate(state.response_texts, 1):
            ui.label(f"Claude response {number}").classes("font-semibold text-purple-700")
            ui.markdown(text).classes("response-prose w-full min-w-0")
        if not state.response_texts and not state.results:
            ui.label(
                "Waiting for Claude’s response…"
                if state.status == "running" and not state.error
                else "No agent response was received."
            ).classes("text-slate-500")
        if state.turns or state.cost:
            ui.label(f"{state.turns} model turns · ${state.cost:.4f} reported cost").classes(
                "text-xs text-slate-500"
            )
    elif state.evidence is not None:
        ui.badge("LOCAL PYTHON RESULT", color="secondary")
        ui.label(
            "Computed locally or recorded as a teaching fixture. Your prompt was not sent to Claude."
        ).classes("text-sm text-slate-500")
        render_value(state.evidence)
    for title, value in state.results:
        with ui.card().classes("course-card w-full p-4"):
            render_value(value, title)
    if state.evidence is not None and run_id:
        if exercise == "document" and state.evidence.get("document"):
            ui.link(
                "Download incident report (.docx)",
                f"/api/runs/{run_id}/artifacts/incident-report.docx",
                new_tab=True,
            ).classes("font-semibold")
        if exercise == "images":
            ui.image(f"/api/runs/{run_id}/artifacts/pixel.png").classes("w-16 h-16").props(
                "fit=contain"
            )
            ui.link(
                "Download generated image", f"/api/runs/{run_id}/artifacts/pixel.png", new_tab=True
            )
    if state.mode == "live" and state.evidence is not None:
        with ui.expansion("Local exercise results (separate from Claude’s response)").classes(
            "w-full"
        ):
            render_value(state.evidence)
