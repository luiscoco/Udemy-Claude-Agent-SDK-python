"""Owned session catalog experiments with actual public SDK persistence operations."""

import asyncio
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any
from uuid import UUID

from claude_agent_sdk import ClaudeAgentOptions, SystemMessage, project_key_for_directory

from agent_lab.config import Settings
from agent_lab.foundations import Evidence
from agent_lab.models import Event, LessonError, RunRequest, lesson_request
from agent_lab.policy import redact

FIXTURE_SESSION = "00000000-0000-4000-8000-000000000019"


def catalog_options(
    work: Path, config: Path, request: RunRequest, settings: Settings
) -> ClaudeAgentOptions:
    from agent_lab.sdk import isolated_env, resolve_cli_path

    return ClaudeAgentOptions(
        cwd=str(work.resolve()),
        model=settings.model,
        cli_path=resolve_cli_path(settings) if request.mode == "live" else None,
        tools=[],
        allowed_tools=[],
        setting_sources=[],
        strict_mcp_config=True,
        env=isolated_env(config.resolve()),
        max_turns=request.max_turns,
        max_budget_usd=request.max_budget_usd,
        system_prompt="Reply briefly to the user. This session is a disposable session-management experiment. No tools are available; do not claim any file or catalog operation ran.",
    )


def write_catalog_fixture(work: Path, config: Path, prompt: str) -> str:
    """A labelled, correctly keyed transcript; not a fake live session or provider call."""
    folder = config / "projects" / project_key_for_directory(str(work.resolve()))
    folder.mkdir(parents=True, exist_ok=True)
    parent = "00000000-0000-4000-8000-000000000001"
    common = {
        "sessionId": FIXTURE_SESSION,
        "cwd": str(work.resolve()),
        "timestamp": "2026-11-03T00:00:00.000Z",
    }
    rows = [
        {
            **common,
            "type": "user",
            "uuid": parent,
            "parentUuid": None,
            "message": {"role": "user", "content": prompt},
        },
        {
            **common,
            "type": "assistant",
            "uuid": "00000000-0000-4000-8000-000000000002",
            "parentUuid": parent,
            "message": {
                "role": "assistant",
                "model": "recorded-fixture",
                "content": [{"type": "text", "text": "Recorded session catalog fixture."}],
            },
        },
    ]
    (folder / f"{FIXTURE_SESSION}.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8"
    )
    return FIXTURE_SESSION


async def operate_catalog(
    work: Path, config: Path, session_id: str, request: RunRequest, prompt_digest: str
) -> dict:
    """Never mutate server environment or accept a caller-selected session/config/project path."""
    config_path = await asyncio.to_thread(config.resolve)
    project_path = await asyncio.to_thread(work.resolve)
    payload = {
        "config": str(config_path),
        "project": str(project_path),
        "session_id": str(UUID(session_id)),
        "prompt_digest": prompt_digest,
        **request.lesson_options,
    }
    script = Path(__file__).with_name("session_catalog_child.py")
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-I",
        str(script),
        env={**os.environ, "CLAUDE_CONFIG_DIR": str(config_path)},
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        async with asyncio.timeout(30):
            stdout, _ = await process.communicate(json.dumps(payload).encode())
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()
    try:
        data = json.loads(stdout)
    except ValueError as exc:
        raise LessonError("The isolated session catalog returned no valid report.") from exc
    if process.returncode != 0:
        raise LessonError(
            "The isolated SDK catalog could not establish ownership or complete the operation."
        )
    return redact(data)


def catalog_report(state: Evidence, catalog: dict, closed: bool, prompt_digest: str) -> dict:
    """Observed persistence, isolation, pagination and operation effects are required."""
    report = state.report()
    before, after, mutation = (catalog.get(key, {}) for key in ("before", "after", "mutation"))
    selected = state.selected
    terminal = state.terminals[-1] if state.terminals else {}
    session_id = terminal.get("session_id")
    original_uuids = before.get("message_uuids", [])
    base = bool(
        report["experiment_passed"]
        and state.initialized
        and closed
        and before.get("session_id") == session_id
        and before.get("info_session_id") == session_id
        and before.get("info_found") is True
        and session_id in before.get("catalog_session_ids", [])
        and before.get("message_session_ids") == [session_id]
        and before.get("first_user_digest") == prompt_digest
        and {"user", "assistant"}.issubset(before.get("message_types", []))
        and original_uuids
        and len(set(original_uuids)) == len(original_uuids)
        and len(original_uuids) == before.get("message_count")
        and isinstance(before.get("visible_content_digest"), str)
        and len(before["visible_content_digest"]) == 64
        and before.get("session_page_matches") is True
        and before.get("message_page_matches") is True
        and after.get("session_page_matches") is True
        and after.get("message_page_matches") is True
        and catalog.get("isolation")
        == {"empty_config_session_count": 0, "other_project_session_count": 0}
        and mutation.get("target_session_id") == session_id
        and mutation.get("action") == selected["action"]
        and state.configured.get("tools") == []
        and state.configured.get("setting_sources") == []
    )
    action = selected["action"]
    retained = (
        after.get("info_found") is True
        and after.get("info_session_id") == session_id
        and after.get("message_session_ids") == [session_id]
        and after.get("message_uuids") == original_uuids
        and after.get("visible_content_digest") == before.get("visible_content_digest")
    )
    operation_passed = False
    if action == "inspect":
        operation_passed = retained and mutation.get("original_file_unchanged") is True
    elif action == "rename-tag":
        operation_passed = (
            retained
            and mutation.get("original_file_unchanged") is False
            and after.get("title") == selected["title"]
            and after.get("tag") == selected["tag"]
            and after.get("visible_content_digest") == before.get("visible_content_digest")
            and after.get("message_uuids") == original_uuids
        )
    elif action == "fork":
        fork = mutation.get("fork", {})
        fork_id = mutation.get("fork_session_id")
        fork_uuids = fork.get("message_uuids", [])
        operation_passed = bool(
            retained
            and fork_id
            and fork_id != session_id
            and fork.get("session_id") == fork_id
            and fork.get("info_found") is True
            and fork.get("info_session_id") == fork_id
            and fork.get("title") == selected["title"]
            and fork.get("message_session_ids") == [fork_id]
            and fork.get("visible_content_digest") == before.get("visible_content_digest")
            and len(fork_uuids) == len(original_uuids)
            and set(fork_uuids).isdisjoint(original_uuids)
            and fork.get("session_page_matches") is True
            and fork.get("message_page_matches") is True
            and mutation.get("original_file_unchanged") is True
        )
    elif action == "delete":
        operation_passed = (
            after.get("info_found") is False
            and after.get("message_count") == 0
            and after.get("message_uuids") == []
            and after.get("message_session_ids") == []
            and session_id not in after.get("catalog_session_ids", [])
            and mutation.get("original_file_exists") is False
        )
    passed = base and operation_passed
    report.update(
        catalog=catalog,
        experiment_passed=passed,
        expected_check="passed" if passed else "needs-review",
        connection_closed=closed,
        check_scope="A successful owned parent session was closed, then actual public SDK catalog functions confirmed identity, original prompt digest, pagination, empty-config/project isolation and the selected local operation. Offline transcripts and SDK identities are labelled fixtures. Catalog mutations do not roll back workspace files or authorize unrelated transcripts.",
    )
    return report


