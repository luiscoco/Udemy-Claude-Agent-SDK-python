"""Lesson 36: bounded shell-free host child alongside a separate SDK turn."""

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

from agent_lab.config import Settings
from agent_lab.foundations import Evidence
from agent_lab.models import Event, RunRequest, lesson_request

PROMPT = "For lesson 36, reply exactly SPAWN_OK_36. Use no tools and add no explanation."
SOURCE_LIVE = "live SDK stream and actual host callbacks"


class FrameTap:
    """Observe complete JSONL lines while forwarding original transport bytes."""

    def __init__(self) -> None:
        self.pending = bytearray()
        self.frames: list[dict[str, Any]] = []
        self.partial_chunks = 0
        self.forwarded = bytearray()
        self.complete_lines = bytearray()

    def feed(self, chunk: bytes) -> bytes:
        self.forwarded.extend(chunk)
        self.pending.extend(chunk)
        if b"\n" not in chunk:
            self.partial_chunks += 1
        while b"\n" in self.pending:
            line, _, rest = self.pending.partition(b"\n")
            self.pending = bytearray(rest)
            self.complete_lines.extend(line + b"\n")
            if line:
                self.frames.append(json.loads(line.decode("utf-8")))
        return chunk

    def finish(self) -> bool:
        return not self.pending


async def probe_child(root: Path, action: str, location: str) -> dict[str, Any]:
    """Launch one fixed Python child, capture streams, and always reap it."""
    base = await asyncio.to_thread(root.resolve)
    script = await asyncio.to_thread(Path(__file__).with_name("process_probe.py").resolve)
    directory = await asyncio.to_thread((base / location).resolve)
    if not directory.is_relative_to(base):
        raise ValueError("Child location escapes the owned workspace.")
    await asyncio.to_thread(directory.mkdir, parents=True, exist_ok=True)
    child_case = action if action in {"stderr", "timeout", "cancel"} else "success"
    executable = str(base / "missing-python-36") if action == "failed-launch" else sys.executable
    command = [executable, "-I", str(script), "--case", child_case]
    report: dict[str, Any] = {"command": ["<owned Python>" if item == sys.executable else item for item in command],
                              "cwd": str(directory), "shell": False, "frames": [],
                              "stderr_marker": False, "exit_code": None, "partial_chunks": 0,
                              "bytes_forwarded_unchanged": False, "child_cleaned": False,
                              "launch_error": None, "interrupted": False}
    try:
        process = await asyncio.create_subprocess_exec(*command, cwd=directory,
                                                       stdout=asyncio.subprocess.PIPE,
                                                       stderr=asyncio.subprocess.PIPE)
    except OSError as exc:
        report["launch_error"] = type(exc).__name__
        return report
    assert process.stdout is not None and process.stderr is not None
    stdout_pipe = process.stdout
    stderr_pipe = process.stderr
    tap = FrameTap()

    async def drain_stdout() -> None:
        while chunk := await stdout_pipe.read(7):
            assert tap.feed(chunk) == chunk

    stdout_task = asyncio.create_task(drain_stdout())
    stderr_task = asyncio.create_task(stderr_pipe.read(4096))
    try:
        if action == "cancel":
            await asyncio.sleep(0.05)
            raise asyncio.CancelledError
        async with asyncio.timeout(0.25 if action == "timeout" else 5):
            await process.wait()
    except (TimeoutError, asyncio.CancelledError):
        report["interrupted"] = True
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()
        await stdout_task
        stderr = await stderr_task
        report.update({"frames": tap.frames, "stderr_marker": b"CHILD_DIAGNOSTIC_36" in stderr,
                       "exit_code": process.returncode, "partial_chunks": tap.partial_chunks,
                       "bytes_forwarded_unchanged": tap.forwarded == tap.complete_lines,
                       "child_cleaned": process.returncode is not None and tap.finish()})
    return report


def spawn_options(root: Path, config: Path, request: RunRequest, settings: Settings) -> ClaudeAgentOptions:
    from agent_lab.sdk import isolated_env, resolve_cli_path

    return ClaudeAgentOptions(
        cwd=str(root.resolve()), model=settings.model,
        cli_path=resolve_cli_path(settings) if request.mode == "live" else None,
        tools=[], allowed_tools=[], setting_sources=[], strict_mcp_config=True,
        env=isolated_env(config.resolve()), max_turns=request.max_turns,
        max_budget_usd=request.max_budget_usd,
    )


