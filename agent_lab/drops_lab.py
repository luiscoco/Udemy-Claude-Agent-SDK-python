"""Lesson 40: persisted active chains and guarded truncating resume evidence."""

import asyncio
import hashlib
import json
import re
import secrets
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    HookMatcher,
    ResultMessage,
    SystemMessage,
    UserMessage,
    create_sdk_mcp_server,
    tool,
)
from claude_agent_sdk._errors import ResultError
from claude_agent_sdk._internal.message_parser import parse_message
from claude_agent_sdk._internal.transport.subprocess_cli import SubprocessCLITransport
from claude_agent_sdk.types import PermissionResultDeny, ToolResultBlock, ToolUseBlock

from agent_lab.config import Settings
from agent_lab.models import Event, RunRequest, lesson_request
from agent_lab.sdk import isolated_env, require_live_access, resolve_cli_path

SOURCE_PREPARED = "owned persisted JSONL and explicitly authored SDK fixtures"
SOURCE_LIVE = "real SDK stream and independently parsed CLI JSONL"
BUILD_RE = re.compile(r"^[0-9a-f]{32}$")
PROMPT_TEXTS = (
    "Remember fruit mango. Reply OK.",
    "Remember colour teal. Reply OK.",
    "Call mcp__rewind__pause exactly once with marker {marker}. Then reply OK.",
    "Remember pet cat. Reply OK.",
)


