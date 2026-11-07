"""Owned HTTP cache observer with labelled fixture and native measurements."""

import asyncio
import json
import math
import os
import secrets
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from agent_lab.cache_wire import (
    HAIKU,
    SONNET,
    breakpoints,
    digest_json,
    normalized_usage,
    parse_message_sse,
    sdk_increment,
)
from agent_lab.exercises import EmbeddedServer

ACTIONS = ("anatomy", "switches", "breakers", "model-switch")
TTLS = ("5m", "1h", "off")
PREFIXES = ("stable", "changed", "tool", "dynamic", "short")
POLICIES = ("cap", "allow")


def handbook(operation: str, short: bool = False) -> str:
    header = f"Edition {operation}. Reply only READY. Use no tools.\n"
    if short:
        return header + "Order handbook: verify date, region and approval evidence."
    return header + "\n".join(
        f"Section {index:03d}: Check order date, region, payment, delivery, "
        "manager approval and supporting evidence before release."
        for index in range(1, 181)
    )


def _usage(action: str, ttl: str, prefix: str, turn: int, policy: str = "cap") -> dict[str, Any]:
    if ttl == "off" or prefix == "short":
        write, read = 0, 0
    elif turn == 1:
        write, read = 1200, 0
    elif (action == "breakers" and prefix in {"changed", "tool"}) or (action == "model-switch" and policy == "allow"):
        write, read = 1200, 0
    else:
        write, read = 0, 1200
    hour = write if ttl == "1h" else 0
    return {"input_tokens": 37, "cache_creation_input_tokens": write,
            "cache_read_input_tokens": read, "output_tokens": 3,
            "cache_creation": {"ephemeral_5m_input_tokens": write - hour,
                               "ephemeral_1h_input_tokens": hour}}


def _sse(message_id: str, usage: dict[str, Any], model: str = HAIKU) -> bytes:
    start = {**usage, "output_tokens": 0}
    events: tuple[tuple[str, dict[str, Any]], ...] = (
        ("message_start", {"message": {"id": message_id, "model": model,
                                        "usage": start}}),
        ("message_delta", {"usage": {"output_tokens": usage["output_tokens"]}}),
        ("message_stop", {}),
    )
    return "".join(f"event: {name}\ndata: {json.dumps(payload, separators=(',', ':'))}\n\n"
                   for name, payload in events).encode()


