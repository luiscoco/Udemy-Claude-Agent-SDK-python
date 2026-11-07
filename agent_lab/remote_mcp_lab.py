"""Lesson 43 owned remote MCP transport, authentication, and resource lab."""

import asyncio
import base64
import hashlib
import importlib.metadata
import json
import math
import re
import time
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

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
from agent_lab.remote_fixture_lab import RemoteFixture, discover, host_probe
from agent_lab.sdk import isolated_env, require_live_access, resolve_cli_path

SOURCE_LOCAL = "owned loopback MCP host and real HTTP/SSE client"
SOURCE_LIVE = "provider-backed SDK remote MCP tool and resource calls"
RESOURCES = {"runbook": "docs://runbook", "incident": "docs://incident-43",
             "logo": "files://logo.png", "widget": "ui://orders/widget",
             "order": "orders://1001"}
ACTIONS = {"auth", "cache", "transports", "toolsets", "resources", "host-read", "live-tool", "live-resource", "reconnect", "rotation"}
MAX_EVIDENCE_BYTES = 2_000_000
MAX_EVIDENCE_FRAMES = 700
SECRET_FIELDS = {"authorization", "access_token", "client_secret", "client_id", "api_key", "token"}
PROVIDER_KEY = re.compile(r"sk-ant-[A-Za-z0-9_-]{12,}")
BEARER = re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{10,}", re.I)


def scrub_evidence(value: Any, issued: list[str]) -> Any:
    """Remove fixture and provider-shaped secrets before returning an evidence tree."""
    if isinstance(value, dict):
        return {key: scrub_evidence(item, issued) for key, item in value.items()
                if key.lower() not in SECRET_FIELDS}
    if isinstance(value, list):
        return [scrub_evidence(item, issued) for item in value]
    if isinstance(value, str):
        cleaned = value
        for secret in issued:
            if secret:
                cleaned = cleaned.replace(secret, "[redacted]")
        return BEARER.sub("[redacted bearer]", PROVIDER_KEY.sub("[redacted provider key]", cleaned))
    return value


def _canonical_uuid(value: Any) -> bool:
    try:
        return isinstance(value, str) and str(uuid.UUID(value)) == value
    except (ValueError, AttributeError, TypeError):
        return False


