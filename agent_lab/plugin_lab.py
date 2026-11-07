"""Owned local-plugin discovery, namespaced commands and Skill invocation."""

import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, SystemMessage

from agent_lab.config import Settings
from agent_lab.foundations import Evidence, record_call
from agent_lab.hooks import lesson_hooks, permission_callback
from agent_lab.models import Event, LessonError, RunRequest, lesson_request

PLUGIN = "python-teaching"
SKILL = f"{PLUGIN}:python-example"
MARKERS = {"explain": "PLUGIN_EXPLAIN_23", "quiz": "PLUGIN_QUIZ_23", "skill": "PLUGIN_SKILL_23"}
NAMES = {"explain": f"{PLUGIN}:explain", "quiz": f"{PLUGIN}:quiz"}


def prepare_plugin(root: Path) -> tuple[Path, dict[str, str]]:
    directory = root.resolve() / "teaching-plugin"
    files = {
        ".claude-plugin/plugin.json": json.dumps({"name": PLUGIN, "version": "1.0.0", "description": "Owned Python lesson plugin"}),
        "commands/explain.md": f"Explain the owned Python lesson briefly. Reply with exactly {MARKERS['explain']} and nothing else.\n",
        "commands/quiz.md": f"Create a tiny Python quiz. Reply with exactly {MARKERS['quiz']} and nothing else.\n",
        "skills/python-example/SKILL.md": (
            "---\nname: python-example\ndescription: Give the fixed Python lesson skill marker when asked to invoke this skill.\n---\n"
            f"After invocation, answer with exactly {MARKERS['skill']} and nothing else.\n"
        ),
    }
    for relative, value in files.items():
        target = directory / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(value, encoding="utf-8")
    hashes = {relative: hashlib.sha256((directory / relative).read_bytes()).hexdigest() for relative in files}
    return directory, hashes


def plugin_options(root: Path, directory: Path, config: Path, request: RunRequest, settings: Settings, permitted: Any, audit: Any) -> ClaudeAgentOptions:
    from agent_lab.sdk import isolated_env, resolve_cli_path

    selected = request.lesson_options
    enabled = selected["enabled"]
    skill_action = selected["action"] == "skill"
    return ClaudeAgentOptions(
        cwd=str(root.resolve()),
        model=settings.model,
        cli_path=resolve_cli_path(settings) if request.mode == "live" else None,
        plugins=[{"type": "local", "path": str(directory)}] if enabled else [],
        skills=[SKILL] if enabled and skill_action else [],
        tools=["Skill"] if skill_action else [],
        allowed_tools=[],
        setting_sources=[],
        strict_mcp_config=True,
        env=isolated_env(config.resolve()),
        system_prompt={"type": "preset", "preset": "claude_code", "append": "This is a fixed plugin lesson. Invoke only the selected owned extension. Do not read files or use other tools. Reply briefly."},
        hooks=lesson_hooks(permitted, audit),
        can_use_tool=permission_callback(permitted),
        max_turns=request.max_turns,
        max_budget_usd=request.max_budget_usd,
    )


def plugin_prompt(action: str) -> str:
    if action == "skill":
        return f"Invoke the {SKILL} skill with the Skill tool, then follow its instruction."
    return "/" + NAMES[action]


def plugin_report(state: Evidence, selected: dict, inventory: list[str] | None, answers: list[str], before: dict, after: dict, closed: bool) -> dict:
    base = state.report()
    action, enabled = selected["action"], selected["enabled"]
    marker = MARKERS[action]
    configured = state.configured
    name = NAMES.get(action)
    discovered = inventory is not None and name in inventory if name else None
    inventory_ok = inventory is not None and (discovered is enabled if name else True)
    answer = answers[-1].strip() if answers else None
    terminal = state.terminals[-1] if state.terminals else {}
    init = state.initialized[-1] if state.initialized else {}
    identity_ok = bool(init.get("session_id") and init.get("session_id") == terminal.get("session_id"))
    settings_ok = (
        configured.get("plugins") == ([PLUGIN] if enabled else [])
        and configured.get("setting_sources") == []
        and configured.get("tools") == (["Skill"] if action == "skill" else [])
    )
    candidates = [c for c in state.calls if c["name"] == "Skill" and c.get("arguments", {}).get("skill") == SKILL and not c.get("parent_tool_use_id")]
    skill_call_ok = (
        len(candidates) == 1
        and len(state.calls) == 1
        and len(state.results) == 1
        and state.results[0].get("id") == candidates[0].get("id")
        and state.results[0].get("run_id") == state.run_id
        and state.results[0].get("is_error") is False
    )
    tool_ok = skill_call_ok if action == "skill" else not state.calls
    observed = bool(base["experiment_passed"] and closed and before == after and identity_ok and settings_ok and inventory_ok and tool_ok)
    passed = bool(observed and enabled and answer == marker)
    if not enabled:
        passed = bool(observed and action != "skill" and answer != marker)
    return {
        **base,
        "configured": configured,
        "plugin_file_hashes": before,
        "plugin_files_unchanged": before == after,
        "command_inventory": inventory,
        "command_discovered": discovered,
        "skill_call_correlated": skill_call_ok,
        "observed_answer": answer,
        "marker_label": marker,
        "connection_closed": closed,
        "observation_passed": observed,
        "experiment_passed": passed,
        "check_scope": "The owned plugin must be explicitly configured, its command discovered and invoked or its named Skill call/result correlated, with unchanged files and a matching SDK session. The disabled-plugin control checks absence of its command.",
    }


