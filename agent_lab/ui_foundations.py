"""Accessible controls for lesson-specific SDK experiments."""

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

        elif lesson == 11:
            select(
                "loading",
                "Skill loading",
                {
                    "invoke": "Explicit invocation",
                    "discovery": "Discovery only",
                    "preload": "Host preload",
                },
                "invoke",
            )
            select(
                "discovery",
                "Skill source",
                {"project": "Project directory", "plugin": "Local plugin"},
                "project",
            )
            tick("visible", "Include the prepared skill in the SDK filter")
            values["visible"].bind_enabled_from(
                values["loading"], "value", lambda value: value != "preload"
            )
            tick("load_support", "Also load the supporting checklist", False)
            ui.label(
                "Preload places prepared instructions in the system appendix and hides the Skill listing. "
                "Discovery and preload alone do not pass the invocation check. Offline calls are labelled fixtures. "
                "The skill filter is not a filesystem sandbox."
            ).classes("text-sm text-slate-600")

        elif lesson == 12:
            tick("interactive", "Keep session open for manual messages", False)
            select(
                "queue_timing",
                "Script follow-up timing",
                {"immediate": "Queue both messages", "after-result": "Wait for the first result"},
                "immediate",
            )
            select(
                "runtime_control",
                "Script runtime control",
                {"none": "No change", "model": "Request haiku", "permission": "Request plan mode"},
                "none",
            )
            for key in ("queue_timing", "runtime_control"):
                values[key].bind_enabled_from(
                    values["interactive"], "value", lambda value: not value
                )
            values["max_messages"] = (
                ui.number("Authorized message limit", value=2, min=2, max=4, precision=0)
                .props("outlined")
                .classes("w-full")
            )
            ui.label(
                "Run exercise opens one connection. In manual mode, queue messages and then choose End input to drain and close. Cancel aborts. Runtime controls require an SDK acknowledgement; submitted messages are not completed turns."
            ).classes("text-sm text-slate-600")

        elif lesson == 13:
            select(
                "transport",
                "MCP server transport",
                {
                    "sdk": "In-process SDK server",
                    "stdio": "Child process (stdio)",
                    "http": "Loopback HTTP server",
                },
                "sdk",
            )
            select(
                "tool",
                "Permitted inventory tool",
                {"stock": "Inspect stock", "reserve": "Reserve inventory"},
                "reserve",
            )
            select("sku", "Inventory item", {"notebook": "notebook", "pen": "pen"}, "notebook")
            values["quantity"] = (
                ui.number("Reservation quantity", value=2, min=1, max=5, precision=0)
                .props("outlined")
                .classes("w-full")
            )
            for key in ("sku", "quantity"):
                values[key].bind_enabled_from(
                    values["tool"], "value", lambda value: value == "reserve"
                )
            tick("enabled", "Configure the inventory MCP server")
            select(
                "lifecycle",
                "MCP lifecycle comparison",
                {
                    "none": "Inspect status and call",
                    "toggle": "Disable then enable",
                    "reconnect": "Reconnect before calling",
                },
                "none",
            )
            ui.label(
                "Offline uses real owned MCP transports with recorded agent identities. Live uses actual SDK status, lifecycle controls and tool events. Configuration alone never passes the check. Agent reservations are limited to one authorized write per run."
            ).classes("text-sm text-slate-600")

        elif lesson == 14:
            values["model"] = (
                ui.input("Model (blank = configured model)")
                .props("outlined maxlength=100")
                .classes("w-full")
            )
            select(
                "thinking",
                "Thinking mode",
                {"disabled": "Disabled", "adaptive": "Adaptive", "enabled": "Enabled with budget"},
                "adaptive",
            )
            effort_choices = {
                "omitted": "Omitted",
                "low": "Low",
                "medium": "Medium",
                "high": "High",
                "xhigh": "Extra high",
                "max": "Maximum",
            }
            select("effort", "Requested effort", effort_choices, "medium")
            values["budget_tokens"] = (
                ui.number(
                    "Budget tokens (enabled lanes only)",
                    value=4000,
                    min=1024,
                    max=16384,
                    precision=0,
                )
                .props("outlined")
                .classes("w-full")
            )
            select(
                "display",
                "Thinking display (ignored when disabled)",
                {"default": "SDK default", "summarized": "Summarized", "omitted": "Omitted"},
                "default",
            )
            select(
                "comparison",
                "Comparison setting",
                {
                    "none": "Single lane",
                    "effort": "Change effort only",
                    "model": "Change model only",
                    "thinking": "Change thinking only",
                },
                "none",
            )
            select("comparison_effort", "Comparison effort", effort_choices, "high")
            values["comparison_effort"].bind_enabled_from(
                values["comparison"], "value", lambda v: v == "effort"
            )
            values["comparison_model"] = (
                ui.input("Comparison model", value="sonnet")
                .props("outlined maxlength=100")
                .classes("w-full")
            )
            values["comparison_model"].bind_enabled_from(
                values["comparison"], "value", lambda v: v == "model"
            )
            select(
                "comparison_thinking",
                "Comparison thinking",
                {"disabled": "Disabled", "adaptive": "Adaptive", "enabled": "Enabled with budget"},
                "disabled",
            )
            values["comparison_thinking"].bind_enabled_from(
                values["comparison"], "value", lambda v: v == "thinking"
            )
            tick(
                "authorize_comparison",
                "I authorize both paid lanes; the budget threshold applies to each lane separately.",
                False,
            )
            values["authorize_comparison"].bind_visibility_from(
                mode, "value", lambda v: v == "live"
            )
            ui.label(
                "The same prompt is sent to fresh connections. Valid SDK shapes do not prove model support. Stop observations may differ from requested effort; that alone does not establish fallback. Offline model latency and usage remain unknown."
            ).classes("text-sm text-slate-600")

        if lesson == 15:
            tick("omit_turn_limit", "Omit SDK turn limit (host deadline still applies)", False)
            tick("omit_budget_limit", "Omit SDK dollar threshold (not a billing guarantee)", False)
            tick("allow_agent", "Permit the restricted Agent helper tool", False)
            values["task_tokens"] = ui.number("Planning token guidance (blank = omitted)", value=None, min=1, max=100000, precision=0).props("outlined clearable").classes("w-full")
            ui.label("task_budget guides planning; terminal error_max_turns and error_max_budget_usd show enforced stops. Final usage is observed, not predicted.").classes("text-sm text-slate-600")

    def read() -> dict[str, Any]:
        if mode.value == "live" and lesson in {5, 10}:
            return {}  # Offline-only drafts must not become live tool arguments.
        result = {key: element.value for key, element in values.items()}
        if lesson == 15 and result["task_tokens"] is not None:
            if result["task_tokens"] != int(result["task_tokens"]):
                raise ValueError("Choose a whole planning-token value.")
            result["task_tokens"] = int(result["task_tokens"])
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
        if lesson == 12:
            result["max_messages"] = int(result["max_messages"])
        if lesson == 13:
            if result["quantity"] != int(result["quantity"]):
                raise ValueError("Choose a whole reservation quantity.")
            result["quantity"] = int(result["quantity"])
        if lesson == 14:
            result["model"] = (result["model"] or "").strip() or None
            for key in ("effort", "comparison_effort"):
                if result[key] == "omitted":
                    result[key] = None
            if result["budget_tokens"] != int(result["budget_tokens"]):
                raise ValueError("Choose a whole thinking-token budget.")
            result["budget_tokens"] = int(result["budget_tokens"])
        return result

    return read
