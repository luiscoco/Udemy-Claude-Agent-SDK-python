"""Plan-mode proposal, host approval gate, and SDK mode transition."""

import asyncio
from pathlib import Path
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, SystemMessage

from agent_lab.config import Settings
from agent_lab.foundations import Evidence
from agent_lab.harness_lab import FILE_TEXT, PROPOSALS, host_execute, host_gate
from agent_lab.models import Event, LessonError, RunRequest, lesson_request


def plan_options(root: Path, config: Path, request: RunRequest, settings: Settings) -> ClaudeAgentOptions:
    from agent_lab.sdk import isolated_env, resolve_cli_path
    from agent_lab.services import Plan

    schema = Plan.model_json_schema()
    schema.pop("$schema", None)
    return ClaudeAgentOptions(
        cwd=str(root.resolve()), model=settings.model,
        cli_path=resolve_cli_path(settings) if request.mode == "live" else None,
        permission_mode="plan", tools=[], allowed_tools=[], setting_sources=[],
        strict_mcp_config=True, env=isolated_env(config.resolve()),
        system_prompt="Return the exact requested JSON task proposal. Do not execute or alter files. The host validates and decides whether to approve it.",
        output_format={"type": "json_schema", "schema": schema},
        max_turns=request.max_turns, max_budget_usd=request.max_budget_usd,
    )


def plan_prompt(kind: str) -> str:
    import json

    return "In plan mode, propose exactly this JSON without changing tasks, paths, or dependencies. Do not run tools or execute anything: " + json.dumps(PROPOSALS[kind], separators=(",", ":"))


def plan_report(state: Evidence, selected: dict[str, Any], proposal: Any, verdict: str,
                mode_events: list[dict[str, Any]], workers: list[str], hashes: dict[str, str], closed: bool) -> dict[str, Any]:
    import hashlib

    base = state.report()
    accepted = verdict == "accepted"
    should_execute = accepted and selected["approve"]
    expected_verdict = "accepted" if selected["proposal"] == "valid" else "duplicate-owner"
    init = state.initialized[0] if state.initialized else {}
    expected_turns = 2 if should_execute else 1
    terminals_ok = bool(init.get("session_id") and len(state.terminals) == expected_turns
        and all(row.get("session_id") == init["session_id"] and row.get("subtype") == "success" and row.get("is_error") is False for row in state.terminals))
    mode_ok = bool(state.configured.get("permission_mode") == "plan"
        and mode_events == ([{"mode": "plan", "step": "proposal"}, {"mode": "default", "step": "approved"}, {"mode": "default", "step": "confirmation"}] if should_execute else [{"mode": "plan", "step": "proposal"}])
        and (state.source != "live SDK stream and actual host callbacks"
             or [row.get("permissionMode") for row in state.initialized] == (["plan", "default"] if should_execute else ["plan"])))
    expected_hashes = {name: hashlib.sha256(text.encode()).hexdigest() for name, text in FILE_TEXT.items()}
    execution_ok = (len(workers) == 2 and set(workers) == {"T1", "T2"} and hashes == expected_hashes) if should_execute else (not workers and not hashes)
    internal_only = bool(
        (len(state.calls) == len(state.results) == expected_turns
         and all(call.get("name") == "StructuredOutput"
                 and not call.get("parent_tool_use_id")
                 and result.get("id") == call.get("id")
                 and result.get("is_error") is False
                 for call, result in zip(state.calls, state.results, strict=True)))
        if state.source == "live SDK stream and actual host callbacks" else not state.calls and not state.results
    )
    observed = bool(base["experiment_passed"] and terminals_ok and mode_ok and execution_ok and internal_only and closed)
    passed = bool(observed and verdict == expected_verdict and isinstance(proposal, dict))
    return {**base, "selected": selected, "proposal_present": isinstance(proposal, dict),
        "host_verdict": verdict, "host_approved": selected["approve"],
        "mode_events": mode_events, "workers_started": workers, "written_hashes": hashes,
        "terminal_sessions_verified": terminals_ok, "mode_sequence_verified": mode_ok,
        "execution_verified": execution_ok, "connection_closed": closed,
        "observation_passed": observed, "experiment_passed": passed,
        "check_scope": "The SDK starts in plan mode and returns a structured proposal. The host validates the exact owned plan. Only an accepted proposal with selected host approval triggers a successful set_permission_mode(default) control, a confirmation turn on the same session, and deterministic host workers. Review-only and rejected proposals stay in plan mode without workers."}