def canonical(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return str(uuid.UUID(value)) == value
    except (ValueError, AttributeError):
        return False


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def owned_dir(storage: Path, build_id: str) -> Path:
    if not BUILD_RE.fullmatch(build_id):
        raise ValueError("Unknown lesson 40 build ID.")
    base = storage.resolve()
    path = (base / build_id).resolve()
    if path.parent != base:
        raise ValueError("Build path escaped owned storage.")
    return path


def session_file(home: Path, session_id: str) -> Path:
    if not canonical(session_id):
        raise ValueError("Invalid SDK session identity.")
    base = home.resolve()
    matches = []
    for path in base.rglob(session_id + ".jsonl"):
        relative = path.relative_to(base)
        if len(relative.parts) > 5 or any(parent.is_symlink() for parent in (path, *path.parents) if parent != base):
            raise ValueError("Unsafe transcript path.")
        if path.stat().st_nlink != 1 or path.stat().st_size > 2_000_000:
            raise ValueError("Unsafe transcript size or link count.")
        matches.append(path)
    if len(matches) != 1:
        raise ValueError("Expected exactly one owned SDK transcript.")
    return matches[0]


def read_jsonl(path: Path) -> tuple[list[dict[str, Any]], str]:
    if path.is_symlink() or path.stat().st_nlink != 1 or path.stat().st_size > 2_000_000:
        raise ValueError("Unsafe transcript file.")
    raw = path.read_bytes()
    lines = raw.splitlines()
    if not lines or len(lines) > 2000:
        raise ValueError("Transcript record count is outside the lesson bound.")
    try:
        rows = [json.loads(line) for line in lines]
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid transcript JSONL.") from exc
    if not all(isinstance(row, dict) for row in rows):
        raise ValueError("Transcript rows must be objects.")
    return rows, digest(raw)


def active_chain(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for row in rows:
        ident = row.get("uuid")
        if ident is None:
            continue
        if not canonical(ident) or ident in index:
            raise ValueError("Duplicate or malformed transcript UUID.")
        parent = row.get("parentUuid")
        if parent is not None and not canonical(parent):
            raise ValueError("Malformed transcript parent UUID.")
        index[ident] = row
    tips = [row for row in rows if row.get("uuid") and not row.get("isSidechain")]
    if not tips:
        raise ValueError("No active transcript entries.")
    cursor = tips[-1]
    seen: set[str] = set()
    chain = []
    while True:
        ident = cursor["uuid"]
        if ident in seen:
            raise ValueError("Cycle in transcript ancestry.")
        seen.add(ident)
        chain.append(cursor)
        parent = cursor.get("parentUuid")
        if parent is None:
            break
        if parent not in index:
            raise ValueError("Missing transcript parent.")
        cursor = index[parent]
    return list(reversed(chain))


def prompt(row: dict[str, Any]) -> str | None:
    if row.get("type") != "user":
        return None
    message = row.get("message")
    if not isinstance(message, dict):
        return None
    content = message.get("content")
    return content if isinstance(content, str) and content.strip() else None


def turns(chain: list[dict[str, Any]]) -> list[dict[str, Any]]:
    starts = [index for index, row in enumerate(chain) if prompt(row) is not None]
    result = []
    for number, start in enumerate(starts):
        end = starts[number + 1] - 1 if number + 1 < len(starts) else len(chain) - 1
        segment = chain[start:end + 1]
        candidates: list[dict[str, Any]] = []
        queued: list[dict[str, Any]] = []
        for row in segment:
            if row.get("type") == "assistant":
                content = row.get("message", {}).get("content", [])
                if isinstance(content, list):
                    candidates.extend({"uuid": row["uuid"], "tool_use_id": block.get("id")}
                                      for block in content if isinstance(block, dict) and block.get("type") == "tool_use")
            attachment = row.get("attachment")
            if row.get("type") == "attachment" and isinstance(attachment, dict) and attachment.get("type") == "queued_command":
                queued.append({"uuid": row["uuid"], "prompt": attachment.get("prompt")})
        result.append({"number": number + 1, "start": start, "end": end,
                       "prompt_id": chain[start]["uuid"], "prompt": prompt(chain[start]),
                       "last_id": chain[end]["uuid"], "tool_use": candidates, "queued": queued})
    return result


def summarize(path: Path) -> dict[str, Any]:
    rows, sha = read_jsonl(path)
    chain = active_chain(rows)
    return {"sha256": sha, "physical_records": len(rows), "active_records": len(chain),
            "chain_ids": [row["uuid"] for row in chain], "turns": turns(chain),
            "inactive_records": len([row for row in rows if row.get("uuid")]) - len(chain)}


def manifest_path(storage: Path, build_id: str) -> Path:
    return owned_dir(storage, build_id) / "manifest.json"


def load_manifest(storage: Path, build_id: str) -> dict[str, Any]:
    path = manifest_path(storage, build_id)
    if not path.is_file() or path.is_symlink() or path.stat().st_nlink != 1 or path.stat().st_size > 16_384:
        raise ValueError("Owned build manifest is missing or unsafe.")
    item = json.loads(path.read_text(encoding="utf-8"))
    if item.get("build_id") != build_id or not canonical(item.get("session_id")):
        raise ValueError("Build manifest identity mismatch.")
    if len(item.get("main", [])) != 4 or not all(canonical(row.get("id")) for row in item["main"]):
        raise ValueError("Build manifest main prompts are invalid.")
    if not canonical(item.get("queued", {}).get("id")):
        raise ValueError("Build manifest queued identity is invalid.")
    return item


def state(storage: Path, build_id: str | None = None) -> dict[str, Any]:
    if build_id is None:
        pointer = storage / "latest.json"
        if not pointer.is_file() or pointer.is_symlink() or pointer.stat().st_size > 128:
            raise ValueError("No completed lesson 40 build is available.")
        build_id = json.loads(pointer.read_text(encoding="utf-8"))["build_id"]
    manifest = load_manifest(storage, build_id)
    path = session_file(owned_dir(storage, build_id) / "home", manifest["session_id"])
    summary = summarize(path)
    if summary["sha256"] != manifest["original_sha256"]:
        raise ValueError("Original transcript changed after the completed build.")
    if [turn["prompt_id"] for turn in summary["turns"]] != [row["id"] for row in manifest["main"]]:
        raise ValueError("Main prompt chain differs from the owned manifest.")
    queued = summary["turns"][2]["queued"]
    if len(queued) != 1 or queued[0]["prompt"] != manifest["queued"]["text"]:
        raise ValueError("Queued command attachment is missing or mismatched.")
    return {"manifest": manifest, "summary": summary,
            "transcript_path": str(path.relative_to(owned_dir(storage, build_id)))}


def dry(settings: Settings) -> dict[str, Any]:
    rows = []
    sid, cutoff, drop = (str(uuid.uuid4()) for _ in range(3))
    for label, selected in (("last", True), ("recovery", False)):
        opts = ClaudeAgentOptions(resume=sid, fork_session=True,
            resume_session_at=cutoff if selected else None,
            resume_drops_turn=drop if selected else None,
            tools=[], setting_sources=[], max_turns=1, max_budget_usd=0.05)
        tap = SubprocessCLITransport(prompt="", options=opts)
        tap._cli_path = "inert-cli"  # type: ignore[attr-defined]
        argv = tap._build_command()
        rows.append({"label": label, "argv": argv,
                     "serialized": f"--resume={sid}" in argv and "--fork-session" in argv
                     and (f"--resume-session-at={cutoff}" in argv) is selected
                     and (f"--resume-drops-turn={drop}" in argv) is selected})
    return {"rows": rows, "all_serialized": all(row["serialized"] for row in rows),
            "inert_process": True, "sdk_called": False, "model_cost_usd": 0}


def new_build(storage: Path, mode: str) -> tuple[str, Path, dict[str, Any]]:
    build_id = uuid.uuid4().hex
    base = owned_dir(storage, build_id)
    (base / "work").mkdir(parents=True)
    (base / "home").mkdir()
    marker = "BUILD_" + build_id
    ids = [str(uuid.uuid4()) for _ in range(5)]
    texts = [text.format(marker=marker) for text in PROMPT_TEXTS]
    queued = "QUEUED_" + ids[4] + " Remember city Oslo."
    manifest = {"build_id": build_id, "mode": mode, "session_id": None,
                "main": [{"id": ids[index], "text": texts[index]} for index in range(4)],
                "queued": {"id": ids[4], "text": queued},
                "original_sha256": None, "created_at": datetime.now(UTC).isoformat()}
    return build_id, base, manifest


def prepared_rows(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    main = manifest["main"]
    sid = str(uuid.uuid4())
    manifest["session_id"] = sid
    rows: list[dict[str, Any]] = []
    parent: str | None = None

    def add(kind: str, *, ident: str | None = None, **fields: Any) -> str:
        nonlocal parent
        value = ident or str(uuid.uuid4())
        rows.append({"type": kind, "uuid": value, "parentUuid": parent,
                     "sessionId": sid, "isSidechain": False, **fields})
        parent = value
        return value

    tool_id = "toolu_" + secrets.token_hex(10)
    for index, item in enumerate(main):
        add("user", ident=item["id"], message={"role": "user", "content": item["text"]})
        if index == 2:
            add("assistant", message={"role": "assistant", "content": [
                {"type": "tool_use", "id": tool_id, "name": "mcp__rewind__pause",
                 "input": {"marker": "BUILD_" + manifest["build_id"]}}]})
            add("user", message={"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": tool_id, "content": "pause complete"}]})
            add("attachment", attachment={"type": "queued_command", "prompt": manifest["queued"]["text"]})
        add("assistant", message={"role": "assistant", "content": [{"type": "text", "text": "OK"}]})
    side = {"type": "assistant", "uuid": str(uuid.uuid4()), "parentUuid": main[0]["id"],
            "sessionId": sid, "isSidechain": True,
            "message": {"role": "assistant", "content": [{"type": "text", "text": "inactive branch"}]}}
    rows.append(side)
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows), encoding="utf-8")


