"""Accessible controls for lesson-specific SDK experiments."""

import json
from collections.abc import Callable
from typing import Any

from nicegui import ui

from agent_lab.foundation_models import INPUT_MODELS


def experiment_controls(lesson: int, mode: Any) -> Callable[..., dict[str, Any]]:
    if lesson not in INPUT_MODELS:
        return lambda *, reset_consent=False: {}
    values: dict[str, Any] = {}

    def select(key: str, label: str, options: dict[Any, str], value: Any) -> None:
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

        if lesson == 38:
            select("variant", "Suggestion switch", {"enabled": "Enabled", "omitted": "Omitted option", "disabled": "Disabled", "env-off": "Environment off", "setting-off": "Setting off", "env-on": "Environment on", "plan": "Plan mode", "small": "Small context", "cached": "Cached", "uncached": "Uncached", "queued": "Queued input"}, "enabled")
            tick("edited", "Edit a suggestion before sending", False)
            ui.label("A suggestion is proposed text after a completed turn. It becomes a user turn only when sent through the validated queue. The live probe may have no suggestion. Setting-off and cache variants are comparison-only in this Python CLI build.").classes("text-sm text-slate-600")
        if lesson == 39:
            select("action", "Configuration experiment", {"where": "Compare origins", "takeover": "Exact Bash takeover"}, "where")
            select("cwd", "Working directory", {"trusted": "Trusted checkout", "branch": "Branch checkout", "docs": "Docs checkout"}, "branch")
            select("root", "Configuration root", {"trusted": "Trusted checkout", "branch": "Branch checkout", "omitted": "Omitted"}, "trusted")
            select("sources", "Setting sources", {"project-local": "Project and local", "none": "Disabled"}, "project-local")
            ui.label("cwd selects files; project-config-root selects configuration. The takeover comparison requires branch cwd, project/local sources and trusted or omitted root. Fixed invalid roots run only through /api/c39/try startup mode without provider credentials.").classes("text-sm text-slate-600")
        if lesson == 40:
            tick("recover", "Try one recovery fork after refusal", True)
            ui.label("The lab parses the active persisted JSONL chain and keeps queued attachments inside their logical turn. Prepared results are authored fixtures. On this Python SDK, an unsafe guard can raise during connection; the live check verifies the CLI result frame preserved in ResultError, never the exception text alone.").classes("text-sm text-slate-600")
        if lesson == 41:
            ui.label("This Python edition compares three turns on one ClaudeSDKClient with a fresh client that resumes its owned session. Prepared mode uses a scripted CLI fixture. The historical TypeScript V2 API is not present in the Python SDK.").classes("text-sm text-slate-600")
        if lesson == 42:
            select("action", "Web experiment", {"basics": "Search and fetch", "fetch-lab": "Fetch one page", "injection": "Compare page treatment", "guard": "Host URL guard", "research": "Research lanes"}, "basics")
            select("page", "Fixed fetch page", {"page": "About page", "json": "Release JSON", "redirect": "Trailing slash", "missing": "Missing page"}, "page")
            ui.label("The host restricts WebFetch to fixed HTTPS Node.js URLs and rewrites WebSearch domains in PreToolUse. Prepared evidence is authored. The injection example overlays harmless text after a real public fetch; redaction is heuristic, and cited URL provenance does not prove claim support.").classes("text-sm text-slate-600")
        if lesson == 44:
            select("action", "Telemetry experiment", {"signals": "Signal views", "privacy": "Privacy comparison", "tracing": "Parent trace", "rich": "Denied tool comparison", "exporters": "Exporter temporality", "collector": "Collector authentication"}, "signals")
            tick("consent", "Authorize this paid telemetry action", False)
            values["consent"].bind_visibility_from(mode, "value", lambda value: value == "live")
            values["action"].on_value_change(lambda _: values["consent"].set_value(False))
            mode.on_value_change(lambda _: values["consent"].set_value(False))
            ui.label("Each local action posts authored OTLP JSON to an owned loopback collector. Live actions use an isolated SDK subprocess and require fresh consent; privacy and exporter comparisons run two bounded queries.").classes("text-sm text-slate-600")
        if lesson == 45:
            select("action", "Cloud experiment", {"catalog": "Catalog and startup checks", "same": "Five provider formats", "auth": "Credential comparison", "models": "Model mapping", "failures": "Denied and explicit recovery"}, "catalog")
            select("auth_case", "Fixed authentication case", {"bearer": "Bedrock bearer", "sigv4": "Bedrock SigV4", "wif": "Vertex owned token exchange", "foundry": "Foundry key", "gateway": "Gateway bearer"}, "bearer")
            select("model_case", "Fixed model case", {"alias": "Haiku alias", "profile": "Owned Bedrock profile", "region": "EU model prefix"}, "profile")
            tick("consent", "Authorize this bounded paid cloud action", False)
            values["consent"].bind_visibility_from(mode, "value", lambda value: value == "live")
            for key in ("action", "auth_case", "model_case"):
                values[key].on_value_change(lambda _: values["consent"].set_value(False))
            mode.on_value_change(lambda _: values["consent"].set_value(False))
            ui.label("The local proxy compares five provider wire formats with generated credentials; it is not a cloud deployment. Live actions use isolated SDK subprocesses through the proxy. Each inference query has a $0.10 SDK ceiling; the five-provider comparison has five such ceilings, and refusal plus explicit recovery has two.").classes("text-sm text-slate-600")
        if lesson == 46:
            select("action", "Cache experiment", {"anatomy": "Cache anatomy", "switches": "TTL switch", "breakers": "Prefix breaker", "model-switch": "Model switch policy"}, "anatomy")
            select("ttl", "Cache TTL", {"5m": "Five minutes", "1h": "One hour", "off": "Disabled"}, "5m")
            select("prefix", "Fixed prefix", {"stable": "Stable handbook", "changed": "Changed edition", "tool": "Added owned tool", "dynamic": "Dynamic suffix", "short": "Short handbook"}, "stable")
            select("policy", "Model switch policy", {"cap": "Zero-dollar cap", "allow": "Allow switch"}, "cap")
            tick("consent", "Authorize this paid two-turn cache action", False)
            values["consent"].bind_visibility_from(mode, "value", lambda value: value == "live")
            for key in ("action", "ttl", "prefix", "policy"):
                values[key].on_value_change(lambda _: values["consent"].set_value(False))
            mode.on_value_change(lambda _: values["consent"].set_value(False))
            ui.label("Local rows are authored HTTP fixtures. Live rows compare native SDK counters with owned upstream observations. Breakpoints request reuse; only usage counters show a hit. Each session has a $0.15 SDK ceiling.").classes("text-sm text-slate-600")
        if lesson == 49:
            choices = {"headless": "CLI and SDK", "ci": "Clean and buggy CI",
                       "limits": "Process failure limits", "deploy": "Local worker drain"}
            select("action", "Headless action", choices, "headless")
            tick("consent", "Authorize this bounded paid headless action", False)
            values["consent"].bind_visibility_from(mode, "value", lambda value: value == "live")
            values["action"].on_value_change(lambda _: values["consent"].set_value(False))

            def mode_changed(_event: Any) -> None:
                allowed = {key: label for key, label in choices.items()
                           if mode.value == "offline" or key in {"headless", "ci"}}
                if values["action"].value not in allowed:
                    values["action"].set_value("headless")
                values["action"].set_options(allowed)
                values["consent"].set_value(False)

            mode.on_value_change(mode_changed)
            ui.label("Limits and Local worker drain run owned processes only. Live mode is available for CLI and SDK or Clean and buggy CI.").classes("text-sm text-slate-600")
        if lesson == 48:
            select("action", "Security probe", {"permissions": "Path permissions", "lockdown": "Tool and environment lockdown", "secrets": "Known secret rewrite", "injection": "Untrusted ticket"}, "permissions")
            tick("consent", "Authorize this bounded paid security action", False)
        if lesson == 47:
            select("action", "Orchestration pattern", {"orchestrator": "Orchestrator delegation", "hierarchy": "Three-level hierarchy", "pipeline": "Verified pipeline", "fanout": "Regional fan-out", "evaluator": "Writer and critic"}, "orchestrator")
            select("limit", "Host concurrency", {1: "One worker", 2: "Two workers"}, 2)
            tick("consent", "Authorize this bounded paid orchestration action", False)
            values["consent"].bind_visibility_from(mode, "value", lambda value: value == "live")
            values["action"].on_value_change(lambda _: values["consent"].set_value(False))
            values["limit"].on_value_change(lambda _: values["consent"].set_value(False))
            mode.on_value_change(lambda _: values["consent"].set_value(False))
            ui.label("Local workers are authored host fixtures over owned CSV files. Live delegation and separate-query patterns use bounded SDK calls; parent prose alone does not pass the worker check.").classes("text-sm text-slate-600")
        if lesson == 43:
            select("action", "Remote MCP experiment", {"auth": "Machine credential challenge", "cache": "Token reuse and renewal", "transports": "HTTP and SSE", "toolsets": "Tool inventory", "resources": "Resource inventory and read", "host-read": "Host resource read", "live": "Agent step"}, "auth")
            select("step", "Agent step", {"tool": "Call status tool", "resource": "Read resource", "rotate": "Rotate credential"}, "tool")
            values["step"].bind_visibility_from(values["action"], "value", lambda value: value == "live")
            select("transport", "Transport", {"http": "Streamable HTTP", "sse": "Legacy SSE"}, "http")
            select("resource", "Fixed resource", {"runbook": "Runbook", "incident": "Incident note", "order": "Order 1001", "logo": "PNG logo", "widget": "Inert HTML widget"}, "runbook")
            ui.label("The owned loopback fixture uses short-lived machine credentials. Live rotation replaces the connected server configuration through a version-guarded private SDK control, then verifies credential-2 on the second tool receipt.").classes("text-sm text-slate-600")
            ui.label("Only Agent step uses the billed live mode. Local actions and local Agent step rehearsals make no provider call.").classes("text-sm text-slate-600")
        if lesson == 37:
            select("action", "Gate decision", {"allow": "Allow Write", "edit": "Edit Write input", "remember": "Allow and propose session rule", "deny": "Deny Write", "interrupt": "Deny and interrupt", "malformed": "Malformed gate response", "missing-effect": "Allow without host effect (prepared only)"}, "allow")
            ui.label("The prepared run starts an owned Python stdio MCP gate and makes a real client/server round trip. Live mode uses the SDK permission prompt tool and checks the resulting file. The session rule is a proposal; reuse is not claimed.").classes("text-sm text-slate-600")
        if lesson == 36:
            select("action", "Child action", {"success": "Successful child", "stderr": "Separate stderr", "failed-launch": "Failed launch", "timeout": "Timed out child", "cancel": "Cancelled child"}, "success")
            select("location", "Local machine simulation", {"machine-a": "Machine A", "machine-b": "Machine B"}, "machine-a")
            ui.label("These locations are owned directories on this host. The Python SDK CLI runs separately; a local child does not claim a remote machine or carry the SDK protocol.").classes("text-sm text-slate-600")
        if lesson == 35:
            select("action", "Storage experiment", {"commit": "Commit host transcript", "interrupted": "Interrupt before replace", "resume": "Resume SDK session", "durable-resume": "Resume from SQLite store"}, "commit")
            select("flush", "Mirror flush", {"eager": "Eager", "batched": "Batched"}, "eager")
            tick("enabled", "Enable SDK session mirror", True)
            select("fault", "Mirror fault", {"none": "None", "reject-append": "Reject append", "delay-load": "Delay load"}, "none")
            ui.label("The host transcript and SDK session mirror are separate. The interrupted case leaves the old JSON intact; durable resume reopens an owned SQLite store with a fresh SDK configuration.").classes("text-sm text-slate-600")
        if lesson == 34:
            select("style", "Owned output style", {"teaching": "Teaching marker", "brief": "Brief marker"}, "teaching")
            select("source", "SDK setting source", {"project": "Project enabled", "none": "Project disabled"}, "project")
            ui.label("The host writes the selected style and settings.json in the lesson workspace. A fixed marker question compares project loading with a disabled source. Model tools remain disabled in every variant.").classes("text-sm text-slate-600")
        if lesson == 33:
            select("action", "Simulated MCP form response", {"accept": "Accept local booking", "decline": "Decline booking", "cancel": "Cancel request"}, "accept")
            ui.label("The owned SDK tool calls the Python MCP client/server, which answers only the fixed rooms form. Accept sends Student booking data; decline and cancel send no content. The choice is simulated and no external calendar is contacted.").classes("text-sm text-slate-600")
        if lesson == 32:
            select("proposal", "Fixed plan proposal", {"valid": "Valid owned plan", "duplicate": "Duplicate file owner"}, "valid")
            tick("approve", "Approve validated plan in host control", True)
            ui.label("The SDK starts in plan mode. Only a validated, approved proposal triggers a switch to default mode, a confirmation turn, and fixed host workers. Approval here is a selected lab control, not a person reviewing during the run.").classes("text-sm text-slate-600")
        if lesson == 31:
            select("answer", "Simulated host answer", {"Concise": "Concise", "Detailed": "Detailed"}, "Concise")
            ui.label("The host injects this labelled simulated answer through can_use_tool after validating the exact question. The live SDK run checks the tool call, result, and callback.").classes("text-sm text-slate-600")
        if lesson == 30:
            select("sequence", "TodoWrite sequence", {"valid": "Valid three-step progress", "skip": "Skip pending to completed", "parallel": "Two tasks in progress", "reopen": "Reopen completed task"}, "valid")
            ui.label("The host validates each real TodoWrite proposal before execution and commits its ledger only after a successful PostToolUse callback. Rejected proposals keep prior state.").classes("text-sm text-slate-600")
        if lesson == 29:
            select("color", "Owned image color", {"red": "Red square", "blue": "Blue square"}, "red")
            ui.label("The host creates one bounded PNG inside the lesson workspace, validates its bytes, and sends a typed base64 image block plus a text question. No uploaded file or external path is accepted.").classes("text-sm text-slate-600")
        if lesson == 28:
            select("outcome", "Fixed refund outcome", {"recover": "Transient errors, then recover", "permanent": "Permanent rejection", "exhausted": "Transient errors exhaust retry limit"}, "recover")
            ui.label("The real SDK tool uses an in-memory A-100 ledger. The host retries only transient statuses, with two bounded backoff waits and at most three attempts. No payment service is contacted.").classes("text-sm text-slate-600")
        if lesson == 27:
            select("ending", "Host watcher ending", {"cancel": "Cancel and await", "finish": "Release and await"}, "cancel")
            ui.label("The host watcher stays pending during one real SDK turn. The host then cancels or releases it, awaits cleanup, and closes the SDK client.").classes("text-sm text-slate-600")
        if lesson == 26:
            select("action", "Control experiment", {"switch": "Switch model and permission mode", "interrupt": "Interrupt a long turn"}, "switch")
            select("target_model", "Second-turn model", {"current": "Current configured model", "sonnet": "Claude Sonnet 5.5"}, "current")
            select("permission_mode", "Second-turn permission mode", {"plan": "Plan", "default": "Default"}, "plan")
            ui.label("The switch experiment uses two turns on one SDK session. The interrupt experiment stops a long turn after a stream event. Both check that the disconnected client rejects another query.").classes("text-sm text-slate-600")
        if lesson == 25:
            select("limit", "Tool result limit", {600: "600 characters", 200: "200 characters"}, 600)
            tick("retain_summary", "Retain compact host progress summary", True)
            ui.label("The real MCP tool bounds its own result and marks removed content. The host summary is separate; PreCompact is observed only if the SDK triggers it. This short run does not force automatic compaction.").classes("text-sm text-slate-600")
        if lesson == 24:
            select("proposal", "Fixed plan proposal", {"valid": "Valid two-task plan", "duplicate": "Duplicate file owner", "cycle": "Dependency cycle", "outside": "Outside owned scope"}, "valid")
            tick("approve", "Approve host execution after validation", True)
            ui.label("Only the exact accepted two-file plan can reach fixed host workers. Review-only and rejected proposals start no workers. SDK structured output is validated again by the host.").classes("text-sm text-slate-600")
        if lesson == 23:
            select("action", "Plugin extension", {"explain": "Explain command", "quiz": "Quiz command", "skill": "Python example Skill"}, "explain")
            tick("enabled", "Load the owned local plugin", True)
            ui.label("The host owns the manifest, two namespaced commands and one Skill. The disabled-plugin comparison checks command non-discovery. The model may invoke only the selected Skill tool.").classes("text-sm text-slate-600")
        if lesson == 22:
            select("source", "Project settings", {"project": "Load owned CLAUDE.md", "none": "No project settings"}, "project")
            select("system_mode", "System prompt", {"preset": "Claude Code preset", "custom": "Custom prompt (control)"}, "preset")
            select("rule", "Owned project rule", {"alpha": "Alpha marker", "beta": "Beta marker"}, "alpha")
            ui.label("The fixed question tests the marker without reading files. The CLI configuration disables automatic memory. This shows observed behavior, not the resolved system prompt.").classes("text-sm text-slate-600")
        if lesson == 21:
            select("source", "Filesystem settings source", {"project": "Owned project settings", "none": "No filesystem settings (discovery control)"}, "project")
            select("template", "Command template", {"summary": "Three bullet summary", "quiz": "Two quiz questions"}, "summary")
            ui.label("The host writes only the owned command file. The SDK inventory must discover it and the response must show its marker after one matching Read. Without project settings, discovery is absent and the invocation check needs review.").classes("text-sm text-slate-600")
        if lesson == 20:
            select("behavior", "Hook experiment", {"observe": "Allow and audit", "deny": "Deny before execution", "rewrite": "Rewrite Read to alternate fixture", "tool-error": "Observe missing-file failure", "callback-error": "Contain a synthetic callback error"}, "observe")
            select("matcher", "Teaching pre-hook matcher", {"Read": "Read", "Read|Glob": "Read|Glob", "Write|Edit": "Write|Edit (does not match Read)"}, "Read")
            tick("post_hook", "Enable success audit")
            tick("failure_hook", "Enable failure audit")
            tick("prompt_hook", "Observe UserPromptSubmit")
            tick("stop_hook", "Observe Stop without blocking")
            ui.label("The independent host guard always stays active. Disabled audit/lifecycle channels need review. Matchers are regexes on tool names; hook logs store markers and hashes, not response or error bodies. Stop never asks for another turn.").classes("text-sm text-slate-600")
        if lesson == 19:
            select("action", "Owned catalog operation", {"inspect": "Inspect and paginate", "rename-tag": "Rename and tag", "fork": "Fork the owned transcript", "delete": "Delete this disposable transcript"}, "inspect")
            values["page_size"] = ui.number("Page size", value=2, min=1, max=10, precision=0).props("outlined").classes("w-full")
            values["offset"] = ui.number("Page offset", value=0, min=0, max=20, precision=0).props("outlined").classes("w-full")
            values["title"] = ui.input("Owned session title", value="Lesson 19 reviewed session").props("outlined maxlength=80").classes("w-full")
            select("tag", "Owned session tag", {"reviewed": "reviewed", "practice": "practice"}, "reviewed")
            values["title"].bind_enabled_from(values["action"], "value", lambda value: value in {"rename-tag", "fork"})
            values["tag"].bind_enabled_from(values["action"], "value", lambda value: value == "rename-tag")
            ui.label("Every run creates its own session. Catalog operations run only after the client closes, in an isolated child. Delete affects only this run's disposable transcript. Empty pages are valid; no external session IDs or paths are accepted.").classes("text-sm text-slate-600")
        if lesson == 18:
            from agent_lab.sandbox_native import sandbox_capability

            select("target", "Owned Read target", {"inside": "Inside: notes.txt", "outside": "Outside: synthetic neighbor", "protected": "Protected: synthetic config file"}, "inside")
            tick("native_required", "Require the native OS sandbox process probe (live, supported platforms only)", False)
            ui.label(sandbox_capability()["reason"]).classes("text-sm text-slate-600")
            ui.label("Policy comparisons expose Read only. The actual host child counterexample is not sandboxed. Native verification permits only a fixed local probe, forbids unsandboxed retry, and checks filesystem and direct loopback isolation.").classes("text-sm text-slate-600")
        if lesson == 17:
            from agent_lab.checkpointing import REPLACEMENTS

            tick("checkpointing", "Enable SDK file checkpointing")
            tick("replay_messages", "Replay user messages to capture checkpoint UUIDs")
            select("action", "After the edit", {"rewind": "Rewind the owned file", "inspect": "Inspect only (does not pass restoration check)"}, "rewind")
            select("replacement", "Disposable replacement", {"short": "Short lesson note", "long": "Detailed lesson note"}, "short")
            ui.label().bind_text_from(values["replacement"], "value", lambda value: REPLACEMENTS[value]).classes("text-sm whitespace-pre-wrap break-words")
            ui.label("Only the exact displayed Write to this run's notes.txt is allowed. Offline backups are scripted; live mode uses native rewind. Conversation history is retained. Inspect-only or disabled options need review.").classes("text-sm text-slate-600")
        if lesson == 16:
            select("sources", "Filesystem settings sources", {"none": "None (explicit empty list)", "project": "Owned project fixture", "project-local": "Owned project and local fixtures"}, "none")
            tick("env_override", "Override the non-secret demo environment variable")
            select("demo_value", "Demo environment value", {"alpha": "alpha", "beta": "beta"}, "alpha")
            ui.label("Only host-authored env settings are loaded. The child probe tests process environment, not CLI settings precedence. Inherited environment is not sanitized; credentials are never displayed.").classes("text-sm text-slate-600")
        if lesson == 15:
            tick("omit_turn_limit", "Omit SDK turn limit (host deadline still applies)", False)
            tick("omit_budget_limit", "Omit SDK dollar threshold (not a billing guarantee)", False)
            tick("allow_agent", "Permit the restricted Agent helper tool", False)
            values["task_tokens"] = ui.number("Planning token guidance (blank = omitted)", value=None, min=1, max=100000, precision=0).props("outlined clearable").classes("w-full")
            ui.label("task_budget guides planning; terminal error_max_turns and error_max_budget_usd show enforced stops. Final usage is observed, not predicted.").classes("text-sm text-slate-600")

    def read(*, reset_consent: bool = False) -> dict[str, Any]:
        if mode.value == "live" and lesson in {5, 10}:
            return {}  # Offline-only drafts must not become live tool arguments.
        result = {key: element.value for key, element in values.items()}
        if lesson == 19:
            for key in ("page_size", "offset"):
                if result[key] != int(result[key]):
                    raise ValueError("Choose whole pagination values.")
                result[key] = int(result[key])
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
        if reset_consent and lesson in {44, 45, 46, 47, 48, 49}:
            values["consent"].set_value(False)
        return result

    return read
