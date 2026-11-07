"""Owned, bounded OTLP/HTTP JSON collector for the Lesson 44 lab."""

import asyncio
import hashlib
import json
import math
import re
import uuid
from typing import Any

ALLOWED = {"service.name", "service.version", "lab.run", "lab.lane", "session.id",
           "session_id", "tool_use_id", "gen_ai.tool.call.id", "tool_name", "event.name",
           "event.sequence", "event.timestamp", "model", "query_source", "type",
           "decision", "decision_type", "decision_source", "success", "cost_usd",
           "duration_ms", "span.type", "parent.source", "deployment.environment"}
SIGNALS = {"metrics": "resourceMetrics", "logs": "resourceLogs", "traces": "resourceSpans"}
HEX16 = re.compile(r"^[0-9a-fA-F]{16}$")
HEX32 = re.compile(r"^[0-9a-fA-F]{32}$")
SENSITIVE = re.compile(r"[/\\@]|sk-ant-|Bearer\s|[A-Za-z0-9_-]{50,}", re.I)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _attributes(raw: list[dict[str, Any]] | None) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for item in raw or []:
        key = item.get("key")
        if key not in ALLOWED:
            continue
        value = item.get("value", {})
        if not isinstance(value, dict):
            continue
        selected = next((value[k] for k in ("stringValue", "intValue", "doubleValue", "boolValue")
                         if k in value), None)
        if isinstance(selected, str) and (len(selected) > 160 or SENSITIVE.search(selected)):
            continue
        if isinstance(selected, (str, int, float, bool)) and not (
            isinstance(selected, float) and not math.isfinite(selected)
        ):
            result[key] = selected
    return result


def _timestamp(value: Any) -> int:
    if not isinstance(value, str) or not value.isdecimal() or len(value) > 22:
        raise ValueError("Invalid nanosecond timestamp")
    return int(value)


def decode(signal: str, body: bytes) -> tuple[list[dict[str, Any]], bool]:
    """Validate the whole envelope before returning sanitized rows."""
    try:
        envelope = json.loads(body)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("Malformed OTLP JSON") from exc
    key = SIGNALS[signal]
    if not isinstance(envelope, dict) or set(envelope) != {key} or not isinstance(envelope[key], list):
        raise ValueError("Wrong OTLP signal envelope")
    rows: list[dict[str, Any]] = []
    content_seen = b"L44-CONTENT-" in body
    for resource in envelope[key]:
        if not isinstance(resource, dict) or not isinstance(resource.get("resource"), dict):
            raise ValueError("Missing resource")
        resource_attrs = _attributes(resource["resource"].get("attributes"))
        scopes = resource.get({"metrics": "scopeMetrics", "logs": "scopeLogs",
                               "traces": "scopeSpans"}[signal])
        if not isinstance(scopes, list):
            raise ValueError("Missing scopes")
        for scope in scopes:
            if not isinstance(scope, dict):
                raise ValueError("Malformed scope")
            if signal == "metrics":
                for metric in scope.get("metrics", []):
                    if not isinstance(metric, dict) or not isinstance(metric.get("name"), str):
                        raise ValueError("Malformed metric")
                    if len(metric["name"]) > 120 or SENSITIVE.search(metric["name"]):
                        raise ValueError("Unsafe metric name")
                    kinds = [kind for kind in ("sum", "gauge") if kind in metric]
                    if len(kinds) != 1:
                        raise ValueError("Only numeric sum and gauge are supported")
                    kind = kinds[0]
                    data = metric[kind]
                    temporality = data.get("aggregationTemporality") if kind == "sum" else None
                    if kind == "sum" and temporality not in (1, 2):
                        raise ValueError("Invalid sum temporality")
                    for point in data.get("dataPoints", []):
                        value = point.get("asDouble", point.get("asInt"))
                        if not isinstance(value, (int, float, str)) or isinstance(value, bool):
                            raise ValueError("Invalid numeric point")
                        try:
                            number = float(value)
                        except (ValueError, OverflowError) as exc:
                            raise ValueError("Invalid numeric point") from exc
                        if not math.isfinite(number):
                            raise ValueError("Nonfinite numeric point")
                        rows.append({"signal": signal, "resource": resource_attrs,
                                     "attributes": _attributes(point.get("attributes")),
                                     "name": metric["name"][:120], "unit": metric.get("unit", "")[:40],
                                     "kind": kind, "temporality": temporality,
                                     "value": number, "timestamp": _timestamp(point.get("timeUnixNano"))})
            elif signal == "logs":
                for item in scope.get("logRecords", []):
                    if not isinstance(item, dict):
                        raise ValueError("Malformed log")
                    if (item.get("traceId") and not HEX32.fullmatch(item["traceId"])) or (
                        item.get("spanId") and not HEX16.fullmatch(item["spanId"])):
                        raise ValueError("Malformed log trace identity")
                    rows.append({"signal": signal, "resource": resource_attrs,
                                 "attributes": _attributes(item.get("attributes")),
                                 "timestamp": _timestamp(item.get("timeUnixNano")),
                                 "trace_id": item.get("traceId") if HEX32.fullmatch(item.get("traceId", "")) else None,
                                 "span_id": item.get("spanId") if HEX16.fullmatch(item.get("spanId", "")) else None})
            else:
                for item in scope.get("spans", []):
                    if not isinstance(item, dict) or not HEX32.fullmatch(item.get("traceId", "")) or not HEX16.fullmatch(item.get("spanId", "")):
                        raise ValueError("Invalid trace or span ID")
                    if item.get("parentSpanId") and not HEX16.fullmatch(item["parentSpanId"]):
                        raise ValueError("Invalid parent span ID")
                    start, end = _timestamp(item.get("startTimeUnixNano")), _timestamp(item.get("endTimeUnixNano"))
                    if end < start:
                        raise ValueError("Span ends before it starts")
                    name = item.get("name")
                    if not isinstance(name, str) or len(name) > 120 or SENSITIVE.search(name):
                        raise ValueError("Unsafe span name")
                    rows.append({"signal": signal, "resource": resource_attrs,
                                 "attributes": _attributes(item.get("attributes")), "name": name,
                                 "trace_id": item["traceId"], "span_id": item["spanId"],
                                 "parent_span_id": item.get("parentSpanId"), "start": start, "end": end})
            if len(rows) > 2000:
                raise ValueError("Too many records")
    return rows, content_seen


