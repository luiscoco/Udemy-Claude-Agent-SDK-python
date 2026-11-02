"""Small, accessible controls for the first nine lesson-specific experiments."""

import json
from collections.abc import Callable
from typing import Any

from nicegui import ui

from agent_lab.foundation_models import INPUT_MODELS


def experiment_controls(lesson: int, mode: Any) -> Callable[[], dict[str, Any]]:
    if lesson not in INPUT_MODELS:
        return lambda: {}
    values: dict[str, Any] = {}

    def select(key: str, label: str, options: dict[str, str], value: str) -> None:
        values[key] = (
            ui.select(options, value=value, label=label).props("outlined").classes("w-full")
        )

    def text(key: str, label: str, value: str) -> None:
        values[key] = (
            ui.textarea(label, value=value)
            .props("outlined rows=3 maxlength=2000")
            .classes("w-full")
        )

    def tick(key: str, label: str, value: bool = True) -> None:
        values[key] = ui.checkbox(label, value=value)

    with ui.column().classes("w-full gap-3 foundation-controls"):
        ui.label("Lesson experiment").classes("text-lg font-bold")
        if lesson == 2:
            values["model"] = (
                ui.input("Model (blank = omitted)")
                .props("outlined maxlength=100")
                .classes("w-full")
            )
            select(
                "system_mode",
                "System prompt mode",
                {
                    "default": "Omitted",
                    "custom": "Custom text",
                    "preset": "Preset + append",
                },
                "default",
            )
            text("system_text", "System instruction", "Teach using concise Python examples.")
            values["system_text"].bind_enabled_from(
                values["system_mode"], "value", lambda value: value != "default"
            )
            tick("partial_messages", "Include partial messages")
            tick("omit_turn_limit", "Omit the SDK turn limit", False)
            tick("omit_budget_limit", "Omit the SDK budget threshold", False)
            ui.label(
                "Omitted limits are not sent to the SDK. The host deadline remains; an omitted threshold does not cap billing."
            ).classes("text-sm text-slate-600")
        elif lesson == 3:
            select(
                "tool",
                "Available built-in tool",
                {
                    "Read": "Read notes.txt",
                    "Glob": "List fixture text files",
                    "Grep": "Search fixture text",
                    "Bash": "Fixed python --version command",
                },
                "Read",
            )
            tick("permit_tool", "Host policy permits the selected tool")
            ui.label(
                "Tool inventory and permission are separate. The shell experiment permits only the displayed fixed command."
            ).classes("text-sm text-slate-600")
        elif lesson == 4:
            select(
                "decision",
                "Permission decision",
                {
                    "deny": "Deny",
                    "allow": "Allow",
                    "update": "Redirect to approved.txt",
                    "ask": "Ask me in a permission dialog",
                },
                "deny",
            )
            select(
                "target",
                "Owned fixture target",
                {"draft.txt": "draft.txt", "notes.txt": "notes.txt"},
                "draft.txt",
            )
            text("content", "Offline write content", "A permission-controlled lesson note.\n")
            ui.label(
                "Only files in this run's disposable workspace can be changed. The automatic criterion checks denied writes; allow and redirect are separate observations."
            ).classes("text-sm text-slate-600")
        elif lesson == 5:
            for key, value in (("a", 19.0), ("b", 23.0)):
                values[key] = (
                    ui.number(f"Offline argument {key}", value=value, min=-1e6, max=1e6)
                    .props("outlined")
                    .classes("w-full")
                    .bind_enabled_from(mode, "value", lambda value: value == "offline")
                )
            ui.label(
                "Offline numbers drive the real local handler. In live mode, the agent supplies arguments from your prompt."
            ).classes("text-sm text-slate-600")
        elif lesson == 6:
            select(
                "strategy",
                "Session strategy",
                {
                    "same-client": "Same client",
                    "resume": "Resume previous session",
                    "fresh": "Fresh client",
                },
                "same-client",
            )
            ui.label(
                "Compare two turns inside this run. Cross-browser session storage is a separate workshop; recalled answer quality is manual."
            ).classes("text-sm text-slate-600")
        elif lesson == 7:
            tick("pre_hook", "Enable teaching PreToolUse")
            tick("post_hook", "Enable PostToolUse")
            ui.label(
                "The host path guard stays registered independently of the teaching hook."
            ).classes("text-sm text-slate-600")
            select(
                "behavior",
                "Pre-use behavior",
                {
                    "observe": "Observe",
                    "block": "Block",
                    "rewrite": "Rewrite Read to alternate.txt",
                },
                "observe",
            )
        elif lesson == 8:
            select(
                "worker_tools",
                "Reviewer tool scope",
                {"read-only": "Read, Glob and Grep", "none": "No file tools"},
                "read-only",
            )
            select(
                "worker_model",
                "Reviewer model",
                {"inherit": "Inherit", "haiku": "Haiku", "sonnet": "Sonnet"},
                "inherit",
            )
        elif lesson == 9:
            select(
                "variant",
                "System prompt variant",
                {
                    "default": "Omitted",
                    "custom": "Custom text",
                    "preset": "Preset + append",
                    "boundary": "Dynamic boundary",
                    "project": "Owned CLAUDE.md",
                },
                "preset",
            )
            text("instruction", "System instruction", "Teach using concise Python examples.")
            text("context", "Dynamic context", "The student is practising SDK configuration.")
            values["instruction"].bind_enabled_from(
                values["variant"], "value", lambda value: value != "default"
            )
            values["context"].props("maxlength=1000").bind_enabled_from(
                values["variant"], "value", lambda value: value == "boundary"
            )
        elif lesson == 10:
            text(
                "payload",
                "Offline structured JSON",
                '{"summary":"Host-validated example","next_steps":["Inspect the terminal result"]}',
            )
            values["payload"].bind_enabled_from(mode, "value", lambda value: value == "offline")
            values["payload"].props("rows=6 maxlength=10000")
            select(
                "stop_experiment",
                "Offline stop comparison",
                {"interrupt": "Interrupt, then continue", "abort": "Abort by closing the client"},
                "interrupt",
            )
            values["stop_experiment"].bind_enabled_from(
                mode, "value", lambda value: value == "offline"
            )
            ui.label(
                "Choose the Stop comparison scenario to use the official client with a scripted transport. Live Cancel aborts the run. This separate experiment never passes the structured-output check."
            ).classes("text-sm text-slate-600")

    def read() -> dict[str, Any]:
        if mode.value == "live" and lesson in {5, 10}:
            return {}  # Offline-only drafts must not become live tool arguments.
        result = {key: element.value for key, element in values.items()}
        if lesson == 2:
            result["model"] = (result["model"] or "").strip() or None
            if result["system_mode"] == "default":
                result.pop("system_text")
        if lesson == 9:
            if result["variant"] == "default":
                result.pop("instruction")
            if result["variant"] != "boundary":
                result.pop("context")
        if lesson == 10:
            result["payload"] = json.loads(result["payload"])
        return result

    return read
