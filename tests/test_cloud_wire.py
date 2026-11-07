"""Offline protocol checks for the owned Lesson 45 proxy primitives."""

import json
import zlib
from datetime import UTC, datetime, timedelta

from agent_lab.cloud_wire import (
    HAIKU,
    PROFILE,
    SONNET,
    SSEDecoder,
    canonical_model,
    eventstream_packet,
    fixture_sigv4,
    verify_sigv4,
)


def test_fixed_model_mapping() -> None:
    assert canonical_model(HAIKU) == HAIKU
    assert canonical_model("us.anthropic." + HAIKU + "-v1:0") == HAIKU
    assert canonical_model("eu.anthropic." + HAIKU + "-v1:0") == HAIKU
    assert canonical_model("anthropic." + HAIKU + "@20251001") == HAIKU
    assert canonical_model("claude-haiku-4-5@20251001") == HAIKU
    assert canonical_model("claude-sonnet-4-5@20250929") == SONNET
    assert canonical_model(PROFILE) == HAIKU
    assert canonical_model(SONNET) == SONNET
    assert canonical_model("claude-opus-4-5-20251101") is None


def test_sigv4_exact_received_wire_and_tampering() -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    path = b"/r/owned/bedrock/model/" + PROFILE.replace("/", "%2F").encode() + b"/invoke"
    headers = {"host": "127.0.0.1", "x-amz-date": stamp,
               "content-type": "application/json"}
    body = b'{"prompt":"READY"}'
    auth = fixture_sigv4("POST", path, b"z=2&a=1", headers, body, "OWNED", "secret", "us-east-1")
    received = {**headers, "authorization": auth}
    def check(**kwargs: object) -> bool:
        return verify_sigv4(
            kwargs.get("method", "POST"), kwargs.get("path", path), kwargs.get("query", b"z=2&a=1"),
            kwargs.get("headers", received), kwargs.get("body", body),
            kwargs.get("access", "OWNED"), kwargs.get("secret", "secret"),
            kwargs.get("region", "us-east-1"), now=kwargs.get("now", now))
    assert check()
    assert not check(body=body + b" ")
    assert not check(secret="wrong")
    assert not check(region="eu-west-1")
    assert not check(path=path + b"x")
    assert not check(headers={**received, "host": "127.0.0.1:9999"})
    assert not check(now=now + timedelta(minutes=6))
    assert not check(access="FOREIGN")


def test_eventstream_framing_crc_and_length() -> None:
    assert zlib.crc32(b"123456789") == 0xcbf43926
    event = b'event: message_start\ndata: {"message":{"id":"msg_1"}}\n\n'
    packet = eventstream_packet(event)
    assert int.from_bytes(packet[:4], "big") == len(packet)
    header_length = int.from_bytes(packet[4:8], "big")
    assert header_length > 0
    assert int.from_bytes(packet[8:12], "big") == zlib.crc32(packet[:8])
    assert int.from_bytes(packet[-4:], "big") == zlib.crc32(packet[:-4])
    assert json.loads(packet[12 + header_length:-4])["bytes"]


def test_sse_fragmented_utf8_and_crlf() -> None:
    decoder = SSEDecoder()
    source = 'event: message_start\r\ndata: {"type":"message_start","message":{"id":"é"}}\r\n\r\n'.encode()
    result = []
    for value in source:
        result.extend(decoder.feed(bytes((value,))))
    assert result == [{"type": "message_start", "message": {"id": "é"}}]
