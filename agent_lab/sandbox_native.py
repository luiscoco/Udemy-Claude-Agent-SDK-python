"""Minimal Linux/macOS SDK sandbox acceptance, also runnable from a WSL venv."""

import asyncio
import dataclasses
import json
import platform
import shutil
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    ClaudeAgentOptions,
    ClaudeSDKClient,
    HookMatcher,
    ResultMessage,
    SystemMessage,
)

COMMAND = "python3 -I sandbox_probe.py"


def sandbox_capability() -> dict[str, Any]:
    system = platform.system()
    missing = (
        [name for name in ("bwrap", "socat") if not shutil.which(name)] if system == "Linux" else []
    )
    supported = system in {"Linux", "Darwin"} and not missing
    return {
        "system": system,
        "supported": supported,
        "missing_dependencies": missing,
        "enforcement_verified": False,
        "reason": "Eligible platform; an actual process probe is still required."
        if supported
        else "Native Windows is unsupported; use Linux/WSL2 or macOS."
        if system == "Windows"
        else "Missing sandbox dependencies or unsupported platform.",
    }


def native_options(
    root: Path, config: Path, model: str, cli_path: str | None = None
) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        cwd=str(root.resolve()),
        model=model,
        cli_path=cli_path,
        tools=["Bash"],
        allowed_tools=[],
        setting_sources=[],
        strict_mcp_config=True,
        permission_mode="default",
        max_turns=4,
        max_budget_usd=0.10,
        env={
            "CLAUDE_CONFIG_DIR": str(config.resolve()),
            "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1",
            "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        },
        sandbox={
            "enabled": True,
            "autoAllowBashIfSandboxed": False,
            "allowUnsandboxedCommands": False,
            "excludedCommands": [],
            "network": {"allowedDomains": [], "allowAllUnixSockets": False},
        },
        # SDK 0.2.174 lacks typed fields for these CLI settings; pass the documented inline extension.
        settings=json.dumps(
            {
                "sandbox": {
                    "failIfUnavailable": True,
                    "filesystem": {
                        "denyWrite": [str((root.parent / "outside-write.txt").resolve())]
                    },
                }
            }
        ),
        system_prompt="Run exactly the supplied Bash command once. The host owns the probe script. Do not edit files, add commands or request an unsandboxed retry. After the tool result reply Done.",
    )


def native_command_allowed(name: str, args: dict) -> bool:
    return (
        name == "Bash"
        and args.get("command") == COMMAND
        and not args.get("dangerouslyDisableSandbox")
    )


