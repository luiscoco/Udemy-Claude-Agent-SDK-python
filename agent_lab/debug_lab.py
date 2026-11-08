"""Lesson 53 fixed diagnostics: bounded traces, causal findings and prepared replays."""

import asyncio
import hashlib
import json
import os
import re
import stat
import time
import uuid
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from agent_lab.config import ROOT
from agent_lab.policy import redact

SCENARIOS = ("success", "denied", "missing", "max-turns", "startup", "api-error", "truncated")
LIVE_SCENARIOS = ("success", "denied", "missing", "max-turns")
TEMPLATES = ROOT / "agent_lab/content/debug_scenarios.json"
ROW_LIMIT = 300
FORCED_LIMIT = 350
BYTE_LIMIT = 500_000
LOG_LIMIT = 128_000
_ASSIGNMENT = re.compile(r"(?i)\b(?:ANTHROPIC_API_KEY|api_key|access_token|password|secret)\s*=\s*[^\s;,]+")


class DebugInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    mode: Literal["prepared", "live"] = "prepared"
    scenario: Literal["success", "denied", "missing", "max-turns", "startup", "api-error", "truncated"] = "success"
    maxTurns: int = Field(default=4, ge=1, le=5)
    captureLog: bool = True
    consent: bool = False
    budget: float = Field(default=1.0, ge=0.10, le=1.0, allow_inf_nan=False)
    compareId: uuid.UUID | None = None


def effective(value: DebugInput) -> dict[str, Any]:
    return {"policy": "deny" if value.scenario == "denied" else "allow",
            "fixture": "missing" if value.scenario == "missing" else "present",
            "maxTurns": 1 if value.scenario == "max-turns" else value.maxTurns,
            "captureLog": value.captureLog,
            "producerFault": value.scenario if value.scenario in {"startup", "api-error", "truncated"} else "none"}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_redact(value: Any, root: Path | None = None) -> Any:
    value = redact(value)
    if isinstance(value, dict):
        return {str(key)[:80]: safe_redact(item, root) for key, item in list(value.items())[:40]}
    if isinstance(value, list):
        return [safe_redact(item, root) for item in value[:80]]
    if isinstance(value, str):
        value = _ASSIGNMENT.sub("[REDACTED ASSIGNMENT]", value)
        if root is not None:
            value = value.replace(str(root), "$RUN_ROOT")
        return value[:8192]
    return value


def owned_file(path: Path) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError("Owned fixture or log is not a single regular file")
    return True


def prepare_fixture(root: Path, run_id: uuid.UUID, *, missing: bool) -> tuple[Path, str | None]:
    root.mkdir(parents=True, exist_ok=False)
    path = root / "fixture.txt"
    if missing:
        return path, None
    payload = f"LESSON53:{run_id}:verified\n".encode()
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(descriptor, payload)
    finally:
        os.close(descriptor)
    if not owned_file(path):
        raise ValueError("Owned fixture disappeared")
    return path, digest(path.read_bytes())


def bounded_debug_log(path: Path, owned_root: Path) -> dict[str, Any]:
    if path != owned_root / "raw-debug.log":
        raise ValueError("Only this run's raw-debug.log may be inspected")
    if not owned_file(path):
        return {"found": False, "truncated": False, "text": "Debug log unavailable: file is missing."}
    before = path.lstat()
    descriptor = os.open(path, os.O_RDONLY)
    try:
        opened = os.fstat(descriptor)
        if (not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1 or
                (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)):
            raise ValueError("Debug log changed between inspection and open")
        raw = os.read(descriptor, LOG_LIMIT + 1)
    finally:
        os.close(descriptor)
    text = redact(raw[:LOG_LIMIT].decode("utf-8", errors="replace"))
    text = _ASSIGNMENT.sub("[REDACTED ASSIGNMENT]", text).replace(str(owned_root), "$RUN_ROOT")
    return {"found": True, "truncated": len(raw) > LOG_LIMIT, "text": text}


class Collector:
    def __init__(self, run_id: uuid.UUID, root: Path) -> None:
        self.run_id = run_id
        self.root = root
        self.started = time.monotonic()
        self.rows: list[dict[str, Any]] = []
        self.overflow = False

    def add(self, kind: str, name: str, data: dict[str, Any], *, forced: bool = False) -> dict[str, Any] | None:
        row = {"runId": str(self.run_id), "seq": len(self.rows) + 1,
               "milliseconds": max(0, round((time.monotonic() - self.started) * 1000)),
               "kind": kind, "name": name[:80], "data": safe_redact(data, self.root)}
        if kind not in {"host", "sdk", "hook", "permission", "stderr"}:
            raise ValueError("Unknown trace source")
        if len(self.rows) >= FORCED_LIMIT:
            self.overflow = True
            return None
        if not forced and (len(self.rows) >= ROW_LIMIT or
                           len(json.dumps(self.rows + [row], ensure_ascii=False).encode()) > BYTE_LIMIT):
            self.overflow = True
            return None
        self.rows.append(row)
        return row


