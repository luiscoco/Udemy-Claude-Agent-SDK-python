"""Owned project command discovery and invocation experiment for lesson 21."""

import asyncio
import hashlib
from pathlib import Path
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, SystemMessage

from agent_lab.config import Settings
from agent_lab.foundations import Evidence, record_call
from agent_lab.hooks import lesson_hooks, permission_callback
from agent_lab.models import Event, LessonError, RunRequest, lesson_request
from agent_lab.policy import inside

COMMAND = ".claude/commands/lesson-summary.md"
MARKERS = {"summary": "COMMAND_SUMMARY_21", "quiz": "COMMAND_QUIZ_21"}


def command_path(root: Path) -> Path:
    """The one host-authored settings file; model tools still cannot read .claude."""
    return root.resolve() / COMMAND


def command_text(template: str) -> str:
    marker = MARKERS[template]
    instruction = (
        "Summarize the note in three concise bullet points."
        if template == "summary"
        else "Ask two short quiz questions about the note."
    )
    return (
        "---\n"
        "description: Read the owned Python lesson note and respond in the selected format\n"
        "---\n"
        f"Read notes.txt exactly once. {instruction} Include the exact marker {marker} "
        "on its own final line. Do not read any other file.\n"
    )


def prepare(root: Path, template: str) -> dict[str, str]:
    command = command_path(root)
    command.parent.mkdir(parents=True, exist_ok=True)
    command.write_text(command_text(template), encoding="utf-8")
    note = inside(root, "notes.txt")
    return {
        "command": hashlib.sha256(command.read_bytes()).hexdigest(),
        "note": hashlib.sha256(note.read_bytes()).hexdigest(),
    }


def command_options(root: Path, config: Path, request: RunRequest, settings: Settings, permitted: Any, audit: Any) -> ClaudeAgentOptions:
    from agent_lab.sdk import isolated_env, resolve_cli_path

    return ClaudeAgentOptions(
        cwd=str(root.resolve()),
        model=settings.model,
        cli_path=resolve_cli_path(settings) if request.mode == "live" else None,
        tools=["Read"],
        allowed_tools=[],
        setting_sources=["project"] if request.lesson_options["source"] == "project" else [],
        strict_mcp_config=True,
        env=isolated_env(config.resolve()),
        max_turns=request.max_turns,
        max_budget_usd=request.max_budget_usd,
        system_prompt={
            "type": "preset",
            "preset": "claude_code",
            "append": "This is a fixed lesson command experiment. Use only the project command when discovered. Only Read of notes.txt is authorized. Do not inspect command files directly, use other tools, or guess a marker.",
        },
        hooks=lesson_hooks(permitted, audit),
        can_use_tool=permission_callback(permitted),
    )


def command_report(state: Evidence, selected: dict, inventory: list[str] | None, texts: list[str], before: dict, after: dict, closed: bool, prompt: str) -> dict:
    base = state.report()
    marker = MARKERS[selected["template"]]
    discovered = inventory is not None and "lesson-summary" in inventory
    wanted = selected["source"] == "project"
    inventory_ok = inventory is not None and discovered is wanted
    valid_calls = [
        c for c in state.calls
        if c["name"] == "Read"
        and not c.get("parent_tool_use_id")
        and Path(str(c.get("arguments", {}).get("file_path", ""))).resolve() == inside(state.root, "notes.txt")
    ]
    read_ok = (
        len(valid_calls) == 1
        and len(state.calls) == 1
        and len(state.results) == 1
        and state.results[0]["id"] == valid_calls[0]["id"]
        and state.results[0]["run_id"] == state.run_id
        and state.results[0]["is_error"] is False
    )
    marker_seen = any(marker in item for item in texts)
    fixture_ok = before == after
    source_ok = state.configured.get("setting_sources") == (["project"] if wanted else [])
    # An absent project source is a useful observed control, never a passing invocation.
    terminal = state.terminals[-1] if state.terminals else {}
    initialized = state.initialized[-1] if state.initialized else {}
    identity_ok = bool(initialized.get("session_id") and terminal.get("session_id") == initialized.get("session_id"))
    observed = bool(base["experiment_passed"] and identity_ok and closed and fixture_ok and inventory_ok and source_ok)
    passed = bool(observed and wanted and read_ok and marker_seen and prompt == "/lesson-summary")
    return {
        **base,
        "configured": state.configured,
        "command_inventory": inventory,
        "command_discovered": discovered,
        "command_prompt": prompt,
        "command_hash": before["command"],
        "note_hash": before["note"],
        "fixture_hashes_unchanged": fixture_ok,
        "read_correlated": read_ok,
        "marker_observed": marker_seen,
        "marker_label": marker,
        "connection_closed": closed,
        "observation_passed": observed,
        "experiment_passed": passed,
        "check_scope": "The owned command must appear in the SDK inventory, the slash prompt must invoke it, one matching Read must finish successfully, and the final response must include its template marker. The no-project control records absence without passing invocation.",
    }


