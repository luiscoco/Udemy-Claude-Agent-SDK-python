"""Lesson 44 telemetry actions over the owned OTLP JSON collector."""

import asyncio
import hashlib
import json
import math
import os
import secrets
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    HookMatcher,
    ResultMessage,
    SystemMessage,
    UserMessage,
)
from claude_agent_sdk.types import ToolResultBlock, ToolUseBlock

from agent_lab.config import Settings
from agent_lab.exercises import EmbeddedServer
from agent_lab.models import Event, RunRequest, lesson_request
from agent_lab.sdk import require_live_access, resolve_cli_path
from agent_lab.telemetry_collector import Collector, aggregate

ACTIONS = ("signals", "privacy", "tracing", "rich", "exporters", "collector")
SIGNALS = ("metrics", "logs", "traces")


def facts() -> dict[str, Any]:
    return {"lesson": 44, "actions": list(ACTIONS), "signals": list(SIGNALS),
            "criterion": "Collector received a nonempty successful telemetry export for a completed lane.",
            "mode_labels": {"local": "authored OTLP fixture over loopback HTTP",
                            "live": "native SDK subprocess"}}


def attrs(values: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for key, value in values.items():
        wrapped = ({"boolValue": value} if isinstance(value, bool)
                   else {"doubleValue": value} if isinstance(value, (int, float))
                   else {"stringValue": str(value)})
        rows.append({"key": key, "value": wrapped})
    return rows


def payload(signal: str, run_id: str, lane: str, *, temporality: int = 1,
            content: str | None = None, rich: bool = False,
            trace_id: str | None = None, parent_id: str | None = None) -> dict[str, Any]:
    common = {"session.id": "fixture-session-44", "tool_use_id": "fixture-Read-44"}
    resource = {"attributes": attrs({"service.name": "lesson44-fixture",
                "lab.run": run_id, "lab.lane": lane,
                "deployment.environment": "lesson44"})}
    now = time.time_ns()
    if signal == "metrics":
        points = [{"timeUnixNano": str(now + i), "asDouble": value,
                   "attributes": attrs(common)} for i, value in enumerate((0.01, 0.02))]
        return {"resourceMetrics": [{"resource": resource, "scopeMetrics": [{"metrics": [{
            "name": "claude_code.cost.usage", "unit": "USD",
            "sum": {"aggregationTemporality": temporality, "dataPoints": points}}]}]}]}
    if signal == "logs":
        entries = [{"timeUnixNano": str(now), "attributes": attrs({
            **common, "event.name": "user_prompt", "prompt": content or "omitted"})}]
        if rich:
            entries += [
                {"timeUnixNano": str(now + 1), "attributes": attrs({
                    **common, "event.name": "tool_decision", "tool_name": "Bash", "decision": "deny"})},
                {"timeUnixNano": str(now + 2), "attributes": attrs({
                    **common, "event.name": "tool_decision", "tool_name": "Read", "decision": "allow"})},
            ]
        return {"resourceLogs": [{"resource": resource, "scopeLogs": [{"logRecords": entries}]}]}
    return {"resourceSpans": [{"resource": resource, "scopeSpans": [{"spans": [{
        "traceId": trace_id or uuid.uuid4().hex, "spanId": uuid.uuid4().hex[:16],
        "parentSpanId": parent_id or "", "name": "lesson44.fixture.interaction",
        "startTimeUnixNano": str(now), "endTimeUnixNano": str(now + 1_000_000),
        "attributes": attrs(common)}]}]}]}


def lanes_for(action: str) -> list[str]:
    return {"privacy": ["private", "content"],
            "exporters": ["delta", "cumulative"]}.get(action, ["main"])


def evaluate(report: dict[str, Any]) -> bool:
    if report.get("scenario") != "normal" or not report.get("closed"):
        return False
    for lane in report.get("lanes", []):
        receipts, records = lane["receipts"], lane["records"]
        for signal in SIGNALS:
            matches = {item["id"] for item in receipts if item["status"] == 200
                       and item["signal"] == signal and item["count"] > 0
                       and item["sender"] == "fixture"}
            if not any(row["receipt_id"] in matches and row["signal"] == signal
                       and row["resource"].get("lab.run") == report["run_id"]
                       and row["resource"].get("lab.lane") == lane["name"]
                       for row in records):
                return False
        if report["action"] == "privacy" and lane["content_seen"] != (lane["name"] == "content"):
            return False
        if report["action"] == "exporters":
            expected = 0.03 if lane["name"] == "delta" else 0.02
            if (len(lane["series"]) != 1 or abs(lane["series"][0]["value"] - expected) > 1e-9
                    or lane["protobuf_probe_status"] != 415 or lane["protobuf_decoded"]):
                return False
        if report["action"] == "collector" and lane["unauthorized_status"] != 401:
            return False
        if report["action"] == "tracing" and not lane["host_linked"]:
            return False
        if report["action"] == "rich":
            decisions = {(row["attributes"].get("tool_name"),
                          row["attributes"].get("decision")) for row in records if row["signal"] == "logs"}
            if not {("Bash", "deny"), ("Read", "allow")} <= decisions:
                return False
    return bool(report.get("lanes"))


async def local_action(action: str, scenario: str = "normal") -> dict[str, Any]:
    if action not in ACTIONS or scenario not in {"normal", "missing", "foreign", "failed"}:
        raise ValueError("Unknown Lesson 44 action or scenario")
    run_id = str(uuid.uuid4())
    lanes = lanes_for(action)
    credential = uuid.uuid4().hex if action == "collector" else None
    collector = Collector(run_id, lanes, credential)
    reports = []
    async with EmbeddedServer(collector).running() as base:
        collector.base = base
        async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
            for lane in lanes:
                url = f"{base}/r/{run_id}/{lane}/v1/"
                unauthorized_status = None
                if credential:
                    response = await client.post(url + "metrics", json=payload("metrics", run_id, lane))
                    unauthorized_status = response.status_code
                headers = {"Authorization": "Bearer " + credential} if credential else {}
                trace_id, host_id = uuid.uuid4().hex, uuid.uuid4().hex[:16]
                for signal in SIGNALS:
                    body = payload(signal, run_id, lane,
                        temporality=2 if lane == "cumulative" else 1,
                        content=f"L44-CONTENT-{uuid.uuid4()}" if lane == "content" and signal == "logs" else None,
                        rich=action == "rich", trace_id=trace_id,
                        parent_id=host_id if action == "tracing" else None)
                    response = await client.post(url + signal, json=body, headers=headers)
                    if response.status_code != 200:
                        raise ValueError(f"Owned collector rejected {signal}: {response.status_code}")
                protobuf_status = None
                if action == "exporters":
                    response = await client.post(url + "metrics", content=b"fixed-protobuf-probe",
                        headers={"Content-Type": "application/x-protobuf"})
                    protobuf_status = response.status_code
                host_linked = False
                if action == "tracing":
                    host = payload("traces", run_id, lane, trace_id=trace_id)
                    span = host["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
                    span["spanId"], span["name"] = host_id, "lesson44.manual-host"
                    host["resourceSpans"][0]["resource"]["attributes"] = attrs({
                        "service.name": "student-support-host", "lab.run": run_id, "lab.lane": lane})
                    response = await client.post(base + "/host/v1/traces", json=host)
                    spans = [row for row in collector.records if row["signal"] == "traces"
                             and row["lane"] == lane]
                    host_linked = bool(response.status_code == 200 and
                        any(row["sender"] == "host" and row["trace_id"] == trace_id
                            and row["span_id"] == host_id for row in spans) and
                        any(row["sender"] == "fixture" and row["trace_id"] == trace_id
                            and row["parent_span_id"] == host_id for row in spans))
                records = [row for row in collector.records if row["lane"] == lane]
                reports.append({"name": lane, "signals": list(SIGNALS),
                    "receipts": [row for row in collector.receipts if row["lane"] == lane],
                    "records": records, "series": aggregate(records),
                    "content_seen": collector.content_seen[lane],
                    "raw_body_retained": False, "unauthorized_status": unauthorized_status,
                    "host_linked": host_linked, "protobuf_probe_status": protobuf_status,
                    "protobuf_decoded": False})
    report: dict[str, Any] = {"action": action, "mode": "local",
              "source_label": "authored OTLP fixture over loopback HTTP",
              "scenario": scenario, "run_id": run_id, "lanes": reports, "closed": True}
    if scenario == "missing":
        report["lanes"][0]["receipts"] = []
    elif scenario == "foreign":
        for row in report["lanes"][0]["records"]:
            row["resource"]["lab.run"] = "foreign"
    elif scenario == "failed":
        report["closed"] = False
    report["experiment_passed"] = evaluate(report)
    return report



def _telemetry_env(home: Path, base: str, run_id: str, lane: str,
                   trace_id: str, parent_id: str, *,
                   content: bool, cumulative: bool, credential: str | None) -> dict[str, str]:
    clean = {key: "" for key in os.environ
             if key.startswith(("OTEL_", "TRACEPARENT", "TRACESTATE",
                                "BETA_TRACING", "ENABLE_BETA_TRACING")) or
             key in {"CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC", "DISABLE_TELEMETRY",
                     "DO_NOT_TRACK"}}
    clean.update({
        "CLAUDE_CONFIG_DIR": str(home),
        "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1",
        "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
        "CLAUDE_CODE_ENHANCED_TELEMETRY_BETA": "1",
        "OTEL_METRICS_EXPORTER": "otlp",
        "OTEL_LOGS_EXPORTER": "otlp",
        "OTEL_TRACES_EXPORTER": "otlp",
        "OTEL_EXPORTER_OTLP_PROTOCOL": "http/json",
        "OTEL_EXPORTER_OTLP_ENDPOINT": f"{base}/r/{run_id}/{lane}",
        "OTEL_METRIC_EXPORT_INTERVAL": "500",
        "OTEL_LOGS_EXPORT_INTERVAL": "500",
        "OTEL_TRACES_EXPORT_INTERVAL": "500",
        "OTEL_EXPORTER_OTLP_TIMEOUT": "2000",
        "OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE": "CUMULATIVE" if cumulative else "DELTA",
        "OTEL_RESOURCE_ATTRIBUTES": f"lab.run={run_id},lab.lane={lane},deployment.environment=lesson44",
        "OTEL_SERVICE_NAME": "student-claude-subprocess",
        "OTEL_LOG_USER_PROMPTS": "1" if content else "0",
        "TRACEPARENT": f"00-{trace_id}-{parent_id}-01",
    })
    if credential:
        header = "Authorization=Bearer " + credential
        clean["OTEL_EXPORTER_OTLP_HEADERS"] = header
        for signal in ("METRICS", "LOGS", "TRACES"):
            clean[f"OTEL_EXPORTER_OTLP_{signal}_HEADERS"] = header
    return clean


async def live_action(storage: Path, settings: Settings, action: str) -> dict[str, Any]:
    if action not in ACTIONS:
        raise ValueError("Unknown Lesson 44 action")
    require_live_access(settings)
    run_id = str(uuid.uuid4())
    lanes = lanes_for(action)
    credential = secrets.token_urlsafe(24) if action == "collector" else None
    collector = Collector(run_id, lanes, credential, native=True)
    lane_reports: list[dict[str, Any]] = []
    closed = False
    async with EmbeddedServer(collector).running() as base:
        collector.base = base
        try:
            for lane in lanes:
                folder = storage / run_id / lane
                work, home = folder / "work", folder / "home"
                work.mkdir(parents=True)
                home.mkdir(parents=True)
                notes = work / "notes.txt"
                notes.write_text("OSPREY-44\n", encoding="utf-8")
                expected_hash = hashlib.sha256(notes.read_bytes()).hexdigest()
                trace_id, parent_id = uuid.uuid4().hex, uuid.uuid4().hex[:16]
                environment = _telemetry_env(home, base, run_id, lane, trace_id, parent_id,
                    content=lane == "content", cumulative=lane == "cumulative", credential=credential)
                unauthorized_status = None
                if credential:
                    async with httpx.AsyncClient(timeout=5, trust_env=False) as http:
                        response = await http.post(base + f"/r/{run_id}/{lane}/v1/metrics",
                            json=payload("metrics", run_id, lane))
                        unauthorized_status = response.status_code
                pre: list[dict[str, Any]] = []
                post: list[dict[str, Any]] = []

                async def guard(data: dict[str, Any], call_id: str | None,
                                context: Any, *, _notes: Path = notes,
                                _pre: list[dict[str, Any]] = pre) -> dict[str, Any]:
                    name, args = data.get("tool_name"), data.get("tool_input")
                    allow = bool(name == "Read" and args == {"file_path": str(_notes)})
                    _pre.append({"id": call_id, "name": name, "allowed": allow})
                    return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                        "permissionDecision": "allow" if allow else "deny"}}

                async def observed(data: dict[str, Any], call_id: str | None,
                                   context: Any, *, _notes: Path = notes,
                                   _post: list[dict[str, Any]] = post,
                                   _hash: str = expected_hash) -> dict[str, Any]:
                    current = await asyncio.to_thread(_notes.read_bytes) if data.get("tool_name") == "Read" else b""
                    _post.append({"id": call_id, "name": data.get("tool_name"),
                        "hash_matches": hashlib.sha256(current).hexdigest() == _hash if current else False})
                    return {}

                options = ClaudeAgentOptions(
                    cwd=str(work), cli_path=resolve_cli_path(settings), model="claude-haiku-4-5",
                    tools=["Read", "Bash"] if action == "rich" else ["Read"],
                    allowed_tools=["Read"], setting_sources=[], strict_mcp_config=True, mcp_servers={},
                    env=environment, thinking={"type": "disabled"}, max_turns=5, max_budget_usd=0.10,
                    hooks={"PreToolUse": [HookMatcher(matcher="Read|Bash", hooks=[guard])],  # type: ignore[list-item]
                           "PostToolUse": [HookMatcher(matcher="Read|Bash", hooks=[observed])]})  # type: ignore[list-item]
                calls: list[dict[str, Any]] = []
                results: list[dict[str, Any]] = []
                inits: list[dict[str, Any]] = []
                terminals: list[dict[str, Any]] = []
                async with ClaudeSDKClient(options=options) as client:
                    prompt = f"Read the exact file {notes} once and report its recovery code."
                    if action == "rich":
                        prompt = ("First call Bash with the exact command printf L44_DENIED once. "
                                  "When denied, do not retry. Then " + prompt)
                    if lane == "content":
                        prompt += f" This synthetic test marker is L44-CONTENT-{uuid.uuid4()}."
                    await client.query(prompt)
                    async for message in client.receive_response():
                        if isinstance(message, SystemMessage) and message.subtype == "init":
                            inits.append({"session_id": message.data.get("session_id")})
                        elif isinstance(message, AssistantMessage):
                            for block in message.content:
                                if isinstance(block, ToolUseBlock):
                                    calls.append({"id": block.id, "name": block.name,
                                                  "input_matches": (block.input == {"file_path": str(notes)}
                                                  if block.name == "Read" else
                                                  block.input == {"command": "printf L44_DENIED"})})
                        elif isinstance(message, UserMessage):
                            for part in message.content:
                                if isinstance(part, ToolResultBlock):
                                    results.append({"id": part.tool_use_id, "is_error": part.is_error,
                                                    "contains_code": "OSPREY-44" in str(part.content)})
                        elif isinstance(message, ResultMessage):
                            terminals.append({"uuid": message.uuid, "session_id": message.session_id,
                                "subtype": message.subtype, "is_error": message.is_error,
                                "cost_usd": message.total_cost_usd})
                await asyncio.sleep(1)
                host_linked = False
                if action == "tracing":
                    host = payload("traces", run_id, lane, trace_id=trace_id)
                    span = host["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
                    span["spanId"], span["name"] = parent_id, "lesson44.manual-host"
                    host["resourceSpans"][0]["resource"]["attributes"] = attrs({
                        "service.name": "student-support-host", "lab.run": run_id, "lab.lane": lane})
                    async with httpx.AsyncClient(timeout=5, trust_env=False) as http:
                        response = await http.post(base + "/host/v1/traces", json=host)
                    spans = [row for row in collector.records if row["signal"] == "traces"
                             and row["lane"] == lane]
                    host_linked = bool(response.status_code == 200 and
                        any(row["sender"] == "host" and row["trace_id"] == trace_id
                            and row["span_id"] == parent_id for row in spans) and
                        any(row["sender"] == "subprocess" and row["trace_id"] == trace_id
                            and row["parent_span_id"] == parent_id for row in spans))
                records = [row for row in collector.records if row["lane"] == lane]
                protobuf_status = None
                if action == "exporters":
                    async with httpx.AsyncClient(timeout=5, trust_env=False) as http:
                        response = await http.post(base + f"/r/{run_id}/{lane}/v1/metrics",
                            content=b"fixed-protobuf-probe",
                            headers={"Content-Type": "application/x-protobuf"})
                    protobuf_status = response.status_code
                lane_reports.append({"name": lane, "signals": list(SIGNALS),
                    "receipts": [row for row in collector.receipts if row["lane"] == lane],
                    "records": records, "series": aggregate(records),
                    "content_seen": collector.content_seen[lane], "raw_body_retained": False,
                    "unauthorized_status": unauthorized_status, "host_linked": host_linked,
                    "protobuf_probe_status": protobuf_status, "protobuf_decoded": False,
                    "auth_attempts": [row for row in collector.auth_attempts if row["lane"] == lane],
                    "pre": pre, "post": post, "calls": calls, "results": results,
                    "initialization": inits, "terminals": terminals})
        finally:
            closed = True
    report: dict[str, Any] = {
        "action": action, "mode": "live", "source_label": "native SDK subprocess",
        "scenario": "normal", "run_id": run_id, "lanes": lane_reports, "closed": closed}
    report["experiment_passed"] = evaluate_live(report)
    return report


def evaluate_live(report: dict[str, Any]) -> bool:
    if not report["closed"] or not report["lanes"]:
        return False
    for lane in report["lanes"]:
        inits, terminals = lane["initialization"], lane["terminals"]
        if len(inits) != 1 or len(terminals) != 1:
            return False
        terminal = terminals[0]
        session = inits[0]["session_id"]
        try:
            valid_ids = (str(uuid.UUID(session)) == session and
                         str(uuid.UUID(terminal["uuid"])) == terminal["uuid"])
        except (ValueError, TypeError, AttributeError):
            valid_ids = False
        if (terminal["subtype"] != "success" or terminal["is_error"] or
            terminal["session_id"] != session or not valid_ids or
            not isinstance(terminal["cost_usd"], (int, float)) or
            not math.isfinite(terminal["cost_usd"]) or terminal["cost_usd"] < 0):
            return False
        reads = [call for call in lane["calls"] if call["name"] == "Read" and call["input_matches"]]
        if len(reads) != 1 or not any(row["id"] == reads[0]["id"] and row["contains_code"]
                                    and not row["is_error"] for row in lane["results"]):
            return False
        if not any(row["id"] == reads[0]["id"] and row["allowed"] for row in lane["pre"]):
            return False
        if not any(row["id"] == reads[0]["id"] and row["hash_matches"] for row in lane["post"]):
            return False
        for signal in SIGNALS:
            good_receipts = {row["id"] for row in lane["receipts"] if row["sender"] == "subprocess"
                             and row["signal"] == signal and row["status"] == 200 and row["count"] > 0}
            if not any(row["receipt_id"] in good_receipts and row["signal"] == signal
                       and row["session_id"] == session
                       and row["resource"].get("lab.run") == report["run_id"]
                       and row["resource"].get("lab.lane") == lane["name"]
                       for row in lane["records"]):
                return False
        if not any(row["tool_id"] == reads[0]["id"] and row["sender"] == "subprocess"
                   and row["session_id"] == session
                   and row["resource"].get("lab.run") == report["run_id"]
                   and row["resource"].get("lab.lane") == lane["name"]
                   for row in lane["records"]):
            return False
        if report["action"] == "privacy" and lane["content_seen"] != (lane["name"] == "content"):
            return False
        if report["action"] == "collector" and lane["unauthorized_status"] != 401:
            return False
        if report["action"] == "exporters":
            expected = 2 if lane["name"] == "cumulative" else 1
            if lane["protobuf_probe_status"] != 415 or lane["protobuf_decoded"]:
                return False
            if not any(row["signal"] == "metrics" and row["sender"] == "subprocess"
                       and row["kind"] == "sum" and row["temporality"] == expected
                       for row in lane["records"]):
                return False
        if report["action"] == "tracing" and not lane["host_linked"]:
            return False
        if report["action"] == "rich":
            denied = [call for call in lane["calls"] if call["name"] == "Bash" and call["input_matches"]]
            if len(denied) != 1 or not any(row["id"] == denied[0]["id"] and not row["allowed"]
                                           for row in lane["pre"]):
                return False
            if not any(row["id"] == denied[0]["id"] and row["is_error"] is True
                       for row in lane["results"]):
                return False
            if any(row["id"] == denied[0]["id"] or row["name"] == "Bash" for row in lane["post"]):
                return False
            if not any(row["tool_id"] == denied[0]["id"] and row["sender"] == "subprocess"
                       for row in lane["records"]):
                return False
    return True

async def run(storage: Path, settings: Settings, action: str, mode: str,
              scenario: str = "normal") -> dict[str, Any]:
    if mode not in {"local", "live"} or action not in ACTIONS:
        raise ValueError("Unknown Lesson 44 action or mode")
    if mode == "live" and scenario != "normal":
        raise ValueError("Live faults are unavailable")
    async with asyncio.timeout(120):
        report = (await live_action(storage, settings, action) if mode == "live"
                  else await local_action(action, scenario))
    oversized = len(json.dumps(report).encode()) > 3_000_000
    frames = sum(len(lane.get(key, [])) for lane in report["lanes"] for key in
                 ("receipts", "records", "pre", "post", "calls", "results", "initialization", "terminals"))
    if oversized or frames > 2500:
        report["experiment_passed"] = False
        report["evidence_bound_hit"] = True
        report["lanes"] = [{"name": lane["name"], "truncated": True} for lane in report["lanes"]]
    if report["experiment_passed"]:
        folder = storage / report["run_id"]
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "summary.json").write_text(json.dumps({
            "run_id": report["run_id"], "action": action, "mode": mode, "check": "passed",
            "created_at": datetime.now(UTC).isoformat()}), encoding="utf-8")
        pointer = storage / ("latest-" + report["run_id"] + ".json")
        pointer.write_text(json.dumps({"run_id": report["run_id"]}), encoding="utf-8")
        pointer.replace(storage / "latest.json")
    return report


