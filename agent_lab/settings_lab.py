"""Owned settings fixtures, a real child-process env probe and bounded SDK evidence."""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, SystemMessage

from agent_lab.config import Settings
from agent_lab.doctor import resolve_cli_path
from agent_lab.foundations import Evidence
from agent_lab.models import Event, LessonError, RunRequest, lesson_request

MARKER = "LAB_SETTINGS_DEMO"


def settings_options(
    root: Path, config: Path, request: RunRequest, settings: Settings
) -> ClaudeAgentOptions:
    """Only host-authored files and one non-secret env variable can be selected."""
    from agent_lab.sdk import isolated_env

    selected = lesson_request(16, request).lesson_options
    folder = root / ".claude"
    folder.mkdir(parents=True, exist_ok=True)
    for filename, value in (("settings.json", "project"), ("settings.local.json", "local")):
        (folder / filename).write_text(json.dumps({"env": {MARKER: value}}), encoding="utf-8")
    sources = {"none": [], "project": ["project"], "project-local": ["project", "local"]}
    env = isolated_env(config.resolve())
    if selected["env_override"]:
        env[MARKER] = selected["demo_value"]
    return ClaudeAgentOptions(
        cwd=str(root.resolve()),
        setting_sources=sources[selected["sources"]],  # type: ignore[arg-type]
        env=env,
        tools=["Read"],
        allowed_tools=[],
        strict_mcp_config=True,
        model=settings.model,
        cli_path=resolve_cli_path(settings) if request.mode == "live" else None,
        max_turns=request.max_turns,
        max_budget_usd=request.max_budget_usd,
        system_prompt="Teach settings isolation. Read notes.txt before answering. Do not claim to inspect environment variables; no shell tool is available.",
    )


