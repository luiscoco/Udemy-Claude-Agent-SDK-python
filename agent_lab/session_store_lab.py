"""Lesson 35: application transcript commits and SDK session mirroring."""

import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from claude_agent_sdk import (
    ClaudeAgentOptions,
    ClaudeSDKClient,
    InMemorySessionStore,
    SessionKey,
    SessionStore,
    SessionStoreEntry,
    SessionStoreListEntry,
    SessionSummaryEntry,
    project_key_for_directory,
)

from agent_lab.config import Settings
from agent_lab.foundations import Evidence
from agent_lab.models import Event, RunRequest, lesson_request
from agent_lab.observed_session_store import ObservedSessionStore
from agent_lab.sqlite_session_store import SQLiteSessionStore

FIRST_PROMPT = "Remember the code word ORBIT_35. Reply exactly STORED_35. Use no tools."
RESUME_PROMPT = "What code word did I ask you to remember? Reply with only that code word. Use no tools."
SOURCE_LIVE = "live SDK stream and actual host callbacks"
FIXTURE_USER_UUID = "00000000-0000-4000-8000-000000000035"
FIXTURE_ASSISTANT_UUID = "00000000-0000-4000-8000-000000000036"
FIXTURE_NEXT_USER_UUID = "00000000-0000-4000-8000-000000000037"
FIXTURE_NEXT_ASSISTANT_UUID = "00000000-0000-4000-8000-000000000038"


def local_transcript_uuids(config: Path, root: Path, session_id: str) -> tuple[int, list[str]]:
    """Inspect only the owned CLI JSONL and return identities, never content."""
    UUID(session_id)
    project = project_key_for_directory(str(root.resolve()))
    folder = config.resolve() / "projects" / project
    path = folder / f"{session_id}.jsonl"
    if not path.is_file():
        return 0, []
    uuids: list[str] = []
    count = 0
    with path.open(encoding="utf-8") as source:
        for line in source:
            count += 1
            item = json.loads(line)
            value = item.get("uuid")
            if isinstance(value, str):
                uuids.append(value)
    return count, uuids


def save_transcript(root: Path, action: str) -> dict[str, Any]:
    """Write one owned host transcript, simulating interruption before replace."""
    root.mkdir(parents=True, exist_ok=True)
    target = root / "transcript.json"
    temporary = root / "transcript.tmp"
    baseline = [{"role": "user", "text": FIRST_PROMPT}]
    target.write_bytes(json.dumps(baseline, sort_keys=True).encode())
    before = hashlib.sha256(target.read_bytes()).hexdigest()
    proposed = baseline + [{"role": "assistant", "text": "STORED_35"}]
    temporary.write_bytes(json.dumps(proposed, sort_keys=True).encode())
    if action != "interrupted":
        temporary.replace(target)
    after_bytes = target.read_bytes()
    expected = baseline if action == "interrupted" else proposed
    return {
        "before_hash": before,
        "after_hash": hashlib.sha256(after_bytes).hexdigest(),
        "read_back": json.loads(after_bytes),
        "temporary_exists": temporary.exists(),
        "host_boundary_verified": json.loads(after_bytes) == expected
        and (temporary.exists() == (action == "interrupted"))
        and ((before == hashlib.sha256(after_bytes).hexdigest()) == (action == "interrupted")),
    }


def store_options(root: Path, config: Path, request: RunRequest, settings: Settings,
                  store: SessionStore, resume: str | None = None) -> ClaudeAgentOptions:
    from agent_lab.sdk import isolated_env, resolve_cli_path

    return ClaudeAgentOptions(
        cwd=str(root.resolve()), model=settings.model,
        cli_path=resolve_cli_path(settings) if request.mode == "live" else None,
        tools=[], allowed_tools=[], setting_sources=[], strict_mcp_config=True,
        env=isolated_env(config.resolve()), session_store=store if request.lesson_options["enabled"] else None,
        session_store_flush=request.lesson_options["flush"], resume=resume,
        max_turns=request.max_turns, max_budget_usd=request.max_budget_usd,
    )