def _server_status(value: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [{"name": item.get("name"), "status": item.get("status"),
             "tool_names": [tool.get("name") if isinstance(tool, dict) else tool
                            for tool in item.get("tools", [])]}
            for item in value.get("mcpServers", []) if isinstance(item, dict)]


def _rotation_control_supported() -> bool:
    """Keep the private control shim limited to the SDK version verified live here."""
    return importlib.metadata.version("claude-agent-sdk") == "0.2.174"


def facts() -> dict[str, Any]:
    return {"lesson": 43, "transports": ["http", "sse"],
            "actions": ["auth", "cache", "transports", "toolsets", "resources", "host-read", "live"],
            "live_steps": ["tool", "resource", "rotate"], "cli_control": "reconnect",
            "tools": ["get_status", "find_order"], "resources": RESOURCES,
            "auth": "Local machine credential grant; not provider OAuth certification.",
            "rotation_limit": "Python SDK 0.2.174 needs a version-guarded private control request for same-client rotation."}


def _pass(probe: dict[str, Any], fixture: RemoteFixture, marker: str,
          resource: str | None = None) -> bool:
    status = probe.get("status_payload", {})
    good = (probe.get("fixture_id") == fixture.id and
            set(probe.get("tools", [])) == {"get_status", "find_order"} and
            "orders://{order_id}" in probe.get("templates", []) and
            any(item.get("type") == "resource_link" and item.get("uri") == "orders://1001"
                for item in probe.get("resource_links", [])) and
            status.get("status") == "ready" and status.get("marker") == marker and
            status.get("fixtureId") == fixture.id and
            any(row.get("receipt_id") == status.get("receiptId") and
                row.get("marker") == marker and _wire_matches(fixture, row)
                for row in fixture.handlers) and
            not probe.get("status_is_error"))
    if resource:
        contents = probe.get("resource_contents") or []
        if contents:
            item = contents[0]
            raw = (item.get("text", "").encode() if "text" in item else
                   base64.b64decode(item.get("blob", "")) if "blob" in item else b"")
            digest = hashlib.sha256(raw).hexdigest()
        else:
            digest = ""
        good = bool(good and contents and str(contents[0].get("uri")) == resource and
                    (resource != "orders://1001" or probe.get("followed_order_link") is True) and
                    any(row["uri"] == resource and row["sha256"] == digest and
                        row["bytes"] == len(raw) for row in fixture.reads) and
                    any(row.get("rpc_method") == "resources/read" and
                        row.get("resource_uri") == resource and row.get("status") in {200, 202}
                        for row in fixture.wire))
    return bool(good)


def _wire_matches(fixture: RemoteFixture, handler: dict[str, Any]) -> bool:
    return any(row.get("rpc_method") == "tools/call" and row.get("tool_name") == "get_status"
               and row.get("marker") == handler.get("marker")
               and str(row.get("rpc_id")) == str(handler.get("rpc_id"))
               and row.get("connection_id") == handler.get("connection_id")
               and row.get("credential_label") == handler.get("credential_label")
               and row.get("status") in {200, 202}
               for row in fixture.wire)


def _protocol_pair(fixture: RemoteFixture, probe: dict[str, Any], marker: str) -> dict[str, Any]:
    matching = [row for row in fixture.wire if row.get("rpc_method") == "tools/call"
                and row.get("tool_name") == "get_status" and row.get("marker") == marker]
    wire = matching[-1] if matching else {}
    key = (str(wire.get("connection_id")) + ":" + str(wire.get("rpc_id"))) if wire else None
    payload = probe.get("status_payload") or {}
    return {"call": {"scoped_key": key, "rpc_id": wire.get("rpc_id"),
                     "connection_id": wire.get("connection_id"), "marker": marker,
                     "credential_label": wire.get("credential_label")},
            "result": {"scoped_key": key, "receipt_id": payload.get("receiptId"),
                       "marker": payload.get("marker"), "fixture_id": payload.get("fixtureId"),
                       "is_error": probe.get("status_is_error")}}


def _pair_pass(pair: dict[str, Any], fixture: RemoteFixture) -> bool:
    call, result = pair["call"], pair["result"]
    return bool(call["scoped_key"] and call["scoped_key"] == result["scoped_key"]
                and call["marker"] == result["marker"] and result["fixture_id"] == fixture.id
                and not result["is_error"] and
                any(row["receipt_id"] == result["receipt_id"] and
                    row["connection_id"] == call["connection_id"] and
                    row["credential_label"] == call["credential_label"]
                    for row in fixture.handlers))


async def _auth_checks(base: str, fixture: RemoteFixture, token: str) -> dict[str, int]:
    body = {"jsonrpc": "2.0", "id": 11, "method": "tools/list"}
    async with httpx.AsyncClient(timeout=8, trust_env=False) as client:
        absent = await client.post(base + "/mcp", json=body)
        foreign = await client.post(base + "/mcp", json=body,
                                    headers={"Authorization": "Bearer foreign"})
        missing_init = await client.post(base + "/mcp", json=body,
                                         headers={"Authorization": "Bearer " + token})
        unknown = await client.post(base + "/mcp", json=body,
                                    headers={"Authorization": "Bearer " + token,
                                             "Mcp-Session-Id": "foreign-session"})
    return {"missing_token": absent.status_code, "foreign_token": foreign.status_code,
            "missing_initialize": missing_init.status_code, "unknown_session": unknown.status_code}


async def local_action(action: str, transport: str = "http", resource: str = "runbook",
                       scenario: str = "normal") -> dict[str, Any]:
    if (action not in ACTIONS or transport not in {"http", "sse"} or resource not in RESOURCES or
            scenario not in {"normal", "missing", "foreign", "failed"}):
        raise ValueError("Choose a fixed lesson 43 action, transport, resource, and scenario.")
    if action == "transports":
        lanes = [await local_action("host-read", choice, resource, scenario) for choice in ("http", "sse")]
        return {"action": action, "source_label": SOURCE_LOCAL, "lanes": lanes,
                "scenario": scenario, "experiment_passed": all(lane["experiment_passed"] for lane in lanes)}
    fixture = RemoteFixture(transport)
    async with EmbeddedServer(fixture).running() as base:
        fixture.base = base
        token, label, steps = await discover(base, fixture)
        marker = fixture.id + ":1"
        checks = await _auth_checks(base, fixture, token) if action == "auth" else None
        selected = RESOURCES[resource] if action in {"resources", "host-read", "live-resource"} else None
        first = await host_probe(base, fixture, token, transport, marker, selected)
        if scenario == "missing":
            first["status_payload"].pop("receiptId", None)
        elif scenario == "foreign":
            first["status_payload"]["fixtureId"] = "foreign-fixture"
        elif scenario == "failed":
            first["status_is_error"] = True
        first_pair = _protocol_pair(fixture, first, marker)
        passed = _pass(first, fixture, marker, selected) and _pair_pass(first_pair, fixture)
        pairs = [first_pair]
        second = None
        revoked_status = None
        expired_status = None
        if action == "auth":
            fixture.tokens[token] = (label, time.monotonic() - 1)
            async with httpx.AsyncClient(timeout=8, trust_env=False) as client:
                expired = await client.post(base + "/mcp", json={"jsonrpc": "2.0", "id": 12,
                    "method": "tools/list"}, headers={"Authorization": "Bearer " + token})
                expired_status = expired.status_code
            passed = bool(passed and expired_status == 401)
        if action in {"cache", "rotation"}:
            if action == "cache":
                second = await host_probe(base, fixture, token, transport, marker)
                second_pair = _protocol_pair(fixture, second, marker)
                pairs.append(second_pair)
                passed = passed and _pass(second, fixture, marker) and _pair_pass(second_pair, fixture)
            fixture.revoke()
            async with httpx.AsyncClient(timeout=8, trust_env=False) as client:
                expired = await client.post(base + "/mcp", json={"jsonrpc": "2.0", "id": 4,
                    "method": "tools/list"}, headers={"Authorization": "Bearer " + token})
                revoked_status = expired.status_code
            token2, label2, steps2 = await discover(base, fixture)
            second = await host_probe(base, fixture, token2, transport, fixture.id + ":2", "docs://incident-43")
            second_pair = _protocol_pair(fixture, second, fixture.id + ":2")
            pairs.append(second_pair)
            passed = bool(passed and revoked_status == 401 and label2 != label and
                          _pass(second, fixture, fixture.id + ":2", "docs://incident-43") and
                          _pair_pass(second_pair, fixture))
        else:
            label2, steps2 = None, None
        if checks is not None:
            passed = bool(passed and checks == {"missing_token": 401, "foreign_token": 401,
                                                "missing_initialize": 400, "unknown_session": 404})
        report = {"action": action, "transport": transport, "source_label": SOURCE_LOCAL,
                "scenario": scenario,
                "fixture_id": fixture.id, "discovery": steps, "auth_checks": checks,
                "credential_labels": [x for x in (label, label2) if x],
                "second_discovery": steps2, "revoked_status": revoked_status,
                "expired_status": expired_status,
                "probe": first, "second_probe": second, "wire": fixture.wire,
                "protocol_pairs": pairs,
                "handlers": fixture.handlers, "resource_reads": fixture.reads,
                "agent_executed": False, "agent_context": False,
                "agent_inventory_observed": False,
                "candidate_toolsets": ({"empty": [], "resources": ["ListMcpResourcesTool", "ReadMcpResourceTool"],
                                        "default": "not executed"} if action == "toolsets" else None),
                "experiment_passed": passed}
        return cast(dict[str, Any], scrub_evidence(report, fixture.issued_values +
                                                   [fixture.client_id, fixture.client_secret]))


async def live_action(storage: Path, settings: Settings, action: str,
                      transport: str = "http", resource: str = "runbook") -> dict[str, Any]:
    if action not in {"live-tool", "live-resource", "reconnect", "rotation"}:
        raise ValueError("Choose a live MCP tool, resource, reconnect, or rotation action.")
    if action == "rotation" and not _rotation_control_supported():
        raise ValueError("Same-client MCP credential rotation is verified only with claude-agent-sdk 0.2.174.")
    require_live_access(settings)
    fixture = RemoteFixture(transport)
    async with EmbeddedServer(fixture).running() as base:
        fixture.base = base
        token, label, discovery = await discover(base, fixture)
        marker = fixture.id + ":1"
        selected = RESOURCES[resource] if action == "live-resource" else None
        allowed = {"mcp__lesson_remote__get_status"}
        if selected:
            allowed.update({"ListMcpResourcesTool", "ReadMcpResourceTool"})
        pre: list[dict[str, Any]] = []

        async def guard(data: dict[str, Any], call_id: str | None, context: Any) -> dict[str, Any]:
            tool, args = data.get("tool_name"), data.get("tool_input")
            valid = bool((tool == "mcp__lesson_remote__get_status" and args == {"marker": marker}) or
                         (tool == "ListMcpResourcesTool" and selected and isinstance(args, dict) and
                          args.get("server") == "lesson_remote") or
                         (tool == "ReadMcpResourceTool" and selected and isinstance(args, dict) and
                          args.get("uri") == selected and args.get("server") == "lesson_remote"))
            pre.append({"id": call_id, "tool": tool, "input": args, "allowed": valid})
            return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                           "permissionDecision": "allow" if valid else "deny"}}

        folder = storage / uuid.uuid4().hex
        work, home = folder / "work", folder / "home"
        work.mkdir(parents=True)
        options = ClaudeAgentOptions(cwd=str(work), model=settings.model,
            cli_path=resolve_cli_path(settings), tools=["ListMcpResourcesTool", "ReadMcpResourceTool"] if selected else [],
            allowed_tools=sorted(allowed), setting_sources=[], strict_mcp_config=True,
            env=isolated_env(home), thinking={"type": "disabled"}, max_turns=5,
            max_budget_usd=0.15 if action in {"reconnect", "rotation"} else 0.10,
            mcp_servers=cast(Any, {"lesson_remote": {"type": transport,
                "url": base + ("/mcp" if transport == "http" else "/sse"),
                "headers": {"Authorization": "Bearer " + token}}}),
            hooks={"PreToolUse": [HookMatcher(matcher="mcp__lesson_remote__get_status|ListMcpResourcesTool|ReadMcpResourceTool",
                                              hooks=[guard]) ]})  # type: ignore[list-item]
        client = ClaudeSDKClient(options=options)
        calls: list[dict[str, Any]] = []
        results: list[dict[str, Any]] = []
        init: list[dict[str, Any]] = []
        terminals: list[dict[str, Any]] = []
        terminal: dict[str, Any] | None = None
        reconnect: dict[str, Any] | None = None
        server_status: list[dict[str, Any]] = []
        closed = False
        try:
            async with asyncio.timeout(90):
                await client.connect()
                prompt = f"Call mcp__lesson_remote__get_status exactly once with marker {marker}."
                if selected:
                    prompt += (" Then use ListMcpResourcesTool on server lesson_remote, "
                               f"followed by ReadMcpResourceTool to read {selected} from that server.")
                prompt += " Report the returned status and stop."
                await client.query(prompt)
                async for message in client.receive_response():
                    if isinstance(message, SystemMessage) and message.subtype == "init":
                        init.append({"session_id": message.data.get("session_id"),
                                     "mcp_servers": message.data.get("mcp_servers")})
                    elif isinstance(message, AssistantMessage):
                        for block in message.content:
                            if isinstance(block, ToolUseBlock):
                                calls.append({"id": block.id, "name": block.name, "input": block.input})
                    elif isinstance(message, UserMessage):
                        for part in message.content:
                            if isinstance(part, ToolResultBlock):
                                results.append({"id": part.tool_use_id, "is_error": part.is_error,
                                                "content": str(part.content)[:5000]})
                    elif isinstance(message, ResultMessage):
                        terminal = {"uuid": message.uuid, "session_id": message.session_id, "subtype": message.subtype,
                                    "is_error": message.is_error, "cost_usd": message.total_cost_usd}
                        terminals.append(terminal)
                server_status = _server_status(await client.get_mcp_status())
                if action in {"reconnect", "rotation"}:
                    before = [(row["name"], row["status"]) for row in
                              (await client.get_mcp_status())["mcpServers"]]
                    if action == "rotation":
                        fixture.revoke()
                        async with httpx.AsyncClient(timeout=8, trust_env=False) as http:
                            revoked = await http.post(base + "/mcp", json={"jsonrpc": "2.0", "id": 4,
                                "method": "tools/list"}, headers={"Authorization": "Bearer " + token})
                        token2, label2, second_discovery = await discover(base, fixture)
                        query = client._query
                        send_control = getattr(query, "_send_control_request", None)
                        if not callable(send_control):
                            raise ValueError("Connected SDK query is unavailable for credential rotation.")
                        changed = await send_control({"subtype": "mcp_set_servers",
                            "servers": {"lesson_remote": {"type": transport,
                                "url": base + ("/mcp" if transport == "http" else "/sse"),
                                "headers": {"Authorization": "Bearer " + token2}}}})
                        if changed.get("errors") or "lesson_remote" not in changed.get("added", []):
                            raise ValueError("The CLI did not accept the replacement MCP server configuration.")
                    else:
                        label2, second_discovery, changed, revoked = label, None, None, None
                    await client.reconnect_mcp_server("lesson_remote")
                    after = [(row["name"], row["status"]) for row in
                             (await client.get_mcp_status())["mcpServers"]]
                    reconnect = {"before": before, "after": after, "acknowledged": True,
                                 "set_servers": changed, "second_discovery": second_discovery,
                                 "second_credential_label": label2,
                                 "revoked_status": revoked.status_code if revoked else None}
                    marker = fixture.id + ":2"
                    await client.query(f"Call mcp__lesson_remote__get_status exactly once with marker {marker}. Say ready.")
                    async for message in client.receive_response():
                        if isinstance(message, SystemMessage) and message.subtype == "init":
                            init.append({"session_id": message.data.get("session_id"),
                                         "mcp_servers": message.data.get("mcp_servers")})
                        elif isinstance(message, AssistantMessage):
                            for block in message.content:
                                if isinstance(block, ToolUseBlock):
                                    calls.append({"id": block.id, "name": block.name, "input": block.input})
                        elif isinstance(message, UserMessage):
                            for part in message.content:
                                if isinstance(part, ToolResultBlock):
                                    results.append({"id": part.tool_use_id, "is_error": part.is_error,
                                                    "content": str(part.content)[:5000]})
                        elif isinstance(message, ResultMessage):
                            terminal = {"uuid": message.uuid, "session_id": message.session_id, "subtype": message.subtype,
                                        "is_error": message.is_error, "cost_usd": message.total_cost_usd}
                            terminals.append(terminal)
        finally:
            await client.disconnect()
            closed = True
        status_calls = [row for row in calls if row["name"] == "mcp__lesson_remote__get_status"]
        resource_calls = [row for row in calls if row["name"] == "ReadMcpResourceTool"]
        result_ids = {row["id"] for row in results if not row["is_error"]}
        receipts = [row["receipt_id"] for row in fixture.handlers if row["marker"] == marker]
        status_results = [row for row in results if status_calls and row["id"] == status_calls[0]["id"]]
        passed = bool(len(status_calls) == 1 and status_calls[0]["input"] == {"marker": marker}
            and status_calls[0]["id"] in result_ids and
            len(status_results) == 1 and any(receipt in status_results[0]["content"] for receipt in receipts) and
            any(row["marker"] == marker and row["credential_label"] == label
                and _wire_matches(fixture, row) for row in fixture.handlers)
            and len(pre) >= len(calls) and all(row["allowed"] for row in pre)
            and len(init) == 1 and terminal and terminal["subtype"] == "success"
            and not terminal["is_error"] and terminal["session_id"] == init[0]["session_id"]
            and _canonical_uuid(terminal["session_id"]) and _canonical_uuid(terminal["uuid"])
            and isinstance(terminal["cost_usd"], (int, float)) and math.isfinite(terminal["cost_usd"])
            and terminal["cost_usd"] >= 0
            and any(row["name"] == "lesson_remote" and row["status"] == "connected"
                    and "get_status" in row["tool_names"]
                    for row in server_status)
            and any(isinstance(row, dict) and row.get("name") == "lesson_remote"
                    and row.get("status") == "connected"
                    for row in (init[0].get("mcp_servers") or []))
            and closed)
        if selected:
            listed = [row for row in calls if row["name"] == "ListMcpResourcesTool"]
            resource_results = [row for row in results if resource_calls and row["id"] == resource_calls[0]["id"]]
            passed = bool(passed and len(resource_calls) == 1 and
                          len(listed) == 1 and listed[0]["id"] in result_ids and
                          len(resource_results) == 1 and resource_calls[0]["id"] in result_ids and
                          selected in resource_results[0]["content"] and
                          any(row["uri"] == selected for row in fixture.reads) and
                          any(row.get("rpc_method") == "resources/read" and
                              row.get("resource_uri") == selected and row.get("status") in {200, 202}
                              for row in fixture.wire))
        if action in {"reconnect", "rotation"}:
            markers = [fixture.id + ":1", fixture.id + ":2"]
            paired = all(
                len([call for call in status_calls if call["input"] == {"marker": selected_marker}]) == 1
                and any(row["marker"] == selected_marker and row["credential_label"] == label
                        and _wire_matches(fixture, row)
                        and any(row["receipt_id"] in result["content"] and result["id"] ==
                                next(call["id"] for call in status_calls if call["input"] == {"marker": selected_marker})
                                for result in results if not result["is_error"])
                        for row in fixture.handlers)
                for selected_marker, label in zip(markers, (label, label2), strict=True))
            passed = bool(paired and len(status_calls) == 2 and len(init) == 2 and
                          len(terminals) == 2 and len({row["session_id"] for row in init + terminals}) == 1 and
                          all(row["subtype"] == "success" and not row["is_error"] for row in terminals) and
                          all(_canonical_uuid(row["uuid"]) and
                              isinstance(row["cost_usd"], (int, float)) and math.isfinite(row["cost_usd"])
                              and row["cost_usd"] >= 0 for row in terminals) and
                          reconnect and reconnect["acknowledged"] and
                          (action != "rotation" or (reconnect["revoked_status"] == 401
                           and reconnect["second_credential_label"] != label
                           and reconnect["set_servers"].get("added") == ["lesson_remote"])) and
                          ("lesson_remote", "connected") in reconnect["before"] and
                          ("lesson_remote", "connected") in reconnect["after"] and
                          any(row["name"] == "lesson_remote" and row["status"] == "connected"
                              and "get_status" in row["tool_names"] for row in server_status) and
                          len(pre) >= len(calls) and all(row["allowed"] for row in pre) and closed)
        report = {"action": action, "transport": transport, "source_label": SOURCE_LIVE,
                "fixture_id": fixture.id, "discovery": discovery, "credential_label": label,
                "calls": calls, "results": results, "pre": pre, "initialization": init,
                "terminal": terminal, "terminals": terminals, "reconnect": reconnect,
                "server_status": server_status,
                "wire": fixture.wire, "handlers": fixture.handlers,
                "resource_reads": fixture.reads, "connection_closed": closed,
                "experiment_passed": passed}
        return cast(dict[str, Any], scrub_evidence(report, fixture.issued_values +
                                                   [fixture.client_id, fixture.client_secret]))


