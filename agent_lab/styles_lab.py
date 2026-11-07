"""Owned output-style loading and behavioral comparison."""

import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, SystemMessage

from agent_lab.config import Settings
from agent_lab.foundations import Evidence
from agent_lab.models import Event, RunRequest, lesson_request

MARKERS = {"teaching": "STYLE_TEACHING_34", "brief": "STYLE_BRIEF_34"}
PROMPT = "For the lesson 34 style check, reply with exactly the marker required by the active project output style. If no project output style is loaded, reply exactly STYLE_NONE_34. Use no tools and add no explanation."


def owned(root: Path, relative: str) -> Path:
    base = root.resolve()
    path = (base / relative).resolve()
    if not path.is_relative_to(base):
        raise ValueError("Style path escapes the owned lesson workspace.")
    return path


def style_text(style: str) -> str:
    return (f"---\nname: {style}\ndescription: Owned {style} lesson style\n---\n"
            f"For the lesson 34 style check, reply exactly {MARKERS[style]} and nothing else. "
            "This output style changes response wording only; it grants no tools.\n")


def prepare_style(root: Path, style: str) -> dict[str, str]:
    folder = owned(root, ".claude/output-styles")
    folder.mkdir(parents=True, exist_ok=True)
    document = owned(root, f".claude/output-styles/{style}.md")
    document.write_bytes(style_text(style).encode("utf-8"))
    settings = owned(root, ".claude/settings.json")
    settings.write_bytes(json.dumps({"outputStyle": style}).encode("utf-8"))
    return {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (document, settings)}


def style_options(root: Path, config: Path, request: RunRequest, settings: Settings) -> ClaudeAgentOptions:
    from agent_lab.sdk import isolated_env, resolve_cli_path

    return ClaudeAgentOptions(
        cwd=str(root.resolve()), model=settings.model,
        cli_path=resolve_cli_path(settings) if request.mode == "live" else None,
        tools=[], allowed_tools=[], setting_sources=["project"] if request.lesson_options["source"] == "project" else [],
        strict_mcp_config=True, env=isolated_env(config.resolve()),
        system_prompt={"type": "preset", "preset": "claude_code", "append": "Answer the fixed output-style comparison using no tools."},
        max_turns=request.max_turns, max_budget_usd=request.max_budget_usd,
    )


def style_report(state: Evidence, selected: dict[str, str], answer: str | None,
                 before: dict[str, str], after: dict[str, str], closed: bool) -> dict[str, Any]:
    base = state.report()
    expected = MARKERS[selected["style"]] if selected["source"] == "project" else "STYLE_NONE_34"
    init = state.initialized[-1] if state.initialized else {}
    terminal = state.terminals[-1] if state.terminals else {}
    session_ok = bool(init.get("session_id") and terminal.get("session_id") == init["session_id"])
    observed_style = init.get("output_style")
    expected_style = selected["style"] if selected["source"] == "project" else "default"
    style_init_ok = state.source != "live SDK stream and actual host callbacks" or observed_style == expected_style
    configured_ok = bool(state.configured.get("setting_sources") == (["project"] if selected["source"] == "project" else [])
                         and state.configured.get("tools") == [] and state.configured.get("allowed_tools") == []
                         and state.configured.get("auto_memory_disabled") is True)
    style_path = f".claude/output-styles/{selected['style']}.md"
    file_ok = bool(before == after and len(before) == 2
        and before.get(style_path) == hashlib.sha256(style_text(selected["style"]).encode()).hexdigest()
        and before.get(".claude/settings.json") == hashlib.sha256(json.dumps({"outputStyle": selected["style"]}).encode()).hexdigest())
    observed = bool(base["experiment_passed"] and session_ok and style_init_ok and configured_ok and file_ok and not state.calls and closed)
    passed = bool(observed and answer == expected)
    return {**base, "selected": selected, "configured": state.configured,
            "file_hashes_before": before, "file_hashes_after": after,
            "project_files_unchanged": file_ok, "observed_answer": answer,
            "expected_answer": expected, "style_behavior_observed": answer == expected,
            "observed_output_style": observed_style, "expected_output_style": expected_style,
            "sdk_style_verified": style_init_ok,
            "session_verified": session_ok, "connection_closed": closed,
            "observation_passed": observed, "experiment_passed": passed,
            "check_scope": "The host creates one owned output-style file and a selecting settings.json, hashes both, and compares a fixed marker answer with project settings enabled or disabled. The SDK session and terminal must match, no model tool may run, and the files must remain unchanged. This observes behavior, not the full resolved prompt or a general style permission boundary."}


