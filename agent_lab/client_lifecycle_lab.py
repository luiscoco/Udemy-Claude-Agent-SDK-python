"""Lesson 41: owned Python interactive client lifecycle and resume comparison."""

import asyncio
import json
import math
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    ClaudeAgentOptions,
    ClaudeSDKClient,
    CLIConnectionError,
    ResultMessage,
    SystemMessage,
)

from agent_lab.config import Settings
from agent_lab.models import Event, RunRequest, lesson_request
from agent_lab.scripted_cli import ScriptedCLI
from agent_lab.sdk import isolated_env, require_live_access, resolve_cli_path

TASKS = (
    "Remember that Ana teaches Python. Reply OK.",
    "Suggest one short Python course title. Reply on one line.",
    "Recall the supplied name and subject in one short line.",
)
FOLLOW_UP = "Recall the supplied name and subject in one short line."
SOURCE_PREPARED = "real Python SDK client with a scripted CLI fixture"
SOURCE_LIVE = "real Python SDK client and provider-backed CLI"


def _directory(storage: Path, build_id: str) -> Path:
    try:
        if uuid.UUID(build_id).hex != build_id:
            raise ValueError
    except (ValueError, AttributeError) as exc:
        raise ValueError("Invalid owned lesson 41 build ID.") from exc
    return storage / build_id