async def execute_plan_mode(root: Path, request: RunRequest, settings: Settings, emit: Any, config: Path | None = None) -> dict[str, Any]:
    from agent_lab.sdk import message_data, require_live_access

    request = lesson_request(32, request)
    root = await asyncio.to_thread(root.resolve)
    config = config or root.parent / "config"
    selected = request.lesson_options
    state = Evidence(32, root.parent.name, root, selected,
        "live SDK stream and actual host callbacks" if request.mode == "live" else "local host effects plus explicitly recorded SDK correlation fixtures",
        request.max_turns, request.max_budget_usd)
    if request.mode == "live":
        require_live_access(settings)
    options = plan_options(root, config, request, settings)
    state.configured = {"permission_mode": options.permission_mode, "tools": options.tools,
        "allowed_tools": options.allowed_tools, "setting_sources": options.setting_sources,
        "output_format": "json_schema", "strict_mcp_config": options.strict_mcp_config}
    await emit(Event(kind="options", data={"lesson_id": 32, "sdk_options": state.configured}))
    proposal: Any = None
    verdict = "no-verdict"
    workers: list[str] = []
    hashes: dict[str, str] = {}
    mode_events = [{"mode": "plan", "step": "proposal"}]
    client = None
    closed = False
    try:
        if request.mode == "live":
            config.mkdir(parents=True, exist_ok=True)
            client = ClaudeSDKClient(options=options)
            await client.connect()
            await client.query(plan_prompt(selected["proposal"]))
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
                raise LessonError("Plan-mode proposal did not finish successfully.")
        else:
            proposal = PROPOSALS[selected["proposal"]]
            state.initialized = [{"session_id": "plan-fixture"}]
            state.terminals = [{"session_id": "plan-fixture", "subtype": "success", "is_error": False}]
            if request.scenario == "missing-evidence":
                state.terminals.clear()
            elif request.scenario == "wrong-identity":
                state.terminals[0]["session_id"] = "foreign"
            elif request.scenario == "missing-proposal":
                proposal = None
        plan, verdict = host_gate(proposal, root)
        if plan is not None and selected["approve"] and state.report()["experiment_passed"]:
            if client is not None:
                await client.set_permission_mode("default")
            mode_events.append({"mode": "default", "step": "approved"})
            if client is not None:
                await client.query("The host has approved the validated plan and switched to default mode. Reply exactly READY. Do not use tools or edit files; host workers perform the fixed task.")
                async for message in client.receive_response():
                    data = message_data(message)
                    event = Event(kind="result" if data["message_class"] == "ResultMessage" else "message", data=data)
                    state.observe(event)
                    await emit(event)
            else:
                state.terminals.append({"session_id": "plan-fixture", "subtype": "success", "is_error": False})
            mode_events.append({"mode": "default", "step": "confirmation"})
            workers, hashes = await host_execute(plan, root)
        if request.mode == "offline":
            if request.scenario == "missing-switch":
                mode_events[:] = mode_events[:1]
            elif request.scenario == "unapproved-work":
                workers.append("T1")
            elif request.scenario == "wrong-worker":
                workers.append("foreign")
    finally:
        if client is not None:
            await client.disconnect()
        closed = True
        report = plan_report(state, selected, proposal, verdict, mode_events, workers, hashes, closed)
        report["scenario"] = request.scenario
        report["expected_check"] = "passed" if report["experiment_passed"] else "needs-review"
        proof = {"experiment": report, "experiment_passed": report["experiment_passed"]}
        await emit(Event(kind="evidence", data={"lesson_id": 32, "result": proof}))
    return proof


async def local_plan_mode(root: Path, request: RunRequest) -> dict[str, Any]:
    async def ignore(event: Event) -> None:
        pass

    return await execute_plan_mode(root, request.model_copy(update={"mode": "offline"}), Settings(), ignore)
