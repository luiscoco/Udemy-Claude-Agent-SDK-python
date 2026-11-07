"""Owned loopback MCP fixture with local machine credentials and resources."""

import hashlib
import json
import secrets
import time
import uuid
from typing import Any, cast
from urllib.parse import parse_qs

import httpx
from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamable_http_client
from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ResourceLink
from pydantic import AnyUrl


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class RemoteFixture:
    def __init__(self, transport: str = "http") -> None:
        if transport not in {"http", "sse"}:
            raise ValueError("Choose an owned HTTP or SSE fixture.")
        self.transport = transport
        self.id = str(uuid.uuid4())
        self.client_id = secrets.token_urlsafe(20)
        self.client_secret = secrets.token_urlsafe(32)
        self.tokens: dict[str, tuple[str, float]] = {}
        self.issued_values: list[str] = []
        self.label_number = 0
        self.base = ""
        self.sessions: set[str] = set()
        self.wire: list[dict[str, Any]] = []
        self.handlers: list[dict[str, Any]] = []
        self.reads: list[dict[str, Any]] = []
        self.server = self._server()
        self.app = self.server.streamable_http_app() if transport == "http" else self.server.sse_app()

    def _server(self) -> FastMCP:
        server = FastMCP("lesson_remote", log_level="WARNING", json_response=True,
                         stateless_http=False, streamable_http_path="/mcp")

        @server.tool()
        def get_status(marker: str, ctx: Context) -> str:
            """Return ready only for this fixture's numbered literal marker."""
            if marker not in {self.id + ":1", self.id + ":2"}:
                raise ValueError("Foreign fixture marker.")
            receipt = str(uuid.uuid4())
            payload = {"status": "ready", "marker": marker, "fixtureId": self.id,
                       "receiptId": receipt}
            request_row = next((row for row in reversed(self.wire)
                                if row.get("rpc_method") == "tools/call" and
                                row.get("marker") == marker and
                                str(row.get("rpc_id")) == str(ctx.request_id)), None)
            self.handlers.append({"tool": "get_status", "marker": marker,
                                  "fixture_id": self.id, "receipt_id": receipt,
                                  "rpc_id": ctx.request_id,
                                  "credential_label": request_row.get("credential_label") if request_row else None,
                                  "connection_id": request_row.get("connection_id") if request_row else None})
            return json.dumps(payload)

        @server.tool()
        def find_order() -> ResourceLink:
            """Find the fixed order resource URI."""
            return ResourceLink(type="resource_link", uri=AnyUrl("orders://1001"),
                                name="order 1001", mimeType="application/json")

        @server.resource("docs://runbook")
        def runbook() -> str:
            """Read the owned recovery runbook."""
            return self._resource("docs://runbook", f"Recovery word OSPREY-43. Fixture {self.id}.")

        @server.resource("docs://incident-43")
        def incident() -> str:
            """Read a local incident note."""
            return self._resource("docs://incident-43", "Reconnect with a new credential label.")

        @server.resource("files://logo.png", mime_type="image/png")
        def logo() -> bytes:
            """Read a fixed tiny PNG resource."""
            data = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000b49444154789c636000020000050001a5f645400000000049454e44ae426082")
            self.reads.append({"uri": "files://logo.png", "sha256": _sha(data), "bytes": len(data)})
            return data

        @server.resource("ui://orders/widget", mime_type="text/html")
        def widget() -> str:
            """Read inert fixture HTML as data."""
            return self._resource("ui://orders/widget", "<div>Owned order widget fixture; display as data.</div>")

        @server.resource("orders://{order_id}")
        def order(order_id: str) -> str:
            """Read only the fixed shipped order."""
            if order_id != "1001":
                raise ValueError("Only order 1001 is available.")
            return self._resource("orders://1001", json.dumps({"id": "1001", "status": "shipped"}))

        return server

    def _resource(self, uri: str, content: str) -> str:
        raw = content.encode()
        self.reads.append({"uri": uri, "sha256": _sha(raw), "bytes": len(raw)})
        return content

    def revoke(self) -> None:
        self.tokens.clear()

    def issue(self) -> tuple[str, str]:
        self.label_number += 1
        label = f"credential-{self.label_number}"
        value = secrets.token_urlsafe(32)
        self.tokens[value] = (label, time.monotonic() + 60)
        self.issued_values.append(value)
        return value, label

    def credential_label(self, headers: dict[str, str]) -> str | None:
        auth = headers.get("authorization", "")
        if not auth.startswith("Bearer "):
            return None
        granted = self.tokens.get(auth.removeprefix("Bearer "))
        return granted[0] if granted and granted[1] > time.monotonic() else None

    async def _respond(self, send: Any, status: int, data: dict[str, Any],
                       extra: list[tuple[bytes, bytes]] | None = None) -> None:
        raw = json.dumps(data).encode()
        headers = [(b"content-type", b"application/json"), (b"content-length", str(len(raw)).encode())]
        await send({"type": "http.response.start", "status": status,
                    "headers": headers + (extra or [])})
        await send({"type": "http.response.body", "body": raw})

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        headers = {key.decode().lower(): value.decode() for key, value in scope.get("headers", [])}
        host = headers.get("host", "")
        if not host.startswith("127.0.0.1:") or ("origin" in headers and headers["origin"] != self.base):
            await self._respond(send, 400, {"error": "invalid_host_or_origin"})
            return
        if path == "/.well-known/oauth-protected-resource/mcp":
            await self._respond(send, 200, {"resource": self.base + "/mcp",
                                            "authorization_servers": [self.base + "/issuer"]})
            return
        if path == "/.well-known/oauth-authorization-server/issuer":
            await self._respond(send, 200, {"issuer": self.base + "/issuer",
                                            "token_endpoint": self.base + "/issuer/credential",
                                            "grant_types_supported": ["client_credentials"],
                                            "token_endpoint_auth_methods_supported": ["client_secret_post"]})
            return
        if path == "/issuer/credential" and scope.get("method") == "POST":
            chunks = []
            while True:
                message = await receive()
                chunks.append(message.get("body", b""))
                if not message.get("more_body"):
                    break
            fields = parse_qs(b"".join(chunks).decode())
            if (fields.get("client_id") != [self.client_id] or
                fields.get("client_secret") != [self.client_secret] or
                fields.get("grant_type") != ["client_credentials"] or
                fields.get("resource") != [self.base + "/mcp"]):
                await self._respond(send, 401, {"error": "invalid_client"})
                return
            token, _ = self.issue()
            await self._respond(send, 200, {"access_token": token, "token_type": "Bearer",
                                            "expires_in": 60})
            return
        protected = path == "/mcp" or path == "/sse" or path.startswith("/messages")
        if protected:
            label = self.credential_label(headers)
            if label is None:
                challenge = f'Bearer resource_metadata="{self.base}/.well-known/oauth-protected-resource/mcp"'
                await self._respond(send, 401, {"error": "invalid_token"},
                                    [(b"www-authenticate", challenge.encode())])
                return
            session = headers.get("mcp-session-id")
            query_session = parse_qs(scope.get("query_string", b"").decode()).get("session_id", [None])[0]
            if path == "/mcp" and session and session not in self.sessions:
                await self._respond(send, 404, {"error": "unknown_session"})
                return
            if path == "/mcp" and scope.get("method") == "POST" and not session:
                # The MCP server itself handles initialize. Other methods need a session.
                chunks = []
                while True:
                    message = await receive()
                    chunks.append(message.get("body", b""))
                    if not message.get("more_body"):
                        break
                raw = b"".join(chunks)
                try:
                    method = json.loads(raw).get("method")
                except (ValueError, AttributeError):
                    method = None
                if method != "initialize":
                    await self._respond(send, 400, {"error": "initialization_required"})
                    return
                yielded = False

                async def replay() -> dict[str, Any]:
                    nonlocal yielded
                    if yielded:
                        return {"type": "http.request", "body": b"", "more_body": False}
                    yielded = True
                    return {"type": "http.request", "body": raw, "more_body": False}

                receive = replay
            row: dict[str, Any] = {"path": path, "method": scope.get("method"),
                                   "credential_label": label, "session_id": session,
                                   "connection_id": self.id + ":" + (session or query_session or "initializing")}
            self.wire.append(row)

            async def tap(message: dict[str, Any]) -> None:
                if message.get("type") == "http.response.start":
                    for key, value in message.get("headers", []):
                        if key.lower() == b"mcp-session-id":
                            self.sessions.add(value.decode())
                            row["connection_id"] = self.id + ":" + value.decode()
                    row["status"] = message.get("status")
                await send(message)

            body_parts: list[bytes] = []

            async def observed_receive() -> dict[str, Any]:
                message = await receive()
                if message.get("type") == "http.request" and len(body_parts) < 4:
                    body_parts.append(message.get("body", b"")[:16384])
                    if not message.get("more_body"):
                        try:
                            request = json.loads(b"".join(body_parts))
                            if isinstance(request, dict):
                                row["rpc_method"] = request.get("method")
                                row["rpc_id"] = request.get("id")
                                params = request.get("params")
                                if request.get("method") == "tools/call" and isinstance(params, dict):
                                    row["tool_name"] = params.get("name")
                                    arguments = params.get("arguments")
                                    if params.get("name") == "get_status" and isinstance(arguments, dict):
                                        row["marker"] = arguments.get("marker")
                                if request.get("method") == "resources/read" and isinstance(params, dict):
                                    row["resource_uri"] = params.get("uri")
                        except ValueError:
                            pass
                return message

            await self.app(scope, observed_receive, cast(Any, tap))
            return
        await self._respond(send, 404, {"error": "not_found"})


