"""Owned CLAUDE.md loading comparisons without exposing the resolved system prompt."""

import asyncio
import hashlib
from pathlib import Path
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, SystemMessage

from agent_lab.config import Settings
from agent_lab.foundations import Evidence
from agent_lab.models import Event, LessonError, RunRequest, lesson_request
from agent_lab.policy import inside

MARKERS = {"alpha": "PROJECT_ALPHA_22", "beta": "PROJECT_BETA_22"}
PROMPT = "Reply with the marker specified by the loaded project instructions. If no project marker is available, reply exactly UNKNOWN. Do not inspect files or use tools."


def memory_text(rule: str) -> str:
    return (
        "# Owned Python lesson instructions\n\n"
        f"For the lesson's marker question, reply with exactly {MARKERS[rule]} and nothing else.\n"
        "This file is written by the lab host. Do not edit it.\n"
    )


def prepare_memory(root: Path, rule: str) -> str:
    path = inside(root, "CLAUDE.md")
    path.write_text(memory_text(rule), encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def memory_options(root: Path, config: Path, request: RunRequest, settings: Settings) -> ClaudeAgentOptions:
    from agent_lab.sdk import isolated_env, resolve_cli_path

    selected = request.lesson_options
    prompt: Any = (
        {"type": "preset", "preset": "claude_code", "append": "Answer the fixed memory comparison question concisely. Do not use tools."}
        if selected["system_mode"] == "preset"
        else "Answer the fixed memory comparison question concisely. Do not use tools."
    )
    return ClaudeAgentOptions(
        cwd=str(root.resolve()),
        model=settings.model,
        cli_path=resolve_cli_path(settings) if request.mode == "live" else None,
        tools=[],
        allowed_tools=[],
        setting_sources=["project"] if selected["source"] == "project" else [],
        strict_mcp_config=True,
        env=isolated_env(config.resolve()),
        system_prompt=prompt,
        max_turns=request.max_turns,
        max_budget_usd=request.max_budget_usd,
    )


def memory_report(state: Evidence, selected: dict, answers: list[str], before: str, after: str, auto_files: list[str], closed: bool) -> dict:
    base = state.report()
    expected_loaded = selected["source"] == "project"
    expected_answer = MARKERS[selected["rule"]] if expected_loaded else "UNKNOWN"
    observed_answer = answers[-1].strip() if answers else None
    configured = state.configured
    source_ok = configured.get("setting_sources") == (["project"] if selected["source"] == "project" else [])
    preset_ok = configured.get("system_mode") == selected["system_mode"]
    env_ok = configured.get("auto_memory_disabled") is True
    terminal = state.terminals[-1] if state.terminals else {}
    init = state.initialized[-1] if state.initialized else {}
    identity_ok = bool(init.get("session_id") and init.get("session_id") == terminal.get("session_id"))
    observed = bool(base["experiment_passed"] and identity_ok and closed and before == after and not auto_files and not state.calls and source_ok and preset_ok and env_ok)
    passed = bool(observed and observed_answer == expected_answer)
    return {
        **base,
        "configured": configured,
        "project_file_hash_before": before,
        "project_file_hash_after": after,
        "project_file_unchanged": before == after,
        "auto_memory_files": auto_files,
        "observed_answer": observed_answer,
        "expected_answer": expected_answer,
        "project_instruction_behavior_observed": observed_answer == expected_answer,
        "connection_closed": closed,
        "observation_passed": observed,
        "experiment_passed": passed,
        "check_scope": "The fixed question compares a host-owned CLAUDE.md marker with project/preset controls, a matching SDK session and a read-only configuration. This tests observed behavior, not the CLI's resolved system prompt or all persistence locations.",
    }


async def execute_memory(root: Path, request: RunRequest, settings: Settings, emit: Any, config: Path | None = None) -> dict:
    from agent_lab.sdk import message_data, require_live_access

    request = lesson_request(22, request)
    root = await asyncio.to_thread(root.resolve)
    selected = request.lesson_options
    before = await asyncio.to_thread(prepare_memory, root, selected["rule"])
    config = config or root.parent / "config"
    state = Evidence(22, root.parent.name, root, selected, "live SDK stream and actual host callbacks" if request.mode == "live" else "local host effects plus explicitly recorded SDK correlation fixtures", request.max_turns, request.max_budget_usd)
    if request.mode == "live":
        require_live_access(settings)
    options = memory_options(root, config, request, settings)
    state.configured = {
        "tools": options.tools,
        "setting_sources": options.setting_sources,
        "system_mode": selected["system_mode"],
        "auto_memory_disabled": options.env.get("CLAUDE_CODE_DISABLE_AUTO_MEMORY") == "1",
        "strict_mcp_config": options.strict_mcp_config,
    }
    await emit(Event(kind="options", data={"lesson_id": 22, "sdk_options": state.configured}))
    client = None
    answers: list[str] = []
    closed = False
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
                raise LessonError("Memory comparison did not finish with a successful SDK result.")
        else:
            state.initialized = [{"session_id": "memory-fixture"}]
            answers = [MARKERS[selected["rule"]] if selected["source"] == "project" else "UNKNOWN"]
            state.terminals = [{"subtype": "success", "is_error": False, "session_id": "memory-fixture"}]
            if request.scenario == "missing-evidence":
                state.terminals.clear()
            elif request.scenario == "wrong-identity":
                state.terminals[-1]["session_id"] = "foreign"
            elif request.scenario == "wrong-answer":
                answers = ["UNKNOWN" if answers[-1] != "UNKNOWN" else MARKERS[selected["rule"]]]
            elif request.scenario == "changed-file":
                inside(root, "CLAUDE.md").write_text("Recorded changed project file\n", encoding="utf-8")
            elif request.scenario == "auto-memory-file":
                config.mkdir(parents=True, exist_ok=True)
                (config / "MEMORY.md").write_text("Recorded auto memory", encoding="utf-8")
    finally:
        try:
            if client is not None:
                await client.disconnect()
            closed = True
        finally:
            after = hashlib.sha256(inside(root, "CLAUDE.md").read_bytes()).hexdigest()
            auto_files = [p.relative_to(config).as_posix() for p in config.rglob("MEMORY.md")] if config.is_dir() else []
            report = memory_report(state, selected, answers, before, after, auto_files, closed)
            report["scenario"] = request.scenario
            report["expected_check"] = "passed" if report["experiment_passed"] else "needs-review"
            proof = {"experiment": report, "experiment_passed": report["experiment_passed"]}
            async with asyncio.timeout(1):
                await emit(Event(kind="evidence", data={"lesson_id": 22, "result": proof}))
    return proof


async def local_memory(root: Path, request: RunRequest) -> dict:
    async def ignore(event: Event) -> None:
        pass

    return await execute_memory(root, request.model_copy(update={"mode": "offline"}), Settings(), ignore)