class CacheObserver:
    def __init__(self, operation: str, nonce: str, action: str, ttl: str, prefix: str,
                 upstream_key: str | None = None, policy: str = "cap") -> None:
        self.operation, self.nonce = operation, nonce
        self.action, self.ttl, self.prefix = action, ttl, prefix
        self.policy = policy
        self.key = secrets.token_urlsafe(32)
        self.port = 0
        self.receipts: list[dict[str, Any]] = []
        self.closed = False
        self.upstream_key = upstream_key
        self.forwarded = 0

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            return
        headers = {key.decode("latin1").lower(): value.decode("latin1")
                   for key, value in scope["headers"]}
        async def respond(status: int, payload: bytes) -> None:
            await send({"type": "http.response.start", "status": status,
                        "headers": [(b"content-type", b"text/event-stream" if status == 200
                                     else b"application/json"),
                                    (b"content-length", str(len(payload)).encode())]})
            await send({"type": "http.response.body", "body": payload})

        if (scope["method"] != "POST" or scope["path"] != "/v1/messages"
                or scope.get("query_string", b"") not in {b"", b"beta=true"}
                or "origin" in headers or headers.get("host") != f"127.0.0.1:{self.port}"):
            await respond(404, b'{"error":"not_found"}')
            return
        if not secrets.compare_digest(headers.get("x-api-key", ""), self.key):
            await respond(401, b'{"error":"unauthorized"}')
            return
        if len(self.receipts) >= 4:
            await respond(429, b'{"error":"request_limit"}')
            return
        chunks: list[bytes] = []
        size = 0
        while True:
            event = await receive()
            if event["type"] == "http.disconnect":
                return
            size += len(event.get("body", b""))
            if size > 1_000_000:
                await respond(413, b'{"error":"body_limit"}')
                return
            chunks.append(event.get("body", b""))
            if not event.get("more_body", False):
                break
        raw = b"".join(chunks)
        try:
            body = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError):
            await respond(400, b'{"error":"invalid_json"}')
            return
        allowed_models = {HAIKU, SONNET} if self.action == "model-switch" else {HAIKU}
        if (not isinstance(body, dict) or body.get("model") not in allowed_models
                or self.nonce not in raw.decode("utf-8")):
            await respond(403, b'{"error":"model_or_nonce"}')
            return
        turn = len(self.receipts) + 1
        if self.upstream_key:
            if self.forwarded >= 2:
                await respond(429, b'{"error":"upstream_limit"}')
                return
            self.forwarded += 1
            native_digest = digest_json(body)
            if self.action == "switches" and self.ttl == "1h":
                for group in ("system", "tools"):
                    for block in body.get(group, []):
                        if isinstance(block, dict) and isinstance(block.get("cache_control"), dict):
                            block["cache_control"]["ttl"] = "1h"
                for message in body.get("messages", []):
                    if isinstance(message, dict) and isinstance(message.get("content"), list):
                        for block in message["content"]:
                            if isinstance(block, dict) and isinstance(block.get("cache_control"), dict):
                                block["cache_control"]["ttl"] = "1h"
                if isinstance(body.get("cache_control"), dict):
                    body["cache_control"]["ttl"] = "1h"
            if self.action == "breakers" and turn == 2 and self.prefix == "changed":
                system = body.get("system")
                if isinstance(system, list) and system and isinstance(system[0], dict):
                    system[0]["text"] = str(system[0].get("text", "")) + "\nChanged edition " + self.operation
            if self.action == "breakers" and turn == 2 and self.prefix == "tool":
                tools = body.get("tools")
                if isinstance(tools, list):
                    tools.append({"name": "owned_noop", "description": "Never call this tool.",
                                  "input_schema": {"type": "object", "properties": {}}})
            if self.action == "breakers" and self.prefix == "dynamic":
                system = body.get("system")
                if isinstance(system, list):
                    system.append({"type": "text", "text": "Customer suffix owned."})
            body["max_tokens"] = min(int(body.get("max_tokens", 128)), 128)
            forwarded_headers = {"x-api-key": self.upstream_key,
                                 "anthropic-version": headers.get("anthropic-version", "2023-06-01"),
                                 "content-type": "application/json"}
            if "anthropic-beta" in headers:
                forwarded_headers["anthropic-beta"] = headers["anthropic-beta"]
            try:
                async with httpx.AsyncClient(timeout=60, follow_redirects=False, trust_env=False) as client:
                    async with client.stream("POST", "https://api.anthropic.com/v1/messages",
                                             headers=forwarded_headers, json=body) as upstream:
                        status = upstream.status_code
                        parts: list[bytes] = []
                        total = 0
                        async for part in upstream.aiter_bytes():
                            total += len(part)
                            if total > 2_000_000:
                                raise ValueError("Upstream cache stream exceeded limit")
                            parts.append(part)
                response = b"".join(parts)
                if status != 200:
                    self.receipts.append({"operation": self.operation, "lane": "main",
                                          "turn": turn, "status": status,
                                          "authenticated": True, "nonce_match": True,
                                          "model": body["model"], "upstream_status": status})
                    await respond(502, b'{"error":"upstream_rejected"}')
                    return
                parsed = parse_message_sse(response)
            except (httpx.HTTPError, ValueError):
                await respond(502, b'{"error":"upstream_failed"}')
                return
        else:
            message_id = "msg_" + uuid.uuid4().hex
            usage = _usage(self.action, self.ttl, self.prefix, turn, self.policy)
            response = _sse(message_id, usage, body["model"])
            parsed = parse_message_sse(response)
        self.receipts.append({"operation": self.operation, "lane": "main", "turn": turn,
                              "receipt_id": str(uuid.uuid4()), "status": 200,
                              "authenticated": True, "nonce_match": True,
                              "model": body["model"], "message_id": parsed["message_id"],
                              "system_sha256": digest_json(body.get("system", [])),
                              "tools_sha256": digest_json(body.get("tools", [])),
                              "native_request_sha256": native_digest if self.upstream_key else None,
                              "request_sha256": digest_json(body),
                              "dynamic_suffix_added": bool(self.upstream_key and self.action == "breakers" and
                                                           self.prefix == "dynamic"),
                              "breakpoints": breakpoints(body), "usage": parsed["usage"],
                              "estimate_usd": parsed["estimate_usd"],
                              "upstream_status": 200 if self.upstream_key else None,
                              "variant_source": "owned-wire-perturbation" if self.upstream_key and
                              self.action in {"switches", "breakers"} else "native-sdk" if self.upstream_key
                              else "authored-http"})
        await respond(200, response)