async def execute_plugin(root: Path, request: RunRequest, settings: Settings, emit: Any, config: Path | None = None) -> dict:
    from agent_lab.sdk import message_data, require_live_access

    request = lesson_request(23, request)
    root = await asyncio.to_thread(root.resolve)
    selected = request.lesson_options
    directory, before = await asyncio.to_thread(prepare_plugin, root)
    config = config or root.parent / "config"
    state = Evidence(23, root.parent.name, root, selected, "live SDK stream and actual host callbacks" if request.mode == "live" else "local host effects plus explicitly recorded SDK correlation fixtures", request.max_turns, request.max_budget_usd)

    def permitted(name: str, arguments: dict) -> tuple[bool, str]:
        return name == "Skill" and arguments.get("skill") == SKILL and selected["enabled"] and selected["action"] == "skill", "Only the selected owned plugin Skill is authorized."

    async def audit(kind: str, data: dict) -> None:
        if kind == "hook":
            await emit(Event(kind="plugin_guard", data={"tool": data.get("tool"), "allowed": data.get("allowed")}))

    if request.mode == "live":
        require_live_access(settings)
    options = plugin_options(root, directory, config, request, settings, permitted, audit)
    state.configured = {"plugins": [PLUGIN] if options.plugins else [], "skills": options.skills, "tools": options.tools, "setting_sources": options.setting_sources, "strict_mcp_config": options.strict_mcp_config}
    await emit(Event(kind="options", data={"lesson_id": 23, "sdk_options": state.configured}))
    client = None
    inventory: list[str] | None = None
    answers: list[str] = []
    closed = False
    try:
        if request.mode == "live":
            config.mkdir(parents=True, exist_ok=True)
            client = ClaudeSDKClient(options=options)
            await client.connect()
            info = await client.get_server_info()
            if info is not None:
                inventory = [str(item.get("name", "")).lstrip("/") for item in info.get("commands", []) if isinstance(item, dict)]
            await client.query(plugin_prompt(selected["action"]))
            async for message in client.receive_response():
                if isinstance(message, SystemMessage) and message.subtype == "api_retry" and message.data.get("error_status") == 401:
                    raise PermissionError("Claude rejected authentication (HTTP 401). No host retry was attempted.")
                data = message_data(message)
                if data["message_class"] == "AssistantMessage":
                    for block in data.get("content", []):
                        if isinstance(block, dict) and isinstance(block.get("text"), str):
                            answers.append(block["text"])
                if data["message_class"] == "ResultMessage" and isinstance(data.get("result"), str):
                    answers.append(data["result"])
                event = Event(kind="result" if data["message_class"] == "ResultMessage" else "message", data=data)
                state.observe(event)
                await emit(event)
            if not state.report()["experiment_passed"]:
                raise LessonError("Plugin run did not finish with a successful SDK result.")
        else:
            inventory = list(NAMES.values()) if selected["enabled"] else []
            state.initialized = [{"session_id": "plugin-fixture"}]
            if selected["enabled"]:
                answers = [MARKERS[selected["action"]]]
                if selected["action"] == "skill":
                    record_call(state, "Skill", {"skill": SKILL}, "plugin-skill")
                    state.results = [{"id": "plugin-skill", "run_id": state.run_id, "is_error": False}]
            else:
                answers = ["UNKNOWN"]
            state.terminals = [{"session_id": "plugin-fixture", "subtype": "success", "is_error": False}]
            if request.scenario == "missing-evidence":
                state.terminals.clear()
            elif request.scenario == "wrong-identity":
                state.terminals[-1]["session_id"] = "foreign"
            elif request.scenario == "missing-discovery":
                inventory.clear()
            elif request.scenario == "wrong-marker":
                answers = ["UNKNOWN"]
            elif request.scenario == "unmatched-skill":
                if not state.results:
                    record_call(state, "Skill", {"skill": SKILL}, "unexpected-skill")
                    state.results = [{"id": "foreign", "run_id": state.run_id, "is_error": False}]
                else:
                    state.results[0]["id"] = "foreign"
    finally:
        try:
            if client is not None:
                await client.disconnect()
            closed = True
        finally:
            after = {relative: hashlib.sha256((directory / relative).read_bytes()).hexdigest() for relative in before}
            report = plugin_report(state, selected, inventory, answers, before, after, closed)
            report["scenario"] = request.scenario
            report["expected_check"] = "passed" if report["experiment_passed"] else "needs-review"
            proof = {"experiment": report, "experiment_passed": report["experiment_passed"]}
            async with asyncio.timeout(1):
                await emit(Event(kind="evidence", data={"lesson_id": 23, "result": proof}))
    return proof


async def local_plugin(root: Path, request: RunRequest) -> dict:
    async def ignore(event: Event) -> None:
        pass

    return await execute_plugin(root, request.model_copy(update={"mode": "offline"}), Settings(), ignore)
