"""Real owned MCP transports and a bounded, token-scoped lifecycle workshop.

Workshop operations open/close a transport in the same request task. The workshop
handle persists inventory and enablement, not a live Claude conversation or CLI.
"""

import asyncio
import contextlib
import json
import secrets
import sys
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.memory import create_connected_server_and_client_session

from agent_lab.config import ROOT, Settings
from agent_lab.foundation_models import McpInputs
from agent_lab.integrations.inventory_mcp import Inventory, build_server, sdk_server
from agent_lab.models import LessonError, RunRequest, lesson_request


@contextlib.asynccontextmanager
async def server_config(inventory: Inventory, transport: str) -> AsyncIterator[tuple[dict, dict]]:
    """Only host-created commands, loopback URLs and SDK servers can be selected."""
    if transport == "sdk":
        config = sdk_server(inventory)
        yield config, {"type": "sdk", "name": "inventory"}
    elif transport == "stdio":
        config = {
            "type": "stdio",
            "command": sys.executable,
            "args": ["-m", "agent_lab.integrations.inventory_mcp"],
            "env": {
                "PYTHONPATH": str(ROOT),
                "LAB_INVENTORY_PATH": str(inventory.path.resolve()),
                "LAB_INVENTORY_LIMIT": str(inventory.reserve_limit),
                "LAB_INVENTORY_EXPECTED": json.dumps(inventory.expected),
            },
        }
        yield config, {k: v for k, v in config.items() if k != "env"}
    else:
        from agent_lab.exercises import EmbeddedServer

        async with EmbeddedServer(build_server(inventory).streamable_http_app()).running() as base:
            config = {"type": "http", "url": base + "/mcp"}
            yield config, dict(config)


@contextlib.asynccontextmanager
async def connected(
    inventory: Inventory, transport: str
) -> AsyncIterator[tuple[ClientSession, dict]]:
    """Enter/exit every MCP/HTTP/subprocess context in one owner task."""
    async with server_config(inventory, transport) as (config, echo):
        if transport == "sdk":
            async with create_connected_server_and_client_session(config["instance"]) as client:
                yield client, echo
        elif transport == "stdio":
            parameters = StdioServerParameters(
                command=config["command"], args=config["args"], env=config["env"]
            )
            async with stdio_client(parameters) as (reader, writer):
                async with ClientSession(reader, writer) as client:
                    await client.initialize()
                    yield client, echo
        else:
            async with streamable_http_client(config["url"]) as (reader, writer, _):
                async with ClientSession(reader, writer) as client:
                    await client.initialize()
                    yield client, echo


@dataclass
class Workshop:
    id: str
    token: str
    inventory: Inventory
    transport: str
    enabled: bool = True
    closed: bool = False
    connection_open: bool = False
    last_connected: bool = False
    tools: list[dict] = field(default_factory=list)
    timeline: list[dict] = field(default_factory=list)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    actions: int = 0
    created: float = field(default_factory=time.monotonic)

    def snapshot(self) -> dict:
        return {
            "application_handle": self.id,
            "transport": self.transport,
            "enabled": self.enabled,
            "closed": self.closed,
            "connection_open": self.connection_open,
            "last_probe_connected": self.last_connected,
            "discovered_tools": self.tools,
            "timeline": list(self.timeline),
            "scope": "Direct MCP workshop; no model. Each operation closes its owned transport. This handle is not an SDK session ID.",
        }

    async def operation(self, action: str, arguments: dict | None = None) -> dict:
        arguments = arguments or {}
        async with self.lock:
            if self.closed or time.monotonic() - self.created > 600:
                self.closed = True
                raise LessonError("The workshop is closed or expired. Open a new one.")
            if self.actions >= 30 and action != "end":
                raise LessonError(
                    "This workshop's action limit is reached. End it and open a new one."
                )
            self.actions += 1
            if action == "end":
                self.closed = True
                self.timeline.append({"action": "end", "connection_closed": True})
                return self.snapshot()
            if action == "reset":
                data = await asyncio.to_thread(self.inventory.reset)
                self.timeline.append({"action": "reset", "stock": data["stock"]})
                return data
            if action == "toggle":
                self.enabled = arguments["enabled"]
                self.timeline.append({"action": "toggle", "enabled": self.enabled})
                return self.snapshot()
            if action == "set-servers":
                self.transport = arguments["transport"]
                self.last_connected = False
                self.tools = []
                self.timeline.append({"action": "set-servers", "transport": self.transport})
                return self.snapshot()
            if not self.enabled:
                self.timeline.append({"action": action, "blocked": "server disabled"})
                raise LessonError(
                    "The inventory server is disabled; no transport or tool was started."
                )
            before = await asyncio.to_thread(self.inventory.read)
            self.connection_open = True
            self.last_connected = False
            try:
                async with asyncio.timeout(20):
                    async with connected(self.inventory, self.transport) as (client, echo):
                        tools = await client.list_tools()
                        self.tools = [
                            {"name": t.name, "input_schema": t.inputSchema} for t in tools.tools
                        ]
                        self.last_connected = True
                        self.timeline.append(
                            {"action": action, "connected": True, "configuration": echo}
                        )
                        if action in {"status", "reconnect"}:
                            return {"configuration": echo, "tools": self.tools}
                        name = arguments["tool"]
                        payload = arguments.get("arguments", {})
                        result = await client.call_tool(name, payload)
                        after = await asyncio.to_thread(self.inventory.read)
                        observed = {
                            "tool": name,
                            "arguments": payload,
                            "is_error": result.isError is True,
                            "content": [c.model_dump() for c in result.content],
                            "stock_before": before,
                            "stock_after": after,
                        }
                        self.timeline.append({"action": "tool-result", **observed})
                        return observed
            except Exception as exc:
                self.timeline.append({"action": "protocol-error", "error_type": type(exc).__name__})
                raise LessonError(
                    "The MCP connection or protocol failed. Inspect the workshop timeline; no automatic retry was made."
                ) from exc
            finally:
                self.connection_open = False
                self.timeline.append({"action": "transport-closed"})