def _request(operation: str, nonce: str, action: str, ttl: str, prefix: str,
             turn: int, policy: str = "cap") -> dict[str, Any]:
    short = action == "anatomy" and prefix == "short" or action == "breakers" and prefix == "short"
    text = handbook(operation, short)
    if action == "breakers" and prefix == "changed" and turn == 2:
        text = handbook(str(uuid.uuid4()), short)
    system: list[dict[str, Any]] = [{"type": "text", "text": text}]
    if ttl != "off":
        system[0]["cache_control"] = {"type": "ephemeral", "ttl": ttl}
    if action == "breakers" and prefix == "dynamic":
        system.append({"type": "text", "text": "Customer suffix owned."})
    tools: list[dict[str, Any]] = []
    if action == "breakers" and prefix == "tool" and turn == 2:
        tools.append({"name": "owned_noop", "description": "Never call this tool.",
                      "input_schema": {"type": "object", "properties": {}}})
    model = SONNET if action == "model-switch" and policy == "allow" and turn == 2 else HAIKU
    return {"model": model, "max_tokens": 24, "stream": True,
            "system": system, "tools": tools,
            "messages": [{"role": "user", "content": f"Turn {turn}. Nonce {nonce}. Reply READY."}]}


def evaluate_local(report: dict[str, Any]) -> bool:
    receipts = report.get("receipts", [])
    turns = report.get("turns", [])
    if (report.get("source_label") != "authored host HTTP fixture"
            or report.get("native") is not False or report.get("closed") is not True
            or len(receipts) != len(turns) or len(turns) != 2):
        return False
    if [item.get("turn") for item in turns] != [1, 2]:
        return False
    if len({item.get("message_id") for item in turns}) != 2:
        return False
    previous = 0.0
    for turn, receipt in zip(turns, receipts, strict=True):
        if (receipt.get("operation") != report.get("operation") or
                receipt.get("lane") != "main" or receipt.get("turn") != turn.get("turn") or
                receipt.get("status") != 200 or not receipt.get("authenticated") or
                not receipt.get("nonce_match") or receipt.get("message_id") != turn.get("message_id") or
                receipt.get("usage") != turn.get("usage") or
                turn.get("model") != (SONNET if report.get("action") == "model-switch" and
                                      report.get("policy") == "allow" and turn.get("turn") == 2 else HAIKU)):
            return False
        try:
            increment = sdk_increment(previous, turn["fixture_cumulative_usd"])
        except (KeyError, ValueError):
            return False
        if not isinstance(turn.get("fixture_increment_usd"), (int, float)) or not math.isclose(
                increment, turn["fixture_increment_usd"], rel_tol=0, abs_tol=1e-12):
            return False
        previous = turn["fixture_cumulative_usd"]
    if report.get("action") == "model-switch":
        hooks = report.get("hooks", [])
        if len([row for row in hooks if row.get("kind") == "pre-model-switch"]) != 1:
            return False
        if report.get("policy") == "allow" and len([row for row in hooks if row.get("kind") == "post-model-switch"]) != 1:
            return False
        if report.get("policy") == "cap" and any(row.get("kind") == "post-model-switch" for row in hooks):
            return False
    return True


