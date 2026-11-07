"""Owned loopback cloud-format proxy for Lesson 45 local protocol work.

The proxy stores only sanitized wire receipts. Its local responder is an
authored fixture, and callers must never use it as evidence of cloud access.
"""

import hashlib
import hmac
import json
import re
import secrets
import uuid
from typing import Any
from urllib.parse import parse_qs, unquote

import httpx

from agent_lab.cloud_wire import (
    HAIKU,
    PROFILE,
    SONNET,
    SSEDecoder,
    canonical_model,
    eventstream_packet,
    verify_sigv4,
)

PROVIDERS = ("firstParty", "bedrock", "vertex", "foundry", "gateway")
LANE_REGIONS = {"bedrock": "us-east-1", "vertex": "us-east5"}
AUDIENCE = "//iam.googleapis.com/projects/123/locations/global/workloadIdentityPools/lesson45/providers/owned"
SUBJECT_TYPE = "urn:ietf:params:oauth:token-type:jwt"
GRANT_TYPE = "urn:ietf:params:oauth:grant-type:token-exchange"


class CloudProxy:
    def __init__(self, run_id: str, lane: str, provider: str, *, inspect_only: bool = False,
                 upstream_key: str | None = None,
                 upstream_transport: httpx.AsyncBaseTransport | None = None) -> None:
        if provider not in PROVIDERS or not lane or len(lane) > 32:
            raise ValueError("Unknown owned cloud lane")
        self.run_id, self.lane, self.provider = run_id, lane, provider
        self.inspect_only = inspect_only
        self.prefix = f"/r/{run_id}/{lane}/{provider}"
        self.access_id = "LAB" + secrets.token_hex(8).upper()
        self.secret = secrets.token_hex(32)
        self.bearer = secrets.token_hex(32)
        self.subject = secrets.token_hex(32)
        self.issued_vertex: set[str] = set()
        self.receipts: list[dict[str, Any]] = []
        self.base = ""
        self.closed = False
        self.forwarded = 0
        self.forward_diagnostics: list[dict[str, Any]] = []
        self.upstream_key = upstream_key
        self.upstream_transport = upstream_transport

    async def _forward(self, body: bytes, streaming: bool, beta: str) -> tuple[int, bytes, str, str | None, int]:
        """Translate one fixed Haiku request; never forward provider credentials."""
        if not self.upstream_key or self.forwarded >= 8:
            return 503, b'{"error":"upstream_unavailable"}', "application/json", None, 0
        try:
            payload = json.loads(body)
            if not isinstance(payload, dict) or not isinstance(payload.get("messages"), list):
                raise ValueError
            payload.pop("anthropic_version", None)
            payload.pop("anthropic_beta", None)
            payload["model"] = HAIKU
            payload["stream"] = streaming
            system_messages = [item for item in payload["messages"] if isinstance(item, dict)
                               and item.get("role") == "system"]
            if system_messages:
                payload["messages"] = [item for item in payload["messages"] if item not in system_messages]
                existing = payload.get("system")
                system_parts = [existing] if isinstance(existing, str) else []
                for item in system_messages:
                    content = item.get("content")
                    if isinstance(content, str):
                        system_parts.append(content)
                    elif isinstance(content, list):
                        system_parts.extend(block["text"] for block in content if isinstance(block, dict)
                                            and isinstance(block.get("text"), str))
                payload["system"] = "\n".join(system_parts)
            tokens = payload.get("max_tokens")
            payload["max_tokens"] = min(tokens, 96) if isinstance(tokens, int) and tokens > 0 else 96
        except (ValueError, UnicodeError):
            return 400, b'{"error":"invalid_message"}', "application/json", None, 0
        headers = {"x-api-key": self.upstream_key, "anthropic-version": "2023-06-01",
                   "content-type": "application/json"}
        if beta and len(beta) <= 500 and all(character.isalnum() or character in "-_., " for character in beta):
            headers["anthropic-beta"] = beta
        self.forwarded += 1
        try:
            async with httpx.AsyncClient(timeout=20, trust_env=False, follow_redirects=False,
                                         transport=self.upstream_transport) as client:
                response = await client.post("https://api.anthropic.com/v1/messages", headers=headers,
                                             json=payload)
            if response.status_code != 200:
                try:
                    failure = response.json().get("error", {})
                    message = failure.get("message", "") if isinstance(failure, dict) else ""
                    kind = failure.get("type") if isinstance(failure, dict) else None
                    safe_message = re.sub(r"(?:sk-ant-|Bearer |https?://)[^\s]+|[A-Za-z0-9_-]{40,}",
                                          "[redacted]", str(message))[:180]
                except (ValueError, UnicodeError):
                    kind, safe_message = None, ""
                self.forward_diagnostics.append({"status": response.status_code,
                    "error_type": kind if isinstance(kind, str) and re.fullmatch(r"[a-z_]{1,40}", kind) else None,
                    "message": safe_message, "body_keys": sorted(payload)[:30]})
            if len(response.content) > 2_000_000:
                return 502, b'{"error":"upstream_limit"}', "application/json", None, response.status_code
            if response.status_code != 200:
                return 502, b'{"error":"upstream_rejected"}', "application/json", None, response.status_code
            message_id: str | None = None
            if streaming:
                decoder = SSEDecoder(max_pending=2_000_000)
                events = decoder.feed(response.content)
                for event in events:
                    message = event.get("message")
                    if event.get("type") == "message_start" and isinstance(message, dict):
                        candidate = message.get("id")
                        if isinstance(candidate, str):
                            message_id = candidate
                            break
                if not isinstance(message_id, str):
                    return 502, b'{"error":"missing_message_identity"}', "application/json", None, 200
                if self.provider == "bedrock":
                    frames = [eventstream_packet(
                        ("event: " + str(event.get("type", "message")) + "\n" +
                         "data: " + json.dumps(event, separators=(",", ":")) + "\n\n").encode())
                        for event in events]
                    return 200, b"".join(frames), "application/vnd.amazon.eventstream", message_id, 200
                return 200, response.content, "text/event-stream", message_id, 200
            data = response.json()
            message_id = data.get("id") if isinstance(data, dict) else None
            if not isinstance(message_id, str):
                return 502, b'{"error":"missing_message_identity"}', "application/json", None, 200
            return 200, response.content, "application/json", message_id, 200
        except (httpx.HTTPError, ValueError, UnicodeError):
            return 502, b'{"error":"upstream_transport"}', "application/json", None, 0

    @staticmethod
    def _response(status: int, data: dict[str, Any]) -> tuple[int, bytes]:
        return status, json.dumps(data, separators=(",", ":")).encode()

    def _route(self, method: str, suffix: str, body: bytes) -> tuple[str, str | None, str | None, bool]:
        if method == "GET" and suffix in {"/catalog", "/inference-profiles", f"/inference-profiles/{PROFILE}"}:
            return "catalog", None, None, False
        if method == "POST" and suffix == "/sts" and self.provider == "vertex":
            return "sts", None, None, False
        if method != "POST":
            return "rejected", None, None, False
        model: str | None = None
        streaming = False
        if self.provider == "bedrock" and suffix.startswith("/model/"):
            if suffix.endswith("/invoke-with-response-stream"):
                model, streaming = unquote(suffix[7:-28]), True
            elif suffix.endswith("/invoke"):
                model = unquote(suffix[7:-7])
        elif self.provider == "vertex":
            prefix = "/v1/projects/lesson45-project/locations/"
            if suffix.startswith(prefix) and "/publishers/anthropic/models/" in suffix:
                head, tail = suffix.split("/publishers/anthropic/models/", 1)
                if head[len(prefix):] in {"us-east5", "europe-west1"}:
                    if tail.endswith(":streamRawPredict"):
                        model, streaming = unquote(tail[:-17]), True
                    elif tail.endswith(":rawPredict"):
                        model = unquote(tail[:-11])
        elif ((self.provider == "foundry" and suffix == "/anthropic/v1/messages") or
              (self.provider in {"firstParty", "gateway"} and suffix == "/v1/messages")):
            try:
                parsed = json.loads(body)
                model = parsed.get("model") if isinstance(parsed, dict) else None
                streaming = parsed.get("stream") is True if isinstance(parsed, dict) else False
            except (ValueError, UnicodeError):
                pass
        return ("model" if isinstance(model, str) else "rejected"), model, canonical_model(model) if isinstance(model, str) else None, streaming

    def _authenticated(self, method: str, path: bytes, query: bytes,
                       headers: dict[str, str], body: bytes, kind: str) -> tuple[bool, str]:
        if self.provider == "bedrock":
            if headers.get("authorization", "").startswith("AWS4-HMAC-SHA256 "):
                return (verify_sigv4(method, path, query, headers, body, self.access_id,
                        self.secret, LANE_REGIONS["bedrock"]), "sigv4")
            return (hmac.compare_digest(headers.get("authorization", ""), "Bearer " + self.bearer), "bearer")
        if self.provider == "vertex":
            if kind == "sts":
                return True, "owned-subject"
            token = headers.get("authorization", "")
            return (token.startswith("Bearer ") and token[7:] in self.issued_vertex, "wif")
        if self.provider == "gateway":
            return (hmac.compare_digest(headers.get("authorization", ""), "Bearer " + self.bearer), "bearer")
        return (hmac.compare_digest(headers.get("x-api-key", ""), self.bearer), "x-api-key")

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            return
        method = scope["method"]
        path = scope["path"]
        raw_path = scope.get("raw_path", path.encode())
        query = scope.get("query_string", b"")
        header_pairs = [(key.decode("latin1").lower(), value.decode("latin1"))
                        for key, value in scope["headers"]]
        headers = dict(header_pairs)
        duplicate = len(headers) != len(header_pairs)
        chunks: list[bytes] = []
        size = 0
        too_large = False
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            part = message.get("body", b"")
            size += len(part)
            if size <= 2_000_000:
                chunks.append(part)
            else:
                too_large = True
            if not message.get("more_body", False):
                break
        body = b"".join(chunks)
        suffix = path[len(self.prefix):] if path.startswith(self.prefix + "/") else ""
        kind, wire_model, canonical, streaming = self._route(method, suffix, body)
        host = headers.get("host", "")
        owned_host = self.base.split("//", 1)[-1]
        host_ok = host == owned_host or (self.provider == "bedrock" and host == "127.0.0.1")
        origin_ok = headers.get("origin", self.base) == self.base
        valid_route = bool(suffix and kind != "rejected")
        auth_ok, auth_kind = self._authenticated(method, raw_path, query, headers, body, kind)
        reason = "accepted"
        marker: str | None = None
        native_body: bytes | None = None
        content_type = "application/json"
        upstream_status: int | None = None
        upstream_message_id: str | None = None
        answer: dict[str, Any]
        if self.closed or len(self.receipts) >= 40:
            status, answer, reason = 429, {"error": "lane_closed_or_full"}, "limit"
        elif too_large:
            status, answer, reason = 413, {"error": "body_limit"}, "body"
        elif duplicate or not host_ok or not origin_ok or not valid_route:
            status, answer, reason = 400, {"error": "route_rejected"}, "route"
        elif not auth_ok:
            status, answer, reason = 401, {"error": "unauthorized"}, "auth"
        elif kind == "sts":
            try:
                if headers.get("content-type", "").startswith("application/x-www-form-urlencoded"):
                    values = parse_qs(body.decode("utf-8"), strict_parsing=True)
                    request = {key: item[0] for key, item in values.items() if len(item) == 1}
                else:
                    request = json.loads(body)
            except (ValueError, UnicodeError):
                request = {}
            if (not isinstance(request, dict) or request.get("audience") != AUDIENCE or
                    request.get("subject_token_type") != SUBJECT_TYPE or
                    request.get("grant_type") != GRANT_TYPE or
                    request.get("subject_token") != self.subject):
                status, answer, reason = 401, {"error": "invalid_subject"}, "auth"
            else:
                token = secrets.token_hex(32)
                self.issued_vertex.add(token)
                status, answer = 200, {"access_token": token, "token_type": "Bearer", "expires_in": 300}
        elif kind == "catalog":
            if suffix.endswith(PROFILE):
                status, answer = 200, {"inferenceProfileArn": PROFILE, "models": [HAIKU]}
            else:
                status, answer = 200, {"models": [HAIKU, SONNET], "profile": PROFILE}
        elif self.inspect_only:
            status, answer, reason = 403, {"error": "inspection_only"}, "inspection"
        elif canonical is None:
            status, answer, reason = 400, {"error": "unsupported_model"}, "model"
        elif canonical == SONNET:
            answer = ({"message": "Model access denied by owned lab", "__type": "AccessDeniedException",
                       "type": "error", "error": {"type": "permission_error",
                                                  "message": "Model access denied by owned lab"}}
                      if self.provider == "bedrock" else {"error": "controlled_access_denial"})
            status, reason = 403, "model"
        else:
            marker_match = re.search(r"L45-[A-Za-z0-9-]{1,40}", body.decode("utf-8", "ignore"))
            marker = marker_match.group() if marker_match else None
            if self.upstream_key:
                status, native_body, content_type, upstream_message_id, upstream_status = await self._forward(
                    body, streaming, headers.get("anthropic-beta", ""))
                answer = {"id": upstream_message_id} if upstream_message_id else {"error": "upstream_failure"}
            else:
                status, answer = 200, {"id": "msg_" + uuid.uuid4().hex, "type": "message",
                                        "model": HAIKU, "content": [{"type": "text", "text": "READY " + (marker or "")}]}
        safe_path = (path if kind in {"catalog", "sts"} or canonical is not None
                     else "[unsupported-model-route]" if kind == "model" else "[rejected-route]")
        safe_wire_model = (wire_model if wire_model == PROFILE or
                           (isinstance(wire_model, str) and len(wire_model) <= 120 and
                            re.fullmatch(r"(?:(?:us|eu|apac|global)\.)?(?:anthropic\.)?claude-[a-z0-9:@._-]+",
                                         wire_model)) else None)
        receipt = {"id": str(uuid.uuid4()), "provider": self.provider, "lane": self.lane,
                   "run_id": self.run_id, "method": method, "path": safe_path,
                   "body_sha256": hashlib.sha256(body).hexdigest(), "auth_kind": auth_kind,
                   "auth_verdict": bool(auth_ok and reason != "auth"), "status": status,
                   "kind": kind, "route_reason": reason,
                   "wire_model": safe_wire_model,
                   "canonical_model": canonical, "streaming": streaming,
                   "marker_seen": marker if kind == "model" and status == 200 else None,
                   "message_id": answer.get("id") if isinstance(answer, dict) else None,
                   "upstream_status": upstream_status}
        self.receipts.append(receipt)
        if native_body is None:
            status, response_body = self._response(status, answer)
        else:
            response_body = native_body
        response_headers = [(b"content-type", content_type.encode()),
                            (b"content-length", str(len(response_body)).encode())]
        if self.provider == "bedrock" and status == 403 and canonical == SONNET:
            response_headers.append((b"x-amzn-errortype", b"AccessDeniedException"))
            response_headers.append((b"x-should-retry", b"false"))
        await send({"type": "http.response.start", "status": status,
                    "headers": response_headers})
        await send({"type": "http.response.body", "body": response_body})
