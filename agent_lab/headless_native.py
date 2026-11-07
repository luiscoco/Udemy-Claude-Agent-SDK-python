"""Bounded Lesson 49 native CLI and SDK headless producers."""

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
from agent_lab.hardening_policy import digest
from agent_lab.headless_lab import (
    environment,
    evaluate,
    fixture,
    mapped_exit,
    report_valid,
    run_process,
)

MODEL = "claude-haiku-4-5-20251001"


def bundled_cli() -> Path:
    import claude_agent_sdk

    path = Path(claude_agent_sdk.__file__).parent / "_bundled" / (
        "claude.exe" if sys.platform == "win32" else "claude")
    if not path.is_file():
        raise FileNotFoundError("Pinned SDK CLI executable is absent")
    return path


def schema(run_id: str) -> dict[str, Any]:
    return {"type": "object", "properties": {
        "run": {"type": "string", "const": run_id},
        "verdict": {"type": "string", "enum": ["PASS", "FAIL"]},
        "issues": {"type": "array", "items": {"type": "string",
                                             "enum": ["EVAL", "PERCENT"]}}},
        "required": ["run", "verdict", "issues"], "additionalProperties": False}


def prompt(run_id: str, text: str) -> str:
    return (f"Run ID: {run_id}. Review this owned pricing source as text only. "
            "Do not execute it. A correct percent calculation rounds cents times "
            "one minus percent divided by one hundred. If the source defines eval, "
            "include EVAL. If the percent calculation omits division by one hundred, "
            "include PERCENT. Return verdict PASS with [] only if neither issue exists; "
            "otherwise FAIL with issue names ordered EVAL then PERCENT. Return only the schema object.\n"
            f"<source>\n{text}\n</source>")