async def local_action(action: str, ttl: str = "5m", prefix: str = "stable",
                       policy: str = "cap", scenario: str = "normal") -> dict[str, Any]:
    if action not in ACTIONS or ttl not in TTLS or prefix not in PREFIXES or policy not in POLICIES or scenario not in {"normal", "missing", "foreign", "failed"}:
        raise ValueError("Unknown Lesson 46 fixed option")
    operation, nonce = str(uuid.uuid4()), secrets.token_hex(12)
    observer = CacheObserver(operation, nonce, action, ttl, prefix, policy=policy)
    turns: list[dict[str, Any]] = []
    cumulative = 0.0
    async with EmbeddedServer(observer).running() as base:
        observer.port = int(base.rsplit(":", 1)[1])
        async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
            for number in (1, 2):
                response = await client.post(base + "/v1/messages", json=_request(
                    operation, nonce, action, ttl, prefix, number, policy),
                    headers={"x-api-key": observer.key})
                if response.status_code != 200:
                    raise ValueError("Owned cache observer rejected a fixed turn")
                parsed = parse_message_sse(response.content)
                increment = parsed["estimate_usd"]
                assert isinstance(increment, float)
                cumulative += increment
                turns.append({"turn": number, "model": parsed["model"],
                              "message_id": parsed["message_id"], "usage": parsed["usage"],
                              "estimate_usd": parsed["estimate_usd"],
                              "fixture_cumulative_usd": cumulative,
                              "fixture_increment_usd": increment})
    observer.closed = True
    hooks: list[dict[str, Any]] = []
    if action == "model-switch":
        hooks.append({"kind": "pre-model-switch", "source": "authored-fixture",
                      "from_model": HAIKU, "to_model": SONNET, "prompt_cache_warm": True,
                      "estimated_cache_write_usd": 0.0172,
                      "decision": "deny" if policy == "cap" else "allow"})
        if policy == "allow":
            hooks.append({"kind": "post-model-switch", "source": "authored-fixture",
                          "from_model": HAIKU, "to_model": SONNET})
    report: dict[str, Any] = {"lesson": 46, "operation": operation, "action": action, "mode": "local",
              "ttl": ttl, "prefix": prefix, "policy": policy,
              "source_label": "authored host HTTP fixture", "native": False,
              "turns": turns, "receipts": observer.receipts, "hooks": hooks,
              "closed": observer.closed, "created_at": datetime.now(UTC).isoformat()}
    if scenario == "missing":
        report["turns"][1]["usage"] = {}
    elif scenario == "foreign":
        report["receipts"][1]["operation"] = str(uuid.uuid4())
    elif scenario == "failed":
        report["turns"][1]["fixture_cumulative_usd"] = -1.0
    report["experiment_passed"] = evaluate_local(report)
    return report


def save_passing(report: dict[str, Any], storage: Path) -> None:
    if not report.get("experiment_passed"):
        return
    summary = {key: report[key] for key in ("lesson", "operation", "action", "mode", "ttl",
                                            "prefix", "policy", "created_at")}
    data = json.dumps(summary, separators=(",", ":")).encode()
    if len(data) > 4096:
        raise ValueError("Cache summary exceeds limit")
    storage.mkdir(parents=True, exist_ok=True)
    target = storage / "latest.json"
    if target.is_symlink():
        raise ValueError("Unsafe saved cache summary")
    if target.exists():
        stat = target.lstat()
        if not target.is_file() or stat.st_nlink != 1 or target.is_symlink() or stat.st_size > 4096:
            raise ValueError("Unsafe saved cache summary")
    temporary = storage / ("latest-" + uuid.uuid4().hex + ".tmp")
    temporary.write_bytes(data)
    temporary.replace(target)


async def execute_lesson(root: Path, request: Any, settings: Any, emit: Any) -> dict[str, Any]:
    from agent_lab.models import Event, lesson_request

    request = lesson_request(46, request)
    choices = request.lesson_options
    if request.mode == "live":
        if not settings.enable_live:
            raise PermissionError("Enable bounded paid calls with LAB_ENABLE_LIVE=true")
        report = await live_action(choices["action"], choices["ttl"],
                                   choices["prefix"], choices["policy"])
        results = [row for row in report["frames"] if row.get("kind") == "result"]
        if results:
            await emit(Event(kind="result", data={"lesson_id": 46,
                                                  "total_cost_usd": results[-1]["total_cost_usd"]}))
    else:
        scenario = {"success": "normal", "missing-evidence": "missing",
                    "wrong-identity": "foreign"}.get(request.scenario, request.scenario)
        report = await local_action(choices["action"], choices["ttl"],
                                    choices["prefix"], choices["policy"], scenario)
    save_passing(report, root / "owned-cache")
    proof = {"experiment": report, "experiment_passed": report["experiment_passed"]}
    await emit(Event(kind="evidence", data={"lesson_id": 46, "result": proof}))
    return proof