def spawn_report(state: Evidence, child: dict[str, Any], answer: str | None,
                 closed: bool) -> dict[str, Any]:
    base = state.report()
    selected = state.selected
    init = state.initialized[-1] if state.initialized else {}
    terminal = state.terminals[-1] if state.terminals else {}
    sdk_ok = bool(init.get("session_id") and terminal.get("session_id") == init["session_id"]
                  and terminal.get("subtype") == "success" and terminal.get("is_error") is False
                  and answer == "SPAWN_OK_36" and not state.calls)
    frames = child["frames"]
    host_ok = bool([item.get("kind") for item in frames] == ["init", "host_tool", "done"]
                   and frames[0].get("location") == selected["location"]
                   and frames[-1].get("outcome") == "HOST_OK_36"
                   and child["exit_code"] == 0 and child["shell"] is False
                   and child["partial_chunks"] > 0 and child["bytes_forwarded_unchanged"]
                   and child["child_cleaned"] and child["stderr_marker"] == (selected["action"] == "stderr"))
    configured_ok = state.configured == {"tools": [], "allowed_tools": [], "setting_sources": [],
                                          "strict_mcp_config": True, "auto_memory_disabled": True}
    passed = bool(base["experiment_passed"] and sdk_ok and host_ok and configured_ok and closed)
    return {**base, "selected": selected, "child": child, "sdk_success": sdk_ok,
            "host_success": host_ok, "configured": state.configured,
            "connection_closed": closed, "experiment_passed": passed,
            "check_scope": "An owned Python child launches with fixed argv and cwd, no shell, separately captured stderr, complete JSONL frames and unchanged forwarded bytes. Timeout/cancel paths reap the child. A separate real SDK CLI turn must have a successful matching terminal. Python SDK has no public custom-spawner option; this does not claim the host child carried the SDK protocol or ran remotely."}


async def execute_spawn(root: Path, request: RunRequest, settings: Settings,
                        emit: Any, config: Path | None = None) -> dict[str, Any]:
    from agent_lab.sdk import message_data, require_live_access

    request = lesson_request(36, request)
    root = await asyncio.to_thread(root.resolve)
    selected = request.lesson_options
    child = await probe_child(root, selected["action"], selected["location"])
    config = config or root.parent / "config"
    state = Evidence(36, root.parent.name, root, selected,
                     SOURCE_LIVE if request.mode == "live" else "actual local child and explicitly recorded SDK fixtures",
                     request.max_turns, request.max_budget_usd)
    if request.mode == "live":
        require_live_access(settings)
    options = spawn_options(root, config, request, settings)
    state.configured = {"tools": options.tools, "allowed_tools": options.allowed_tools,
                        "setting_sources": options.setting_sources, "strict_mcp_config": options.strict_mcp_config,
                        "auto_memory_disabled": options.env.get("CLAUDE_CODE_DISABLE_AUTO_MEMORY") == "1"}
    await emit(Event(kind="options", data={"lesson_id": 36, "sdk_options": state.configured}))
    answer: str | None = None
    closed = False
    try:
        if request.mode == "live":
            config.mkdir(parents=True, exist_ok=True)
            client = ClaudeSDKClient(options=options)
            try:
                await client.connect()
                await client.query(PROMPT)
                async for message in client.receive_response():
                    data = message_data(message)
                    if data["message_class"] == "ResultMessage" and isinstance(data.get("result"), str):
                        answer = data["result"].strip()
                    event = Event(kind="result" if data["message_class"] == "ResultMessage" else "message", data=data)
                    state.observe(event)
                    await emit(event)
            finally:
                await client.disconnect()
        else:
            state.initialized = [{"session_id": "spawn-fixture"}]
            state.terminals = [{"session_id": "spawn-fixture", "subtype": "success", "is_error": False}]
            answer = "SPAWN_OK_36"
            if request.scenario == "missing-evidence":
                state.terminals.clear()
            elif request.scenario == "wrong-identity":
                state.terminals[0]["session_id"] = "foreign"
            elif request.scenario == "wrong-frame":
                child["frames"][-1]["outcome"] = "WRONG_36"
            elif request.scenario == "wrong-answer":
                answer = "OTHER_36"
    finally:
        closed = True
        report = spawn_report(state, child, answer, closed)
        report["scenario"] = request.scenario
        report["expected_check"] = "passed" if report["experiment_passed"] else "needs-review"
        proof = {"experiment": report, "experiment_passed": report["experiment_passed"]}
        await emit(Event(kind="evidence", data={"lesson_id": 36, "result": proof}))
    return proof


async def local_spawn(root: Path, request: RunRequest) -> dict[str, Any]:
    async def ignore(event: Event) -> None:
        pass

    return await execute_spawn(root, request.model_copy(update={"mode": "offline"}), Settings(), ignore)