async def probe_environment(options: ClaudeAgentOptions) -> dict[str, Any]:
    """Observe env overlay in a Python child, without resolving CLI settings or printing secrets."""
    names = [MARKER, "CLAUDE_CONFIG_DIR", "CLAUDE_CODE_DISABLE_AUTO_MEMORY"]
    script = "import json,os,sys; print(json.dumps({n:os.getenv(n) for n in sys.argv[1:]}))"
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        script,
        *names,
        cwd=options.cwd,
        env={**os.environ, **options.env},
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        async with asyncio.timeout(10):
            stdout, _ = await process.communicate()
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()
    if process.returncode != 0:
        raise LessonError("The isolated environment probe failed.")
    observed = json.loads(stdout)
    # An inherited demo value may contain arbitrary host data: never return it.
    return {
        "source": "actual Python child process; not CLI settings resolution",
        "config_matches": observed["CLAUDE_CONFIG_DIR"] == options.env["CLAUDE_CONFIG_DIR"],
        "auto_memory_disabled": observed["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] == "1",
        "demo_override_matches": observed[MARKER] == options.env[MARKER]
        if MARKER in options.env
        else None,
    }


def settings_report(evidence: Evidence, probe: dict[str, Any], closed: bool) -> dict[str, Any]:
    """Configuration and child-env checks never assert that CLI settings were applied."""
    report = evidence.report()
    selected = evidence.selected
    expected = {"none": [], "project": ["project"], "project-local": ["project", "local"]}[
        selected["sources"]
    ]
    paired_read = any(
        call["name"] == "Read"
        and not call.get("parent_tool_use_id")
        and call.get("run_id") == evidence.run_id
        and (evidence.root / str(call["arguments"].get("file_path", ""))).resolve()
        == (evidence.root / "notes.txt").resolve()
        and sum(other["id"] == call["id"] for other in evidence.calls) == 1
        and sum(result["id"] == call["id"] for result in evidence.results) == 1
        and any(
            result["id"] == call["id"]
            and result["run_id"] == evidence.run_id
            and result["is_error"] is False
            for result in evidence.results
        )
        for call in evidence.calls
    )
    passed = bool(
        report["experiment_passed"]
        and evidence.initialized
        and evidence.configured.get("setting_sources") == expected
        and evidence.configured.get("tools") == ["Read"]
        and probe.get("config_matches") is True
        and probe.get("auto_memory_disabled") is True
        and (not selected["env_override"] or probe.get("demo_override_matches") is True)
        and paired_read
        and closed
    )
    report.update(
        experiment_passed=passed,
        environment_probe=probe,
        connection_closed=closed,
        check_scope="Selected SDK sources, isolated child environment, matching parent session and Read result, terminal success and connection closure. This does not certify CLI settings precedence, model adherence or a sanitized inherited environment.",
        expected_check="passed" if passed else "needs-review",
    )
    return report


async def execute_settings(
    root: Path, request: RunRequest, settings: Settings, emit: Any, config: Path | None = None
) -> dict[str, Any]:
    from agent_lab.hooks import lesson_hooks, permission_callback
    from agent_lab.policy import decide
    from agent_lab.sdk import ClaudeSDKClient, message_data, require_live_access

    request = lesson_request(16, request)
    live = request.mode == "live"
    if live:
        require_live_access(settings)
    config = config or root.parent / "settings-config"
    config.mkdir(parents=True, exist_ok=True)
    options = settings_options(root, config, request, settings)
    state = Evidence(
        16,
        root.parent.name,
        root,
        request.lesson_options,
        "live SDK stream and actual host callbacks"
        if live
        else "local host effects plus explicitly recorded SDK identities",
    )
    state.configured = {
        "setting_sources": options.setting_sources,
        "tools": options.tools,
        "environment": {
            "demo_override": request.lesson_options["env_override"],
            "private_config": True,
        },
    }
    probe = await probe_environment(options)
    await emit(Event(kind="options", data={"lesson_id": 16, "sdk_options": state.configured}))
    client = None
    closed = False
    try:
        if live:

            def permitted(name: str, args: dict) -> tuple[bool, str]:
                if name != "Read":
                    return False, "Only Read is available."
                return decide(root, name, args)

            async def audit(kind: str, data: dict) -> None:
                await emit(Event(kind=kind, data=data))

            async def no_questions(args: dict) -> dict:
                return {}

            options.can_use_tool = permission_callback(permitted, no_questions)
            options.hooks = lesson_hooks(permitted, audit)
            client = ClaudeSDKClient(options=options)
            await client.connect()
            await client.query(request.prompt)
            async for message in client.receive_response():
                if (
                    isinstance(message, SystemMessage)
                    and message.subtype == "api_retry"
                    and message.data.get("error_status") == 401
                ):
                    raise PermissionError("Claude rejected authentication (HTTP 401). No host retry was attempted.")
                data = message_data(message)
                event = Event(
                    kind="result" if data["message_class"] == "ResultMessage" else "message",
                    data=data,
                )
                state.observe(event)
                await emit(event)
            if (
                not state.terminals
                or state.terminals[-1].get("is_error") is not False
                or state.terminals[-1].get("subtype") != "success"
            ):
                raise LessonError(
                    "The settings experiment did not finish successfully. Inspect the terminal evidence."
                )
        else:
            # Local file read is real; SDK session and call identities below are fixtures.
            (root / "notes.txt").read_text(encoding="utf-8")
            state.initialized = [{"session_id": "settings-fixture", "tools": ["Read"]}]
            state.calls = [
                {
                    "id": "read-fixture",
                    "name": "Read",
                    "arguments": {"file_path": str((root / "notes.txt").resolve())},
                    "run_id": state.run_id,
                }
            ]
            state.results = [{"id": "read-fixture", "is_error": False, "run_id": state.run_id}]
            state.terminals = [
                {"subtype": "success", "is_error": False, "session_id": "settings-fixture"}
            ]
            if request.scenario == "missing-evidence":
                state.terminals.clear()
            elif request.scenario == "wrong-identity":
                state.terminals[0]["session_id"] = "foreign-session"
            elif request.scenario == "wrong-environment":
                probe["config_matches"] = False
            elif request.scenario == "unmatched-read":
                state.results[0]["id"] = "foreign-call"
    finally:
        try:
            if client is not None:
                await client.disconnect()
            closed = True
        finally:
            report = settings_report(state, probe, closed)
            report["scenario"] = request.scenario
            proof = {"experiment": report, "experiment_passed": report["experiment_passed"]}
            async with asyncio.timeout(1):
                await emit(Event(kind="evidence", data={"lesson_id": 16, "result": proof}))
    return proof


async def local_settings(root: Path, request: RunRequest) -> dict[str, Any]:
    async def ignore(event: Event) -> None:
        pass

    return await execute_settings(
        root, request.model_copy(update={"mode": "offline"}), Settings(), ignore
    )