async def local(root: Path, request: Any) -> dict[str, Any]:
    from agent_lab.config import Settings
    from agent_lab.models import Event

    async def ignore(event: Event) -> None:
        pass

    return await execute_lesson(root, request.model_copy(update={"mode": "offline"}),
                                Settings(), ignore)


def evaluate_native(report: dict[str, Any]) -> bool:
    if (report.get("source_label") != "native SDK subprocess" or not report.get("closed")
            or report.get("forwarded") != 2):
        return False
    receipts = report.get("receipts", [])
    frames = report.get("frames", [])
    if len(receipts) != 2 or not isinstance(frames, list):
        return False
    previous = 0.0
    sessions: set[str] = set()
    for turn in (1, 2):
        rows = [row for row in frames if row.get("turn") == turn]
        init = [row for row in rows if row.get("kind") == "init"]
        assistant = [row for row in rows if row.get("kind") == "assistant"]
        results = [row for row in rows if row.get("kind") == "result"]
        receipt = receipts[turn - 1]
        if (not init or len(assistant) != 1 or len(results) != 1 or
                receipt.get("operation") != report.get("operation") or
                receipt.get("turn") != turn or receipt.get("status") != 200 or
                not receipt.get("authenticated") or not receipt.get("nonce_match") or
                receipt.get("message_id") != assistant[0].get("message_id") or
                assistant[0].get("model") != receipt.get("model") or
                results[0].get("subtype") != "success" or results[0].get("is_error") is not False):
            return False
        session = results[0].get("session_id")
        if not isinstance(session, str) or not session or assistant[0].get("session_id") != session:
            return False
        if not any(row.get("session_id") == session for row in init):
            return False
        sessions.add(session)
        try:
            sdk_usage = normalized_usage(results[0]["usage"])
            sdk_increment(previous, results[0]["total_cost_usd"])
        except (KeyError, TypeError, ValueError):
            return False
        if sdk_usage != receipt.get("usage"):
            return False
        previous = results[0]["total_cost_usd"]
    if len(sessions) != 1:
        return False
    if report.get("action") == "switches":
        ttl = report.get("ttl")
        layouts = [row.get("breakpoints", []) for row in receipts]
        if ttl == "off" and any(layout for layout in layouts):
            return False
        if ttl in {"5m", "1h"} and (not all(layouts) or any(
                point.get("ttl") != ttl for layout in layouts for point in layout)):
            return False
    if report.get("action") == "breakers":
        prefix = report.get("prefix")
        if prefix == "changed" and receipts[0].get("system_sha256") == receipts[1].get("system_sha256"):
            return False
        if prefix == "tool" and receipts[0].get("tools_sha256") == receipts[1].get("tools_sha256"):
            return False
        if prefix in {"stable", "dynamic"} and receipts[0].get("system_sha256") != receipts[1].get("system_sha256"):
            return False
        if prefix == "dynamic" and not all(row.get("dynamic_suffix_added") for row in receipts):
            return False
    if report.get("action") == "model-switch":
        hooks = report.get("hooks", [])
        pre = [item for item in hooks if item.get("kind") == "pre-model-switch" and
               item.get("source") == "native-hook"]
        post = [item for item in hooks if item.get("kind") == "post-model-switch" and
                item.get("source") == "native-hook"]
        switch = [item for item in frames if item.get("kind") == "switch-result"]
        if len(pre) != 1 or len(switch) != 1:
            return False
        if (pre[0].get("from_model") != HAIKU or pre[0].get("to_model") != SONNET or
                type(pre[0].get("prompt_cache_warm")) is not bool or
                not isinstance(pre[0].get("estimated_cache_write_usd"), (int, float)) or
                not math.isfinite(pre[0]["estimated_cache_write_usd"]) or
                pre[0]["estimated_cache_write_usd"] < 0):
            return False
        denied = pre[0].get("decision") == "deny"
        expected_denial = (report.get("policy") == "cap" and
                           pre[0]["prompt_cache_warm"] and
                           pre[0]["estimated_cache_write_usd"] > 0)
        if denied != expected_denial:
            return False
        if denied:
            if (switch[0].get("accepted") is not False or post or
                    receipts[1].get("model") != HAIKU):
                return False
        elif (switch[0].get("accepted") is not True or len(post) != 1 or
              post[0].get("from_model") != HAIKU or post[0].get("to_model") != SONNET or
              receipts[1].get("model") != SONNET):
            return False
    return True


