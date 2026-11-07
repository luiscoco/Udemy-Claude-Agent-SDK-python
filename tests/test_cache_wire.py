"""Lesson 46 cache measurements require actual complete counters."""

import json

import pytest

from agent_lab.cache_wire import (
    HAIKU,
    SONNET,
    breakpoints,
    estimate_usd,
    normalized_usage,
    parse_message_sse,
    sdk_increment,
)


def _event(kind: str, payload: dict[str, object]) -> bytes:
    return f"event: {kind}\r\ndata: {json.dumps(payload)}\r\n\r\n".encode()


def test_complete_sse_usage_and_price() -> None:
    start = {"message": {"id": "msg_46", "model": HAIKU, "usage": {
        "input_tokens": 10, "cache_creation_input_tokens": 100,
        "cache_read_input_tokens": 300, "output_tokens": 0,
        "cache_creation": {"ephemeral_5m_input_tokens": 60, "ephemeral_1h_input_tokens": 40}}}}
    data = (_event("message_start", start) +
            _event("message_delta", {"usage": {"output_tokens": 5}}) +
            _event("message_stop", {}))
    result = parse_message_sse(data)
    assert result["usage"] == {"input": 10, "write5m": 60, "write1h": 40,
                               "read": 300, "output": 5}
    assert result["estimate_usd"] == pytest.approx(0.00022)
    with pytest.raises(ValueError, match="Incomplete"):
        parse_message_sse(data.rsplit(b"event: message_stop", 1)[0])


def test_usage_rejects_missing_or_inconsistent_counters() -> None:
    base = {"input_tokens": 10, "cache_creation_input_tokens": 5,
            "cache_read_input_tokens": 0, "output_tokens": 1}
    assert normalized_usage(base)["write5m"] == 5
    for bad in ({**base, "cache_read_input_tokens": None},
                {**base, "cache_creation": {"ephemeral_1h_input_tokens": 6}},
                {**base, "cache_creation": {"ephemeral_5m_input_tokens": 2,
                                              "ephemeral_1h_input_tokens": 2}}):
        with pytest.raises(ValueError):
            normalized_usage(bad)
    assert estimate_usd(SONNET, {"input": 1, "write5m": 0, "write1h": 0,
                                 "read": 0, "output": 1}) == pytest.approx(0.000018)
    assert estimate_usd("unknown", {"input": 1}) is None
    assert sdk_increment(0.01, 0.03) == pytest.approx(0.02)
    with pytest.raises(ValueError):
        sdk_increment(0.03, 0.01)


def test_all_breakpoint_locations_are_distinct() -> None:
    control = {"type": "ephemeral"}
    body = {"cache_control": control, "tools": [{"cache_control": control}],
            "system": [{"cache_control": {**control, "ttl": "1h"}}],
            "messages": [{"content": [{"cache_control": control}]}]}
    assert breakpoints(body) == [
        {"location": "top-level", "type": "ephemeral", "ttl": "5m"},
        {"location": "tools[0]", "type": "ephemeral", "ttl": "5m"},
        {"location": "system[0]", "type": "ephemeral", "ttl": "1h"},
        {"location": "messages[0].content[0]", "type": "ephemeral", "ttl": "5m"},
    ]