def store_report(state: Evidence, host: dict[str, Any], sessions: list[SessionStoreListEntry],
                 mirrored: list[SessionStoreEntry], answer: str | None, closed: bool,
                 store_reopened: bool = False, local_uuids: list[str] | None = None,
                 mirror_errors: int = 0, store_observations: list[dict[str, Any]] | None = None,
                 local_line_count: int = 0,
                 summaries: list[SessionSummaryEntry] | None = None) -> dict[str, Any]:
    base = state.report()
    action = state.selected["action"]
    resumed = action in {"resume", "durable-resume"}
    ids = [item.get("session_id") for item in state.initialized]
    terminals = state.terminals
    expected_answer = "ORBIT_35" if resumed else "STORED_35"
    sdk_ok = bool(ids and len(terminals) == (2 if resumed else 1)
                  and all(item.get("session_id") == ids[0] and item.get("subtype") == "success"
                          and item.get("is_error") is False for item in terminals)
                  and answer == expected_answer
                  and (not resumed or (len(ids) == 2 and ids[1] == ids[0])))
    kinds = [item.get("type") for item in mirrored]
    required_turns = 2 if resumed else 1
    mirror_ok = bool(sessions and any(item.get("session_id") == ids[0] for item in sessions)
                     and kinds.count("user") >= required_turns
                     and kinds.count("assistant") >= required_turns)
    local_ids = set(local_uuids or [])
    stored_ids = {entry["uuid"] for entry in mirrored if isinstance(entry.get("uuid"), str)}
    missing = sorted(local_ids - stored_ids)
    uuid_coverage = bool(local_ids and not missing and len(local_ids) == len(local_uuids or []))
    summary_ok = bool(sessions and summaries and any(
        summary.get("session_id") == ids[0]
        and any(session["session_id"] == ids[0] and summary.get("mtime") == session["mtime"]
                for session in sessions)
        for summary in summaries
    ))
    expected_store = "SQLiteSessionStore" if action == "durable-resume" else "InMemorySessionStore"
    configured_ok = state.configured == {"tools": [], "allowed_tools": [],
        "setting_sources": [], "session_store": expected_store if state.selected["enabled"] else None,
        "session_store_flush": state.selected["flush"], "auto_memory_disabled": True}
    passed = bool(base["experiment_passed"] and host["host_boundary_verified"]
                  and sdk_ok and mirror_ok and summary_ok and configured_ok and not state.calls and closed
                  and uuid_coverage and mirror_errors == 0
                  and (action != "durable-resume" or store_reopened))
    return {**base, "action": action, "host_transcript": host,
            "store_sessions": sessions, "mirrored_entry_count": len(mirrored),
            "mirrored_entry_types": kinds,
            "observed_answer": answer, "session_verified": sdk_ok,
            "mirror_verified": mirror_ok, "configured": state.configured,
            "store_reopened": store_reopened,
            "local_line_count": local_line_count, "stored_line_count": len(mirrored),
            "local_uuids": local_uuids or [], "stored_entries": [
                {"type": item.get("type"), "uuid": item.get("uuid")} for item in mirrored],
            "local_uuid_count": len(local_uuids or []), "stored_uuid_count": len(stored_ids),
            "missing_uuids": missing, "missing_uuid_count": len(missing), "mirror_errors": mirror_errors,
            "summary_verified": summary_ok, "summary_count": len(summaries or []),
            "store_observations": store_observations or [],
            "uuid_coverage_verified": uuid_coverage,
            "connection_closed": closed, "experiment_passed": passed,
            "check_scope": "The host atomically replaces its own JSON transcript or simulates interruption before replacement. The SDK mirror must contain every UUID-bearing entry in the first owned local CLI transcript, with zero mirror errors. Resume must recall the fixed word. The durable case reopens SQLite with an isolated CLI configuration. This is UUID coverage, not byte equality or proof for entries without UUIDs. Host JSON is not SDK state."}