async def live_action(action: str, ttl: str = "5m", prefix: str = "stable",
                      policy: str = "cap") -> dict[str, Any]:
    """Run a bounded native two-turn session through the host-owned observer."""
    from dotenv import dotenv_values

    from agent_lab.config import ROOT

    if action not in ACTIONS or ttl not in TTLS or prefix not in PREFIXES or policy not in POLICIES:
        raise ValueError("Unknown fixed cache option")
    key = dotenv_values(ROOT / ".env").get("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
    if not isinstance(key, str) or not key.startswith("sk-ant-"):
        raise PermissionError("Private host Anthropic key is required")
    operation, nonce = str(uuid.uuid4()), secrets.token_hex(12)
    folder = ROOT / ".lab-data" / "cache-live-probe" / operation
    work, home = folder / "work", folder / "home"
    work.mkdir(parents=True)
    home.mkdir()
    (home / "aws-config").write_text("", encoding="utf-8")
    (home / "aws-credentials").write_text("", encoding="utf-8")
    observer = CacheObserver(operation, nonce, action, ttl, prefix, upstream_key=key)
    essentials = {"SYSTEMROOT", "WINDIR", "PATH", "PATHEXT", "COMSPEC", "TEMP", "TMP",
                  "LOCALAPPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)",
                  "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE"}
    environment = {name: value for name, value in os.environ.items() if name.upper() in essentials}
    environment.update({"HOME": str(home), "USERPROFILE": str(home),
                        "APPDATA": str(home / "appdata")})
    frames: list[dict[str, Any]] = []
    hooks: list[dict[str, Any]] = []
    async with EmbeddedServer(observer).running() as base:
        observer.port = int(base.rsplit(":", 1)[1])
        child_env = {"CLAUDE_CONFIG_DIR": str(home),
                     "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1",
                     "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
                     "CLAUDE_CODE_MAX_RETRIES": "1",
                     "AWS_CONFIG_FILE": str(home / "aws-config"),
                     "AWS_SHARED_CREDENTIALS_FILE": str(home / "aws-credentials"),
                     "AWS_EC2_METADATA_DISABLED": "true",
                     "ANTHROPIC_BASE_URL": base,
                     "ANTHROPIC_API_KEY": observer.key,
                     "ANTHROPIC_DEFAULT_HAIKU_MODEL": HAIKU,
                     "ANTHROPIC_DEFAULT_SONNET_MODEL": SONNET}
        if ttl == "off":
            child_env["DISABLE_PROMPT_CACHING"] = "1"
        job = {"work": str(work), "handbook": handbook(operation, prefix == "short"),
               "nonce": nonce, "action": action, "policy": policy,
               "haiku": HAIKU, "sonnet": "sonnet",
               "environment": child_env}
        process = await asyncio.create_subprocess_exec(
            sys.executable, str(ROOT / "scripts" / "cache_native_helper.py"),
            cwd=str(ROOT), env=environment, stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL)
        try:
            output, _ = await asyncio.wait_for(
                process.communicate(json.dumps(job).encode()), timeout=175)
            result = json.loads(output)
            frames = result.get("frames", []) if isinstance(result, dict) else []
            hooks = result.get("hooks", []) if isinstance(result, dict) else []
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()
    observer.closed = True
    report: dict[str, Any] = {"lesson": 46, "operation": operation, "action": action, "mode": "live",
              "ttl": ttl, "prefix": prefix, "policy": policy,
              "source_label": "native SDK subprocess", "native": True,
              "frames": frames, "hooks": hooks, "receipts": observer.receipts,
              "forwarded": observer.forwarded, "closed": observer.closed,
              "created_at": datetime.now(UTC).isoformat()}
    report["experiment_passed"] = evaluate_native(report)
    folder.joinpath("report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