async def discover(base: str, fixture: RemoteFixture) -> tuple[str, str, list[dict[str, Any]]]:
    steps: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=8, follow_redirects=False, trust_env=False) as client:
        challenge = await client.post(base + "/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        if challenge.status_code != 401:
            raise ValueError("Initial protected request did not challenge.")
        steps.append({"step": 1, "status": 401, "kind": "challenge"})
        protected = await client.get(base + "/.well-known/oauth-protected-resource/mcp")
        meta = protected.json()
        if meta != {"resource": base + "/mcp", "authorization_servers": [base + "/issuer"]}:
            raise ValueError("Protected resource metadata mismatch.")
        steps.append({"step": 2, "status": 200, "kind": "protected-resource"})
        authorization = await client.get(base + "/.well-known/oauth-authorization-server/issuer")
        auth = authorization.json()
        if auth.get("issuer") != base + "/issuer" or auth.get("token_endpoint") != base + "/issuer/credential":
            raise ValueError("Authorization server metadata mismatch.")
        steps.append({"step": 3, "status": 200, "kind": "authorization-server"})
        grant = await client.post(base + "/issuer/credential", data={"client_id": fixture.client_id,
            "client_secret": fixture.client_secret, "grant_type": "client_credentials",
            "resource": base + "/mcp"})
        token = grant.json().get("access_token")
        if grant.status_code != 200 or token not in fixture.tokens:
            raise ValueError("Local machine grant failed.")
        label = fixture.tokens[token][0]
        steps.append({"step": 4, "status": 200, "kind": "machine-grant", "credential_label": label})
        return token, label, steps


async def host_probe(base: str, fixture: RemoteFixture, token: str,
                     transport: str, marker: str, resource: str | None = None) -> dict[str, Any]:
    headers = {"Authorization": "Bearer " + token}
    if transport == "http":
        async with httpx.AsyncClient(headers=headers, timeout=20, trust_env=False) as client:
            async with streamable_http_client(base + "/mcp", http_client=client) as (reader, writer, session_id):
                async with ClientSession(reader, writer) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    resources = await session.list_resources()
                    templates = await session.list_resource_templates()
                    result = await session.call_tool("get_status", {"marker": marker})
                    link = await session.call_tool("find_order", {})
                    target = _resource_target(link, resource)
                    read = await session.read_resource(target) if target else None
                    return _probe_result(fixture, transport, tools.tools, resources.resources,
                                         templates.resourceTemplates, result, read, session_id(), link,
                                         resource == "orders://1001" and target is not None)
    async with sse_client(base + "/sse", headers=headers, timeout=20, sse_read_timeout=25) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            tools = await session.list_tools()
            resources = await session.list_resources()
            templates = await session.list_resource_templates()
            result = await session.call_tool("get_status", {"marker": marker})
            link = await session.call_tool("find_order", {})
            target = _resource_target(link, resource)
            read = await session.read_resource(target) if target else None
            return _probe_result(fixture, transport, tools.tools, resources.resources,
                                 templates.resourceTemplates, result, read, None, link,
                                 resource == "orders://1001" and target is not None)


def _resource_target(link: Any, requested: str | None) -> AnyUrl | None:
    if requested is None:
        return None
    if requested == "orders://1001":
        linked = [item.uri for item in link.content if isinstance(item, ResourceLink)]
        if len(linked) != 1 or str(linked[0]) != requested:
            raise ValueError("Fixed order resource link was missing or foreign.")
        return linked[0]
    return AnyUrl(requested)


def _probe_result(fixture: RemoteFixture, transport: str, tools: Any, resources: Any,
                  templates: Any, result: Any, read: Any, session_id: str | None,
                  link: Any, followed_order_link: bool) -> dict[str, Any]:
    content = [item.text for item in result.content if getattr(item, "type", "") == "text"]
    payload = json.loads(content[0]) if content else {}
    returned = None
    if read is not None:
        returned = [item.model_dump(mode="json") for item in read.contents]
    return {"transport": transport, "fixture_id": fixture.id, "session_id": session_id,
            "tools": [item.name for item in tools],
            "resources": [str(item.uri) for item in resources],
            "templates": [str(item.uriTemplate) for item in templates],
            "resource_links": [item.model_dump(mode="json") for item in link.content
                               if getattr(item, "type", "") == "resource_link"],
            "followed_order_link": followed_order_link,
            "status_is_error": result.isError, "status_payload": payload,
            "resource_contents": returned}
