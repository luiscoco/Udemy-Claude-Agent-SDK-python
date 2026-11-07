"""Send a validated, workspace-owned PNG as a typed SDK user content block."""

import asyncio
import base64
import binascii
import hashlib
import struct
import zlib
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, SystemMessage

from agent_lab.config import Settings
from agent_lab.foundations import Evidence
from agent_lab.models import Event, LessonError, RunRequest, lesson_request
from agent_lab.policy import inside

SIZE = 256
MIME = "image/png"
QUESTION = "What is the dominant color of the solid square in this image? Answer with exactly one uppercase word: RED or BLUE."
COLORS = {"red": (255, 0, 0), "blue": (0, 0, 255)}
SIGNATURE = b"\x89PNG\r\n\x1a\n"


def make_png(color: str) -> bytes:
    """Encode one fixed RGB test square without loading untrusted files."""
    rgb = bytes(COLORS[color])

    def chunk(kind: bytes, payload: bytes) -> bytes:
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", binascii.crc32(kind + payload) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", SIZE, SIZE, 8, 2, 0, 0, 0)
    pixels = (b"\x00" + rgb * SIZE) * SIZE
    return SIGNATURE + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(pixels)) + chunk(b"IEND", b"")


def validated_image(path: Path) -> tuple[bytes, str]:
    data = path.read_bytes()
    if len(data) > 1_000_000 or not data.startswith(SIGNATURE) or len(data) < 33:
        raise LessonError("The owned image is not a bounded PNG.")
    width, height, depth, color_type = struct.unpack(">IIBB", data[16:26])
    if (width, height, depth, color_type) != (SIZE, SIZE, 8, 2):
        raise LessonError("The owned PNG dimensions or encoding changed.")
    return data, hashlib.sha256(data).hexdigest()


async def image_turn(data: bytes, sent: list[dict[str, Any]]) -> AsyncIterator[dict[str, Any]]:
    image = {"type": "image", "source": {"type": "base64", "media_type": MIME, "data": base64.b64encode(data).decode("ascii")}}
    sent.append({"type": "image", "source_type": "base64", "media_type": MIME, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "width": SIZE, "height": SIZE, "text": QUESTION})
    yield {"type": "user", "message": {"role": "user", "content": [image, {"type": "text", "text": QUESTION}]}, "parent_tool_use_id": None, "session_id": "default"}


def image_options(root: Path, config: Path, request: RunRequest, settings: Settings) -> ClaudeAgentOptions:
    from agent_lab.sdk import isolated_env, resolve_cli_path

    return ClaudeAgentOptions(
        cwd=str(root.resolve()),
        model=settings.model,
        cli_path=resolve_cli_path(settings) if request.mode == "live" else None,
        tools=[],
        allowed_tools=[],
        setting_sources=[],
        strict_mcp_config=True,
        env=isolated_env(config.resolve()),
        system_prompt={"type": "preset", "preset": "claude_code", "append": "This is a fixed image-input lesson. Use no tools. Answer the image color question with exactly one uppercase word."},
        max_turns=request.max_turns,
        max_budget_usd=request.max_budget_usd,
    )


def image_report(state: Evidence, selected: dict, sent: list[dict], expected_hash: str, final_hash: str, answer: str | None, closed: bool) -> dict:
    base = state.report()
    terminal = state.terminals[-1] if state.terminals else {}
    init = state.initialized[-1] if state.initialized else {}
    identity_ok = bool(init.get("session_id") and init.get("session_id") == terminal.get("session_id"))
    input_ok = len(sent) == 1 and sent[0] == {"type": "image", "source_type": "base64", "media_type": MIME, "bytes": len(make_png(selected["color"])), "sha256": expected_hash, "width": SIZE, "height": SIZE, "text": QUESTION}
    file_ok = final_hash == expected_hash
    observed = bool(base["experiment_passed"] and identity_ok and input_ok and file_ok and answer == selected["color"].upper() and closed)
    return {
        **base,
        "selected": selected,
        "input_observation": sent,
        "owned_file_sha256_before": expected_hash,
        "owned_file_sha256_after": final_hash,
        "typed_image_verified": input_ok,
        "owned_file_unchanged": file_ok,
        "observed_answer": answer,
        "session_identity_verified": identity_ok,
        "connection_closed": closed,
        "observation_passed": observed,
        "experiment_passed": observed,
        "check_scope": "The host validates an exact workspace-owned PNG, yields one typed base64 image plus text to the SDK, observes a successful session and the selected red/blue answer, and verifies the file hash stayed unchanged. The response gives behavioral evidence of image input; the provider's internal vision processing is not directly visible.",
    }


