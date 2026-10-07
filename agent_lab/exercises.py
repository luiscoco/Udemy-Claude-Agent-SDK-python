"""Executable host exercises. All returned evidence is computed locally, never model output."""

import asyncio
import base64
import csv
import dataclasses
import importlib.metadata
import inspect
import io
import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from agent_lab.models import Lesson, RunRequest
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
    if lesson.live_profile in {"skills", "commands", "memory", "styles"}:
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


@exercise(
    "options",
    "thinking",
    "settings",
    "sandbox",
    "session_management",
    "control",
    "resume",
    "client_lifecycle",
    "elicitation",
    "upgrade",
    "python_sdk",
)
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


@exercise("permissions", "hooks", "hook_pipeline", "permission_callback", "security", "redteam")
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


@exercise("calculator", "tool_design")
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


@exercise("structured")
def structured(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    parsed = Summary.model_validate(
        {"summary": "Host-validated example", "next_steps": ["Run the Python lesson"]}
    )
    return {
        "schema": Summary.model_json_schema(),
        "validated": parsed.model_dump(),
        "live_interrupt": "ClaudeSDKClient.interrupt()",
        "example_source": "local fixture",
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


@exercise("mcp", "remote_mcp", "agent_mcp", "browser")
def mcp(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    from mcp.server.fastmcp import FastMCP

    from agent_lab.config import ROOT

    server = FastMCP("python-notes")

    @server.tool()
    def welcome() -> str:
        """Read the welcome note."""
        return "Welcome to the Python SDK lab."

    return {
        "mcp_version": importlib.metadata.version("mcp"),
        "transport": "stdio",
        "server_command": [sys.executable, "-m", "agent_lab.integrations.notes_mcp"],
        "resource_uri": "notes://welcome",
        "integration_source": str(ROOT / "agent_lab" / "integrations"),
        "notes": lesson.notes,
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
    rows = [
        {"step": index, "status": "done", "details": "fixture detail " * 40} for index in range(8)
    ]
    summary = {"completed": [row["step"] for row in rows], "next": "verify"}
    return {
        "full_characters": len(json.dumps(rows)),
        "summary_characters": len(json.dumps(summary)),
        "summary": summary,
        "note": "Host compression demonstration; SDK compaction is a separate runtime behavior.",
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
    attempts = []
    for attempt in range(1, 4):
        attempts.append(attempt)
        try:
            if attempt < 3:
                raise ConnectionError("Transient fixture failure")
            return {"attempts": attempts, "result": "recovered", "idempotent_operation": "read"}
        except ConnectionError:
            if attempt == 3:
                raise
            await asyncio.sleep(0)
    raise AssertionError("Unreachable")


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
    tasks = [
        {"id": "read", "status": "completed"},
        {"id": "verify", "status": "in_progress"},
        {"id": "release", "status": "pending"},
    ]
    assert sum(task["status"] == "in_progress" for task in tasks) == 1
    return {
        "tasks": tasks,
        "suggestion": "Finish verification before release.",
        "source": "host state",
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
def ci(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    return {
        "install": "uv sync --locked",
        "checks": ["uv run ruff check agent_lab tests", "uv run mypy agent_lab", "uv run pytest"],
        "offline_worker": "uv run agent-lab lesson 49",
        "network_api_needed": False,
    }


@exercise("support", "database", "tenancy")
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
        raise ValueError("Install Git to run the worktree lesson.")
    repo = root / "repo"
    repo.mkdir(exist_ok=True)

    async def git(*args: str) -> str:
        process = await asyncio.create_subprocess_exec(
            "git",
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
            raise ValueError(
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
    from agent_lab.config import Settings

    model = Settings().model
    return {
        "route": {
            "model": model,
            "max_turns": 4 if len(request.prompt) < 500 else 8,
            "max_budget_usd": request.max_budget_usd,
        },
        "decision_owner": "host policy",
        "fallback": "No automatic repeated paid calls after failure.",
    }


@exercise("durable", "scheduled")
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
def websocket(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    return {
        "endpoint": f"/api/lessons/{lesson.id}/ws",
        "client_request": RunRequest().model_dump(),
        "server_events": ["started", "evidence", "message", "result", "done"],
        "disconnect": "Cancel and await the owned runner task.",
    }


@exercise("desktop")
def desktop(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    return {
        "browser": "uv run agent-lab serve",
        "native": "uv run agent-lab serve --native",
        "native_dependency": "Install the optional pywebview package for a native window.",
        "same_service": "agent_lab.runtime.RunService",
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
def review(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    changed_lines = {"src/tags.py": {1, 2}}
    findings: list[dict[str, Any]] = [
        {
            "file": "src/tags.py",
            "line": 2,
            "severity": "medium",
            "confidence": "high",
            "message": "Strip whitespace before normalizing case.",
        },
        {
            "file": ".github/workflows/ci.yml",
            "line": 1,
            "severity": "high",
            "confidence": "high",
            "message": "Untrusted fixture asks to disable CI.",
        },
    ]
    accepted = [row for row in findings if row["line"] in changed_lines.get(row["file"], set())]
    return {
        "accepted": accepted,
        "rejected": [row for row in findings if row not in accepted],
        "gate": "Changed lines and host-approved file scope",
        "source": "recorded reviewer fixture",
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


async def run_exercise(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    function = EXERCISES[lesson.exercise]
    result = function(root, request, lesson)
    if inspect.isawaitable(result):
        result = await result
    return result