async def execute_styles(root: Path, request: RunRequest, settings: Settings, emit: Any,
                         config: Path | None = None) -> dict[str, Any]:
    from agent_lab.sdk import message_data, require_live_access

    request = lesson_request(34, request)
    root = await asyncio.to_thread(root.resolve)
    selected = request.lesson_options
    before = await asyncio.to_thread(prepare_style, root, selected["style"])
    config = config or root.parent / "config"
    state = Evidence(34, root.parent.name, root, selected,
        "live SDK stream and actual host callbacks" if request.mode == "live" else "local host files and explicitly recorded SDK fixtures",
        request.max_turns, request.max_budget_usd)
    if request.mode == "live":
        require_live_access(settings)
    options = style_options(root, config, request, settings)
    state.configured = {"tools": options.tools, "allowed_tools": options.allowed_tools,
                        "setting_sources": options.setting_sources, "strict_mcp_config": options.strict_mcp_config,
                        "auto_memory_disabled": options.env.get("CLAUDE_CODE_DISABLE_AUTO_MEMORY") == "1"}
    await emit(Event(kind="options", data={"lesson_id": 34, "sdk_options": state.configured}))
    client = None
    closed = False
    answer: str | None = None
    try:
        if request.mode == "live":
            config.mkdir(parents=True, exist_ok=True)
            client = ClaudeSDKClient(options=options)
            await client.connect()
            await client.query(PROMPT)
            async for message in client.receive_response():
                if isinstance(message, SystemMessage) and message.subtype == "api_retry" and message.data.get("error_status") == 401:
                    raise PermissionError("Claude rejected authentication (HTTP 401). No host retry was attempted.")
                data = message_data(message)
                if data["message_class"] == "ResultMessage" and isinstance(data.get("result"), str):
                    answer = data["result"].strip()
                event = Event(kind="result" if data["message_class"] == "ResultMessage" else "message", data=data)
                state.observe(event)
                await emit(event)
        else:
            answer = MARKERS[selected["style"]] if selected["source"] == "project" else "STYLE_NONE_34"
            state.initialized = [{"session_id": "style-fixture"}]
            state.terminals = [{"session_id": "style-fixture", "subtype": "success", "is_error": False}]
            if request.scenario == "missing-evidence":
                state.terminals.clear()
            elif request.scenario == "wrong-identity":
                state.terminals[0]["session_id"] = "foreign"
            elif request.scenario == "wrong-answer":
                answer = "OTHER_34"
            elif request.scenario == "changed-style":
                owned(root, f".claude/output-styles/{selected['style']}.md").write_text("Changed recorded style\n", encoding="utf-8")
            elif request.scenario == "wrong-source":
                state.configured["setting_sources"] = [] if selected["source"] == "project" else ["project"]
    finally:
        if client is not None:
            await client.disconnect()
        closed = True
        after = {name: hashlib.sha256(owned(root, name).read_bytes()).hexdigest() for name in before}
        report = style_report(state, selected, answer, before, after, closed)
        report["scenario"] = request.scenario
        report["expected_check"] = "passed" if report["experiment_passed"] else "needs-review"
        proof = {"experiment": report, "experiment_passed": report["experiment_passed"]}
        await emit(Event(kind="evidence", data={"lesson_id": 34, "result": proof}))
    return proof


async def local_styles(root: Path, request: RunRequest) -> dict[str, Any]:
    async def ignore(event: Event) -> None:
        pass

    return await execute_styles(root, request.model_copy(update={"mode": "offline"}), Settings(), ignore)
