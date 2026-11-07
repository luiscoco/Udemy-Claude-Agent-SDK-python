"""Pure wire-format helpers for the owned Lesson 45 cloud proxy.

This module accepts only the lesson's fixed model family. It never handles a
real cloud credential; callers supply fresh, per-lane fixture values.
"""

import base64
import hashlib
import hmac
import json
import re
import zlib
from datetime import UTC, datetime
from urllib.parse import parse_qsl, quote

HAIKU = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-4-5-20250929"
PROFILE = "arn:aws:bedrock:us-east-1:111122223333:application-inference-profile/lesson45"
_PREFIX = re.compile(r"^(?:(?:us|eu|apac|global)\.|anthropic\.)+")
_SUFFIX = re.compile(r"(?:-v\d+:\d+|@\d{8})$")
_AWS_AUTH = re.compile(
    r"^AWS4-HMAC-SHA256 Credential=([^/ ,]+)/([0-9]{8})/([^/ ,]+)/([^/ ,]+)/aws4_request,"
    r" SignedHeaders=([a-z0-9;-]+), Signature=([0-9a-f]{64})$"
)


def canonical_model(wire_model: str) -> str | None:
    """Map owned Bedrock/Vertex spellings to a fixed foundation model."""
    if wire_model == PROFILE:
        return HAIKU
    stripped = _SUFFIX.sub("", _PREFIX.sub("", wire_model))
    if wire_model == "claude-haiku-4-5@20251001":
        return HAIKU
    if wire_model == "claude-sonnet-4-5@20250929":
        return SONNET
    return stripped if stripped in {HAIKU, SONNET} else None


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_query(query: bytes) -> str:
    pairs = parse_qsl(query.decode("ascii"), keep_blank_values=True, strict_parsing=False)
    return "&".join(f"{quote(key, safe='-_.~')}={quote(value, safe='-_.~')}"
                    for key, value in sorted(pairs))


def _canonical_request(method: str, path: bytes, query: bytes, headers: dict[str, str],
                       signed_names: list[str], body: bytes) -> str:
    if (not signed_names or signed_names != sorted(set(signed_names)) or
            not {"host", "x-amz-date"} <= set(signed_names)):
        raise ValueError("Invalid signed headers")
    if any(name not in headers for name in signed_names):
        raise ValueError("Missing signed header")
    normalized = {name: " ".join(headers[name].strip().split()) for name in signed_names}
    canonical_headers = "".join(f"{name}:{normalized[name]}\n" for name in signed_names)
    # Native AWS signing URI-escapes the already encoded request target. A
    # literal percent in an encoded model ID therefore becomes %25 here.
    canonical_uri = quote(path.decode("ascii"), safe="/-_.~")
    return "\n".join((method, canonical_uri, canonical_query(query),
                      canonical_headers, ";".join(signed_names), _sha(body)))


def _sign(secret: str, date: str, region: str, service: str, message: str) -> bytes:
    key = ("AWS4" + secret).encode()
    for part in (date, region, service, "aws4_request"):
        key = hmac.new(key, part.encode(), hashlib.sha256).digest()
    return hmac.new(key, message.encode(), hashlib.sha256).digest()


def fixture_sigv4(method: str, path: bytes, query: bytes, headers: dict[str, str],
                  body: bytes, access_id: str, secret: str, region: str) -> str:
    """Sign one authored fixture request using its exact literal Host header."""
    names = sorted({key.lower() for key in headers} | {"host", "x-amz-date"})
    lowered = {key.lower(): value for key, value in headers.items()}
    stamp = lowered["x-amz-date"]
    scope = f"{stamp[:8]}/{region}/bedrock/aws4_request"
    canonical = _canonical_request(method, path, query, lowered, names, body)
    string = f"AWS4-HMAC-SHA256\n{stamp}\n{scope}\n{_sha(canonical.encode())}"
    signature = _sign(secret, stamp[:8], region, "bedrock", string).hex()
    return (f"AWS4-HMAC-SHA256 Credential={access_id}/{scope}, "
            f"SignedHeaders={';'.join(names)}, Signature={signature}")


def verify_sigv4(method: str, path: bytes, query: bytes, headers: dict[str, str],
                 body: bytes, access_id: str, secret: str, region: str,
                 *, now: datetime | None = None) -> bool:
    """Verify AWS Signature V4 against received bytes and the owned lane."""
    lowered = {key.lower(): value for key, value in headers.items()}
    match = _AWS_AUTH.fullmatch(lowered.get("authorization", ""))
    if match is None:
        return False
    supplied_id, date, supplied_region, service, names_text, supplied_hex = match.groups()
    if supplied_id != access_id or supplied_region != region or service != "bedrock":
        return False
    names = names_text.split(";")
    stamp = lowered.get("x-amz-date", "")
    try:
        instant = datetime.strptime(stamp, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
        current = now or datetime.now(UTC)
        if stamp[:8] != date or abs((current - instant).total_seconds()) > 300:
            return False
        canonical = _canonical_request(method, path, query, lowered, names, body)
    except (ValueError, UnicodeError, KeyError):
        return False
    scope = f"{date}/{region}/bedrock/aws4_request"
    string = f"AWS4-HMAC-SHA256\n{stamp}\n{scope}\n{_sha(canonical.encode())}"
    expected = _sign(secret, date, region, "bedrock", string)
    return hmac.compare_digest(expected, bytes.fromhex(supplied_hex))


def eventstream_packet(event: bytes) -> bytes:
    """Frame a Bedrock-compatible AWS eventstream payload with both CRCs."""
    payload = json.dumps({"bytes": base64.b64encode(event).decode("ascii")},
                         separators=(",", ":")).encode()
    def header(name: str, value: str) -> bytes:
        raw_name, raw_value = name.encode(), value.encode()
        return bytes((len(raw_name),)) + raw_name + b"\x07" + len(raw_value).to_bytes(2, "big") + raw_value
    headers = (header(":event-type", "chunk") + header(":message-type", "event") +
               header(":content-type", "application/json"))
    prelude = (16 + len(headers) + len(payload)).to_bytes(4, "big") + len(headers).to_bytes(4, "big")
    prelude += (zlib.crc32(prelude) & 0xffffffff).to_bytes(4, "big")
    message = prelude + headers + payload
    return message + (zlib.crc32(message) & 0xffffffff).to_bytes(4, "big")


class SSEDecoder:
    """Incrementally parse bounded SSE events across byte and CRLF splits."""

    def __init__(self, max_pending: int = 65536) -> None:
        self.pending = b""
        self.max_pending = max_pending

    def feed(self, chunk: bytes) -> list[dict[str, object]]:
        self.pending += chunk
        if len(self.pending) > self.max_pending:
            raise ValueError("SSE event exceeds the lesson bound")
        events: list[dict[str, object]] = []
        while True:
            lf = self.pending.find(b"\n\n")
            crlf = self.pending.find(b"\r\n\r\n")
            choices = [(i, size) for i, size in ((lf, 2), (crlf, 4)) if i >= 0]
            if not choices:
                break
            end, size = min(choices)
            block, self.pending = self.pending[:end], self.pending[end + size:]
            lines = block.decode("utf-8").replace("\r\n", "\n").split("\n")
            data = "\n".join(line[5:].lstrip(" ") for line in lines if line.startswith("data:"))
            if data and data != "[DONE]":
                parsed = json.loads(data)
                if isinstance(parsed, dict):
                    events.append(parsed)
        return events