async def execute_image_input(root: Path, request: RunRequest, settings: Settings, emit: Any, config: Path | None = None) -> dict:
    from agent_lab.sdk import message_data, require_live_access

    request = lesson_request(29, request)
    root = await asyncio.to_thread(root.resolve)
    selected = request.lesson_options
    config = config or root.parent / "config"
    root.mkdir(parents=True, exist_ok=True)
    path = inside(root, "square.png")
    path.write_bytes(make_png(selected["color"]))
    data, before = validated_image(path)
    state = Evidence(29, root.parent.name, root, selected, "live SDK stream and actual host callbacks" if request.mode == "live" else "local host effects plus explicitly recorded SDK correlation fixtures", request.max_turns, request.max_budget_usd)
    state.configured = {"tools": [], "allowed_tools": [], "setting_sources": [], "strict_mcp_config": True, "image_media_type": MIME, "image_dimensions": [SIZE, SIZE]}
    await emit(Event(kind="options", data={"lesson_id": 29, "sdk_options": state.configured}))
    sent: list[dict] = []
    answer: str | None = None
    client = None
    closed = False
    try:
        if request.mode == "live":
            require_live_access(settings)
            config.mkdir(parents=True, exist_ok=True)
            client = ClaudeSDKClient(options=image_options(root, config, request, settings))
            await client.connect()
            await client.query(image_turn(data, sent))
            async for message in client.receive_response():
                if isinstance(message, SystemMessage) and message.subtype == "api_retry" and message.data.get("error_status") == 401:
                    raise PermissionError("Claude rejected authentication (HTTP 401). No host retry was attempted.")
                item = message_data(message)
                if item["message_class"] == "ResultMessage" and isinstance(item.get("result"), str):
                    answer = item["result"].strip()
                event = Event(kind="result" if item["message_class"] == "ResultMessage" else "message", data=item)
                state.observe(event)
                await emit(event)
            if not state.report()["experiment_passed"]:
                raise LessonError("Image-input run did not finish with a successful SDK result.")
        else:
            async for _ in image_turn(data, sent):
                pass
            state.initialized = [{"session_id": "image-fixture"}]
            state.terminals = [{"session_id": "image-fixture", "subtype": "success", "is_error": False}]
            answer = selected["color"].upper()
            if request.scenario == "missing-evidence":
                state.terminals.clear()
            elif request.scenario == "wrong-identity":
                state.terminals[-1]["session_id"] = "foreign"
            elif request.scenario == "wrong-mime":
                sent[0]["media_type"] = "image/jpeg"
            elif request.scenario == "changed-file":
                path.write_bytes(make_png("blue" if selected["color"] == "red" else "red"))
            elif request.scenario == "missing-yield":
                sent.clear()
            elif request.scenario == "wrong-answer":
                answer = "GREEN"
    finally:
        if client is not None:
            await client.disconnect()
        closed = True
        final_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        report = image_report(state, selected, sent, before, final_hash, answer, closed)
        report["scenario"] = request.scenario
        report["expected_check"] = "passed" if report["experiment_passed"] else "needs-review"
        proof = {"experiment": report, "experiment_passed": report["experiment_passed"]}
        async with asyncio.timeout(1):
            await emit(Event(kind="evidence", data={"lesson_id": 29, "result": proof}))
    return proof


async def local_image_input(root: Path, request: RunRequest) -> dict:
    async def ignore(event: Event) -> None:
        pass

    return await execute_image_input(root, request.model_copy(update={"mode": "offline"}), Settings(), ignore)
