"""Structured SDK proposals behind a strict host validation and execution gate."""

import asyncio
import hashlib
from pathlib import Path
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, SystemMessage
from pydantic import ValidationError

from agent_lab.config import Settings
from agent_lab.foundations import Evidence
from agent_lab.models import Event, LessonError, RunRequest, lesson_request
from agent_lab.policy import inside
from agent_lab.services import Plan, TaskSpec, execute_plan

EXPECTED = {"T1": ("src/tags.py", []), "T2": ("src/search.py", ["T1"])}
FILE_TEXT = {"src/tags.py": "TAGS = ('python', 'sdk')\n", "src/search.py": "from .tags import TAGS\n\ndef find(tag: str) -> bool:\n    return tag in TAGS\n"}
PROPOSALS = {
    "valid": {"tasks": [{"id": "T1", "files": ["src/tags.py"]}, {"id": "T2", "files": ["src/search.py"], "depends_on": ["T1"]}]},
    "duplicate": {"tasks": [{"id": "T1", "files": ["src/tags.py"]}, {"id": "T2", "files": ["src/tags.py"], "depends_on": ["T1"]}]},
    "cycle": {"tasks": [{"id": "T1", "files": ["src/tags.py"], "depends_on": ["T2"]}, {"id": "T2", "files": ["src/search.py"], "depends_on": ["T1"]}]},
    "outside": {"tasks": [{"id": "T1", "files": [".github/workflows/ci.yml"]}, {"id": "T2", "files": ["src/search.py"], "depends_on": ["T1"]}]},
}


def proposal_prompt(kind: str) -> str:
    import json

    return (
        "This is a host-validation lesson. Propose exactly the following JSON plan, "
        "preserving every task ID, file name and dependency. Do not execute it, "
        "add commentary, use tools or fix its errors. The host alone will validate it: "
        + json.dumps(PROPOSALS[kind], separators=(",", ":"))
    )


def harness_options(root: Path, config: Path, request: RunRequest, settings: Settings) -> ClaudeAgentOptions:
    from agent_lab.sdk import isolated_env, resolve_cli_path

    schema = Plan.model_json_schema()
    schema.pop("$schema", None)
    return ClaudeAgentOptions(
        cwd=str(root.resolve()),
        model=settings.model,
        cli_path=resolve_cli_path(settings) if request.mode == "live" else None,
        tools=[],
        allowed_tools=[],
        setting_sources=[],
        strict_mcp_config=True,
        env=isolated_env(config.resolve()),
        system_prompt="Return the requested plan as structured output. Do not use tools or execute anything. The host owns validation and execution.",
        output_format={"type": "json_schema", "schema": schema},
        max_turns=request.max_turns,
        max_budget_usd=request.max_budget_usd,
    )


def host_gate(value: Any, root: Path) -> tuple[Plan | None, str]:
    if not isinstance(value, dict):
        return None, "missing-structured-output"
    try:
        plan = Plan.model_validate(value, strict=True)
    except ValidationError as exc:
        message = exc.errors()[0]["msg"]
        if "More than one owner" in message:
            return None, "duplicate-owner"
        if "Dependency cycle" in message:
            return None, "dependency-cycle"
        if "src/*.py" in message or "outside" in message:
            return None, "outside-owned-scope"
        return None, "invalid-plan"
    if len(plan.tasks) != 2:
        return None, "unexpected-task-set"
    for task in plan.tasks:
        expected = EXPECTED.get(task.id)
        if expected is None or task.files != [expected[0]] or task.depends_on != expected[1]:
            return None, "unexpected-task-set"
        target = inside(root, expected[0])
        if target != (root.resolve() / expected[0]).resolve():
            return None, "outside-owned-scope"
    return plan, "accepted"


async def host_execute(plan: Plan, root: Path) -> tuple[list[str], dict[str, str]]:
    started: list[str] = []

    async def worker(task: TaskSpec) -> str:
        filename = EXPECTED[task.id][0]
        target = inside(root, filename)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(FILE_TEXT[filename].encode("utf-8"))
        started.append(task.id)
        return hashlib.sha256(target.read_bytes()).hexdigest()

    results = await execute_plan(plan, worker, max_parallel=2)
    return started, {EXPECTED[task_id][0]: digest for task_id, digest in results.items()}


