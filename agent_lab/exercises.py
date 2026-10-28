"""Executable host exercises. All returned evidence is computed locally, never model output."""

import asyncio
import base64
import contextlib
import csv
import dataclasses
import importlib.metadata
import inspect
import io
import json
import os
import sys
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from agent_lab.hooks import call_hook, lesson_hooks, matches, permission_callback
from agent_lab.models import Lesson, LessonError, RunRequest
from agent_lab.policy import decide, inside, redact
from agent_lab.services import (
    Approval,
    Board,
    Budget,
    Calculation,
    Journal,
    Orders,
    Plan,
    Refund,
    Summary,
    TaskSpec,
    execute_plan,
    retrieve,
)

Exercise = Callable[[Path, RunRequest, Lesson], Any]
EXERCISES: dict[str, Exercise] = {}


def exercise(*names: str) -> Callable[[Exercise], Exercise]:
    def register(function: Exercise) -> Exercise:
        for name in names:
            EXERCISES[name] = function
        return function

    return register


def seed_workspace(root: Path, lesson: Lesson) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "notes.txt").write_text(
        "Python agents combine an SDK, host tools, permissions and sessions.\n", encoding="utf-8"
    )
    (root / "sales.csv").write_text(
        "region,amount\nnorth,120\nsouth,80\nnorth,40\n", encoding="utf-8"
    )
    from agent_lab.sdk import PROJECT_SETTING_PROFILES

    if lesson.live_profile in PROJECT_SETTING_PROFILES:
        (root / ".claude").mkdir(exist_ok=True)
    if lesson.live_profile == "skills":
        folder = root / ".claude" / "skills" / "lesson-summary"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "SKILL.md").write_text(
            "---\nname: lesson-summary\ndescription: Summarize a Python lesson with one example.\n---\nRead notes.txt. Return a concise summary and a Python example.\n",
            encoding="utf-8",
        )
    if lesson.live_profile == "commands":
        folder = root / ".claude" / "commands"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "lesson-summary.md").write_text(
            "Summarize notes.txt in three bullet points.\n", encoding="utf-8"
        )
    if lesson.live_profile == "memory":
        (root / "CLAUDE.md").write_text(
            "This is a Python teaching project. Use concise explanations and Python examples.\n",
            encoding="utf-8",
        )
    if lesson.live_profile == "styles":
        folder = root / ".claude" / "output-styles"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "teaching.md").write_text(
            "---\nname: teaching\ndescription: Concise Python teaching style\n---\nExplain the concept, then show one Python example.\n",
            encoding="utf-8",
        )
        (root / ".claude" / "settings.json").write_text(
            '{"outputStyle":"teaching"}', encoding="utf-8"
        )