async def run(storage: Path, settings: Settings, action: str, mode: str,
              transport: str = "http", resource: str = "runbook",
              scenario: str = "normal") -> dict[str, Any]:
    if action not in ACTIONS or mode not in {"prepared", "local", "live"} or transport not in {"http", "sse"} or resource not in RESOURCES:
        raise ValueError("Unknown fixed lesson 43 action, mode, transport, or resource.")
    if mode == "live" and scenario != "normal":
        raise ValueError("Fault scenarios are prepared only.")
    if mode == "live" and action not in {"live-tool", "live-resource", "reconnect", "rotation"}:
        raise ValueError("This action is an owned host probe; choose the live tool, resource, reconnect, or rotation action.")
    if scenario not in {"normal", "missing", "foreign", "failed"}:
        raise ValueError("Unknown lesson 43 scenario.")
    report = (await live_action(storage, settings, action, transport, resource)
              if mode == "live"
              else await local_action(action, transport, resource, scenario))
    report["mode"] = "live" if mode == "live" else "local"
    report["run_id"] = uuid.uuid4().hex
    report["expected_check"] = "passed" if report["experiment_passed"] else "needs-review"
    lanes = report.get("lanes") or [report]
    frames = sum(len(lane.get(key, [])) for lane in lanes for key in
                 ("wire", "handlers", "resource_reads", "protocol_pairs", "calls", "results", "pre", "initialization"))
    if frames > MAX_EVIDENCE_FRAMES or len(json.dumps(report, default=str).encode()) > MAX_EVIDENCE_BYTES:
        raise ValueError("Lesson 43 evidence exceeded its bounded report limit.")
    if report["experiment_passed"]:
        folder = storage / report["run_id"]
        folder.mkdir(parents=True, exist_ok=True)
        summary = {"run_id": report["run_id"], "action": action, "mode": report["mode"],
                   "check": "passed", "created_at": datetime.now(UTC).isoformat()}
        (folder / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
        pointer = storage / ("latest-" + report["run_id"] + ".json")
        pointer.write_text(json.dumps({"run_id": report["run_id"]}), encoding="utf-8")
        pointer.replace(storage / "latest.json")
    return report


def state(storage: Path) -> dict[str, Any]:
    pointer = storage / "latest.json"
    if not pointer.is_file() or pointer.is_symlink() or pointer.stat().st_nlink != 1 or pointer.stat().st_size > 128:
        raise ValueError("No completed lesson 43 summary is available.")
    pointer_data = json.loads(pointer.read_text(encoding="utf-8"))
    run_id = pointer_data.get("run_id") if isinstance(pointer_data, dict) else None
    try:
        if not isinstance(run_id, str) or uuid.UUID(run_id).hex != run_id:
            raise ValueError
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("Invalid lesson 43 run pointer.") from exc
    target = storage / run_id / "summary.json"
    if not target.is_file() or target.is_symlink() or target.stat().st_nlink != 1 or target.stat().st_size > 2048:
        raise ValueError("Owned lesson 43 summary is unavailable or unsafe.")
    item = json.loads(target.read_text(encoding="utf-8"))
    if (not isinstance(item, dict) or set(item) != {"run_id", "action", "mode", "check", "created_at"}
            or item.get("run_id") != run_id or item.get("check") != "passed"
            or item.get("action") not in ACTIONS or item.get("mode") not in {"local", "live"}):
        raise ValueError("Owned lesson 43 summary identity mismatch.")
    return item


async def execute_lesson(root: Path, request: RunRequest, settings: Settings,
                         emit: Any) -> dict[str, Any]:
    request = lesson_request(43, request)
    selected = request.lesson_options
    action = ({"tool": "live-tool", "resource": "live-resource", "rotate": "rotation"}[selected["step"]]
              if selected["action"] == "live" else selected["action"])
    report = await run(root / "owned-remote-mcp", settings, action,
                       "live" if request.mode == "live" else "prepared", selected["transport"],
                       selected["resource"], "normal" if request.scenario == "success" else request.scenario)
    terminal = report.get("terminal") or {}
    if isinstance(terminal.get("cost_usd"), (int, float)):
        await emit(Event(kind="result", data={"lesson_id": 43, "total_cost_usd": terminal["cost_usd"]}))
    proof = {"experiment": report, "experiment_passed": report["experiment_passed"]}
    await emit(Event(kind="evidence", data={"lesson_id": 43, "result": proof}))
    return proof


async def local(root: Path, request: RunRequest) -> dict[str, Any]:
    async def ignore(event: Event) -> None:
        pass
    return await execute_lesson(root, request.model_copy(update={"mode": "offline"}), Settings(), ignore)