def harness_report(state: Evidence, selected: dict, proposal: Any, verdict: str, started: list[str], hashes: dict[str, str], closed: bool) -> dict:
    base = state.report()
    expected_verdict = {"valid": "accepted", "duplicate": "duplicate-owner", "cycle": "dependency-cycle", "outside": "outside-owned-scope"}[selected["proposal"]]
    accepted = verdict == "accepted"
    executed = accepted and selected["approve"]
    terminal = state.terminals[-1] if state.terminals else {}
    init = state.initialized[-1] if state.initialized else {}
    identity_ok = bool(init.get("session_id") and init.get("session_id") == terminal.get("session_id"))
    if state.source == "live SDK stream and actual host callbacks":
        internal_only = (
            len(state.calls) == 1
            and state.calls[0].get("name") == "StructuredOutput"
            and not state.calls[0].get("parent_tool_use_id")
            and len(state.results) == 1
            and state.results[0].get("id") == state.calls[0].get("id")
            and state.results[0].get("run_id") == state.run_id
            and state.results[0].get("is_error") is False
        )
    else:
        internal_only = not state.calls and not state.results
    execution_ok = (
        set(started) == {"T1", "T2"}
        and hashes == {name: hashlib.sha256(FILE_TEXT[name].encode()).hexdigest() for name in FILE_TEXT}
        if executed else not started and not hashes
    )
    observed = bool(base["experiment_passed"] and closed and identity_ok and internal_only and state.configured.get("tools") == [] and execution_ok)
    passed = bool(observed and verdict == expected_verdict and (not accepted or isinstance(proposal, dict)))
    return {
        **base,
        "configured": state.configured,
        "proposal_kind": selected["proposal"],
        "proposal_present": isinstance(proposal, dict),
        "host_verdict": verdict,
        "host_approved": selected["approve"],
        "workers_started": started,
        "written_hashes": hashes,
        "connection_closed": closed,
        "observation_passed": observed,
        "experiment_passed": passed,
        "check_scope": "A structured SDK proposal is validated by the host for graph and exact owned-file rules. Only an accepted, approved plan starts deterministic workers; rejection and review-only controls start none.",
    }


async def execute_harness(root: Path, request: RunRequest, settings: Settings, emit: Any, config: Path | None = None) -> dict:
    from agent_lab.sdk import message_data, require_live_access

    request = lesson_request(24, request)
    root = await asyncio.to_thread(root.resolve)
    selected = request.lesson_options
    config = config or root.parent / "config"
    state = Evidence(24, root.parent.name, root, selected, "live SDK stream and actual host callbacks" if request.mode == "live" else "local host effects plus explicitly recorded SDK correlation fixtures", request.max_turns, request.max_budget_usd)
    if request.mode == "live":
        require_live_access(settings)
    options = harness_options(root, config, request, settings)
    state.configured = {"tools": options.tools, "setting_sources": options.setting_sources, "output_format": "json_schema", "max_turns": options.max_turns}
    await emit(Event(kind="options", data={"lesson_id": 24, "sdk_options": state.configured}))
    client = None
    proposal: Any = None
    started: list[str] = []
    hashes: dict[str, str] = {}
    closed = False
    try:
        if request.mode == "live":
            config.mkdir(parents=True, exist_ok=True)
            client = ClaudeSDKClient(options=options)
            await client.connect()
            await client.query(proposal_prompt(selected["proposal"]))
            async for message in client.receive_response():
                if isinstance(message, SystemMessage) and message.subtype == "api_retry" and message.data.get("error_status") == 401:
                    raise PermissionError("Claude rejected authentication (HTTP 401). No host retry was attempted.")
                data = message_data(message)
                event = Event(kind="result" if data["message_class"] == "ResultMessage" else "message", data=data)
                state.observe(event)
                if data["message_class"] == "ResultMessage":
                    proposal = data.get("structured_output")
                await emit(event)
            if not state.report()["experiment_passed"]:
                raise LessonError("The SDK did not finish the proposal with a successful result.")
        else:
            proposal = PROPOSALS[selected["proposal"]]
            state.initialized = [{"session_id": "harness-fixture"}]
            state.terminals = [{"session_id": "harness-fixture", "subtype": "success", "is_error": False}]
            if request.scenario == "missing-evidence":
                state.terminals.clear()
            elif request.scenario == "wrong-identity":
                state.terminals[-1]["session_id"] = "foreign"
            elif request.scenario == "missing-proposal":
                proposal = None
        plan, verdict = host_gate(proposal, root)
        if plan is not None and selected["approve"]:
            started, hashes = await host_execute(plan, root)
        if request.scenario == "wrong-worker" and request.mode == "offline":
            started.append("foreign")
    finally:
        try:
            if client is not None:
                await client.disconnect()
            closed = True
        finally:
            report = harness_report(state, selected, proposal, verdict if "verdict" in locals() else "no-verdict", started, hashes, closed)
            report["scenario"] = request.scenario
            report["expected_check"] = "passed" if report["experiment_passed"] else "needs-review"
            proof = {"experiment": report, "experiment_passed": report["experiment_passed"]}
            async with asyncio.timeout(1):
                await emit(Event(kind="evidence", data={"lesson_id": 24, "result": proof}))
    return proof


async def local_harness(root: Path, request: RunRequest) -> dict:
    async def ignore(event: Event) -> None:
        pass

    return await execute_harness(root, request.model_copy(update={"mode": "offline"}), Settings(), ignore)
