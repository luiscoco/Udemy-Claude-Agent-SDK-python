"""Bounded native SDK producer for Lesson 47's fixed orchestration patterns."""

import asyncio
import json
import math
import os
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dotenv import dotenv_values

from agent_lab.config import ROOT
from agent_lab.orchestra_lab import (
    ACTIONS,
    TOPOLOGY,
    FairLimiter,
    check_report,
    digest,
    evaluate,
    expected_report,
    prepare_files,
)

MODEL = "claude-haiku-4-5-20251001"
BUDGETS = {"orchestrator": 0.20, "hierarchy": 0.25,
           "pipeline": 0.15, "fanout": 0.15, "evaluator": 0.10}


def _host_environment() -> dict[str, str]:
    essentials = {"SYSTEMROOT", "WINDIR", "PATH", "PATHEXT", "COMSPEC", "TEMP", "TMP",
                  "LOCALAPPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)",
                  "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE"}
    return {name: value for name, value in os.environ.items() if name.upper() in essentials}


def _query_prompt(action: str, role: str, region: str, work: Path,
                  predecessor: str | None) -> str:
    if action in {"orchestrator", "hierarchy"}:
        first = "manager" if action == "hierarchy" else "analyst"
        return (f"Delegate exactly once to {first}. Do not read or compute the CSV yourself. "
                "Return only its verified region report line. "
                "No Markdown or explanation.")
    if role == "critic":
        return ("The candidate is supplied now between tags. It is present; do not ask for it. "
                f"<candidate>{predecessor}</candidate> Compare its region, total and best product "
                "with independently known north truth: north, 55, P2. "
                "Reply with exactly PASS if all three match; otherwise exactly FAIL. "
                "No explanation or extra characters.")
    if role in {"specialist", "editor"}:
        return (f"Verified prior handoff: {predecessor}. Return its exact single region report "
                "line, without Markdown, heading or explanation.")
    return (f"Read exactly {work / (region + '.csv')} with Read. Sum the units and choose "
            "the product with greatest units. Return only REGION=<region>; TOTAL=<sum>; "
            "BEST=<P-number> after checking the file. No Markdown, quotes, code fence, "
            "heading or explanation.")