async def execute_catalog(
    work: Path, request: RunRequest, settings: Settings, emit: Any, config: Path | None = None
) -> dict:
    from agent_lab.hooks import lesson_hooks, permission_callback
    from agent_lab.sdk import ClaudeSDKClient, message_data, require_live_access

    request = lesson_request(19, request)
    live = request.mode == "live"
    if live:
        require_live_access(settings)
    config = config or work.parent / "catalog-config"
    config.mkdir(parents=True, exist_ok=True)
    prompt = request.prompt + "\nReply briefly: SESSION-CATALOG-OK."
    prompt_digest = hashlib.sha256(prompt.encode()).hexdigest()
    options = catalog_options(work, config, request, settings)
    state = Evidence(
        19,
        work.parent.name,
        work,
        request.lesson_options,
        "live SDK stream and actual host callbacks"
        if live
        else "actual public SDK file operations with explicitly recorded transcript and session identities",
    )
    state.configured = {
        "tools": options.tools,
        "setting_sources": options.setting_sources,
        "strict_mcp_config": options.strict_mcp_config,
    }
    client = None
    closed = False
    catalog = {}

    async def audit(kind, data):
        await emit(Event(kind=kind, data=data))

    async def no_questions(args):
        return {}

    def permitted(name, args):
        return False, "No model tool is available in the session catalog lesson."

    options.hooks = lesson_hooks(permitted, audit)
    options.can_use_tool = permission_callback(permitted, no_questions)
    await emit(Event(kind="options", data={"lesson_id": 19, "sdk_options": state.configured}))
    try:
        try:
            if live:
                client = ClaudeSDKClient(options=options)
                await client.connect()
                await client.query(prompt)
                async for message in client.receive_response():
                    if (
                        isinstance(message, SystemMessage)
                        and message.subtype == "api_retry"
                        and message.data.get("error_status") == 401
                    ):
                        raise PermissionError(
                            "Claude rejected authentication (HTTP 401). No host retry was attempted."
                        )
                    data = message_data(message)
                    event = Event(
                        kind="result" if data["message_class"] == "ResultMessage" else "message",
                        data=data,
                    )
                    state.observe(event)
                    await emit(event)
            else:
                session_id = write_catalog_fixture(work, config, prompt)
                state.initialized = [{"session_id": session_id}]
                state.terminals = [
                    {"subtype": "success", "is_error": False, "session_id": session_id}
                ]
                if request.scenario == "missing-evidence":
                    state.terminals.clear()
                elif request.scenario == "wrong-identity":
                    state.terminals[-1]["session_id"] = "00000000-0000-4000-8000-000000000099"
        finally:
            if client is not None:
                await client.disconnect()
            closed = True
        if not state.report()["experiment_passed"] or not state.initialized:
            if live:
                raise LessonError(
                    "Session catalog requires a matching successful parent result; no catalog operation was attempted."
                )
        else:
            session_id = state.terminals[-1]["session_id"]
            catalog = await operate_catalog(work, config, session_id, request, prompt_digest)
            if request.scenario == "missing-catalog":
                catalog.clear()
            elif request.scenario == "wrong-effect":
                catalog["mutation"]["action"] = "unobserved-operation"
    finally:
        report = catalog_report(state, catalog, closed, prompt_digest)
        report["scenario"] = request.scenario
        proof = {"experiment": report, "experiment_passed": report["experiment_passed"]}
        async with asyncio.timeout(1):
            await emit(Event(kind="evidence", data={"lesson_id": 19, "result": proof}))
    return proof


async def local_catalog(work: Path, request: RunRequest) -> dict:
    async def ignore(event):
        pass

    return await execute_catalog(
        work, request.model_copy(update={"mode": "offline"}), Settings(), ignore
    )