async def run_native_probe(
    root: Path, config: Path, model: str, cli_path: str | None = None
) -> dict:
    """Observe inside writes, denied outside writes and denied direct loopback connections."""
    capability = sandbox_capability()
    if not capability["supported"]:
        return {
            "passed": False,
            "status": "unsupported",
            "capability": capability,
            "model_calls": 0,
        }
    await asyncio.to_thread(root.mkdir, parents=True, exist_ok=True)
    await asyncio.to_thread(config.mkdir, parents=True, exist_ok=True)
    outside = root.parent / "outside-write.txt"
    outside.write_text("owned-native-probe-original", encoding="utf-8")
    original = outside.read_bytes()
    baseline = False
    client = None
    closed = False
    decisions, calls, results, initializations, terminals = [], [], [], [], []
    error = None

    async def connection(reader, writer):
        writer.write(b"lesson-local-only")
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(connection, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    script = f"""import json,socket
from pathlib import Path
inside=Path("inside-write.txt")
outside=Path({str(outside.resolve())!r})
report={{}}
try:
 inside.write_text("inside-ok",encoding="utf-8"); report["inside_write"]=True
except OSError:
 report["inside_write"]=False
try:
 outside.write_text("outside-changed",encoding="utf-8"); report["outside_write_blocked"]=False
except OSError:
 report["outside_write_blocked"]=True
try:
 with socket.create_connection(("127.0.0.1",{port}),timeout=2) as s: s.recv(32)
 report["direct_loopback_blocked"]=False
except OSError:
 report["direct_loopback_blocked"]=True
print(json.dumps(report))
"""
    (root / "sandbox_probe.py").write_text(script, encoding="utf-8")
    options = native_options(root, config, model, cli_path)

    async def guard(data, call_id, context):
        allowed = native_command_allowed(data.get("tool_name", ""), data.get("tool_input", {}))
        decisions.append({"id": call_id, "allowed": allowed})
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow" if allowed else "deny",
                "permissionDecisionReason": "Only the fixed owned sandbox probe is permitted; bypass is forbidden.",
            }
        }

    options.hooks = {"PreToolUse": [HookMatcher(hooks=[guard])]}
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        baseline = await reader.read(32) == b"lesson-local-only"
        writer.close()
        await writer.wait_closed()
        client = ClaudeSDKClient(options=options)
        async with asyncio.timeout(120):
            await client.connect()
            await client.query(f"Run this exact Bash command once: {COMMAND}")
            async for message in client.receive_response():
                if isinstance(message, SystemMessage):
                    if message.subtype == "init":
                        initializations.append(message.data.get("session_id"))
                    if message.subtype == "api_retry" and message.data.get("error_status") == 401:
                        raise RuntimeError("Authentication failed")
                if isinstance(message, ResultMessage):
                    terminals.append(
                        {
                            "session_id": message.session_id,
                            "subtype": message.subtype,
                            "is_error": message.is_error,
                            "cost_usd": message.total_cost_usd,
                            "num_turns": message.num_turns,
                            "duration_ms": message.duration_ms,
                        }
                    )
                if dataclasses.is_dataclass(message):
                    for block in (
                        getattr(message, "content", [])
                        if isinstance(getattr(message, "content", []), list)
                        else []
                    ):
                        if hasattr(block, "name") and hasattr(block, "id"):
                            calls.append(
                                {
                                    "id": block.id,
                                    "name": block.name,
                                    "arguments": block.input,
                                    "parent": getattr(message, "parent_tool_use_id", None),
                                }
                            )
                        if hasattr(block, "tool_use_id"):
                            # Fixed script only emits booleans. Never preserve arbitrary provider payloads.
                            content = block.content
                            text = (
                                content
                                if isinstance(content, str)
                                else "\n".join(
                                    b.get("text", "") for b in content or [] if isinstance(b, dict)
                                )
                            )
                            flags = None
                            for line in text.splitlines():
                                try:
                                    parsed = json.loads(line)
                                    if (
                                        isinstance(parsed, dict)
                                        and set(parsed)
                                        == {
                                            "inside_write",
                                            "outside_write_blocked",
                                            "direct_loopback_blocked",
                                        }
                                        and all(type(v) is bool for v in parsed.values())
                                    ):
                                        flags = parsed
                                except ValueError:
                                    pass
                            results.append(
                                {
                                    "id": block.tool_use_id,
                                    "is_error": bool(block.is_error),
                                    "probe": flags,
                                }
                            )
    except Exception as exc:
        error = type(exc).__name__
    finally:
        try:
            if client is not None:
                await client.disconnect()
            closed = True
        except Exception as exc:
            error = type(exc).__name__
        server.close()
        await server.wait_closed()
    terminal = terminals[-1] if terminals else {}
    paired = [
        r
        for r in results
        if not r["is_error"]
        and r["probe"]
        and all(r["probe"].values())
        and sum(x["id"] == r["id"] for x in results) == 1
        and sum(x["id"] == r["id"] for x in calls) == 1
        and any(
            c["id"] == r["id"]
            and not c["parent"]
            and native_command_allowed(c["name"], c["arguments"])
            for c in calls
        )
        and any(d["id"] == r["id"] and d["allowed"] for d in decisions)
    ]
    unchanged = outside.read_bytes() == original if outside.is_file() else False
    inside_ok = (root / "inside-write.txt").is_file() and (root / "inside-write.txt").read_text(
        encoding="utf-8"
    ) == "inside-ok"
    passed = bool(
        not error
        and baseline
        and closed
        and unchanged
        and inside_ok
        and len(paired) == 1
        and terminal.get("subtype") == "success"
        and terminal.get("is_error") is False
        and initializations
        and terminal.get("session_id") == initializations[-1]
    )
    capability["enforcement_verified"] = passed
    return {
        "passed": passed,
        "status": "completed" if not error else "failed",
        "error_type": error,
        "capability": capability,
        "source": "actual SDK CLI sandbox and OS effects",
        "connection_closed": closed,
        "baseline_loopback_reachable": baseline,
        "outside_unchanged": unchanged,
        "inside_write_observed": inside_ok,
        "calls": calls,
        "results": results,
        "decisions": decisions,
        "terminal_results": terminals,
        "reported_cost_usd": terminal.get("cost_usd"),
    }