def state(storage: Path) -> dict[str, Any]:
    pointer = storage / "latest.json"
    if not pointer.is_file() or pointer.is_symlink() or pointer.stat().st_nlink != 1 or pointer.stat().st_size > 128:
        raise ValueError("No successful Lesson 44 run")
    contents = json.loads(pointer.read_text(encoding="utf-8"))
    run_id = contents.get("run_id") if isinstance(contents, dict) else None
    if not isinstance(run_id, str):
        raise ValueError("Invalid Lesson 44 state")
    try:
        if str(uuid.UUID(run_id)) != run_id:
            raise ValueError
    except ValueError as exc:
        raise ValueError("Invalid Lesson 44 state") from exc
    summary = storage / run_id / "summary.json"
    if not summary.is_file() or summary.is_symlink() or summary.stat().st_nlink != 1 or summary.stat().st_size > 2048:
        raise ValueError("Invalid Lesson 44 state")
    result = json.loads(summary.read_text(encoding="utf-8"))
    if (not isinstance(result, dict) or set(result) != {"run_id", "action", "mode", "check", "created_at"}
            or result.get("run_id") != run_id or result.get("check") != "passed"
            or result.get("action") not in ACTIONS or result.get("mode") not in {"local", "live"}):
        raise ValueError("Invalid Lesson 44 summary")
    return result


async def execute_lesson(root: Path, request: RunRequest, settings: Settings,
                         emit: Any) -> dict[str, Any]:
    request = lesson_request(44, request)
    action = request.lesson_options["action"]
    report = await run(root / "owned-telemetry", settings, action,
                       "live" if request.mode == "live" else "local",
                       "normal" if request.scenario == "success" else request.scenario)
    if request.mode == "live":
        cost = sum(lane["terminals"][0]["cost_usd"] for lane in report["lanes"])
        await emit(Event(kind="result", data={"lesson_id": 44, "total_cost_usd": cost}))
    proof = {"experiment": report, "experiment_passed": report["experiment_passed"]}
    await emit(Event(kind="evidence", data={"lesson_id": 44, "result": proof}))
    return proof


async def local(root: Path, request: RunRequest) -> dict[str, Any]:
    async def ignore(event: Event) -> None:
        pass

    return await execute_lesson(root, request.model_copy(update={"mode": "offline"}),
                                Settings(), ignore)
