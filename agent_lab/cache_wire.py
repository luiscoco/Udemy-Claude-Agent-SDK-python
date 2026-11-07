"""Strict, content-free cache usage and breakpoint observations for Lesson 46."""

import hashlib
import json
import math
from typing import Any

HAIKU = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-4-5-20250929"
RATES_2026_10_19 = {HAIKU: (1.0, 5.0), SONNET: (3.0, 15.0)}


def _counter(value: Any, field: str) -> int:
    if type(value) is not int or not 0 <= value <= 2**53 - 1:
        raise ValueError(f"Invalid or missing {field} counter")
    return value


def normalized_usage(usage: dict[str, Any]) -> dict[str, int]:
    """Require all primary counters; only the optional TTL subdivision defaults to zero."""
    input_tokens = _counter(usage.get("input_tokens"), "input_tokens")
    creation = _counter(usage.get("cache_creation_input_tokens"), "cache_creation_input_tokens")
    read = _counter(usage.get("cache_read_input_tokens"), "cache_read_input_tokens")
    output = _counter(usage.get("output_tokens"), "output_tokens")
    breakdown = usage.get("cache_creation", {})
    if breakdown is None:
        breakdown = {}
    if not isinstance(breakdown, dict):
        raise ValueError("Invalid cache creation breakdown")
    hour = _counter(breakdown.get("ephemeral_1h_input_tokens", 0), "one-hour write")
    if hour > creation:
        raise ValueError("One-hour writes exceed total cache creation")
    if "ephemeral_5m_input_tokens" in breakdown:
        five = _counter(breakdown["ephemeral_5m_input_tokens"], "five-minute write")
        if five + hour != creation:
            raise ValueError("Cache creation subdivisions do not sum to total")
    return {"input": input_tokens, "write5m": creation - hour,
            "write1h": hour, "read": read, "output": output}


def estimate_usd(model: str, usage: dict[str, int]) -> float | None:
    """Dated list-price estimate, separate from an SDK cumulative bill."""
    rates = RATES_2026_10_19.get(model)
    if rates is None:
        return None
    values = {key: _counter(usage.get(key), key)
              for key in ("input", "write5m", "write1h", "read", "output")}
    input_rate, output_rate = rates
    return ((values["input"] + 1.25 * values["write5m"]
             + 2 * values["write1h"] + 0.1 * values["read"]) * input_rate
            + values["output"] * output_rate) / 1_000_000


def _breakpoint(value: Any, location: str) -> dict[str, str] | None:
    if value is None:
        return None
    if not isinstance(value, dict) or value.get("type") != "ephemeral":
        raise ValueError("Unsupported cache breakpoint")
    ttl = value.get("ttl", "5m")
    if ttl not in {"5m", "1h"}:
        raise ValueError("Unsupported cache TTL")
    return {"location": location, "type": "ephemeral", "ttl": ttl}


def breakpoints(body: dict[str, Any]) -> list[dict[str, str]]:
    """Inspect all supported request locations without retaining their content."""
    found: list[dict[str, str]] = []
    top = _breakpoint(body.get("cache_control"), "top-level")
    if top:
        found.append(top)
    for group in ("tools", "system"):
        value = body.get(group, [])
        if isinstance(value, str):
            value = []
        if not isinstance(value, list):
            raise ValueError(f"Invalid {group} blocks")
        for index, block in enumerate(value):
            if isinstance(block, dict):
                item = _breakpoint(block.get("cache_control"), f"{group}[{index}]")
                if item:
                    found.append(item)
    messages = body.get("messages", [])
    if not isinstance(messages, list):
        raise ValueError("Invalid message blocks")
    for message_index, message in enumerate(messages):
        if not isinstance(message, dict):
            raise ValueError("Invalid message")
        content = message.get("content", [])
        if isinstance(content, str):
            content = []
        if not isinstance(content, list):
            raise ValueError("Invalid message content")
        for block_index, block in enumerate(content):
            if isinstance(block, dict):
                item = _breakpoint(block.get("cache_control"),
                                   f"messages[{message_index}].content[{block_index}]")
                if item:
                    found.append(item)
    return found


def digest_json(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                   separators=(",", ":")).encode()).hexdigest()


def parse_message_sse(data: bytes) -> dict[str, Any]:
    """Parse one complete Anthropic SSE message; incomplete streams cannot pass."""
    if len(data) > 2_000_000:
        raise ValueError("Response exceeds cache lab limit")
    try:
        source = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Response is not UTF-8") from exc
    blocks = source.replace("\r\n", "\n").replace("\r", "\n").split("\n\n")
    started: dict[str, Any] | None = None
    final: dict[str, Any] | None = None
    deltas = 0
    stopped = False
    for block in blocks:
        if not block.strip():
            continue
        lines = block.split("\n")
        event = next((line[6:].strip() for line in lines if line.startswith("event:")), None)
        pieces = [line[5:].lstrip() for line in lines if line.startswith("data:")]
        if not event or not pieces:
            raise ValueError("Incomplete SSE event")
        try:
            payload = json.loads("\n".join(pieces))
        except json.JSONDecodeError as exc:
            raise ValueError("Invalid SSE JSON") from exc
        if event == "message_start":
            if started is not None or stopped:
                raise ValueError("Duplicate or late message start")
            started = payload.get("message")
            if not isinstance(started, dict):
                raise ValueError("Missing response message")
        elif event == "message_delta":
            if started is None or stopped:
                raise ValueError("Delta outside message")
            usage = payload.get("usage")
            if not isinstance(usage, dict):
                raise ValueError("Missing final usage")
            final = usage
            deltas += 1
        elif event == "message_stop":
            if started is None or deltas == 0 or stopped:
                raise ValueError("Invalid message stop")
            stopped = True
        elif event == "error":
            raise ValueError("Upstream error event")
        elif stopped:
            raise ValueError("Trailing event after stop")
    if not stopped or started is None or final is None:
        raise ValueError("Incomplete message stream")
    message_id = started.get("id")
    model = started.get("model")
    if not isinstance(message_id, str) or not message_id.startswith("msg_"):
        raise ValueError("Missing response message ID")
    if model not in RATES_2026_10_19:
        raise ValueError("Unsupported response model")
    initial_usage = started.get("usage")
    if not isinstance(initial_usage, dict):
        raise ValueError("Missing start usage")
    merged = {**initial_usage, **final}
    return {"message_id": message_id, "model": model,
            "usage": normalized_usage(merged), "estimate_usd": estimate_usd(model, normalized_usage(merged))}


def sdk_increment(previous: float, current: float) -> float:
    if not all(isinstance(value, (int, float)) and math.isfinite(value) and value >= 0
               for value in (previous, current)) or current < previous:
        raise ValueError("Invalid or decreasing SDK cumulative cost")
    return current - previous