class McpWorkshops:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.items: dict[str, Workshop] = {}
        self.lock = asyncio.Lock()

    async def start(self, transport: str) -> Workshop:
        async with self.lock:
            return await self._start(transport)

    async def _start(self, transport: str) -> Workshop:
        if transport not in {"stdio", "http", "sdk"}:
            raise LessonError("Choose an owned stdio, http or sdk transport.")
        for item in self.items.values():
            if time.monotonic() - item.created > 600:
                item.closed = True
        if sum(not w.closed for w in self.items.values()) >= self.settings.max_concurrent_runs:
            raise LessonError("All MCP workshop slots are occupied.")
        if len(self.items) >= 32:
            oldest = next((k for k, w in self.items.items() if w.closed), None)
            if oldest is None:
                raise LessonError("The workshop archive is full.")
            del self.items[oldest]
        identity = uuid.uuid4().hex
        inventory = Inventory(
            self.settings.data_dir / "mcp-workshops" / identity / "inventory.json"
        )
        await asyncio.to_thread(inventory.reset)
        workshop = Workshop(identity, secrets.token_urlsafe(24), inventory, transport)
        self.items[identity] = workshop
        return workshop

    def lookup(self, identity: str, token: str) -> Workshop:
        item = self.items.get(identity)
        if item is None or not secrets.compare_digest(
            item.token.encode("utf-8"), token.encode("utf-8")
        ):
            raise PermissionError("Unknown workshop or invalid control token.")
        return item

    async def close(self) -> None:
        for item in self.items.values():
            async with item.lock:
                item.closed = True


async def local_mcp(root: Path, request: RunRequest) -> dict:
    from agent_lab.foundations import Evidence, record_call

    request = lesson_request(13, request)
    selected = McpInputs.model_validate(request.lesson_options)
    inventory = Inventory(root / "inventory.json", reserve_limit=1)
    await asyncio.to_thread(
        inventory.reset, {"notebook": 0, "pen": 0} if request.scenario == "tool-error" else None
    )
    workshop = Workshop(
        root.parent.name, "offline-fixture", inventory, selected.transport, selected.enabled
    )
    evidence = Evidence(
        13,
        root.parent.name,
        root,
        selected.model_dump(),
        "actual MCP transports and inventory effects; explicitly recorded agent call/result fixtures",
    )
    evidence.initialized = [{"session_id": "recorded-parent"}]
    evidence.terminals = [
        {"subtype": "success", "is_error": False, "session_id": "recorded-parent"}
    ]
    evidence.configured = {
        "mcp_servers": {"inventory": {"type": selected.transport}} if selected.enabled else {},
        "allowed_tools": ["mcp__inventory__" + selected.tool],
    }
    before = await asyncio.to_thread(inventory.read)
    try:
        if selected.enabled:
            await workshop.operation("status")
            if selected.lifecycle == "toggle":
                await workshop.operation("toggle", {"enabled": False})
                try:
                    await workshop.operation("call", {"tool": selected.tool})
                except LessonError:
                    pass
                await workshop.operation("toggle", {"enabled": True})
            elif selected.lifecycle == "reconnect":
                await workshop.operation("reconnect")
            arguments = (
                {"sku": selected.sku, "quantity": selected.quantity}
                if selected.tool == "reserve"
                else {}
            )
            observed = await workshop.operation(
                "call", {"tool": selected.tool, "arguments": arguments}
            )
            record_call(evidence, "mcp__inventory__" + selected.tool, arguments, "recorded-call-1")
            evidence.results.append(
                {
                    "id": "recorded-call-1",
                    "is_error": observed["is_error"],
                    "run_id": evidence.run_id,
                }
            )
    finally:
        await workshop.operation("end")
    if request.scenario == "missing-evidence":
        evidence.terminals.clear()
    elif request.scenario == "wrong-identity" and evidence.results:
        evidence.results[0]["id"] = "unmatched"
    report = evidence.report()
    report.update(
        scenario=request.scenario,
        local_effects={
            "before": before,
            "after": await asyncio.to_thread(inventory.read),
            **workshop.snapshot(),
        },
        expected_check="passed" if report["experiment_passed"] else "needs-review",
    )
    return {"experiment": report, "experiment_passed": report["experiment_passed"]}