@exercise("messages", "testing")
async def message_exercise(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock

    async def recorded_messages():
        yield AssistantMessage(content=[TextBlock(text="Recorded test text")], model="fixture")
        yield ResultMessage(
            subtype="success",
            duration_ms=0,
            duration_api_ms=0,
            is_error=False,
            num_turns=1,
            session_id="offline-fixture",
            total_cost_usd=0,
            result="Recorded test text",
        )

    text: list[str] = []
    results: list[dict[str, Any]] = []
    async for message in recorded_messages():
        if isinstance(message, AssistantMessage):
            text.extend(block.text for block in message.content if isinstance(block, TextBlock))
        elif isinstance(message, ResultMessage):
            results.append({"session_id": message.session_id, "cost": message.total_cost_usd})
    return {
        "source": "recorded unit-test fixture; no SDK process was started",
        "text": text,
        "results": results,
    }


@exercise("thinking", "python_sdk")
def sdk_contract(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    import claude_agent_sdk as sdk

    fields = {field.name: str(field.type) for field in dataclasses.fields(sdk.ClaudeAgentOptions)}
    focus = {
        "options": ["model", "max_turns", "max_budget_usd", "include_partial_messages"],
        "thinking": ["thinking", "effort", "max_thinking_tokens"],
        "settings": ["setting_sources", "env", "cwd"],
        "sandbox": ["sandbox"],
        "session_management": ["resume", "continue_conversation", "fork_session"],
        "resume": ["resume", "resume_session_at", "fork_session"],
        "elicitation": ["on_elicitation", "hooks"],
    }.get(lesson.exercise, ["model", "tools", "hooks", "can_use_tool", "mcp_servers"])
    return {
        "installed_version": importlib.metadata.version("claude-agent-sdk"),
        "options": {
            name: fields.get(name, "Not available in this installed Python SDK") for name in focus
        },
        "public_client_methods": [
            name
            for name, _ in inspect.getmembers(sdk.ClaudeSDKClient, inspect.isfunction)
            if not name.startswith("_")
        ],
        "session_functions": [
            name
            for name in ("list_sessions", "get_session_messages", "get_session_info")
            if hasattr(sdk, name)
        ],
        "request": request.model_dump(exclude={"prompt", "follow_up"}),
        "note": lesson.notes,
    }


@exercise("workspace", "config_root")
def workspace(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    return {
        "cwd": str(root),
        "files": [p.name for p in root.iterdir() if p.is_file()],
        "notes": inside(root, "notes.txt").read_text(encoding="utf-8"),
        "setting_sources": [],
    }


@exercise("permissions", "security", "redteam")
def permission_cases(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    cases = [
        ("normal read", "Read", {"file_path": "notes.txt"}, True),
        ("path traversal", "Read", {"file_path": "../outside.txt"}, False),
        ("secret read", "Read", {"file_path": ".env"}, False),
        ("shell injection", "Bash", {"command": "echo preapproved"}, False),
        ("unapproved write", "Write", {"file_path": "notes.txt"}, False),
    ]
    rows: list[dict[str, Any]] = []
    for label, tool, arguments, expected in cases:
        allowed, reason = decide(root, tool, arguments)
        rows.append(
            {
                "case": label,
                "tool": tool,
                "allowed": allowed,
                "expected": expected,
                "passed": allowed == expected,
                "reason": reason,
            }
        )
    return {
        "decisions": rows,
        "pass_rate": sum(row["passed"] for row in rows) / len(rows),
        "redacted": redact({"api_key": "fixture-only", "text": "Bearer fake-fixture-token"}),
    }


# Tool calls shaped like the CLI's hook input; the same cases appear in lessons 4, 7, 20 and 37.
TOOL_CALLS = [
    ("normal read", "Read", {"file_path": "notes.txt"}),
    ("path traversal", "Read", {"file_path": "../outside.txt"}),
    ("secret read", "Read", {"file_path": ".env"}),
    ("shell command", "Bash", {"command": "echo preapproved"}),
    ("unapproved write", "Write", {"file_path": "notes.txt", "content": "changed"}),
]


def hook_input(event: str, tool: str, arguments: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return {
        "hook_event_name": event,
        "session_id": "offline-lesson",
        "tool_name": tool,
        "tool_input": arguments,
        **extra,
    }


@exercise("hooks")
async def hooks(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    """Run the live PreToolUse policy hook on recorded tool calls; no tool executes."""
    audit_log: list[dict[str, Any]] = []

    async def audit(kind: str, data: dict[str, Any]) -> None:
        audit_log.append({"event": kind, **data})

    config = lesson_hooks(lambda name, arguments: decide(root, name, arguments), audit)
    pre_tool = config["PreToolUse"][0].hooks[0]
    decisions = []
    for number, (label, tool, arguments) in enumerate(TOOL_CALLS, 1):
        output = await call_hook(
            pre_tool, hook_input("PreToolUse", tool, arguments), f"toolu_{number}"
        )
        decision = output["hookSpecificOutput"]
        decisions.append(
            {
                "case": label,
                "tool": tool,
                "decision": decision["permissionDecision"],
                "reason": decision["permissionDecisionReason"],
            }
        )
    return {
        "registered_events": list(config),
        "decisions": decisions,
        "denied": sum(row["decision"] == "deny" for row in decisions),
        "audit_log": audit_log,
    }


@exercise("hook_pipeline")
async def hook_pipeline(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    """Dispatch matched hooks around a host tool loop, as the CLI does for each tool call."""
    from claude_agent_sdk import HookContext, HookInput, HookJSONOutput, HookMatcher

    timeline: list[dict[str, Any]] = []

    async def audit(kind: str, data: dict[str, Any]) -> None:
        step = {"hook": "PreToolUse hook", "audit": "PostToolUse audit"}[kind]
        timeline.append({"step": step, **data})

    config = lesson_hooks(lambda name, arguments: decide(root, name, arguments), audit)

    async def write_alert(
        arguments: HookInput, tool_use_id: str | None, context: HookContext
    ) -> HookJSONOutput:
        timeline.append({"step": "write alert hook", "tool": arguments.get("tool_name")})
        return {}

    # A matcher-scoped hook: it would only ever see Write or Edit results.
    config["PostToolUse"].append(HookMatcher(matcher="Write|Edit", hooks=[write_alert]))
    for number, (label, tool, arguments) in enumerate(TOOL_CALLS, 1):
        tool_use_id = f"toolu_{number}"
        timeline.append({"step": "tool requested", "case": label, "tool": tool})
        allowed = True
        for matcher in config["PreToolUse"]:
            if matches(matcher.matcher, tool):
                for callback in matcher.hooks:
                    output = await call_hook(
                        callback, hook_input("PreToolUse", tool, arguments), tool_use_id
                    )
                    allowed &= output["hookSpecificOutput"]["permissionDecision"] == "allow"
        if not allowed:
            timeline.append({"step": "tool blocked", "tool": tool})
            continue
        # Only allowed reads reach this point; the host performs the read itself.
        result = inside(root, arguments["file_path"]).read_text(encoding="utf-8")
        timeline.append({"step": "tool executed", "tool": tool, "characters": len(result)})
        for matcher in config["PostToolUse"]:
            if matches(matcher.matcher, tool):
                for callback in matcher.hooks:
                    await call_hook(
                        callback,
                        hook_input("PostToolUse", tool, arguments, tool_response=result),
                        tool_use_id,
                    )
    executed = [row for row in timeline if row["step"] == "tool executed"]
    audited = [row for row in timeline if row["step"] == "PostToolUse audit"]
    return {
        "matchers": {
            event: [matcher.matcher or "*" for matcher in matchers]
            for event, matchers in config.items()
        },
        "timeline": timeline,
        "executed": len(executed),
        "audited": len(audited),
        "every_execution_audited": len(executed) == len(audited),
        "write_alerts": sum(row["step"] == "write alert hook" for row in timeline),
    }


@exercise("permission_callback")
async def permission_callback_cases(
    root: Path, request: RunRequest, lesson: Lesson
) -> dict[str, Any]:
    """Call the live can_use_tool callback and show the SDK result object it returns."""
    callback = permission_callback(lambda name, arguments: decide(root, name, arguments))
    results = []
    for label, tool, arguments in TOOL_CALLS:
        outcome = await callback(tool, arguments, None)
        results.append(
            {
                "case": label,
                "tool": tool,
                "result_type": type(outcome).__name__,
                "behavior": outcome.behavior,
                "message": getattr(outcome, "message", ""),
                "input_unchanged": getattr(outcome, "updated_input", None) == arguments,
            }
        )
    return {
        "results": results,
        "allowed": sum(row["behavior"] == "allow" for row in results),
        "denied": sum(row["behavior"] == "deny" for row in results),
        "note": "A PreToolUse hook that returns allow or deny decides first; can_use_tool is "
        "asked only when no hook or rule settled the call.",
    }


@exercise("calculator")
def calculator(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    good = Calculation(a=19.0, b=23.0)
    errors = []
    for bad in ({"a": True, "b": 1}, {"a": float("nan"), "b": 1}, {"a": 1, "b": 1, "shell": "bad"}):
        try:
            Calculation.model_validate(bad)
        except ValueError:
            errors.append("Invalid calculator arguments rejected by host validation.")
    return {
        "schema": Calculation.model_json_schema(),
        "input": good.model_dump(),
        "sum": good.a + good.b,
        "rejected": errors,
    }


FIX_HINTS = {
    "float_type": "Send a JSON number, not a string or boolean.",
    "finite_number": "Send a finite number; NaN and infinity are not allowed.",
    "extra_forbidden": "Remove this field; the tool accepts only a and b.",
    "missing": "Add this required number.",
    "less_than_equal": "Use a value of at most 1000000.",
    "greater_than_equal": "Use a value of at least -1000000.",
}


@exercise("tool_design")
def tool_design(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    """Turn validation failures into per-field messages the model can act on."""
    cases = {
        "boolean instead of number": {"a": True, "b": 1},
        "not a number": {"a": float("nan"), "b": 1},
        "unexpected field": {"a": 1, "b": 1, "shell": "rm -rf /"},
        "missing argument": {"a": 1},
        "out of range": {"a": 2e6, "b": 1},
    }
    feedback = []
    for label, arguments in cases.items():
        try:
            Calculation.model_validate(arguments)
        except ValidationError as exc:
            for error in exc.errors():
                feedback.append(
                    {
                        "case": label,
                        "field": ".".join(str(part) for part in error["loc"]) or "(input)",
                        "problem": error["msg"],
                        "fix": FIX_HINTS.get(error["type"], "Check the input schema."),
                    }
                )
    schema = Calculation.model_json_schema()
    return {
        "tool_description": "Add two finite numbers between -1000000 and 1000000. Returns their sum.",
        "input_schema": schema,
        "valid_call": {"input": {"a": 12.5, "b": 29.5}, "sum": 42.0},
        "feedback": feedback,
        "every_error_actionable": all(row["fix"] != "Check the input schema." for row in feedback),
    }


@exercise("sessions")
def sessions(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    turns = [
        {"role": "user", "content": request.prompt or lesson.prompt},
        {"role": "user", "content": request.follow_up},
    ]
    return {
        "planned_turns": turns,
        "live_lifecycle": [
            "async with ClaudeSDKClient(options)",
            "await client.query(first)",
            "async for message in client.receive_response()",
            "await client.query(follow_up)",
            "consume response",
            "disconnect in the same owning task",
        ],
        "source": "host conversation plan; no model response",
    }


@exercise("subagents")
def subagents(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    from claude_agent_sdk import AgentDefinition

    reviewer = AgentDefinition(
        description="Read-only Python lesson reviewer",
        prompt="Read notes.txt and explain one improvement. Do not edit files.",
        tools=["Read", "Glob", "Grep"],
    )
    return {
        "reviewer": dataclasses.asdict(reviewer),
        "delegation_tool": "Agent",
        "host_authority": "A subagent's role description does not override its tool permissions.",
    }


@exercise("system_prompts")
def system_prompts(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    return {
        "custom": "Teach Python agents using concise explanations.",
        "preset": {"type": "preset", "preset": "claude_code", "append": "Use Python examples."},
        "difference": "A custom prompt replaces the default; a preset retains its base instructions.",
    }


@exercise("options")
def options(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    """Validate requests first, then build ClaudeAgentOptions only from accepted values."""
    from claude_agent_sdk import ClaudeAgentOptions

    from agent_lab.config import Settings

    valid = {"omitted values": {}, "explicit values": {"max_turns": 2, "max_budget_usd": 0.05}}
    invalid = {
        "zero turns": {"max_turns": 0},
        "budget is not a number": {"max_budget_usd": float("nan")},
        "budget above the lab limit": {"max_budget_usd": 5},
        "unknown option": {"cwd": "C:/"},
    }
    accepted = []
    for label, body in valid.items():
        parsed = RunRequest.model_validate(body)
        accepted.append(
            {
                "case": label,
                "set_by_student": sorted(parsed.model_fields_set) or ["(none)"],
                "max_turns": parsed.max_turns,
                "max_budget_usd": parsed.max_budget_usd,
            }
        )
    rejected = []
    for label, bad in invalid.items():
        try:
            RunRequest.model_validate(bad)
        except ValidationError as exc:
            error = exc.errors()[0]
            rejected.append({"case": label, "field": str(error["loc"][0]), "problem": error["msg"]})
    chosen = RunRequest.model_validate(valid["explicit values"])
    built = ClaudeAgentOptions(
        model=Settings().model,
        max_turns=chosen.max_turns,
        max_budget_usd=chosen.max_budget_usd,
        tools=[],
        setting_sources=[],
    )
    fields = ("model", "max_turns", "max_budget_usd", "tools", "setting_sources")
    return {
        "accepted": accepted,
        "rejected": rejected,
        "built_options": {name: getattr(built, name) for name in fields},
        "sdk_defaults": {name: getattr(ClaudeAgentOptions(), name) for name in fields},
        "note": "None in sdk_defaults means the option is not sent and the CLI decides. "
        "The lab always sends explicit limits.",
    }


@exercise("sandbox")
async def sandbox(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    """Show that a path policy guards tool calls, not the processes they start."""
    from claude_agent_sdk.types import SandboxSettings

    outside = root.parent / "outside-secret.txt"
    outside.write_text("host data outside the lesson workspace", encoding="utf-8")
    try:
        allowed, reason = decide(root, "Read", {"file_path": "../outside-secret.txt"})
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-I",
            "-c",
            "print(open('../outside-secret.txt').read())",
            cwd=root,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        async with asyncio.timeout(30):
            stdout, _ = await process.communicate()
    finally:
        outside.unlink(missing_ok=True)
    return {
        "read_tool_through_policy": {"allowed": allowed, "reason": reason},
        "child_process_read_outside": process.returncode == 0 and bool(stdout.strip()),
        "lesson": "The path policy stopped the Read tool, but a process it would have allowed "
        "to run reads the same file. Only OS isolation confines processes.",
        "sdk_sandbox_settings": sorted(SandboxSettings.__annotations__),
        "lab_choice": "Bash is never enabled, so no model-started process exists to confine.",
    }


async def scripted_turn(client: Any) -> dict[str, Any]:
    from claude_agent_sdk import AssistantMessage, ResultMessage

    chunks, models, result = [], set(), None
    async for message in client.receive_response():
        if isinstance(message, AssistantMessage):
            chunks += [getattr(block, "text", "") for block in message.content]
            models.add(message.model)
        elif isinstance(message, ResultMessage):
            result = message
    assert result is not None
    return {
        "text": "".join(chunks),
        "chunks": len(chunks),
        "models": sorted(models),
        "result_subtype": result.subtype,
        "session_id": result.session_id,
    }


@exercise("structured")
async def structured(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    """Validate a structured answer, then interrupt a streaming turn with the real client."""
    from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ClaudeSDKClient

    from agent_lab.scripted_cli import ScriptedCLI

    parsed = Summary.model_validate(
        {"summary": "Host-validated example", "next_steps": ["Run the Python lesson"]}
    )
    try:
        Summary.model_validate({"summary": "", "next_steps": []})
        invalid = "accepted"
    except ValidationError as exc:
        invalid = f"rejected: {exc.error_count()} validation errors"
    cli = ScriptedCLI([[f"step {n} " for n in range(1, 7)]], chunk_delay=0.05)
    received, subtype = 0, None
    async with asyncio.timeout(20):
        async with ClaudeSDKClient(ClaudeAgentOptions(), transport=cli) as client:
            await client.query("Count to six slowly.")
            async for message in client.receive_response():
                if isinstance(message, AssistantMessage):
                    received += 1
                    if received == 2:
                        await client.interrupt()
                else:
                    subtype = getattr(message, "subtype", None)
    return {
        "schema": Summary.model_json_schema(),
        "validated": parsed.model_dump(),
        "invalid_answer": invalid,
        "interrupt": {
            "chunks_planned": 6,
            "chunks_received": received,
            "result_subtype": subtype,
            "control_requests": [
                m["request"]["subtype"] for m in cli.received if m["type"] == "control_request"
            ],
        },
        "source": "real ClaudeSDKClient talking to a scripted CLI fixture",
    }


@exercise("control")
async def control(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    """Call ClaudeSDKClient control methods and observe their effect on the next turn."""
    from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

    from agent_lab.scripted_cli import ScriptedCLI

    cli = ScriptedCLI([["Before the switch."], ["After the switch."]])
    owner = asyncio.current_task()
    async with asyncio.timeout(20):
        async with ClaudeSDKClient(ClaudeAgentOptions(), transport=cli) as client:
            info = await client.get_server_info()
            await client.query("First turn")
            before = await scripted_turn(client)
            await client.set_model("claude-sonnet-5-5")
            await client.set_permission_mode("plan")
            await client.query("Second turn")
            after = await scripted_turn(client)
            try:
                await client.get_mcp_status()
                unsupported = "accepted"
            except Exception as exc:
                unsupported = str(exc)
            same_owner = asyncio.current_task() is owner
    return {
        "server_info_keys": sorted(info or {}),
        "before": {"models": before["models"], "text": before["text"]},
        "after": {"models": after["models"], "text": after["text"]},
        "cli_permission_mode": cli.permission_mode,
        "control_requests": [
            m["request"]["subtype"] for m in cli.received if m["type"] == "control_request"
        ],
        "unsupported_request": unsupported,
        "context_owned_by_one_task": same_owner,
        "source": "real ClaudeSDKClient talking to a scripted CLI fixture",
    }


@exercise("client_lifecycle")
async def client_lifecycle(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    """Connect, run two turns in one session, disconnect, and refuse use after close."""
    from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, CLIConnectionError

    from agent_lab.scripted_cli import ScriptedCLI

    cli = ScriptedCLI([["Remembered: PYTHON-SESSION."], ["The label was PYTHON-SESSION."]])
    client = ClaudeSDKClient(ClaudeAgentOptions(), transport=cli)
    async with asyncio.timeout(20):
        async with client:
            await client.query("Remember PYTHON-SESSION.")
            first = await scripted_turn(client)
            await client.query("Which label?")
            second = await scripted_turn(client)
    try:
        await client.query("After disconnect")
        after_close = "accepted"
    except CLIConnectionError as exc:
        after_close = f"CLIConnectionError: {exc}"
    return {
        "turns": [first, second],
        "same_session": first["session_id"] == second["session_id"],
        "lifecycle": cli.lifecycle,
        "transport_ready_after_exit": cli.is_ready(),
        "query_after_disconnect": after_close,
        "source": "real ClaudeSDKClient talking to a scripted CLI fixture",
    }


@exercise("skills", "commands", "memory", "styles")
def project_markdown(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    return {
        "files": {
            p.relative_to(root).as_posix(): p.read_text(encoding="utf-8")
            for p in root.rglob("*.md")
        },
        "setting_sources": ["project"],
        "warning": "Only enable settings for a trusted lesson workspace.",
    }


@exercise("plugins")
def plugins(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    directory = root / "teaching-plugin"
    manifest = directory / ".claude-plugin" / "plugin.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        json.dumps(
            {
                "name": "python-teaching",
                "version": "1.0.0",
                "description": "Python teaching commands",
            }
        ),
        encoding="utf-8",
    )
    commands = directory / "commands"
    commands.mkdir(exist_ok=True)
    (commands / "explain.md").write_text(
        "Explain notes.txt with a Python example.\n", encoding="utf-8"
    )
    return {
        "manifest": json.loads(manifest.read_text()),
        "sdk_plugins": [{"type": "local", "path": str(directory)}],
    }


@exercise("streaming")
async def streaming(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    async def inputs():
        for text in [request.prompt or lesson.prompt, request.follow_up]:
            yield {
                "type": "user",
                "message": {"role": "user", "content": text},
                "parent_tool_use_id": None,
                "session_id": "default",
            }

    return {
        "input_messages": [message async for message in inputs()],
        "note": "Token output streaming is a separate include_partial_messages option.",
    }


def tool_text(result: Any) -> str:
    return "\n".join(getattr(block, "text", "") for block in result.content)


@exercise("mcp")
async def mcp_stdio(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    """Launch the notes server as a subprocess and talk to it over stdio, as the SDK does."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    command = [sys.executable, "-m", "agent_lab.integrations.notes_mcp"]
    parameters = StdioServerParameters(command=command[0], args=command[1:])
    async with asyncio.timeout(30):
        async with stdio_client(parameters) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                initialized = await session.initialize()
                tools = await session.list_tools()
                valid = await session.call_tool("read_note", {"name": "refunds"})
                invalid = await session.call_tool("read_note", {"name": "salaries"})
    return {
        "transport": "stdio",
        "server_command": command,
        "server": initialized.serverInfo.name,
        "tools": [
            {"name": item.name, "description": item.description, "input_schema": item.inputSchema}
            for item in tools.tools
        ],
        "valid_call": {
            "arguments": {"name": "refunds"},
            "is_error": valid.isError,
            "text": tool_text(valid),
        },
        "invalid_call": {
            "arguments": {"name": "salaries"},
            "is_error": invalid.isError,
            "text": tool_text(invalid),
        },
        "sdk_config": {"notes": {"type": "stdio", "command": command[0], "args": command[1:]}},
    }


class EmbeddedServer:
    """Uvicorn inside the running app; it must not take over the app's signal handlers."""

    def __init__(self, app: Any) -> None:
        import uvicorn

        class Quiet(uvicorn.Server):
            @contextlib.contextmanager
            def capture_signals(self) -> Any:
                yield

        self.server = Quiet(uvicorn.Config(app, log_level="warning", lifespan="on"))

    @contextlib.asynccontextmanager
    async def running(self) -> AsyncIterator[str]:
        import socket

        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        task = asyncio.create_task(self.server.serve(sockets=[listener]))
        try:
            async with asyncio.timeout(10):
                while not self.server.started:
                    if task.done():
                        task.result()
                    await asyncio.sleep(0.02)
            yield f"http://127.0.0.1:{port}"
        finally:
            self.server.should_exit = True
            await task
            listener.close()


@exercise("remote_mcp")
async def remote_mcp(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    """Serve MCP over streamable HTTP on loopback and inspect it with the remote client."""
    from agent_lab.integrations.notes_mcp import build_server
    from agent_lab.integrations.remote_mcp import inspect_remote

    async with EmbeddedServer(build_server().streamable_http_app()).running() as base:
        url = f"{base}/mcp"
        inspected = await inspect_remote(url)
    try:
        await inspect_remote("http://example.com/mcp")
        insecure = "accepted"
    except ValueError as exc:
        insecure = str(exc)
    return {
        "transport": "streamable HTTP",
        "url": url,
        "server": inspected["server"]["name"],
        "tools": [item["name"] for item in inspected["tools"]],
        "resources": [item["uri"] for item in inspected["resources"]],
        "difference": "Tools are actions the model calls with arguments; resources are "
        "addressable data the client reads by URI.",
        "insecure_url": insecure,
    }


@exercise("agent_mcp")
async def agent_mcp(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    """Call the agent-backed MCP tool end to end with live access forced off."""
    from mcp.shared.memory import create_connected_server_and_client_session

    from agent_lab.config import Settings
    from agent_lab.integrations.agent_mcp import build_server

    # Forced offline: this exercise must never start a paid run, whatever .env says.
    server = build_server(Settings(enable_live=False, data_dir=root / "agent-mcp"))
    async with asyncio.timeout(30):
        async with create_connected_server_and_client_session(server) as session:
            tools = await session.list_tools()
            result = await session.call_tool("explain_python_agent", {"prompt": "What is MCP?"})
    tool = tools.tools[0]
    return {
        "outer_client": "MCP ClientSession (in-memory transport)",
        "tool": {"name": tool.name, "input_schema": tool.inputSchema},
        "inner_agent": "RunService -> claude-agent-sdk live run of lesson 1",
        "call_is_error": result.isError,
        "call_result": tool_text(result),
        "live_gate": "The inner run refused to start because live access is disabled.",
    }


@exercise("budget")
def budget(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    ledger = Budget(limit=0.10)
    ledger.before_call()
    ledger.record(0.08)
    try:
        ledger.before_call(0.03)
    except ValueError as exc:
        rejected = str(exc)
    return {
        "fixture_cost_usd": ledger.spent,
        "next_call": rejected,
        "note": "SDK max_budget_usd is a threshold, not an exact billing guarantee.",
    }


@exercise("checkpoint")
def checkpoint(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    path = inside(root, "notes.txt")
    before = path.read_bytes()
    path.write_text("A host edit for the checkpoint exercise.\n", encoding="utf-8")
    changed = path.read_text(encoding="utf-8")
    path.write_bytes(before)
    return {"changed": changed, "restored": path.read_bytes() == before, "note": lesson.notes}


@exercise("compaction")
def compaction(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    """Bound one oversized tool result and summarize history before it fills the context."""
    limit = 600
    rows = [
        {"step": index, "status": "done", "details": "fixture detail " * 40} for index in range(8)
    ]
    raw = json.dumps(rows)
    marker = f"\n[truncated {len(raw) - limit} characters; ask for a specific step]"
    bounded = raw if len(raw) <= limit else raw[:limit] + marker
    summary = {"completed": [row["step"] for row in rows], "next": "verify"}
    return {
        "limit_characters": limit,
        "full_characters": len(raw),
        "bounded_characters": len(bounded),
        "bounded_within_limit": len(bounded) <= limit + len(marker),
        "truncation_marker": marker.strip(),
        "summary_characters": len(json.dumps(summary)),
        "summary": summary,
        "note": "Host bounding and summarizing; SDK compaction is a separate runtime behavior.",
    }


@exercise("background")
async def background(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    stopped = asyncio.Event()

    async def worker():
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    task = asyncio.create_task(worker())
    await asyncio.sleep(0)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    return {"cancelled": task.cancelled(), "cleanup_ran": stopped.is_set()}


@exercise("retry")
async def retry(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    """Retry transient failures with backoff inside a deadline, without repeating a write."""
    applied: dict[str, str] = {}  # idempotency key -> result: the host's write ledger
    attempts: list[dict[str, Any]] = []

    async def write_refund(key: str, attempt: int) -> str:
        if key not in applied:
            applied[key] = "refund A-100 for 500 cents"
        if attempt == 1:
            # The write succeeded, but its response was lost: the classic ambiguous failure.
            raise ConnectionError("Connection reset after the request was sent")
        if attempt == 2:
            raise TimeoutError("Upstream timed out")
        return applied[key]

    key = "refund-A-100-500"
    delays = [0.01, 0.02]
    result = None
    try:
        async with asyncio.timeout(2):
            for attempt in range(1, 4):
                try:
                    result = await write_refund(key, attempt)
                    attempts.append({"attempt": attempt, "outcome": "succeeded"})
                    break
                except (ConnectionError, TimeoutError) as exc:
                    attempts.append({"attempt": attempt, "outcome": type(exc).__name__})
                    if attempt == 3:
                        raise
                    await asyncio.sleep(delays[attempt - 1])
    except TimeoutError as exc:
        raise LessonError("The retry deadline expired before the write was confirmed.") from exc
    return {
        "deadline_seconds": 2,
        "backoff_seconds": delays,
        "attempts": attempts,
        "result": result,
        "idempotency_key": key,
        "writes_applied": len(applied),
        "duplicate_write_prevented": len(applied) == 1 and len(attempts) > 1,
    }


@exercise("images")
def images(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    # A real one-pixel PNG, not a fabricated model image response.
    data = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aS9sAAAAASUVORK5CYII="
    )
    (root / "pixel.png").write_bytes(data)
    return {
        "block": {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": base64.b64encode(data).decode(),
            },
        },
        "bytes": len(data),
        "note": lesson.notes,
    }


@exercise("todos", "suggestions")
def todos(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    """Validate todo transitions and derive the next suggestion from the resulting state."""
    allowed = {"pending": {"in_progress"}, "in_progress": {"completed", "pending"}}
    tasks = {"read": "pending", "verify": "pending", "release": "pending"}
    requested = [
        ("read", "in_progress"),
        ("read", "completed"),
        ("release", "completed"),  # skips in_progress
        ("verify", "in_progress"),
        ("release", "in_progress"),  # a second task in progress
        ("read", "pending"),  # reopens completed work
    ]
    transitions = []
    for task, target in requested:
        current = tasks[task]
        if target not in allowed.get(current, set()):
            reason = f"{current} cannot move to {target}"
        elif target == "in_progress" and "in_progress" in tasks.values():
            reason = "another task is already in progress"
        else:
            reason = ""
            tasks[task] = target
        transitions.append(
            {"task": task, "from": current, "to": target, "accepted": not reason, "reason": reason}
        )
    active = next((task for task, state in tasks.items() if state == "in_progress"), None)
    waiting = next((task for task, state in tasks.items() if state == "pending"), None)
    suggestion = (
        f"Finish {active} before starting another task."
        if active
        else f"Start {waiting}."
        if waiting
        else "All tasks are complete."
    )
    return {
        "transitions": transitions,
        "rejected": sum(not row["accepted"] for row in transitions),
        "tasks": [{"id": task, "status": state} for task, state in tasks.items()],
        "suggestion": suggestion,
        "source": "derived from validated host state",
    }


@exercise("questions")
def questions(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    return {
        "tool": "AskUserQuestion",
        "input": {
            "questions": [
                {
                    "question": "Which teaching style?",
                    "header": "Style",
                    "options": [
                        {"label": "Concise", "description": "One short example"},
                        {"label": "Detailed", "description": "Explain each step"},
                    ],
                    "multiSelect": False,
                }
            ]
        },
        "response": "The live UI requires a user's answer; offline mode supplies no answer.",
    }


@exercise("plan", "harness", "orchestration")
async def orchestration(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    plan = Plan(
        tasks=[
            TaskSpec(id="T1", files=["src/tags.py"]),
            TaskSpec(id="T2", files=["src/search.py"], depends_on=["T1"]),
            TaskSpec(id="T3", files=["src/report.py"], depends_on=["T1"]),
        ]
    )

    async def worker(task: TaskSpec):
        await asyncio.sleep(0)
        return {"owned_files": task.files, "verified": True, "source": "scripted host worker"}

    return {
        "plan": plan.model_dump(),
        "waves": plan.waves(),
        "results": await execute_plan(plan, worker),
    }


@exercise("store")
def store(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    target = root / "transcript.json"
    temporary = target.with_suffix(".tmp")
    rows = [{"role": "user", "text": request.prompt or lesson.prompt}]
    temporary.write_text(json.dumps(rows), encoding="utf-8")
    temporary.replace(target)
    return {
        "round_trip": json.loads(target.read_text(encoding="utf-8")),
        "atomic_replacement": True,
        "note": lesson.notes,
    }


@exercise("spawn")
async def spawn(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        "print('Python child process')",
        cwd=root,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        async with asyncio.timeout(10):
            stdout, _ = await process.communicate()
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()
    return {"stdout": stdout.decode().strip(), "exit_code": process.returncode, "shell": False}


@exercise("web")
def web(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    return {
        "tools": ["WebSearch", "WebFetch"],
        "evidence": {
            "url": "https://github.com/anthropics/claude-agent-sdk-python",
            "trust": "untrusted retrieved content",
        },
        "network_used": False,
        "live_note": "Live mode enables the SDK's web tools.",
    }


@exercise("telemetry")
def telemetry(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    with provider.get_tracer("agent-lab").start_as_current_span("lesson.host") as span:
        span.set_attribute("lesson.id", lesson.id)
        span.set_attribute("run.mode", "offline")
    spans = exporter.get_finished_spans()
    result = {
        "span": spans[0].name,
        "attributes": dict(spans[0].attributes or {}),
        "external_export": False,
    }
    provider.shutdown()
    return result


@exercise("providers")
def providers(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    selected = [
        name
        for name in ("CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY")
        if os.getenv(name) == "1"
    ]
    if len(selected) > 1:
        raise ValueError("Select only one cloud provider.")
    return {
        "selected": selected or ["direct Anthropic API"],
        "credentials": "not read or displayed",
        "notes": lesson.notes,
    }


@exercise("cache")
def cache(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    usage = {
        "input_tokens": 100,
        "cache_read_input_tokens": 900,
        "cache_creation_input_tokens": 0,
        "output_tokens": 50,
    }
    return {
        "source": "recorded usage fixture",
        "usage": usage,
        "cache_read_ratio": usage["cache_read_input_tokens"]
        / (usage["input_tokens"] + usage["cache_read_input_tokens"]),
    }


@exercise("ci")
async def ci(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    """Run the real CLI headlessly, as a CI job would, and record its exit codes."""
    env = os.environ | {
        "LAB_ENABLE_LIVE": "false",
        "ANTHROPIC_API_KEY": "",
        "LAB_DATA_DIR": str(root / "ci-data"),
    }
    runs = []
    for label, arguments in (
        ("passing lesson", ["lesson", "5"]),
        ("unknown lesson", ["lesson", "99"]),
    ):
        command = [sys.executable, "-m", "agent_lab", *arguments]
        process = await asyncio.create_subprocess_exec(
            *command,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            async with asyncio.timeout(60):
                stdout, stderr = await process.communicate()
        except TimeoutError:
            process.kill()
            await process.wait()
            raise
        lines = [json.loads(line) for line in stdout.decode().splitlines() if line.startswith("{")]
        runs.append(
            {
                "case": label,
                "command": "agent-lab " + " ".join(arguments),
                "exit_code": process.returncode,
                "json_events": len(lines),
                "final_status": lines[-1]["data"].get("status") if lines else None,
                "stderr_first_line": (stderr.decode().strip().splitlines() or [""])[-1][:160],
            }
        )
    return {
        "runs": runs,
        "ci_gate": "A job fails on any nonzero exit code.",
        "checks": ["uv run ruff check agent_lab tests", "uv run mypy agent_lab", "uv run pytest"],
        "network_api_needed": False,
    }


@exercise("database")
def database(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    orders = Orders(root / "orders.sqlite")
    try:
        alice = orders.list("alice")
        injected = orders.list("alice' OR 1=1 --")
        protected = orders.cancel("bob", "A-001", 1, approved=True)
        return {
            "alice": alice,
            "sql_injection_result": injected,
            "cross_tenant_update": protected,
            "mutations": "Only host-approved, version-checked updates are allowed.",
        }
    finally:
        orders.close()


@exercise("evals")
def evals(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    cases = [
        ("refunds requested", "refunds#1"),
        ("password reset links", "security#1"),
        ("lunar rover", None),
    ]
    rows: list[dict[str, Any]] = []
    for query, expected in cases:
        hits = retrieve(query)
        actual = hits[0]["id"] if hits else None
        rows.append(
            {"query": query, "expected": expected, "actual": actual, "passed": actual == expected}
        )
    return {
        "cases": rows,
        "pass_rate": sum(row["passed"] for row in rows) / len(rows),
        "baseline": 1.0,
    }


@exercise("debugging")
def debugging(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    return {
        "trace": redact(
            {
                "run_id": root.name,
                "request": {"api_key": "fixture-secret"},
                "events": [{"type": "started"}, {"type": "verified"}],
            }
        ),
        "raw_sdk_logs": "Never returned to the browser.",
    }


@exercise("board")
def board(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    messages = Board({"T1", "T2", "lead"})
    messages.send("T1", "T2", "normalize_tag(value: str) -> str is ready.")
    messages.send("T2", "lead", "Search imports the completed normalization function.")
    return {"messages": messages.messages, "host_bounds": {"per_sender": 6, "characters": 600}}


@exercise("worktrees")
async def worktrees(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    import shutil

    if not shutil.which("git"):
        raise LessonError("Install Git to run the worktree lesson.")
    repo = root / "repo"
    repo.mkdir(exist_ok=True)

    async def git(*args: str) -> str:
        process = await asyncio.create_subprocess_exec(
            "git",
            # Nested lesson workspaces can exceed the Windows 260-character path limit.
            "-c",
            "core.longpaths=true",
            "-C",
            str(repo),
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            async with asyncio.timeout(15):
                stdout, stderr = await process.communicate()
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()
        if process.returncode:
            raise LessonError(
                f"Git fixture operation failed: {stderr.decode(errors='replace')[:300]}"
            )
        return stdout.decode()

    await git("init", "-b", "main")
    await git(
        "-c",
        "user.name=Python Lab",
        "-c",
        "user.email=lab@example.invalid",
        "commit",
        "--allow-empty",
        "-m",
        "fixture",
    )
    for task in ("T1", "T2"):
        await git("worktree", "add", "-b", task, str(root / task))
    return {
        "worktrees": (await git("worktree", "list", "--porcelain")).splitlines(),
        "remote_operations": False,
    }


@exercise("tool_search")
def tool_search(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    catalog = [
        {"name": "orders.read", "description": "read customer orders"},
        {"name": "policy.search", "description": "search refund policy"},
        {"name": "sales.analyze", "description": "compute sales totals"},
    ]
    terms = set((request.prompt or "search refund policy").lower().split())
    matches = sorted(
        catalog, key=lambda item: len(terms & set(item["description"].split())), reverse=True
    )[:2]
    return {
        "catalog_size": len(catalog),
        "selected": matches,
        "note": "Host catalog selection is distinct from the SDK's native tool-search protocol.",
    }


@exercise("routing")
def routing(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    """Route each task to a model and limits with explicit, testable host rules."""
    from agent_lab.config import Settings

    settings = Settings()
    tiers = {
        "fast": {"model": settings.model, "max_turns": 2, "max_budget_usd": 0.05},
        "capable": {"model": settings.route_model, "max_turns": 6, "max_budget_usd": 0.25},
    }
    signals = ("refactor", "design", "debug", "architecture", "migrate", "security")
    tasks = [
        "Summarize notes.txt in one sentence.",
        "Debug why the retry loop repeats the refund write.",
        "Design the architecture for a multi-tenant agent service.",
    ]
    if request.prompt:
        tasks.append(request.prompt)
    routes = []
    for task in tasks:
        matched = [word for word in signals if word in task.lower()]
        tier = "capable" if matched or len(task) > 400 else "fast"
        routes.append(
            {
                "task": task[:120],
                "tier": tier,
                **tiers[tier],
                "reason": f"matched {', '.join(matched)}"
                if matched
                else "long input"
                if tier == "capable"
                else "short task with no complexity signal",
            }
        )
    return {
        "tiers": tiers,
        "routes": routes,
        "decision_owner": "host policy",
        "fallback": "No automatic repeated paid calls after failure.",
    }


@exercise("durable")
def durable(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    journal = Journal(root / "journal.jsonl")
    side_effects = []

    def run_steps():
        for step in ("prepare", "compute", "verify"):
            if step in journal.completed():
                continue
            side_effects.append(step)
            journal.append({"event": "completed", "step": step, "idempotency_key": step})

    run_steps()
    run_steps()
    return {
        "journal": journal.replay(),
        "effects": side_effects,
        "resume_duplicates": len(side_effects) != len(set(side_effects)),
        "note": "Use an external transactional outbox for side effects that must survive a crash between execution and journaling.",
    }


@exercise("retrieval")
def retrieval(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    return {
        "query": "refunds requested",
        "evidence": retrieve("refunds requested"),
        "unknown_topic": retrieve("lunar rover"),
        "citation_rule": "Cite the id of the evidence returned by the host tool.",
    }


@exercise("approval")
def approval(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    action = Refund(
        order_id="A-001", amount_cents=4200, reason="Fixture return approved by the host"
    )
    pending = Approval(action)
    pending.decide(pending.token, True)
    pending.consume(action)
    try:
        pending.consume(action)
    except ValueError:
        reuse_denied = True
    return {
        "action": action.model_dump(),
        "fingerprint": pending.fingerprint,
        "state": pending.state,
        "reuse_denied": reuse_denied,
        "delivery": "local fixture, no external notification",
    }


@exercise("websocket")
async def websocket(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    """Serve the real WebSocket endpoint on loopback and drive it as a browser would."""
    from websockets.asyncio.client import connect
    from websockets.exceptions import ConnectionClosed

    from agent_lab.api import create_app
    from agent_lab.config import Settings
    from agent_lab.runtime import RunService

    inner = RunService(Settings(enable_live=False, data_dir=root / "ws-runs"))
    app = create_app(inner, with_ui=False)
    async with EmbeddedServer(app).running() as base:
        endpoint = base.replace("http", "ws") + "/api/lessons/5/ws"
        async with asyncio.timeout(30):
            async with connect(endpoint) as socket:
                await socket.send(json.dumps({"mode": "offline"}))
                kinds = []
                async for raw in socket:
                    event = json.loads(raw)
                    kinds.append(event["kind"])
                    if event["kind"] == "done":
                        final_status = event["data"]["status"]
                        break
            async with connect(endpoint) as socket:
                await socket.send(json.dumps({"mode": "offline", "cwd": "outside"}))
                try:
                    await socket.recv()
                    invalid_close = None
                except ConnectionClosed as exc:
                    invalid_close = exc.rcvd.code if exc.rcvd else None
            async with connect(base.replace("http", "ws") + "/api/lessons/57/ws") as socket:
                await socket.send(json.dumps({"mode": "offline"}))
                await socket.recv()  # started, then the browser goes away mid-run
            for _ in range(250):
                if not inner.active:
                    break
                await asyncio.sleep(0.02)
    await inner.close()
    return {
        "endpoint": "/api/lessons/{lesson_id}/ws",
        "server_events": kinds,
        "final_status": final_status,
        "invalid_request_close_code": invalid_close,
        "owned_runs_after_disconnect": len(inner.active),
        "disconnect": "Closing the socket cancels and awaits the owned run.",
    }


@exercise("support")
def support(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    """Bind tools to the signed-in customer and require an exact approval before a refund."""
    customer = "alice"  # chosen by the host session, never by tool arguments
    orders = Orders(root / "orders.sqlite")
    try:
        visible = orders.list(customer)
    finally:
        orders.close()
    proposal = Refund(order_id="A-001", amount_cents=4200, reason="Damaged on arrival")
    steps: list[dict[str, Any]] = []
    approval = Approval(proposal)
    try:
        approval.consume(proposal)
    except ValueError as exc:
        steps.append({"step": "refund before approval", "outcome": str(exc)})
    try:
        approval.decide("guessed-token", True)
    except PermissionError as exc:
        steps.append({"step": "approve with a wrong credential", "outcome": str(exc)})
    approval.decide(approval.token, True)
    steps.append({"step": "staff approves", "outcome": approval.state})
    larger = proposal.model_copy(update={"amount_cents": 9000})
    try:
        approval.consume(larger)
    except ValueError as exc:
        steps.append({"step": "refund a different amount", "outcome": str(exc)})
    approval.consume(proposal)
    steps.append({"step": "refund the approved action", "outcome": approval.state})
    return {
        "customer": customer,
        "visible_orders": visible,
        "proposal": proposal.model_dump(),
        "approval_steps": steps,
        "refunds_executed": 1,
        "final_state": approval.state,
    }


@exercise("tenancy")
def tenancy(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    """Every query runs with the tenant from host state; tool arguments cannot change it."""
    orders = Orders(root / "orders.sqlite")
    try:
        sessions = {"session-alice": "alice", "session-bob": "bob"}

        def list_orders(session_id: str, arguments: dict[str, Any]) -> list[dict[str, Any]]:
            # A model-supplied tenant is ignored: the tool schema has no tenant field.
            return orders.list(sessions[session_id], arguments.get("status", "all"))

        checks: list[dict[str, Any]] = [
            {
                "check": "alice sees her orders",
                "result": [r["id"] for r in list_orders("session-alice", {})],
            },
            {
                "check": "bob sees his orders",
                "result": [r["id"] for r in list_orders("session-bob", {})],
            },
            {
                "check": "alice passes tenant=bob",
                "result": [r["id"] for r in list_orders("session-alice", {"tenant": "bob"})],
            },
            {"check": "injection in tenant", "result": orders.list("alice' OR 1=1 --")},
            {
                "check": "bob cancels alice's order",
                "result": orders.cancel("bob", "A-001", 1, approved=True),
            },
            {
                "check": "alice cancels with a stale version",
                "result": orders.cancel("alice", "A-001", 7, approved=True),
            },
            {
                "check": "alice cancels her current order",
                "result": orders.cancel("alice", "A-001", 1, approved=True),
            },
        ]
    finally:
        orders.close()
    return {
        "tenant_source": "host session table",
        "checks": checks,
        "cross_tenant_rows": 0
        if checks[2]["result"] == ["A-001"] and not checks[3]["result"]
        else 1,
        "cross_tenant_update": checks[4]["result"],
    }


@exercise("scheduled")
async def scheduled(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    """Process each trigger id once and await in-flight jobs before shutting down."""
    journal = Journal(root / "triggers.jsonl")
    deliveries = ["evt-1", "evt-2", "evt-1", "evt-3", "evt-2"]  # at-least-once delivery
    accepted, duplicates = [], []
    tasks: set[asyncio.Task[str]] = set()

    async def job(trigger: str) -> str:
        await asyncio.sleep(0.05)
        journal.append({"event": "completed", "step": trigger})
        return trigger

    for trigger in deliveries:
        seen = {row["step"] for row in journal.replay() if row.get("event") == "received"}
        if trigger in seen:
            duplicates.append(trigger)
            continue
        journal.append({"event": "received", "step": trigger})
        accepted.append(trigger)
        tasks.add(asyncio.create_task(job(trigger)))
    in_flight = sum(not task.done() for task in tasks)
    # Graceful shutdown: stop accepting work, then await owned tasks within a deadline.
    async with asyncio.timeout(5):
        finished = await asyncio.gather(*tasks)
    return {
        "deliveries": deliveries,
        "accepted": accepted,
        "duplicates_ignored": duplicates,
        "in_flight_at_shutdown": in_flight,
        "completed_before_exit": sorted(finished),
        "journal": journal.replay(),
    }


@exercise("settings")
def settings_isolation(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    """Show which runs load project settings and that every run gets its own CLI config."""
    from agent_lab.sdk import isolated_env, setting_sources_for

    hostile = root / ".claude" / "settings.json"
    hostile.parent.mkdir(parents=True, exist_ok=True)
    hostile.write_text(json.dumps({"permissions": {"allow": ["Bash(*)"]}}), encoding="utf-8")
    profiles = ["read", "hooks", "calculator", "skills", "commands", "memory", "styles"]
    run_a = isolated_env(root.parent / "config")
    run_b = isolated_env(root.parent.parent / "another-run" / "config")
    return {
        "workspace_settings_file": {"path": ".claude/settings.json", "content": "allows Bash(*)"},
        "this_lesson": {
            "profile": lesson.live_profile,
            "setting_sources": setting_sources_for(lesson.live_profile),
        },
        "profiles": [
            {"profile": name, "setting_sources": setting_sources_for(name)} for name in profiles
        ],
        "user_settings_ever_loaded": any("user" in setting_sources_for(name) for name in profiles),
        "run_env": run_a,
        "config_dirs_differ": run_a["CLAUDE_CONFIG_DIR"] != run_b["CLAUDE_CONFIG_DIR"],
    }


FIXTURE_SESSION_ID = "00000000-0000-4000-8000-000000000019"


def write_fixture_session(config: Path) -> str:
    """One transcript in the CLI's JSONL format, inside an isolated config directory."""
    folder = config / "projects" / "lesson-workspace"
    folder.mkdir(parents=True, exist_ok=True)
    common = {"sessionId": FIXTURE_SESSION_ID, "cwd": "lesson-workspace"}
    rows = [
        {
            "type": "user",
            "uuid": "00000000-0000-4000-8000-000000000001",
            "parentUuid": None,
            "timestamp": "2026-10-28T10:00:00.000Z",
            "message": {"role": "user", "content": "Remember PYTHON-SESSION."},
            **common,
        },
        {
            "type": "assistant",
            "uuid": "00000000-0000-4000-8000-000000000002",
            "parentUuid": "00000000-0000-4000-8000-000000000001",
            "timestamp": "2026-10-28T10:00:01.000Z",
            "message": {
                "role": "assistant",
                "model": "claude-haiku-4-5",
                "content": [{"type": "text", "text": "Remembered: PYTHON-SESSION."}],
            },
            **common,
        },
    ]
    path = folder / f"{FIXTURE_SESSION_ID}.jsonl"
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    return FIXTURE_SESSION_ID


SESSION_PROBE = """
import dataclasses, json, sys
from claude_agent_sdk import get_session_info, get_session_messages, list_sessions
sessions = list_sessions()
messages = get_session_messages(sys.argv[1]) if sessions else []
info = get_session_info(sys.argv[1])
print(json.dumps({
    "sessions": [dataclasses.asdict(item) for item in sessions],
    "messages": [dataclasses.asdict(item) for item in messages],
    "info_found": info is not None,
}, default=str))
"""


async def probe_sessions(config: Path, session_id: str) -> dict[str, Any]:
    """The session API reads CLAUDE_CONFIG_DIR from the environment, so probe in a child."""
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-I",
        "-c",
        SESSION_PROBE,
        session_id,
        env=os.environ | {"CLAUDE_CONFIG_DIR": str(config)},
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    async with asyncio.timeout(30):
        stdout, stderr = await process.communicate()
    if process.returncode:
        raise LessonError("The session probe failed: " + stderr.decode()[-300:])
    return json.loads(stdout)


def message_text(message: dict[str, Any]) -> str:
    content = message["message"]["content"]
    if isinstance(content, str):
        return content
    return " ".join(block.get("text", "") for block in content if isinstance(block, dict))


@exercise("session_management")
async def session_management(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    """Call list_sessions and get_session_messages against an isolated config directory."""
    config = root / "isolated-config"
    session_id = write_fixture_session(config)
    probe = await probe_sessions(config, session_id)
    return {
        "config_dir": "isolated-config (this run only; your own transcripts are never read)",
        "sessions": [
            {key: row[key] for key in ("session_id", "summary", "first_prompt", "cwd")}
            for row in probe["sessions"]
        ],
        "messages": [{"type": row["type"], "text": message_text(row)} for row in probe["messages"]],
        "info_found": probe["info_found"],
        "source": "official session functions reading a fixture transcript",
    }


@exercise("resume")
async def resume(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    """Resume needs the SDK's own transcript in the same config dir; host files do not count."""
    from claude_agent_sdk import ClaudeAgentOptions

    config = root / "isolated-config"
    session_id = write_fixture_session(config)
    # A host transcript is application data: the SDK neither lists nor resumes it.
    (root / "host-transcript.json").write_text(
        json.dumps([{"role": "user", "content": "Remember HOST-ONLY."}]), encoding="utf-8"
    )
    same_dir = await probe_sessions(config, session_id)
    other_dir = await probe_sessions(root / "empty-config", session_id)
    variants = {
        "continue this session": ClaudeAgentOptions(resume=session_id),
        "branch into a new session": ClaudeAgentOptions(resume=session_id, fork_session=True),
        "most recent session": ClaudeAgentOptions(continue_conversation=True),
    }
    return {
        "resume_options": [
            {
                "goal": goal,
                "resume": options.resume,
                "fork_session": options.fork_session,
                "continue_conversation": options.continue_conversation,
            }
            for goal, options in variants.items()
        ],
        "sdk_sessions_in_run_config": [row["session_id"] for row in same_dir["sessions"]],
        "host_transcript_listed": any(
            "HOST-ONLY" in (row.get("first_prompt") or "") for row in same_dir["sessions"]
        ),
        "sessions_in_another_config_dir": len(other_dir["sessions"]),
        "rule": "Resume with the same CLAUDE_CONFIG_DIR that recorded the session.",
    }


@exercise("elicitation")
async def elicitation(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    """An MCP tool asks the user for structured input; each response type changes the outcome."""
    import claude_agent_sdk as sdk
    from mcp import types
    from mcp.server.fastmcp import Context, FastMCP
    from mcp.shared.memory import create_connected_server_and_client_session
    from pydantic import BaseModel

    class Confirmation(BaseModel):
        confirm: bool
        reason: str = ""

    def build() -> FastMCP:
        server = FastMCP("drafts")

        @server.tool()
        async def delete_draft(name: str, ctx: Context) -> str:
            """Delete a draft after the user confirms."""
            answer = await ctx.elicit(f"Delete the draft {name}?", schema=Confirmation)
            if answer.action == "accept":
                return f"Deleted {name}." if answer.data.confirm else "Kept: not confirmed."
            return f"Not deleted: the user chose {answer.action}."

        return server

    responses: dict[str, types.ElicitResult] = {
        "accept": types.ElicitResult(action="accept", content={"confirm": True}),
        "decline": types.ElicitResult(action="decline"),
        "cancel": types.ElicitResult(action="cancel"),
        "accept with invalid data": types.ElicitResult(
            action="accept", content={"confirm": "maybe"}
        ),
    }
    outcomes = []
    for label, response in responses.items():
        prompts: list[str] = []

        async def answer(
            context: Any,
            params: Any,
            response: types.ElicitResult = response,
            prompts: list[str] = prompts,
        ) -> types.ElicitResult:
            prompts.append(params.message)
            return response

        async with asyncio.timeout(20):
            async with create_connected_server_and_client_session(
                build(), elicitation_callback=answer
            ) as session:
                result = await session.call_tool("delete_draft", {"name": "q3-plan"})
        outcomes.append(
            {
                "response": label,
                "asked": prompts[0] if prompts else "",
                "is_error": result.isError,
                "tool_result": tool_text(result)[:160],
            }
        )
    return {
        "outcomes": outcomes,
        "python_sdk_on_elicitation": "on_elicitation"
        in {field.name for field in dataclasses.fields(sdk.ClaudeAgentOptions)},
        "note": "MCP elicitation runs between an MCP client and server. This installed Python "
        "Agent SDK does not expose an on_elicitation option, so the lab uses the MCP client.",
    }


@exercise("upgrade")
def upgrade(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    """Compare the declared pin, the lockfile and the installed SDK, then gate on interfaces."""
    import tomllib

    import claude_agent_sdk as sdk

    from agent_lab.config import ROOT

    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    pin = next(
        item for item in project["project"]["dependencies"] if item.startswith("claude-agent-sdk")
    )
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    locked = next(item["version"] for item in lock["package"] if item["name"] == "claude-agent-sdk")
    installed = importlib.metadata.version("claude-agent-sdk")
    required = [
        "query",
        "tool",
        "create_sdk_mcp_server",
        "ClaudeAgentOptions",
        "ClaudeSDKClient",
        "HookMatcher",
        "PermissionResultAllow",
        "PermissionResultDeny",
        "Transport",
        "list_sessions",
    ]
    methods = ["connect", "query", "receive_response", "interrupt", "set_model", "disconnect"]
    missing = [name for name in required if not hasattr(sdk, name)]
    missing += [
        f"ClaudeSDKClient.{name}" for name in methods if not hasattr(sdk.ClaudeSDKClient, name)
    ]
    # A candidate release that dropped one method the app uses must be blocked.
    candidate_missing = ["ClaudeSDKClient.interrupt"]
    return {
        "declared_pin": pin,
        "locked_version": locked,
        "installed_version": installed,
        "pin_lock_install_match": pin.endswith(f"=={locked}") and locked == installed,
        "required_interfaces": len(required) + len(methods),
        "missing_interfaces": missing,
        "current_gate": "pass" if not missing else "blocked",
        "simulated_candidate": {"missing": candidate_missing, "gate": "blocked"},
        "reproducible_install": "uv sync --locked",
    }


@exercise("browser")
async def browser(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    """Inspect the browser MCP service's single tool and the origin rule it enforces."""
    from agent_lab.integrations import browser_mcp

    tools = await browser_mcp.mcp.list_tools()
    origin = browser_mcp.teaching_origin()
    candidates = [
        origin + "/?lesson=1",
        origin.replace("127.0.0.1", "localhost"),
        "http://127.0.0.1:9999/",
        "http://127.0.0.1.evil.example/",
        "file:///C:/Windows/win.ini",
    ]
    return {
        "server": browser_mcp.mcp.name,
        "tools": [{"name": item.name, "input_schema": item.inputSchema} for item in tools],
        "teaching_origin": origin,
        "origin_checks": [
            {"url": url, "allowed": browser_mcp.same_origin(url, origin)} for url in candidates
        ],
        "versus_shell": "The agent can only ask for a page at one origin; it cannot run "
        "commands, read files or reach other hosts. A shell tool would allow all of that.",
        "browser_launched": False,
        "start_service": "uv sync --locked --extra browser && uv run playwright install chromium",
    }


@exercise("desktop")
def desktop(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    """The native window and the browser use the same FastAPI app and lesson service."""
    from importlib.util import find_spec

    from agent_lab.api import create_app
    from agent_lab.config import Settings
    from agent_lab.runtime import RunService

    service = RunService(Settings(enable_live=False, data_dir=root / "desktop-runs"))
    app = create_app(service, with_ui=False)
    paths = {str(getattr(route, "path", "")) for route in app.routes}
    routes = sorted(path for path in paths if path.startswith("/api"))
    return {
        "browser_command": "uv run agent-lab serve",
        "native_command": "uv run agent-lab serve --native",
        "native_window_available": find_spec("webview") is not None,
        "install_native": "uv sync --locked --extra desktop",
        "shared_service": type(app.state.runner).__name__,
        "shared_api_routes": routes,
        "notes": lesson.notes,
    }


@exercise("analysis")
def analysis(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    rows = list(csv.DictReader(io.StringIO((root / "sales.csv").read_text(encoding="utf-8"))))
    totals: dict[str, int] = {}
    for row in rows:
        totals[row["region"]] = totals.get(row["region"], 0) + int(row["amount"])
    return {
        "rows": len(rows),
        "totals": totals,
        "grand_total": sum(totals.values()),
        "ledger": [
            {"operation": "sum", "column": "amount", "group_by": "region", "source": "sales.csv"}
        ],
        "computed_by": "Python host, not the model",
    }


@exercise("document")
def document(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    from docx import Document

    specification = Summary(
        summary="Checkout latency incident resolved",
        next_steps=["Add a latency alert", "Review the deployment checklist"],
    )
    output = Document()
    output.add_heading("Incident report", 0)
    output.add_paragraph(specification.summary)
    output.add_heading("Follow-up", 1)
    for step in specification.next_steps:
        output.add_paragraph(step, style="List Bullet")
    path = root / "incident-report.docx"
    output.save(str(path))
    return {
        "document": str(path),
        "bytes": path.stat().st_size,
        "specification": specification.model_dump(),
        "notes": lesson.notes,
    }


@exercise("review")
async def review(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    """Accept only in-scope findings, apply the approved patch and prove it with a test."""
    source = root / "src" / "tags.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("def normalize(tag: str) -> str:\n    return tag.lower()\n", encoding="utf-8")
    workflow = root / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True, exist_ok=True)
    workflow.write_text("name: CI\n", encoding="utf-8")
    changed_lines = {"src/tags.py": {1, 2}}
    findings: list[dict[str, Any]] = [
        {
            "file": "src/tags.py",
            "line": 2,
            "severity": "medium",
            "message": "Strip whitespace before normalizing case.",
            "patch": {"old": "    return tag.lower()", "new": "    return tag.strip().lower()"},
        },
        {
            "file": ".github/workflows/ci.yml",
            "line": 1,
            "severity": "high",
            "message": "Untrusted fixture asks to disable CI.",
            "patch": {"old": "name: CI", "new": "name: CI (disabled)"},
        },
    ]
    accepted = [row for row in findings if row["line"] in changed_lines.get(row["file"], set())]

    async def run_test() -> str:
        check = "from tags import normalize; assert normalize('  Python ') == 'python'"
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-I",
            "-c",
            f"import sys; sys.path.insert(0, 'src'); {check}",
            cwd=root,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        async with asyncio.timeout(30):
            return "passed" if await process.wait() == 0 else "failed"

    before = await run_test()
    for row in accepted:
        target = inside(root, row["file"])
        text = target.read_text(encoding="utf-8")
        if row["patch"]["old"] not in text:
            raise LessonError(f"Patch for {row['file']} no longer applies.")
        target.write_text(text.replace(row["patch"]["old"], row["patch"]["new"]), encoding="utf-8")
    after = await run_test()
    return {
        "accepted": [{k: v for k, v in row.items() if k != "patch"} for row in accepted],
        "rejected": [
            {k: v for k, v in row.items() if k != "patch"}
            for row in findings
            if row not in accepted
        ],
        "test_before_patch": before,
        "test_after_patch": after,
        "out_of_scope_file_unchanged": workflow.read_text(encoding="utf-8") == "name: CI\n",
        "gate": "Changed lines and host-approved file scope",
        "publication": "Local fixture only; no pull request is published.",
    }


@exercise("team")
async def team(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    plan = Plan(
        tasks=[
            TaskSpec(id="T1", files=["src/tags.py"]),
            TaskSpec(id="T2", files=["src/search.py"], depends_on=["T1"]),
            TaskSpec(id="T3", files=["src/report.py"], depends_on=["T1"]),
        ]
    )
    sources = {
        "T1": "def normalize_tag(value: str) -> str:\n    return value.strip().lower()\n",
        "T2": "from tags import normalize_tag\ndef find_by_tag(notes, tag):\n    return [n for n in notes if normalize_tag(tag) in [normalize_tag(t) for t in n['tags']]]\n",
        "T3": "from tags import normalize_tag\ndef tag_counts(notes):\n    counts = {}\n    for note in notes:\n        for tag in set(map(normalize_tag, note['tags'])):\n            counts[tag] = counts.get(tag, 0) + 1\n    return counts\n",
    }
    board = Board({"T1", "T2", "T3", "lead"})
    journal = Journal(root / "team.jsonl")

    async def developer(task: TaskSpec):
        path = inside(root, task.files[0])
        path.parent.mkdir(exist_ok=True)
        code = sources[task.id]
        compile(code, str(path), "exec")
        path.write_text(code, encoding="utf-8")
        board.send(task.id, "lead", f"Compiled {task.files[0]}")
        journal.append({"event": "completed", "step": task.id, "file": task.files[0]})
        return {"file": task.files[0], "compiled": True}

    results = await execute_plan(plan, developer)
    probe = "from tags import normalize_tag\nfrom search import find_by_tag\nfrom report import tag_counts\nnotes=[{'tags':[' Python ','python','AI']}]\nassert normalize_tag(' PYTHON ') == 'python'\nassert len(find_by_tag(notes, 'python')) == 1\nassert tag_counts(notes) == {'python':1, 'ai':1}\nprint('3 acceptance checks passed')\n"
    (root / "src" / "acceptance.py").write_text(probe, encoding="utf-8")
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-I",
        "-c",
        "import sys; sys.path.insert(0, '.'); exec(open('acceptance.py').read())",
        cwd=root / "src",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        async with asyncio.timeout(15):
            stdout, _ = await process.communicate()
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()
    return {
        "plan": plan.model_dump(),
        "waves": plan.waves(),
        "workers": "scripted Python fixtures",
        "results": results,
        "messages": board.messages,
        "journal": journal.replay(),
        "release_gate": process.returncode == 0,
        "acceptance": stdout.decode().strip(),
        "published": False,
    }


def exercise_source(name: str) -> str:
    """The host exercise shown in the Python source tab."""
    return inspect.getsource(EXERCISES[name])


def exercise_context(name: str) -> str:
    """The exercise plus the host classes it names, so the tutor never has to guess them."""
    import re

    import agent_lab.models as models
    import agent_lab.services as services

    source = exercise_source(name)
    body = source[source.index(") -> ") :]  # every signature names Lesson and RunRequest
    blocks = []
    for identifier in sorted(set(re.findall(r"\b[A-Z][A-Za-z]+\b", body))):
        for module in (services, models):
            value = getattr(module, identifier, None)
            if inspect.isclass(value) and value.__module__ == module.__name__:
                path = module.__name__.replace(".", "/")
                blocks.append(f"\n\n# {path}.py\n{inspect.getsource(value)}")
    return source + "".join(blocks)


async def run_exercise(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    function = EXERCISES[lesson.exercise]
    result = function(root, request, lesson)
    if inspect.isawaitable(result):
        result = await result
    return result