async def execute_store(root: Path, request: RunRequest, settings: Settings, emit: Any,
                        config: Path | None = None) -> dict[str, Any]:
    from agent_lab.sdk import message_data, require_live_access

    request = lesson_request(35, request)
    root = await asyncio.to_thread(root.resolve)
    action = request.lesson_options["action"]
    host = await asyncio.to_thread(save_transcript, root, action)
    config = config or root.parent / "config"
    state = Evidence(35, root.parent.name, root, request.lesson_options,
                     SOURCE_LIVE if request.mode == "live" else "local host files and explicitly recorded SDK fixtures",
                     request.max_turns, request.max_budget_usd)
    if request.mode == "live":
        require_live_access(settings)
    store_observations: list[dict[str, Any]] = []
    inner: SessionStore = cast(SessionStore, SQLiteSessionStore(root.parent / "session-store.sqlite3")) if action == "durable-resume" else InMemorySessionStore()
    store: SessionStore = cast(SessionStore, ObservedSessionStore(inner, store_observations, request.lesson_options["fault"]))
    options = store_options(root, config, request, settings, store)
    state.configured = {"tools": options.tools, "allowed_tools": options.allowed_tools,
                        "setting_sources": options.setting_sources,
                        "session_store": type(inner).__name__ if options.session_store else None,
                        "session_store_flush": options.session_store_flush,
                        "auto_memory_disabled": options.env.get("CLAUDE_CODE_DISABLE_AUTO_MEMORY") == "1"}
    await emit(Event(kind="options", data={"lesson_id": 35, "sdk_options": state.configured}))
    answer: str | None = None
    closed = False
    sessions: list[SessionStoreListEntry] = []
    mirrored: list[SessionStoreEntry] = []
    summaries: list[SessionSummaryEntry] = []
    local_uuids: list[str] = []
    local_line_count = 0
    mirror_errors = 0
    store_reopened = False
    try:
        if request.mode == "live":
            config.mkdir(parents=True, exist_ok=True)
            for prompt in ([FIRST_PROMPT, RESUME_PROMPT] if action in {"resume", "durable-resume"} else [FIRST_PROMPT]):
                resume = state.initialized[0]["session_id"] if prompt == RESUME_PROMPT else None
                turn_config = config
                if prompt == RESUME_PROMPT and action == "durable-resume":
                    inner = cast(SessionStore, SQLiteSessionStore(root.parent / "session-store.sqlite3"))
                    store = cast(SessionStore, ObservedSessionStore(inner, store_observations, request.lesson_options["fault"]))
                    store_reopened = bool(await store.load({"project_key": project_key_for_directory(str(root)),
                                                            "session_id": str(resume)}))
                    turn_config = root.parent / "config-resume"
                    turn_config.mkdir(parents=True, exist_ok=True)
                client = ClaudeSDKClient(options=store_options(root, turn_config, request, settings, store, resume))
                try:
                    await client.connect()
                    await client.query(prompt)
                    async for message in client.receive_response():
                        data = message_data(message)
                        if data["message_class"] == "MirrorErrorMessage":
                            mirror_errors += 1
                        if data["message_class"] == "ResultMessage" and isinstance(data.get("result"), str):
                            answer = data["result"].strip()
                        event = Event(kind="result" if data["message_class"] == "ResultMessage" else "message", data=data)
                        state.observe(event)
                        await emit(event)
                finally:
                    await client.disconnect()
                if prompt == FIRST_PROMPT and state.initialized:
                    local_line_count, local_uuids = await asyncio.to_thread(
                        local_transcript_uuids, config, root, state.initialized[0]["session_id"])
        else:
            session_id = "store-fixture"
            answer = "STORED_35"
            state.initialized = [{"session_id": session_id}]
            state.terminals = [{"session_id": session_id, "subtype": "success", "is_error": False}]
            if action in {"resume", "durable-resume"}:
                state.initialized.append({"session_id": session_id})
                state.terminals.append({"session_id": session_id, "subtype": "success", "is_error": False})
                answer = "ORBIT_35"
            entries: list[SessionStoreEntry] = [
                cast(SessionStoreEntry, {"type": "user", "uuid": FIXTURE_USER_UUID, "message": FIRST_PROMPT}),
                cast(SessionStoreEntry, {"type": "assistant", "uuid": FIXTURE_ASSISTANT_UUID, "message": "STORED_35"}),
            ]
            if action in {"resume", "durable-resume"}:
                continuation = [
                    cast(SessionStoreEntry, {"type": "user", "uuid": FIXTURE_NEXT_USER_UUID, "message": RESUME_PROMPT}),
                    cast(SessionStoreEntry, {"type": "assistant", "uuid": FIXTURE_NEXT_ASSISTANT_UUID, "message": "ORBIT_35"}),
                ]
            local_uuids = [FIXTURE_USER_UUID, FIXTURE_ASSISTANT_UUID]
            local_line_count = 2
            if request.scenario != "missing-evidence" and request.lesson_options["enabled"]:
                key: SessionKey = {"project_key": project_key_for_directory(str(root)), "session_id": session_id}
                try:
                    await store.append(key, entries)
                except OSError:
                    pass
                if action == "durable-resume":
                    inner = cast(SessionStore, SQLiteSessionStore(root.parent / "session-store.sqlite3"))
                    store = cast(SessionStore, ObservedSessionStore(inner, store_observations, request.lesson_options["fault"]))
                    store_reopened = (await store.load(key)) == entries
                if action in {"resume", "durable-resume"}:
                    await store.append(key, continuation)
            if request.scenario == "wrong-identity":
                state.terminals[-1]["session_id"] = "foreign"
            if request.scenario == "changed-host":
                (root / "transcript.json").write_bytes(b"[]")
                host["host_boundary_verified"] = False
            if request.scenario == "wrong-answer":
                answer = "OTHER_35"
        if state.initialized:
            project_key = project_key_for_directory(str(root))
            sessions = await store.list_sessions(project_key)
            mirrored = await store.load({"project_key": project_key,
                                         "session_id": state.initialized[0]["session_id"]}) or []
            summaries = await store.list_session_summaries(project_key)
        mirror_errors += sum(item["error_type"] is not None for item in store_observations)
    finally:
        closed = True
        report = store_report(state, host, sessions, mirrored, answer, closed,
                              store_reopened, local_uuids, mirror_errors, store_observations,
                              local_line_count, summaries)
        report["scenario"] = request.scenario
        report["expected_check"] = "passed" if report["experiment_passed"] else "needs-review"
        proof = {"experiment": report, "experiment_passed": report["experiment_passed"]}
        await emit(Event(kind="evidence", data={"lesson_id": 35, "result": proof}))
    return proof


async def local_store(root: Path, request: RunRequest) -> dict[str, Any]:
    async def ignore(event: Event) -> None:
        pass

    return await execute_store(root, request.model_copy(update={"mode": "offline"}), Settings(), ignore)