def publish(storage: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    build_id = manifest["build_id"]
    base = owned_dir(storage, build_id)
    path = session_file(base / "home", manifest["session_id"])
    manifest["original_sha256"] = summarize(path)["sha256"]
    target = base / "manifest.json"
    target.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    verified = state(storage, build_id)
    pointer = storage / "latest.json"
    temp = storage / ("latest-" + build_id + ".json")
    temp.write_text(json.dumps({"build_id": build_id}), encoding="utf-8")
    temp.replace(pointer)
    return verified


async def build_prepared(storage: Path, scenario: str = "normal") -> dict[str, Any]:
    if scenario not in {"normal", "missing", "foreign"}:
        raise ValueError("Unknown prepared build scenario.")
    build_id, base, manifest = new_build(storage, "prepared")
    rows = prepared_rows(manifest)
    path = base / "home" / "projects" / "owned" / (manifest["session_id"] + ".jsonl")
    write_jsonl(path, rows)
    report = {"build_id": build_id, "mode": "prepared", "source": SOURCE_PREPARED,
              "session_id": manifest["session_id"], "main": manifest["main"],
              "queued": manifest["queued"], "handler_calls": [{"marker": "BUILD_" + build_id,
                  "receipt": "BUILD_" + build_id, "authored_fixture": True}],
              "tool_call_id": next(block["id"] for row in rows if row.get("type") == "assistant"
                  for block in row.get("message", {}).get("content", []) if block.get("type") == "tool_use"),
              "turn_results": [{"session_id": manifest["session_id"], "subtype": "success",
                                "is_error": False, "authored_fixture": True} for _ in range(4)],
              "connection_closed": True, "scenario": scenario}
    if scenario == "normal":
        verified = publish(storage, manifest)
        report.update(verified)
        report["build_passed"] = True
    else:
        report["build_passed"] = False
        report["failure_note"] = "Authored negative build evidence is not published as latest."
    return report


async def build_live(storage: Path, settings: Settings) -> dict[str, Any]:
    require_live_access(settings)
    build_id, base, manifest = new_build(storage, "live")
    marker = "BUILD_" + build_id
    queue: asyncio.Queue[dict[str, str] | None] = asyncio.Queue()
    yielded: list[str] = []
    calls: list[dict[str, Any]] = []
    tool_results: list[dict[str, Any]] = []
    handler_calls: list[dict[str, Any]] = []
    pre_events: list[dict[str, Any]] = []
    initializations: list[str] = []
    results: list[dict[str, Any]] = []
    input_closed = False
    connection_closed = False
    queued_sent = False

    async def messages():
        nonlocal input_closed
        try:
            while row := await queue.get():
                yielded.append(row["id"])
                yield {"type": "user", "uuid": row["id"],
                       "message": {"role": "user", "content": row["text"]},
                       "parent_tool_use_id": None, "session_id": "default"}
        finally:
            input_closed = True

    @tool("pause", "Pause only for the literal owned build marker.", {"marker": str})
    async def pause(arguments: dict[str, Any]) -> dict[str, Any]:
        nonlocal queued_sent
        handler_calls.append({"marker": arguments.get("marker")})
        if arguments != {"marker": marker} or len(handler_calls) != 1:
            return {"content": [{"type": "text", "text": "Invalid owned marker."}], "isError": True}
        (base / "receipt.txt").write_text(marker, encoding="utf-8")
        await asyncio.sleep(0.2)
        queue.put_nowait(manifest["queued"])
        queued_sent = True
        await asyncio.sleep(1.5)
        return {"content": [{"type": "text", "text": "pause complete"}]}

    async def pre(data: dict[str, Any], tool_id: str | None, context: Any) -> dict[str, Any]:
        valid = data.get("tool_name") == "mcp__rewind__pause" and data.get("tool_input") == {"marker": marker}
        pre_events.append({"id": tool_id, "valid": valid})
        if valid:
            return {}
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                       "permissionDecisionReason": "Only the fixed owned pause is allowed."}}

    opts = ClaudeAgentOptions(cwd=str(base / "work"), model=settings.model,
        cli_path=resolve_cli_path(settings), tools=[], allowed_tools=["mcp__rewind__pause"],
        mcp_servers={"rewind": create_sdk_mcp_server(name="rewind", tools=[pause])},
        hooks={"PreToolUse": [HookMatcher(matcher="mcp__rewind__pause", hooks=[pre])]},  # type: ignore[list-item]
        setting_sources=[], strict_mcp_config=True, env=isolated_env(base / "home"),
        max_turns=8, max_budget_usd=0.15)
    queue.put_nowait(manifest["main"][0])
    client = ClaudeSDKClient(options=opts)
    try:
        async with asyncio.timeout(90):
            await client.connect(prompt=messages())
            async for message in client.receive_messages():
                if isinstance(message, SystemMessage) and message.subtype == "init":
                    sid = message.data.get("session_id")
                    if isinstance(sid, str):
                        initializations.append(sid)
                elif isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, ToolUseBlock):
                            calls.append({"id": block.id, "name": block.name, "input": block.input})
                elif isinstance(message, UserMessage):
                    for part in message.content:
                        if isinstance(part, ToolResultBlock):
                            tool_results.append({"id": part.tool_use_id, "is_error": part.is_error})
                elif isinstance(message, ResultMessage):
                    results.append({"session_id": message.session_id, "subtype": message.subtype,
                                    "is_error": message.is_error, "cost_usd": message.total_cost_usd})
                    if len(results) < 4 and message.subtype == "success" and not message.is_error:
                        queue.put_nowait(manifest["main"][len(results)])
                        if len(results) == 3:
                            queue.put_nowait(None)
    finally:
        await client.disconnect()
        connection_closed = True
    report = {"build_id": build_id, "mode": "live", "source": SOURCE_LIVE,
              "initialization": initializations, "turn_results": results,
              "main": manifest["main"], "queued": manifest["queued"],
              "yielded_ids": yielded, "handler_calls": handler_calls,
              "pre_events": pre_events, "tool_calls": calls, "tool_results": tool_results,
              "receipt": (base / "receipt.txt").read_text(encoding="utf-8") if (base / "receipt.txt").is_file() else None,
              "input_closed": input_closed, "connection_closed": connection_closed,
              "queued_sent": queued_sent}
    sid = initializations[0] if initializations else None
    valid = bool(sid and len(set(initializations)) == 1 and len(results) == 4
                 and all(row["session_id"] == sid and row["subtype"] == "success" and not row["is_error"]
                         and isinstance(row["cost_usd"], (int, float)) for row in results)
                 and yielded == [item["id"] for item in manifest["main"][:3]] + [manifest["queued"]["id"], manifest["main"][3]["id"]]
                 and len(calls) == len(tool_results) == len(handler_calls) == len(pre_events) == 1
                 and calls[0]["name"] == "mcp__rewind__pause" and calls[0]["input"] == {"marker": marker}
                 and tool_results[0]["id"] == calls[0]["id"] and tool_results[0]["is_error"] is not True
                 and pre_events[0] == {"id": calls[0]["id"], "valid": True}
                 and report["receipt"] == marker and queued_sent and input_closed and connection_closed)
    report["build_passed"] = valid
    if valid and sid:
        manifest["session_id"] = sid
        try:
            report.update(publish(storage, manifest))
        except ValueError as exc:
            report["build_passed"] = False
            report["transcript_error"] = str(exc)
    (base / "build-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def review_text(build_id: str, label: str) -> str:
    return f"Review {label} for owned build {build_id} in one sentence."


def authored_fork(storage: Path, manifest: dict[str, Any], retained: list[dict[str, Any]],
                  label: str) -> dict[str, Any]:
    fork_id, review_id = str(uuid.uuid4()), str(uuid.uuid4())
    rows = [dict(row) for row in retained]
    rows.append({"type": "user", "uuid": review_id, "parentUuid": retained[-1]["uuid"],
                 "sessionId": fork_id, "isSidechain": False,
                 "message": {"role": "user", "content": review_text(manifest["build_id"], label)}})
    rows.append({"type": "assistant", "uuid": str(uuid.uuid4()), "parentUuid": review_id,
                 "sessionId": fork_id, "isSidechain": False,
                 "message": {"role": "assistant", "content": [{"type": "text", "text": "Reviewed."}]}})
    path = owned_dir(storage, manifest["build_id"]) / "home" / "projects" / "owned" / (fork_id + ".jsonl")
    write_jsonl(path, rows)
    summary = summarize(session_file(path.parents[2], fork_id))
    return {"session_id": fork_id, "review_id": review_id, "summary": summary,
            "result": {"session_id": fork_id, "subtype": "success", "is_error": False,
                       "cost_usd": 0.0, "authored_fixture": True}, "connection_closed": True}


def retained_ok(fork: dict[str, Any], expected: list[str], queued_text: str) -> bool:
    turns_found = fork["summary"]["turns"]
    return bool([row["prompt_id"] for row in turns_found] == expected + [fork["review_id"]]
                and len([item for row in turns_found for item in row["queued"]
                         if item["prompt"] == queued_text]) == 1
                and fork["session_id"] != fork.get("source_session_id")
                and fork["result"].get("subtype") == "success"
                and fork["result"].get("is_error") is False
                and fork["result"].get("session_id") == fork["session_id"]
                and fork["connection_closed"])


def classify_refusal(outcome: dict[str, Any]) -> tuple[bool, str | None]:
    result = outcome.get("result")
    if not isinstance(result, dict) or result.get("subtype") != "error_during_execution":
        return False, None
    errors = result.get("errors")
    if not isinstance(errors, list):
        return False, None
    prefix = "Resume rejected by --resume-drops-turn:"
    reasons = [item[len(prefix):].strip() for item in errors
               if isinstance(item, str) and item.startswith(prefix) and item[len(prefix):].strip()]
    good = bool(len(reasons) == 1 and canonical(result.get("uuid"))
                and isinstance(result.get("session_id"), str)
                and isinstance(result.get("cost_usd"), (int, float)))
    return good, reasons[0] if good else None


def terminal_from_result_error(exc: ResultError) -> dict[str, Any] | None:
    """Parse the actual CLI result carried by an SDK initialization failure."""
    if exc.data.get("type") != "result":
        return None
    parsed = parse_message(exc.data)
    if not isinstance(parsed, ResultMessage):
        return None
    return {"uuid": parsed.uuid, "session_id": parsed.session_id,
            "subtype": parsed.subtype, "is_error": parsed.is_error,
            "errors": parsed.errors, "cost_usd": parsed.total_cost_usd,
            "evidence_origin": "CLI result frame preserved by SDK ResultError"}


def cases_report(report: dict[str, Any]) -> dict[str, Any]:
    manifest = report["manifest"]
    expected = [row["id"] for row in manifest["main"]]
    last = report["last"]
    unsafe = report["unsafe"]
    exact = bool(last.get("cutoff") == report["source"]["summary"]["turns"][2]["last_id"]
                 and last.get("drop") == expected[3]
                 and last.get("fork_session") is True
                 and last.get("resume") == manifest["session_id"]
                 and last.get("fork") and retained_ok(last["fork"], expected[:3], manifest["queued"]["text"]))
    refusal, reason = classify_refusal(unsafe)
    unsafe_ok = bool(unsafe.get("cutoff") == report["source"]["summary"]["turns"][1]["last_id"]
                     and unsafe.get("drop") == expected[2]
                     and unsafe.get("resume") == manifest["session_id"]
                     and unsafe.get("fork_session") is True
                     and refusal and reason and "queued" in reason.lower())
    recovery = report.get("recovery")
    recovery_ok = bool(recovery and recovery.get("resume") == manifest["session_id"]
                       and recovery.get("fork_session") is True
                       and recovery.get("cutoff") is None and recovery.get("drop") is None
                       and recovery.get("fork") and retained_ok(recovery["fork"], expected, manifest["queued"]["text"])) if report["recover"] else recovery is None
    identities = [(item.get("result") or {}).get("uuid") for item in (unsafe,)]
    identity_ok = bool(len(set(identities)) == len(identities) and all(canonical(item) for item in identities))
    source_ok = report["source_after_sha256"] == manifest["original_sha256"]
    order_ok = [item["kind"] for item in report["timeline"]] == (["source", "attempt-last", "outcome-last",
        "fork-host-last", "attempt-unsafe", "outcome-unsafe"]
        + (["attempt-recovery", "outcome-recovery", "fork-host-recovery"] if report["recover"] else [])
        + ["source-after", "done"])
    passed = bool(report["build_verified"] and exact and unsafe_ok and recovery_ok
                  and source_ok and order_ok and identity_ok and report["connection_closed"]
                  and report["scenario"] == "normal")
    return {**report, "exact_drop_verified": exact, "unsafe_refusal_verified": unsafe_ok,
            "refusal_reason": reason, "recovery_verified": recovery_ok,
            "source_unchanged": source_ok, "ordered_evidence": order_ok,
            "experiment_passed": passed, "expected_check": "passed" if passed else "needs-review"}


async def cases_prepared(storage: Path, build_id: str, recover: bool,
                         scenario: str = "normal") -> dict[str, Any]:
    if scenario not in {"normal", "missing", "foreign", "duplicate", "interrupted", "tampered"}:
        raise ValueError("Unknown prepared comparison scenario.")
    source = state(storage, build_id)
    manifest = source["manifest"]
    path = session_file(owned_dir(storage, build_id) / "home", manifest["session_id"])
    original, sha = read_jsonl(path)
    chain = active_chain(original)
    turns_found = source["summary"]["turns"]
    timeline = [{"kind": "source", "sha256": sha}]
    last = {"resume": manifest["session_id"], "fork_session": True,
            "cutoff": turns_found[2]["last_id"], "drop": manifest["main"][3]["id"]}
    timeline.append({"kind": "attempt-last"})
    last["fork"] = authored_fork(storage, manifest, chain[:turns_found[2]["end"] + 1], "last")
    last["fork"]["source_session_id"] = manifest["session_id"]
    timeline.extend([{"kind": "outcome-last"}, {"kind": "fork-host-last"}])
    unsafe = {"resume": manifest["session_id"], "fork_session": True,
              "cutoff": turns_found[1]["last_id"], "drop": manifest["main"][2]["id"]}
    timeline.append({"kind": "attempt-unsafe"})
    queued_uuid = turns_found[2]["queued"][0]["uuid"]
    unsafe["result"] = {"uuid": str(uuid.uuid4()), "session_id": manifest["session_id"],
                        "subtype": "error_during_execution", "is_error": True,
                        "errors": ["Resume rejected by --resume-drops-turn: range contains absorbed queued content; entry " + queued_uuid],
                        "cost_usd": 0.0, "authored_fixture": True}
    timeline.append({"kind": "outcome-unsafe"})
    recovery_result = None
    if recover:
        timeline.append({"kind": "attempt-recovery"})
        recovery_result = {"resume": manifest["session_id"], "fork_session": True,
                           "cutoff": None, "drop": None}
        recovery_result["fork"] = authored_fork(storage, manifest, chain, "recovery")
        recovery_result["fork"]["source_session_id"] = manifest["session_id"]
        timeline.extend([{"kind": "outcome-recovery"}, {"kind": "fork-host-recovery"}])
    after = summarize(path)["sha256"]
    timeline.extend([{"kind": "source-after", "sha256": after}, {"kind": "done"}])
    report = {"build_id": build_id, "mode": "prepared", "source_label": SOURCE_PREPARED,
              "manifest": manifest, "source": source, "build_verified": True,
              "last": last, "unsafe": unsafe, "recovery": recovery_result,
              "recover": recover, "source_after_sha256": after,
              "timeline": timeline, "connection_closed": True, "scenario": scenario}
    if scenario == "missing":
        report["unsafe"]["result"]["errors"] = []
    elif scenario == "foreign":
        report["last"]["fork"]["source_session_id"] = "foreign"
    elif scenario == "duplicate":
        report["timeline"].insert(1, {"kind": "source"})
    elif scenario == "interrupted":
        report["connection_closed"] = False
    elif scenario == "tampered":
        report["source_after_sha256"] = "tampered"
    return cases_report(report)


async def live_fork(storage: Path, manifest: dict[str, Any], settings: Settings,
                    label: str, cutoff: str | None, drop: str | None) -> dict[str, Any]:
    base = owned_dir(storage, manifest["build_id"])
    review_id = str(uuid.uuid4())
    denials: list[dict[str, str]] = []

    @tool("pause", "Historical fixed pause; new review execution is disabled.", {"marker": str})
    async def disabled_pause(arguments: dict[str, Any]) -> dict[str, Any]:
        return {"content": [{"type": "text", "text": "Review tool execution is disabled."}], "isError": True}

    async def deny(name: str, arguments: dict[str, Any], context: Any) -> PermissionResultDeny:
        denials.append({"tool_name": name})
        return PermissionResultDeny(message="Review forks do not execute tools.")

    async def one_message():
        yield {"type": "user", "uuid": review_id,
               "message": {"role": "user", "content": review_text(manifest["build_id"], label)},
               "parent_tool_use_id": None, "session_id": "default"}

    opts = ClaudeAgentOptions(cwd=str(base / "work"), model=settings.model,
        cli_path=resolve_cli_path(settings), tools=[], allowed_tools=[],
        mcp_servers={"rewind": create_sdk_mcp_server(name="rewind", tools=[disabled_pause])},
        strict_mcp_config=True, setting_sources=[], env=isolated_env(base / "home"),
        resume=manifest["session_id"], fork_session=True,
        resume_session_at=cutoff, resume_drops_turn=drop,
        can_use_tool=deny, max_turns=1, max_budget_usd=0.05)
    client = ClaudeSDKClient(options=opts)
    attempt: dict[str, Any] = {"label": label, "resume": manifest["session_id"],
        "fork_session": True, "cutoff": cutoff, "drop": drop, "review_id": review_id,
        "result": None, "initializations": [], "fallback_denials": denials,
        "connection_closed": False}
    connected = False
    try:
        async with asyncio.timeout(45):
            try:
                await client.connect(prompt=one_message())
                connected = True
            except ResultError as exc:
                attempt["startup_error"] = str(exc)[:1000]
                attempt["startup_error_type"] = type(exc).__name__
                attempt["raw_error_result"] = {key: exc.data.get(key) for key in
                    ("type", "uuid", "session_id", "subtype", "is_error", "errors", "total_cost_usd")}
                # The SDK has already read this CLI result frame and closed its
                # transport while connect() awaited initialization. Verify the
                # frame itself; the exception text alone proves no guard result.
                try:
                    attempt["result"] = terminal_from_result_error(exc)
                except Exception as parse_error:
                    attempt["raw_result_parse_error"] = type(parse_error).__name__
                attempt["connection_closed"] = True
                attempt["sdk_cleanup_on_connect_failure"] = True
                return attempt
            except Exception as exc:
                attempt["startup_error"] = str(exc)[:1000]
                attempt["startup_error_type"] = type(exc).__name__
                return attempt
            async for message in client.receive_messages():
                if isinstance(message, SystemMessage) and message.subtype == "init":
                    attempt["initializations"].append(message.data.get("session_id"))
                elif isinstance(message, ResultMessage):
                    attempt["result"] = {"uuid": message.uuid, "session_id": message.session_id,
                        "subtype": message.subtype, "is_error": message.is_error,
                        "errors": message.errors, "cost_usd": message.total_cost_usd}
    finally:
        if connected:
            await client.disconnect()
            attempt["connection_closed"] = True
    terminal = attempt["result"]
    if isinstance(terminal, dict) and terminal["subtype"] == "success" and not terminal["is_error"]:
        sid = terminal["session_id"]
        try:
            path = session_file(base / "home", sid)
            attempt["fork"] = {"session_id": sid, "review_id": review_id,
                               "source_session_id": manifest["session_id"],
                               "summary": summarize(path), "result": terminal,
                               "connection_closed": attempt["connection_closed"]}
        except ValueError as exc:
            attempt["fork_error"] = str(exc)
    return attempt


async def cases_live(storage: Path, build_id: str, settings: Settings,
                     recover: bool) -> dict[str, Any]:
    require_live_access(settings)
    source = state(storage, build_id)
    manifest = source["manifest"]
    if manifest["mode"] != "live":
        raise ValueError("Live comparisons require an owned completed live build.")
    path = session_file(owned_dir(storage, build_id) / "home", manifest["session_id"])
    turns_found = source["summary"]["turns"]
    timeline = [{"kind": "source", "sha256": manifest["original_sha256"]},
                {"kind": "attempt-last"}]
    last = await live_fork(storage, manifest, settings, "last",
                           turns_found[2]["last_id"], manifest["main"][3]["id"])
    timeline.extend([{"kind": "outcome-last"}, {"kind": "fork-host-last"}])
    timeline.append({"kind": "attempt-unsafe"})
    unsafe = await live_fork(storage, manifest, settings, "unsafe",
                             turns_found[1]["last_id"], manifest["main"][2]["id"])
    timeline.append({"kind": "outcome-unsafe"})
    recovery = None
    if recover and (unsafe.get("startup_error") or unsafe.get("result")):
        timeline.append({"kind": "attempt-recovery"})
        recovery = await live_fork(storage, manifest, settings, "recovery", None, None)
        timeline.extend([{"kind": "outcome-recovery"}, {"kind": "fork-host-recovery"}])
    after = summarize(path)["sha256"]
    timeline.extend([{"kind": "source-after", "sha256": after}, {"kind": "done"}])
    report = {"build_id": build_id, "mode": "live", "source_label": SOURCE_LIVE,
              "manifest": manifest, "source": source, "build_verified": True,
              "last": last, "unsafe": unsafe, "recovery": recovery, "recover": recover,
              "source_after_sha256": after, "timeline": timeline,
              "connection_closed": all(item.get("connection_closed") for item in
                                       (last, unsafe, *([recovery] if recovery else []))),
              "scenario": "normal"}
    return cases_report(report)


async def undo(storage: Path, build_id: str, mode: str, turn: int,
               boundary: str, settings: Settings) -> dict[str, Any]:
    if mode not in {"prepared", "live"} or turn not in {3, 4} or boundary not in {"last", "assistant", "tool-use"}:
        raise ValueError("Choose a fixed lesson 40 undo variant.")
    source = state(storage, build_id)
    manifest = source["manifest"]
    if manifest["mode"] != mode:
        raise ValueError("Undo mode must match the completed owned build.")
    previous = source["summary"]["turns"][turn - 2]
    cutoff = previous["last_id"]
    if boundary == "tool-use":
        if not previous["tool_use"]:
            raise ValueError("The selected earlier turn has no tool-use boundary.")
        cutoff = previous["tool_use"][-1]["uuid"]
    elif boundary == "assistant":
        path = session_file(owned_dir(storage, build_id) / "home", manifest["session_id"])
        chain = active_chain(read_jsonl(path)[0])
        assistants = [row["uuid"] for row in chain[previous["start"]:previous["end"] + 1]
                      if row.get("type") == "assistant"]
        if not assistants:
            raise ValueError("The selected earlier turn has no assistant boundary.")
        cutoff = assistants[-1]
    drop = manifest["main"][turn - 1]["id"]
    if mode == "live":
        require_live_access(settings)
        outcome = await live_fork(storage, manifest, settings, "undo", cutoff, drop)
    else:
        outcome = {"resume": manifest["session_id"], "fork_session": True,
                   "cutoff": cutoff, "drop": drop, "authored_fixture": True}
        if turn == 4 and boundary == "last":
            path = session_file(owned_dir(storage, build_id) / "home", manifest["session_id"])
            chain = active_chain(read_jsonl(path)[0])
            outcome["fork"] = authored_fork(storage, manifest, chain[:previous["end"] + 1], "undo")
        else:
            outcome["result"] = {"uuid": str(uuid.uuid4()), "session_id": manifest["session_id"],
                "subtype": "error_during_execution", "is_error": True,
                "errors": ["Resume rejected by --resume-drops-turn: selected boundary would discard queued or unrelated entries"],
                "cost_usd": 0.0, "authored_fixture": True}
    return {"build_id": build_id, "mode": mode, "turn": turn, "boundary": boundary,
            "source_sha256": manifest["original_sha256"], "source_after_sha256": state(storage, build_id)["summary"]["sha256"],
            "single_experiment": outcome, "full_comparison_claimed": False}


async def execute_lesson(root: Path, request: RunRequest, settings: Settings,
                         emit: Any) -> dict[str, Any]:
    request = lesson_request(40, request)
    storage = root / "owned-drops"
    selected = request.lesson_options
    if request.mode == "live":
        built = await build_live(storage, settings)
        if not built["build_passed"]:
            report = {"mode": "live", "build": built, "experiment_passed": False,
                      "expected_check": "needs-review", "scenario": request.scenario}
        else:
            report = await cases_live(storage, built["build_id"], settings, selected["recover"])
            report["build"] = built
            costs = [row["cost_usd"] for row in built["turn_results"]
                     if isinstance(row.get("cost_usd"), (int, float))]
            for attempt in (report["last"], report["unsafe"], report.get("recovery") or {}):
                if not isinstance(attempt, dict):
                    continue
                result = attempt.get("result")
                if isinstance(result, dict) and isinstance(result.get("cost_usd"), (int, float)):
                    costs.append(result["cost_usd"])
            if costs:
                await emit(Event(kind="result", data={"lesson_id": 40, "total_cost_usd": sum(costs),
                                                       "reported_cost_sum_note": "Terminal reported totals may include inherited session cost."}))
    else:
        built = await build_prepared(storage)
        report = await cases_prepared(storage, built["build_id"], selected["recover"],
                                      "normal" if request.scenario == "success" else request.scenario)
        report["build"] = built
    proof = {"experiment": report, "experiment_passed": report["experiment_passed"]}
    await emit(Event(kind="evidence", data={"lesson_id": 40, "result": proof}))
    return proof


async def local(root: Path, request: RunRequest) -> dict[str, Any]:
    async def ignore(event: Event) -> None:
        pass

    return await execute_lesson(root, request.model_copy(update={"mode": "offline"}), Settings(), ignore)