def private_key() -> str:
    key = dotenv_values(ROOT / ".env").get("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
    if not isinstance(key, str) or not key.startswith("sk-ant-"):
        raise PermissionError("Private host Anthropic key is required")
    return key


def native_environment(home: Path, key: str) -> dict[str, str]:
    values = environment(home)
    values.update({"ANTHROPIC_API_KEY": key, "ANTHROPIC_BASE_URL": "https://api.anthropic.com",
                   "ANTHROPIC_DEFAULT_HAIKU_MODEL": MODEL,
                   "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1",
                   "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
                   "CLAUDE_CODE_MAX_RETRIES": "1"})
    return values


def _cli_frames(stdout: str) -> list[dict[str, Any]]:
    frames = []
    for line in stdout.splitlines():
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if not isinstance(value, dict):
            continue
        if value.get("type") == "system" and value.get("subtype") == "init":
            frames.append({"kind": "init", "session_id": value.get("session_id")})
        elif value.get("type") == "result":
            frames.append({"kind": "result", "session_id": value.get("session_id"),
                           "uuid": value.get("uuid"), "subtype": value.get("subtype"),
                           "is_error": value.get("is_error"),
                           "cost_usd": value.get("total_cost_usd"),
                           "structured_output": value.get("structured_output"),
                           "permission_denials": value.get("permission_denials", [])})
        if len(frames) > 20:
            raise ValueError("Native CLI frame limit")
    return frames


def _selected(frames: list[dict[str, Any]]) -> dict[str, Any] | None:
    results = [row for row in frames if row.get("kind") == "result"]
    return results[0] if len(results) == 1 else None


async def native_query(operation: str, name: str, source: str, root: Path,
                       key: str) -> dict[str, Any]:
    if name != "cli":
        raise ValueError("Native CLI producer accepts only the fixed cli lane")
    owned = fixture(root / name)
    run_id = str(uuid.uuid4())
    env = native_environment(owned["home"], key)
    text = owned["sources"][source].read_text(encoding="utf-8")
    fixed_prompt = prompt(run_id, text)
    command = ["--bare", "--print", fixed_prompt,
               "--output-format", "stream-json", "--verbose", "--model", "haiku",
               "--system-prompt", "Classify only the supplied fixed source as JSON. No tools.",
               "--tools", "", "--permission-mode", "dontAsk", "--max-turns", "4",
               "--max-budget-usd", "0.10", "--no-session-persistence",
               "--setting-sources", "", "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
               "--json-schema", json.dumps(schema(run_id), separators=(",", ":"))]
    process = await run_process(bundled_cli(), command, cwd=owned["folder"], env=env,
                                deadline_seconds=60)
    frames = _cli_frames(process["stdout"])
    process["stdout_sha256"] = digest(process["stdout"])
    process["stdout_tail"] = process["stdout"][-2000:]
    process["stdout"] = ""
    process["stderr"] = process["stderr"][-2000:]
    terminal = _selected(frames)
    code = mapped_exit(process, {"is_error": terminal.get("is_error"),
                                 "cost_usd": terminal.get("cost_usd"),
                                 "permission_denials": terminal.get("permission_denials")}
                       if terminal else None)
    result = terminal.get("structured_output") if terminal else None
    return {"id": run_id, "operation": operation, "name": name, "fixture": source,
            "source": "native-cli", "native": True, "fixture_sha256": owned["hashes"][source],
            "after_sha256": digest(owned["sources"][source].read_bytes()),
            "process": process, "frames": frames, "terminal": terminal,
            "policy_exit": code, "report_valid": report_valid(result, run_id, source),
            "ci_exit": 20 if code == 0 and source == "buggy" else code,
            "config_owned": True}


async def sdk_query(operation: str, name: str, source: str, root: Path,
                    key: str) -> dict[str, Any]:
    owned = fixture(root / name)
    run_id = str(uuid.uuid4())
    env = native_environment(owned["home"], key)
    job = {"cwd": str(owned["folder"]), "environment": env,
           "schema": schema(run_id),
           "prompt": prompt(run_id, owned["sources"][source].read_text(encoding="utf-8"))}
    process = await run_process(Path(sys.executable),
        [str(ROOT / "scripts/headless_native_helper.py")], cwd=ROOT, env=env,
        deadline_seconds=75, input_data=json.dumps(job).encode())
    output = process["stdout"]
    try:
        frames = json.loads(output).get("frames", [])
    except ValueError:
        frames = [{"kind": "error", "class": "InvalidChildOutput"}]
    terminal = _selected(frames)
    process_record = {**process, "stdout": "", "stderr": process["stderr"][-2000:],
                      "stdout_sha256": digest(output), "stdout_tail": output[-2000:]}
    code = mapped_exit(process_record, {"is_error": terminal.get("is_error"),
                                        "cost_usd": terminal.get("cost_usd"),
                                        "permission_denials": terminal.get("permission_denials")}
                       if terminal else None)
    result = terminal.get("structured_output") if terminal else None
    return {"id": run_id, "operation": operation, "name": name, "fixture": source,
            "source": "native-sdk", "native": True,
            "fixture_sha256": owned["hashes"][source],
            "after_sha256": digest(owned["sources"][source].read_bytes()),
            "process": process_record, "frames": frames, "terminal": terminal,
            "policy_exit": code, "report_valid": report_valid(result, run_id, source),
            "ci_exit": 20 if code == 0 and source == "buggy" else code,
            "config_owned": True}


def evaluate_native(report: dict[str, Any]) -> bool:
    if not evaluate(report) or report.get("source_label") != "native CLI and SDK":
        return False
    for row in report["outcomes"]:
        frames = row.get("frames", [])
        init = [frame for frame in frames if frame.get("kind") == "init"]
        result = [frame for frame in frames if frame.get("kind") == "result"]
        if (len(init) != 1 or len(result) != 1 or
                any(frame.get("kind") == "error" for frame in frames)):
            return False
        terminal = result[0]
        cost = terminal.get("cost_usd")
        if (not isinstance(init[0].get("session_id"), str) or
                init[0]["session_id"] != terminal.get("session_id") or
                not isinstance(terminal.get("uuid"), str) or not terminal["uuid"] or
                terminal.get("subtype") != "success" or terminal.get("is_error") is not False or
                not isinstance(cost, (int, float)) or not math.isfinite(cost) or
                not 0 <= cost <= 0.10 or terminal.get("permission_denials") != [] or
                not report_valid(terminal.get("structured_output"), row["id"], row["fixture"])):
            return False
        if row["name"] == "cli" and row["process"].get("actual_exit") != 0:
            return False
        if row["name"] != "cli" and any(
                any(name != "StructuredOutput" for name in frame.get("tool_names", []))
                for frame in frames if frame.get("kind") == "assistant"):
            return False
    return True


async def live_action(action: str) -> dict[str, Any]:
    if action not in {"headless", "ci"}:
        raise ValueError("Only headless and CI actions use provider-backed mode")
    key = private_key()
    operation = str(uuid.uuid4())
    root = ROOT / ".lab-data/headless-live" / operation
    root.mkdir(parents=True)
    if action == "headless":
        outcomes = [await native_query(operation, "cli", "clean", root, key),
                    await sdk_query(operation, "sdk", "clean", root, key)]
    else:
        outcomes = [await sdk_query(operation, "clean", "clean", root, key),
                    await sdk_query(operation, "buggy", "buggy", root, key)]
    report: dict[str, Any] = {"lesson": 49, "operation": operation, "action": action,
        "mode": "live", "source_label": "native CLI and SDK", "native": True,
        "scenario": "normal", "status": "completed", "outcomes": outcomes,
        "created_at": datetime.now(UTC).isoformat(),
        "check_scope": "CLI and SDK headless paths both exit successfully with exact machine reports."}
    report["experiment_passed"] = evaluate_native(report)
    encoded = json.dumps(report, indent=2).encode()
    if len(encoded) > 500_000:
        raise ValueError("Headless evidence exceeds 500 KB")
    (root / "report.json").write_bytes(encoded)
    return report