async def _native_query(operation: str, node: str, action: str, role: str, region: str,
                        work: Path, folder: Path, key: str,
                        predecessor: str | None) -> dict[str, Any]:
    home = folder / ("home-" + node)
    home.mkdir(parents=True)
    (home / "aws-config").write_text("", encoding="utf-8")
    (home / "aws-credentials").write_text("", encoding="utf-8")
    child_env = {"CLAUDE_CONFIG_DIR": str(home),
                 "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1",
                 "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
                 "CLAUDE_CODE_MAX_RETRIES": "1",
                 "CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS": "1",
                 "AWS_CONFIG_FILE": str(home / "aws-config"),
                 "AWS_SHARED_CREDENTIALS_FILE": str(home / "aws-credentials"),
                 "AWS_EC2_METADATA_DISABLED": "true",
                 "ANTHROPIC_BASE_URL": "https://api.anthropic.com",
                 "ANTHROPIC_API_KEY": key,
                 "ANTHROPIC_DEFAULT_HAIKU_MODEL": MODEL}
    if action in {"orchestrator", "hierarchy"} or role in {"writer", "extractor", "north", "south", "east"}:
        file = region + ".csv"
    else:
        file = ""
    job = {"operation": operation, "node": node, "action": action, "role": role,
           "region": region, "work": str(work), "file": file,
           "model": MODEL, "expected": expected_report(region),
           "prompt": _query_prompt(action, role, region, work, predecessor),
           "budget": BUDGETS[action] if action in {"orchestrator", "hierarchy"} else 0.05,
           "environment": child_env}
    environment = _host_environment()
    environment.update({"HOME": str(home), "USERPROFILE": str(home),
                        "APPDATA": str(home / "appdata")})
    process = await asyncio.create_subprocess_exec(
        sys.executable, str(ROOT / "scripts/orchestra_native_helper.py"),
        cwd=str(ROOT), env=environment, stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    try:
        output, _ = await asyncio.wait_for(process.communicate(json.dumps(job).encode()), timeout=165)
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()
    try:
        value = json.loads(output)
    except (ValueError, UnicodeDecodeError):
        return {"frames": [{"kind": "error", "class": "InvalidChildOutput"}], "hooks": []}
    return value if isinstance(value, dict) else {"frames": [], "hooks": []}


def _query_result(value: dict[str, Any], budget: float) -> dict[str, Any]:
    frames = value.get("frames", [])
    init = [row for row in frames if row.get("kind") == "system" and row.get("subtype") == "init"]
    terminal = [row for row in frames if row.get("kind") == "result"]
    if (len(init) != 1 or len(terminal) != 1 or
            any(row.get("kind") == "error" for row in frames)):
        return {"passed": False, "reason": "Missing unique native init or result", "cost_usd": None}
    result = terminal[0]
    cost = result.get("cost_usd")
    if (result.get("subtype") != "success" or result.get("is_error") is not False or
            not isinstance(result.get("uuid"), str) or not result["uuid"] or
            result.get("session_id") != init[0].get("session_id") or
            not isinstance(cost, (int, float)) or not math.isfinite(cost) or
            cost < 0 or cost > budget):
        return {"passed": False, "reason": "Native terminal or cost did not match", "cost_usd": cost}
    return {"passed": True, "session_id": result["session_id"],
            "uuid": result["uuid"], "cost_usd": cost, "text": result.get("text", "")}


def _join_native_children(report: dict[str, Any]) -> None:
    """Build child rows only from matched SDK task, hook and tool identities."""
    frames = report["native_frames"]
    hooks = report["native_hooks"]
    operation = report["operation"]
    for role, parent, depth, owner in TOPOLOGY[report["action"]][1:]:
        started = [row for row in hooks if row.get("kind") == "agent-start" and
                   row.get("role") == role and isinstance(row.get("id"), str)]
        if len(started) != 1:
            continue
        worker_id = started[0]["id"]
        task_starts = [row for row in frames if row.get("kind") == "system" and
                       row.get("subtype") == "task_started" and row.get("task_id") == worker_id and
                       row.get("subagent_type") == role and row.get("spawn_depth") == depth]
        if len(task_starts) != 1:
            continue
        tool_id = task_starts[0].get("tool_use_id")
        tool_calls = [tool for row in frames if row.get("kind") == "assistant"
                      for tool in row.get("tools", []) if tool.get("id") == tool_id and
                      tool.get("name") == "Agent" and tool.get("target_role") == role]
        admitted = [row for row in hooks if row.get("kind") == "pre" and
                    row.get("tool") == "Agent" and row.get("id") == tool_id and
                    row.get("allowed") is True and row.get("caller") == parent]
        if len(tool_calls) != 1 or len(admitted) != 1:
            continue
        if parent != "lead":
            parent_start = next((row for row in report["starts"] if row["role"] == parent), None)
            if parent_start is None or admitted[0].get("caller_id") != parent_start["id"]:
                continue
        notifications = [row for row in frames if row.get("kind") == "system" and
                         row.get("subtype") == "task_notification" and
                         row.get("task_id") == worker_id and row.get("tool_use_id") == tool_id and
                         row.get("status") == "completed"]
        stops = [row for row in hooks if row.get("kind") == "agent-stop" and
                 row.get("id") == worker_id and row.get("role") == role and
                 row.get("decision") in {"allow", "second-stop-bypass"}]
        if len(notifications) != 1 or len(stops) != 1:
            continue
        text = stops[0].get("text", "")
        checked = check_report(text, "north")[0]
        report["starts"].append({"id": worker_id, "operation": operation,
                                 "role": role, "parent": parent, "depth": depth,
                                 "owner": owner, "source": report["source_label"],
                                 "native_task_id": worker_id, "delegate_tool_id": tool_id})
        report["ends"].append({"id": worker_id, "role": role, "status": "completed",
                               "source": report["source_label"],
                               "native_task_id": worker_id})
        report["reports"].append({"id": worker_id, "text": text,
                                  "source": "native-subagent-stop"})
        report["verdicts"].append({"id": worker_id, "passed": checked,
                                   "source": "host-checker"})
        if owner.endswith(".csv"):
            reads = [row for row in hooks if row.get("kind") == "read" and
                     row.get("caller_id") == worker_id and row.get("path_ok") is True and
                     row.get("sha256") == report["hashes"]["north"]]
            if len(reads) == 1:
                report["reads"].append({"id": worker_id, "sha256": reads[0]["sha256"],
                                        "source": "owned-file-read", "native_id": reads[0].get("id")})


def evaluate_native(report: dict[str, Any], work: Path) -> bool:
    if not evaluate(report, work):
        return False
    action = report["action"]
    queries = report.get("queries", [])
    expected_queries = 1 if action in {"orchestrator", "hierarchy"} else len(TOPOLOGY[action])
    if len(queries) != expected_queries or {row.get("role") for row in queries} != (
            {"lead"} if expected_queries == 1 else {spec[0] for spec in TOPOLOGY[action]}):
        return False
    frames = report.get("native_frames", [])
    for row in queries:
        cost = row.get("cost_usd")
        if (row.get("passed") is not True or not isinstance(cost, (int, float)) or
                not math.isfinite(cost) or cost < 0 or cost > row.get("budget_usd", -1) or
                not isinstance(row.get("session_id"), str) or not row["session_id"] or
                not isinstance(row.get("uuid"), str) or not row["uuid"]):
            return False
        node_frames = [frame for frame in frames if frame.get("node") == row["role"]]
        init = [frame for frame in node_frames if frame.get("kind") == "system" and
                frame.get("subtype") == "init"]
        terminal = [frame for frame in node_frames if frame.get("kind") == "result"]
        if (len(init) != 1 or len(terminal) != 1 or
                init[0].get("session_id") != row["session_id"] or
                terminal[0].get("session_id") != row["session_id"] or
                terminal[0].get("uuid") != row["uuid"] or
                terminal[0].get("cost_usd") != cost or
                terminal[0].get("text") != row.get("text") or
                terminal[0].get("subtype") != "success" or
                terminal[0].get("is_error") is not False):
            return False
        if action not in {"orchestrator", "hierarchy"}:
            worker = next((item for item in report["starts"] if item["role"] == row["role"]), None)
            if worker is None or not any(item["id"] == worker["id"] and
                                          item["text"] == row["text"]
                                          for item in report["reports"]):
                return False
    if action in {"orchestrator", "hierarchy"}:
        hooks = report.get("native_hooks", [])
        for row in report["starts"][1:]:
            worker_id = row["id"]
            tool_id = row.get("delegate_tool_id")
            if (row.get("native_task_id") != worker_id or
                    not any(frame.get("subtype") == "task_started" and
                            frame.get("task_id") == worker_id and frame.get("tool_use_id") == tool_id
                            for frame in frames) or
                    not any(frame.get("subtype") == "task_notification" and
                            frame.get("task_id") == worker_id and frame.get("status") == "completed"
                            for frame in frames) or
                    not any(hook.get("kind") == "agent-stop" and hook.get("id") == worker_id and
                            hook.get("text") == next(item["text"] for item in report["reports"]
                                                      if item["id"] == worker_id)
                            for hook in hooks)):
                return False
    return True


async def live_action(action: str, *, limit: int = 2) -> dict[str, Any]:
    if action not in ACTIONS or limit not in (1, 2):
        raise ValueError("Unknown fixed orchestration option")
    key = dotenv_values(ROOT / ".env").get("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
    if not isinstance(key, str) or not key.startswith("sk-ant-"):
        raise PermissionError("Private host Anthropic key is required")
    operation = str(uuid.uuid4())
    folder = ROOT / ".lab-data" / "orchestra-live" / operation
    work = folder / "work"
    hashes = prepare_files(work)
    report: dict[str, Any] = {"lesson": 47, "operation": operation, "action": action,
        "mode": "live", "source_label": "native SDK and host checks", "native": True,
        "status": "completed", "limit": limit, "scenario": "normal", "hashes": hashes,
        "starts": [], "ends": [], "reads": [], "reports": [], "verdicts": [],
        "handoffs": [], "limiter": [], "queries": [], "native_hooks": [], "native_frames": [],
        "errors": [], "created_at": datetime.now(UTC).isoformat(), "work": str(work)}
    limiter = FairLimiter(limit)

    async def run_role(role: str, parent: str, depth: int, owner: str,
                       predecessor: str | None = None) -> bool:
        worker_id = str(uuid.uuid4())
        region = role if action == "fanout" else "north"
        if action == "fanout":
            await limiter.acquire()
        try:
            result = await _native_query(operation, role, action, role, region, work, folder, key,
                                         predecessor)
            measured = _query_result(result, BUDGETS[action] if action in {"orchestrator", "hierarchy"} else 0.05)
            report["queries"].append({"role": role, "budget_usd": BUDGETS[action] if action in
                                      {"orchestrator", "hierarchy"} else 0.05, **measured})
            report["native_hooks"].extend(result.get("hooks", []))
            report["native_frames"].extend({"node": role, **frame} for frame in result.get("frames", []))
            report["starts"].append({"id": worker_id, "operation": operation,
                                     "role": role, "parent": parent, "depth": depth,
                                     "owner": owner, "source": report["source_label"]})
            if not measured["passed"]:
                report["ends"].append({"id": worker_id, "role": role,
                                       "status": "failed", "source": report["source_label"]})
                report["errors"].append({"role": role, "reason": measured.get("reason")})
                return False
            text = str(measured["text"])
            good = text == "PASS" if role == "critic" else check_report(text, region)[0]
            report["reports"].append({"id": worker_id, "text": text})
            report["verdicts"].append({"id": worker_id, "passed": good, "source": "host-checker"})
            if owner.endswith(".csv"):
                reads = [item for item in result.get("hooks", []) if item.get("kind") == "read"
                         and item.get("path_ok") is True and item.get("sha256") == hashes[region]]
                if reads:
                    report["reads"].append({"id": worker_id, "sha256": reads[-1]["sha256"],
                                            "source": "owned-file-read", "native_id": reads[-1].get("id")})
                else:
                    good = False
                    report["verdicts"][-1]["passed"] = False
            report["ends"].append({"id": worker_id, "role": role,
                                   "status": "completed", "source": report["source_label"]})
            return good
        finally:
            if action == "fanout":
                limiter.release()

    if action in {"orchestrator", "hierarchy"}:
        # The root query is one native invocation. Hook and task records below
        # must supply the actual child rows; parent text cannot fill them in.
        await run_role(*TOPOLOGY[action][0])
        _join_native_children(report)
    elif action == "fanout":
        outcomes = await asyncio.gather(*(run_role(*spec) for spec in TOPOLOGY[action]),
                                        return_exceptions=True)
        for outcome in outcomes:
            if isinstance(outcome, BaseException):
                report["errors"].append({"role": "host", "reason": type(outcome).__name__})
        report["limiter"] = limiter.observations
    else:
        previous: str | None = None
        previous_id: str | None = None
        for spec in TOPOLOGY[action]:
            passed = await run_role(*spec, predecessor=previous)
            if not passed:
                break
            latest = report["reports"][-1]
            if previous_id is not None and previous is not None:
                report["handoffs"].append({"from": previous_id, "to": latest["id"],
                                           "sha256": digest(previous)})
            previous, previous_id = latest["text"], latest["id"]
    if report["errors"]:
        report["status"] = "failed"
    if len(report["native_frames"]) + len(report["native_hooks"]) > 800:
        report["status"] = "failed"
        report["errors"].append({"role": "host", "reason": "Native evidence frame limit"})
    report["experiment_passed"] = evaluate_native(report, work)
    encoded = json.dumps(report, indent=2).encode("utf-8")
    if len(encoded) > 1_000_000:
        raise ValueError("Native orchestration evidence exceeds 1 MB")
    folder.joinpath("report.json").write_bytes(encoded)
    return report