def aggregate(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    series: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row["signal"] != "metrics":
            continue
        key = json.dumps([row[k] for k in ("resource", "name", "unit", "kind", "temporality", "attributes")],
                         sort_keys=True)
        if key not in series:
            series[key] = {**row, "samples": 0}
            if row["kind"] == "sum" and row["temporality"] == 1:
                series[key]["value"] = 0.0
        item = series[key]
        item["samples"] += 1
        if row["kind"] == "sum" and row["temporality"] == 1:
            item["value"] += row["value"]
            item["timestamp"] = max(item["timestamp"], row["timestamp"])
        elif row["timestamp"] >= item["timestamp"]:
            item["value"] = row["value"]
            item["timestamp"] = row["timestamp"]
    return list(series.values())


class Collector:
    def __init__(self, run_id: str, lanes: list[str], credential: str | None = None,
                 *, native: bool = False) -> None:
        self.run_id = run_id
        self.lanes = set(lanes)
        self.credential = credential
        self.native = native
        self.receipts: list[dict[str, Any]] = []
        self.records: list[dict[str, Any]] = []
        self.content_seen: dict[str, bool] = {lane: False for lane in lanes}
        self.auth_attempts: list[dict[str, Any]] = []
        self.base = ""

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            return
        headers = {key.decode().lower(): value.decode() for key, value in scope.get("headers", [])}
        path = scope.get("path", "")
        parts = path.strip("/").split("/")
        sender = "subprocess" if self.native else "fixture"
        if len(parts) == 5 and parts[:1] == ["r"] and parts[1] == self.run_id and parts[2] in self.lanes and parts[3] == "v1":
            lane, signal = parts[2], parts[4]
        elif len(parts) == 3 and parts[0] in {"host", "fixture"} and parts[1] == "v1":
            sender, lane, signal = parts[0], next(iter(self.lanes)), parts[2]
        else:
            await self._reply(send, 404)
            return
        if signal not in SIGNALS or scope["method"] != "POST":
            await self._reply(send, 404)
            return
        host = headers.get("host")
        if not self.base or host != self.base.removeprefix("http://"):
            await self._reply(send, 400)
            return
        if self.credential and headers.get("authorization") != "Bearer " + self.credential:
            self.auth_attempts.append({"lane": lane, "signal": signal,
                "has_authorization": bool(headers.get("authorization")),
                "bearer_scheme": headers.get("authorization", "").startswith("Bearer "),
                "encoded_space": headers.get("authorization", "").startswith("Bearer%20"),
                "lowercase_scheme": headers.get("authorization", "").startswith("bearer ")})
            await self._reply(send, 401)
            return
        if headers.get("origin") and headers["origin"] != self.base:
            await self._reply(send, 400)
            return
        if headers.get("content-type", "").split(";")[0] != "application/json":
            await self._reply(send, 415)
            return
        body = bytearray()
        while True:
            try:
                async with asyncio.timeout(5):
                    event = await receive()
            except TimeoutError:
                await self._reply(send, 408)
                return
            body.extend(event.get("body", b""))
            if len(body) > 2_000_000:
                await self._reply(send, 413)
                return
            if not event.get("more_body", False):
                break
        try:
            rows, seen = decode(signal, bytes(body))
        except ValueError:
            await self._reply(send, 400)
            return
        if len(self.records) + len(rows) > 4000:
            await self._reply(send, 413)
            return
        receipt_id = str(uuid.uuid4())
        self.receipts.append({"id": receipt_id, "status": 200, "signal": signal,
                              "sender": sender, "lane": lane, "bytes": len(body),
                              "sha256": _sha(bytes(body)), "count": len(rows)})
        self.content_seen[lane] |= seen
        for row in rows:
            row.update({"receipt_id": receipt_id, "sender": sender, "lane": lane,
                        "session_id": row["attributes"].get("session.id", row["attributes"].get("session_id")),
                        "tool_id": row["attributes"].get("tool_use_id", row["attributes"].get("gen_ai.tool.call.id"))})
        self.records.extend(rows)
        await self._reply(send, 200)

    @staticmethod
    async def _reply(send: Any, status: int) -> None:
        await send({"type": "http.response.start", "status": status,
                    "headers": [(b"content-type", b"application/json")]})
        await send({"type": "http.response.body", "body": b"{}"})