def _canonical(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return str(uuid.UUID(value)) == value
    except ValueError:
        return False


def facts() -> dict[str, Any]:
    from importlib.metadata import version

    return {"python_sdk_version": version("claude-agent-sdk"),
            "historical_typescript_v2": "not installed in this Python edition",
            "teaching_api": "ClaudeSDKClient.query / receive_response / disconnect",
            "migration_note": "This is the documented Python lifecycle adaptation, not the historical TypeScript V2 export."}


def state(storage: Path, build_id: str | None = None) -> dict[str, Any]:
    if build_id is None:
        pointer = storage / "latest.json"
        if not pointer.is_file() or pointer.is_symlink() or pointer.stat().st_nlink != 1 or pointer.stat().st_size > 128:
            raise ValueError("No completed lesson 41 base is available.")
        build_id = json.loads(pointer.read_text(encoding="utf-8"))["build_id"]
    target = _directory(storage, build_id) / "manifest.json"
    if not target.is_file() or target.is_symlink() or target.stat().st_nlink != 1 or target.stat().st_size > 4096:
        raise ValueError("Owned lesson 41 manifest is unavailable or unsafe.")
    item = json.loads(target.read_text(encoding="utf-8"))
    if item.get("build_id") != build_id or item.get("mode") not in {"prepared", "live"}:
        raise ValueError("Owned lesson 41 manifest identity mismatch.")
    if not isinstance(item.get("session_id"), str) or not item["session_id"]:
        raise ValueError("Owned lesson 41 session ID is missing.")
    if len(item.get("prompt_ids", [])) != 3 or len(set(item["prompt_ids"])) != 3 or not all(_canonical(value) for value in item["prompt_ids"]):
        raise ValueError("Owned lesson 41 prompt IDs are invalid.")
    return item


def _terminal(message: ResultMessage) -> dict[str, Any]:
    return {"uuid": message.uuid, "session_id": message.session_id,
            "subtype": message.subtype, "is_error": message.is_error,
            "cost_usd": message.total_cost_usd, "errors": message.errors}


def _success(result: dict[str, Any], session_id: str | None = None) -> bool:
    return bool(result.get("subtype") == "success" and result.get("is_error") is False
                and isinstance(result.get("session_id"), str) and result["session_id"]
                and (session_id is None or result["session_id"] == session_id)
                and isinstance(result.get("cost_usd"), (int, float))
                and math.isfinite(result["cost_usd"]) and result["cost_usd"] >= 0)


async def _one_turn(client: ClaudeSDKClient, text: str, prompt_id: str) -> tuple[dict[str, Any], list[str]]:
    async def user_message():
        yield {"type": "user", "uuid": prompt_id,
               "message": {"role": "user", "content": text},
               "parent_tool_use_id": None, "session_id": "default"}

    await client.query(user_message())
    result: dict[str, Any] | None = None
    initializations: list[str] = []
    async for message in client.receive_response():
        if isinstance(message, SystemMessage) and message.subtype == "init":
            sid = message.data.get("session_id")
            if isinstance(sid, str):
                initializations.append(sid)
        elif isinstance(message, ResultMessage):
            result = _terminal(message)
    if result is None:
        raise ValueError("The SDK turn ended without a terminal result.")
    return result, initializations


async def base(storage: Path, settings: Settings, mode: str,
               scenario: str = "normal") -> dict[str, Any]:
    if mode not in {"prepared", "live"} or scenario not in {"normal", "missing", "foreign", "failed"}:
        raise ValueError("Unknown lesson 41 base choice.")
    if mode == "live":
        require_live_access(settings)
        if scenario != "normal":
            raise ValueError("Fault scenarios are prepared only.")
    build_id = uuid.uuid4().hex
    directory = _directory(storage, build_id)
    home, work = directory / "home", directory / "work"
    home.mkdir(parents=True)
    work.mkdir()
    ids = [str(uuid.uuid4()) for _ in TASKS]
    fixture = ScriptedCLI([["OK"], ["Python course"], ["Ana teaches Python"]]) if mode == "prepared" else None
    options = ClaudeAgentOptions(cwd=str(work), model=settings.model,
        cli_path=resolve_cli_path(settings) if mode == "live" else None,
        tools=[], allowed_tools=[], setting_sources=[], strict_mcp_config=True,
        env=isolated_env(home), max_turns=3, max_budget_usd=0.10)
    client = ClaudeSDKClient(options=options, transport=fixture)
    terminals: list[dict[str, Any]] = []
    inits: list[str] = []
    async with asyncio.timeout(75):
        try:
            await client.connect()
            for text, ident in zip(TASKS, ids, strict=True):
                terminal, observed = await _one_turn(client, text, ident)
                terminals.append(terminal)
                inits.extend(observed)
                if not _success(terminal, terminals[0]["session_id"]):
                    break
        finally:
            await client.disconnect()
    try:
        await client.query("After disconnect")
        after_close = "accepted"
    except CLIConnectionError:
        after_close = "CLIConnectionError"
    if scenario == "missing":
        terminals.pop()
    elif scenario == "foreign":
        terminals[-1]["session_id"] = "foreign"
    elif scenario == "failed":
        terminals[-1]["subtype"] = "error_during_execution"
    session_id = terminals[0]["session_id"] if terminals else None
    passed = bool(len(terminals) == 3 and session_id
                  and all(_success(result, session_id) for result in terminals)
                  and after_close == "CLIConnectionError"
                  and (mode == "prepared" or len(inits) == 3
                       and all(item == session_id for item in inits)
                       and all(_canonical(result.get("uuid")) for result in terminals)
                       and len({result["uuid"] for result in terminals}) == 3))
    report = {"build_id": build_id, "mode": mode,
              "source_label": SOURCE_LIVE if mode == "live" else SOURCE_PREPARED,
              "session_id": session_id, "prompt_ids": ids, "turns": terminals,
              "initialization_ids": inits, "query_after_disconnect": after_close,
              "connection_closed": True, "experiment_passed": passed,
              "expected_check": "passed" if passed else "needs-review"}
    if passed and session_id:
        manifest = {"build_id": build_id, "mode": mode, "session_id": session_id,
                    "prompt_ids": ids, "created_at": datetime.now(UTC).isoformat()}
        target = directory / "manifest.json"
        target.write_text(json.dumps(manifest), encoding="utf-8")
        state(storage, build_id)
        pointer = storage / ("latest-" + build_id + ".json")
        pointer.write_text(json.dumps({"build_id": build_id}), encoding="utf-8")
        pointer.replace(storage / "latest.json")
    return report


async def resume(storage: Path, build_id: str, settings: Settings,
                 mode: str, scenario: str = "normal") -> dict[str, Any]:
    manifest = state(storage, build_id)
    if mode != manifest["mode"] or scenario not in {"normal", "missing", "foreign", "failed"}:
        raise ValueError("Resume must use an owned base and fixed scenario.")
    if mode == "live":
        require_live_access(settings)
        if scenario != "normal":
            raise ValueError("Fault scenarios are prepared only.")
    directory = _directory(storage, build_id)
    fixture = ScriptedCLI([["Ana teaches Python"]]) if mode == "prepared" else None
    options = ClaudeAgentOptions(cwd=str(directory / "work"), model=settings.model,
        cli_path=resolve_cli_path(settings) if mode == "live" else None,
        tools=[], allowed_tools=[], setting_sources=[], strict_mcp_config=True,
        env=isolated_env(directory / "home"), resume=manifest["session_id"],
        max_turns=1, max_budget_usd=0.10)
    client = ClaudeSDKClient(options=options, transport=fixture)
    prompt_id = str(uuid.uuid4())
    async with asyncio.timeout(45):
        try:
            await client.connect()
            terminal, inits = await _one_turn(client, FOLLOW_UP, prompt_id)
        finally:
            await client.disconnect()
    if scenario == "missing":
        terminal = {}
    elif scenario == "foreign":
        terminal["session_id"] = "foreign"
    elif scenario == "failed":
        terminal["subtype"] = "error_during_execution"
    passed = bool(_success(terminal, manifest["session_id"])
                  and (mode == "prepared" or len(inits) == 1
                       and inits[0] == manifest["session_id"] and _canonical(terminal.get("uuid"))))
    return {"build_id": build_id, "mode": mode,
            "source_label": SOURCE_LIVE if mode == "live" else SOURCE_PREPARED,
            "resume_session_id": manifest["session_id"], "prompt_id": prompt_id,
            "result": terminal, "initialization_ids": inits,
            "connection_closed": True, "experiment_passed": passed,
            "expected_check": "passed" if passed else "needs-review"}


async def compare(storage: Path, settings: Settings, mode: str,
                  scenario: str = "normal") -> dict[str, Any]:
    built = await base(storage, settings, mode, scenario)
    follow = (await resume(storage, built["build_id"], settings, mode)
              if built["experiment_passed"] else None)
    passed = bool(built["experiment_passed"] and follow and follow["experiment_passed"])
    return {"mode": mode, "source_label": built["source_label"],
            "base": built, "resume": follow, "experiment_passed": passed,
            "connection_closed": bool(built["connection_closed"] and (follow is None or follow["connection_closed"])),
            "expected_check": "passed" if passed else "needs-review"}


async def execute_lesson(root: Path, request: RunRequest, settings: Settings,
                         emit: Any) -> dict[str, Any]:
    request = lesson_request(41, request)
    report = await compare(root / "owned-client-lifecycle", settings,
                           "live" if request.mode == "live" else "prepared",
                           "normal" if request.scenario == "success" else request.scenario)
    for result in report["base"]["turns"] + ([report["resume"]["result"]] if report["resume"] else []):
        if isinstance(result.get("cost_usd"), (int, float)) and request.mode == "live":
            await emit(Event(kind="result", data={"lesson_id": 41,
                                                  "total_cost_usd": result["cost_usd"]}))
    proof = {"experiment": report, "experiment_passed": report["experiment_passed"]}
    await emit(Event(kind="evidence", data={"lesson_id": 41, "result": proof}))
    return proof


async def local(root: Path, request: RunRequest) -> dict[str, Any]:
    async def ignore(event: Event) -> None:
        pass

    return await execute_lesson(root, request.model_copy(update={"mode": "offline"}), Settings(), ignore)