def _first(rows: list[dict[str, Any]], name: str, predicate: Any = None) -> dict[str, Any] | None:
    return next((row for row in rows if row["name"] == name and
                 (predicate is None or predicate(row["data"]))), None)


def diagnose(rows: list[dict[str, Any]], observations: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []

    def finding(code: str, row: dict[str, Any] | None, next_check: str) -> None:
        if row is not None:
            findings.append({"code": code, "row": row["seq"], "nextCheck": next_check})

    finding("permission-denied", _first(rows, "pre-read", lambda d: d.get("allowed") is False),
            "Inspect the exact target and the host policy before changing a turn limit.")
    missing = _first(rows, "read-result", lambda d: d.get("isError") is True and d.get("fixtureMissing") is True)
    if (missing and observations.get("fileExists") is False and
            _first(rows, "read-call", lambda d: d.get("callId") == missing["data"].get("callId")) and
            _first(rows, "pre-read", lambda d: d.get("callId") == missing["data"].get("callId") and
                   d.get("allowed") is True)):
        finding("missing-file", missing, "Check fixture creation and the exact admitted Read target.")
    startup = _first(rows, "iterator-exception") if _first(rows, "init") is None else None
    finding("startup", startup, "Inspect runtime, working directory and executable; absent init alone proves no cause.")
    finding("api-error", _first(rows, "terminal", lambda d: d.get("subtype") == "success" and d.get("isError") is True),
            "Inspect the terminal error fields and provider status.")
    finding("max-turns", _first(rows, "terminal", lambda d: d.get("subtype") == "error_max_turns"),
            "Inspect the steps already used and the effective max-turns setting.")
    finding("iterator-exception", _first(rows, "iterator-exception") if _first(rows, "init") else None,
            "Inspect the exception after preserving any earlier terminal result.")
    finding("timeout", _first(rows, "timeout"), "Inspect the last captured event and the owned deadline.")
    if _first(rows, "stream-end") and _first(rows, "terminal") is None and startup is None:
        finding("missing-terminal", _first(rows, "stream-end"),
                "Inspect the stream boundary; partial text does not establish a terminal outcome.")
    if not findings and not observations.get("readVerified"):
        finding("inspect-outcome", _first(rows, "stream-end"),
                "Verify the exact Read result against the independently hashed owned fixture.")
    return sorted(findings, key=lambda item: item["row"])


def correlate(rows: list[dict[str, Any]], path: Path, before: str | None) -> dict[str, Any]:
    present = owned_file(path)
    after = digest(path.read_bytes()) if present else None
    calls = {row["data"].get("callId"): row for row in rows if row["name"] == "read-call"}
    decisions = {row["data"].get("callId"): row for row in rows if row["name"] == "pre-read"}
    matched = any(row["data"].get("callId") in calls and
                  decisions.get(row["data"].get("callId"), {}).get("data", {}).get("allowed") is True and
                  row["data"].get("containsFixture") is True and row["data"].get("isError") is False
                  for row in rows if row["name"] == "read-result")
    init = _first(rows, "init")
    terminal = _first(rows, "terminal")
    terminal_success = bool(init and terminal and terminal["data"].get("session") == init["data"].get("session") and
                            terminal["data"].get("subtype") == "success" and terminal["data"].get("isError") is False)
    return {"beforeHash": before, "afterHash": after, "fileExists": present,
            "unchanged": before == after and before is not None,
            "matchedRead": matched, "readVerified": matched and before == after and present,
            "terminalSuccess": terminal_success}


def comparison(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    fields = ("policy", "fixture", "maxTurns", "captureLog", "producerFault")
    changed = [key for key in fields if previous["effectiveConfig"][key] != current["effectiveConfig"][key]]
    same = previous["mode"] == current["mode"]
    return {"previousId": previous["id"], "changed": changed, "sameProvenance": same,
            "oneVariable": same and len(changed) == 1,
            "previousFirst": next(iter(previous["findings"]), None),
            "currentFirst": next(iter(current["findings"]), None),
            "limitation": "A single configuration change is not a controlled causal experiment; fresh IDs and model variation differ."}


def criterion(start_id: str, selected: DebugInput, saved: dict[str, Any], loaded: dict[str, Any]) -> bool:
    serialized = (json.dumps(saved, ensure_ascii=False, indent=2) + "\n").encode()
    if (loaded.get("source") != "persisted-file-reload" or loaded.get("id") != start_id or
            loaded.get("sha256") != digest(serialized) or loaded.get("bundle") != saved):
        return False
    if (saved.get("id") != start_id or saved.get("mode") != selected.mode or
            saved.get("scenario") != selected.scenario or saved.get("effectiveConfig") != effective(selected) or
            saved.get("compareId") != (str(selected.compareId) if selected.compareId else None) or
            not saved.get("closed") or saved.get("interrupted") or saved.get("overflow")):
        return False
    rows = saved.get("rows", [])
    if not rows or len(rows) > FORCED_LIMIT or any(row.get("runId") != start_id or row.get("seq") != index
                                                for index, row in enumerate(rows, 1)):
        return False
    if rows[-1]["name"] != "cleanup" or saved.get("findings") != diagnose(rows, saved["observations"]):
        return False
    calls = [row["data"].get("callId") for row in rows if row["name"] == "read-call"]
    decisions = [row["data"].get("callId") for row in rows if row["name"] == "pre-read"]
    results = [row["data"].get("callId") for row in rows if row["name"] == "read-result"]
    if (len(calls) != len(set(calls)) or len(results) != len(set(results)) or
            any(call not in calls or call not in decisions for call in results) or
            any(row["data"].get("exactTarget") is not True for row in rows if row["name"] == "read-call")):
        return False
    if selected.mode == "prepared":
        if saved.get("modelCalls") != 0 or saved.get("reportedSdkUsd") != 0 or not all(row.get("synthetic") is True for row in rows[:-2]):
            return False
    elif saved.get("modelCalls") != 1 or not isinstance(saved.get("reportedSdkUsd"), (int, float)) or saved["reportedSdkUsd"] > 0.10:
        return False
    expected = {"denied": "permission-denied", "missing": "missing-file", "max-turns": "max-turns",
                "startup": "startup", "api-error": "api-error", "truncated": "missing-terminal"}
    codes = {item["code"] for item in saved["findings"]}
    if selected.scenario == "success":
        return (saved["observations"]["readVerified"] and
                saved["observations"]["terminalSuccess"] and not codes)
    if selected.scenario == "startup":
        return "startup" in codes and any(row["kind"] == "stderr" for row in rows)
    if selected.scenario == "api-error":
        return {"api-error", "iterator-exception"} <= codes
    return expected[selected.scenario] in codes


async def prepared_run(selected: DebugInput, root: Path, run_id: uuid.UUID,
                       abort: asyncio.Event | None = None, on_row: Any = None) -> dict[str, Any]:
    owned = root / str(run_id)
    path, before = prepare_fixture(owned, run_id, missing=selected.scenario == "missing")
    collector = Collector(run_id, owned)
    templates = json.loads(TEMPLATES.read_text(encoding="utf-8"))[selected.scenario]
    interrupted = False
    for item in templates:
        try:
            await asyncio.sleep(0.015)
        except asyncio.CancelledError:
            interrupted = True
            break
        if abort is not None and abort.is_set():
            interrupted = True
            break
        data = dict(item["data"])
        if item["name"] == "read-call":
            data["exactTarget"] = data.get("target") == "fixture.txt"
        if item["name"] == "read-result" and data.get("containsFixture"):
            data["containsFixture"] = owned_file(path) and path.read_text(encoding="utf-8") == f"LESSON53:{run_id}:verified\n"
        row = collector.add(item["kind"], item["name"], data)
        if row is not None:
            row["synthetic"] = True
            if on_row is not None:
                await on_row(row)
        if collector.overflow:
            interrupted = True
            break
    collector.add("host", "stream-end", {"closed": True}, forced=True)
    collector.add("host", "cleanup", {"closed": True}, forced=True)
    log_path = owned / "raw-debug.log"
    if selected.captureLog:
        log_path.write_text("ANTHROPIC_API_KEY=sk-ant-synthetic-demo-credential\nPrepared replay only.\n", encoding="utf-8")
    observations = correlate(collector.rows, path, before)
    bundle = {"id": str(run_id), "mode": "prepared", "scenario": selected.scenario,
              "effectiveConfig": effective(selected), "compareId": str(selected.compareId) if selected.compareId else None,
              "rows": collector.rows, "findings": diagnose(collector.rows, observations),
              "observations": observations, "closed": True, "interrupted": interrupted,
              "overflow": collector.overflow, "modelCalls": 0, "reportedSdkUsd": 0.0,
              "log": bounded_debug_log(log_path, owned) if selected.captureLog else
                     {"found": False, "truncated": False, "text": "Log capture was disabled."},
              "limitations": ["Prepared SDK lifecycle rows are authored, not provider evidence.",
                              "Redaction is best effort; review before sharing."]}
    if len(json.dumps(bundle, ensure_ascii=False).encode()) > BYTE_LIMIT:
        raise ValueError("Diagnostic bundle exceeded its byte ceiling")
    return bundle