async def execute_commands(root: Path, request: RunRequest, settings: Settings, emit: Any, config: Path | None = None) -> dict:
    from agent_lab.sdk import message_data, require_live_access

    request = lesson_request(21, request)
    root = await asyncio.to_thread(root.resolve)
    selected = request.lesson_options
    before = prepare(root, selected["template"])
    config = config or root.parent / "config"
    state = Evidence(21, root.parent.name, root, selected, "live SDK stream and actual host callbacks" if request.mode == "live" else "local host effects plus explicitly recorded SDK correlation fixtures", request.max_turns, request.max_budget_usd)

    def permitted(name: str, arguments: dict) -> tuple[bool, str]:
        target = Path(str(arguments.get("file_path", "")))
        allowed = name == "Read" and target.resolve() == inside(root, "notes.txt")
        return allowed, "Only Read of the owned notes.txt fixture is authorized."

    async def audit(kind: str, data: dict) -> None:
        if kind == "hook":
            await emit(Event(kind="command_guard", data={"tool": data.get("tool"), "allowed": data.get("allowed")}))

    if request.mode == "live":
        require_live_access(settings)
    options = command_options(root, config, request, settings, permitted, audit)
    state.configured = {"tools": options.tools, "allowed_tools": options.allowed_tools, "setting_sources": options.setting_sources, "strict_mcp_config": options.strict_mcp_config}
    await emit(Event(kind="options", data={"lesson_id": 21, "sdk_options": state.configured}))
    client = None
    inventory: list[str] | None = None
    texts: list[str] = []
    closed = False
    prompt = "/lesson-summary"
    try:
        if request.mode == "live":
            config.mkdir(parents=True, exist_ok=True)
            client = ClaudeSDKClient(options=options)
            await client.connect()
            info = await client.get_server_info()
            if info is not None:
                inventory = [str(item.get("name", "")).lstrip("/") for item in info.get("commands", []) if isinstance(item, dict)]
            await client.query(prompt)
            async for message in client.receive_response():
                if isinstance(message, SystemMessage) and message.subtype == "api_retry" and message.data.get("error_status") == 401:
                    raise PermissionError("Claude rejected authentication (HTTP 401). No host retry was attempted.")
                data = message_data(message)
                if data["message_class"] == "AssistantMessage":
                    for block in data.get("content", []):
                        if isinstance(block, dict) and isinstance(block.get("text"), str):
                            texts.append(block["text"])
                if data.get("message_class") == "ResultMessage" and isinstance(data.get("result"), str):
                    texts.append(data["result"])
                event = Event(kind="result" if data["message_class"] == "ResultMessage" else "message", data=data)
                state.observe(event)
                await emit(event)
            if not state.report()["experiment_passed"]:
                raise LessonError("Command invocation did not finish with a matching successful SDK result.")
        else:
            inventory = ["lesson-summary"] if selected["source"] == "project" else []
            state.initialized = [{"session_id": "command-fixture"}]
            if selected["source"] == "project":
                record_call(state, "Read", {"file_path": str(inside(root, "notes.txt"))}, "command-read")
                inside(root, "notes.txt").read_text(encoding="utf-8")
                state.results = [{"id": "command-read", "run_id": state.run_id, "is_error": False}]
                texts = [MARKERS[selected["template"]]]
            state.terminals = [{"subtype": "success", "is_error": False, "session_id": "command-fixture"}]
            if request.scenario == "missing-evidence":
                state.terminals.clear()
            elif request.scenario == "wrong-identity":
                state.terminals[-1]["session_id"] = "foreign"
            elif request.scenario == "missing-command":
                inventory.clear()
            elif request.scenario == "missing-invocation":
                texts.clear()
            elif request.scenario == "unmatched-read":
                if state.results:
                    state.results[0]["id"] = "foreign"
    finally:
        try:
            if client is not None:
                await client.disconnect()
            closed = True
        finally:
            after = {"command": hashlib.sha256(command_path(root).read_bytes()).hexdigest(), "note": hashlib.sha256(inside(root, "notes.txt").read_bytes()).hexdigest()}
            report = command_report(state, selected, inventory, texts, before, after, closed, prompt)
            report["scenario"] = request.scenario
            report["expected_check"] = "passed" if report["experiment_passed"] else "needs-review"
            proof = {"experiment": report, "experiment_passed": report["experiment_passed"]}
            async with asyncio.timeout(1):
                await emit(Event(kind="evidence", data={"lesson_id": 21, "result": proof}))
    return proof


async def local_commands(root: Path, request: RunRequest) -> dict:
    async def ignore(event: Event) -> None:
        pass

    return await execute_commands(root, request.model_copy(update={"mode": "offline"}), Settings(), ignore)
