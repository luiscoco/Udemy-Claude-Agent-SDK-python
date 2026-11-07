"""Observe connected SDK control calls, an interrupted turn, and disconnect."""

import asyncio
from pathlib import Path
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, CLIConnectionError, SystemMessage

from agent_lab.config import Settings
from agent_lab.foundations import Evidence
from agent_lab.models import Event, LessonError, RunRequest, lesson_request

BEFORE = "CONTROL_BEFORE_26"
AFTER = "CONTROL_AFTER_26"


def control_options(root: Path, config: Path, request: RunRequest, settings: Settings) -> ClaudeAgentOptions:
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
        system_prompt={"type": "preset", "preset": "claude_code", "append": "This is a fixed control-method lesson. Use no tools. Follow the requested short marker output exactly."},
        include_partial_messages=request.lesson_options["action"] == "interrupt",
        max_turns=request.max_turns,
        max_budget_usd=request.max_budget_usd,
    )


def control_report(state: Evidence, selected: dict, control_calls: list[dict], turn_models: list[list[str]], turn_results: list[dict], markers: list[str], interrupt_observed: bool, info_seen: bool, post_close_rejected: bool, closed: bool) -> dict:
    base = state.report()
    init = state.initialized[-1] if state.initialized else {}
    session = init.get("session_id")
    same_session = bool(session and turn_results and all(row.get("session_id") == session for row in turn_results))
    control_names = [row["name"] for row in control_calls if row.get("acknowledged")]
    if selected["action"] == "switch":
        expected_model = selected["target_model"]
        model_ok = bool(len(turn_models) == 2 and turn_models[0] and turn_models[1] and (
            "sonnet" in turn_models[1][-1].lower() if expected_model == "sonnet" else turn_models[1][-1] == turn_models[0][-1]
        ))
        control_ok = control_names == ["set_model", "set_permission_mode"]
        terminal_ok = len(turn_results) == 2 and all(row.get("subtype") == "success" and row.get("is_error") is False for row in turn_results)
        marker_ok = markers == [BEFORE, AFTER]
        observed = bool(base["experiment_passed"] and same_session and control_ok and model_ok and terminal_ok and marker_ok and info_seen and post_close_rejected and closed)
    else:
        model_ok = None
        control_ok = control_names == ["interrupt"]
        terminal_ok = len(turn_results) == 1 and (turn_results[0].get("is_error") is True or "interrupt" in str(turn_results[0].get("subtype", "")))
        marker_ok = None
        observed = bool(same_session and control_ok and interrupt_observed and terminal_ok and info_seen and post_close_rejected and closed)
    return {
        **base,
        "selected": selected,
        "control_calls": control_calls,
        "turn_models": turn_models,
        "turn_results": turn_results,
        "response_markers": markers,
        "same_session": same_session,
        "control_acknowledged": control_ok,
        "observed_model_matches_target": model_ok,
        "terminal_outcome_matches": terminal_ok,
        "marker_matches": marker_ok,
        "server_info_seen": info_seen,
        "interrupt_after_stream_started": interrupt_observed,
        "post_close_query_rejected": post_close_rejected,
        "connection_closed": closed,
        "observation_passed": observed,
        "experiment_passed": observed,
        "check_scope": "Switch runs require two successful turns on one initialized session, acknowledged control methods, the selected observed model, and fixed response markers. Interrupt runs require a stream event followed by an acknowledged interrupt and a matching interrupted or failed terminal. Both require rejection of a query after disconnect. A permission-mode acknowledgement does not prove every tool-policy consequence.",
    }


async def execute_control(root: Path, request: RunRequest, settings: Settings, emit: Any, config: Path | None = None) -> dict:
    from agent_lab.sdk import message_data, require_live_access

    request = lesson_request(26, request)
    root = await asyncio.to_thread(root.resolve)
    selected = request.lesson_options
    config = config or root.parent / "config"
    state = Evidence(26, root.parent.name, root, selected, "live SDK stream and actual host callbacks" if request.mode == "live" else "local host effects plus explicitly recorded SDK correlation fixtures", request.max_turns, request.max_budget_usd)
    state.configured = {"tools": [], "allowed_tools": [], "setting_sources": [], "strict_mcp_config": True, "include_partial_messages": selected["action"] == "interrupt"}
    await emit(Event(kind="options", data={"lesson_id": 26, "sdk_options": state.configured}))
    control_calls: list[dict] = []
    turn_models: list[list[str]] = []
    turn_results: list[dict] = []
    markers: list[str] = []
    interrupt_observed = False
    info_seen = False
    post_close_rejected = False
    closed = False
    client = None

    async def receive_turn(client: ClaudeSDKClient, interrupt: bool = False) -> None:
        nonlocal interrupt_observed
        models: list[str] = []
        answers: list[str] = []
        async for message in client.receive_response():
            if isinstance(message, SystemMessage) and message.subtype == "api_retry" and message.data.get("error_status") == 401:
                raise PermissionError("Claude rejected authentication (HTTP 401). No host retry was attempted.")
            data = message_data(message)
            if data["message_class"] == "AssistantMessage":
                if isinstance(data.get("model"), str):
                    models.append(data["model"])
                answers.extend(block["text"] for block in data.get("content", []) if isinstance(block, dict) and isinstance(block.get("text"), str))
            if data["message_class"] == "ResultMessage":
                turn_results.append(data)
                if isinstance(data.get("result"), str):
                    answers.append(data["result"])
            event = Event(kind="result" if data["message_class"] == "ResultMessage" else "message", data=data)
            state.observe(event)
            await emit(event)
            stream_event = data.get("event", {}) if data["message_class"] == "StreamEvent" else {}
            delta = stream_event.get("delta", {}) if isinstance(stream_event, dict) else {}
            if interrupt and stream_event.get("type") == "content_block_delta" and delta.get("type") == "text_delta" and delta.get("text") and not interrupt_observed:
                await client.interrupt()
                control_calls.append({"name": "interrupt", "acknowledged": True})
                interrupt_observed = True
        turn_models.append(models)
        if not interrupt:
            markers.append(answers[-1].strip() if answers else "")

    try:
        if request.mode == "live":
            require_live_access(settings)
            config.mkdir(parents=True, exist_ok=True)
            client = ClaudeSDKClient(options=control_options(root, config, request, settings))
            await client.connect()
            info_seen = await client.get_server_info() is not None
            if selected["action"] == "switch":
                await client.query(f"Reply with exactly {BEFORE} and nothing else.")
                await receive_turn(client)
                target = settings.model if selected["target_model"] == "current" else "claude-sonnet-5-5"
                await client.set_model(target)
                control_calls.append({"name": "set_model", "acknowledged": True, "target": target})
                await client.set_permission_mode(selected["permission_mode"])
                control_calls.append({"name": "set_permission_mode", "acknowledged": True, "mode": selected["permission_mode"]})
                await client.query(f"Reply with exactly {AFTER} and nothing else.")
                await receive_turn(client)
            else:
                await client.query("Write a detailed explanation of Python generators in at least 1000 numbered paragraphs. Start immediately and keep writing without tools.")
                await receive_turn(client, interrupt=True)
            if selected["action"] == "switch" and not state.report()["experiment_passed"]:
                raise LessonError("Control-method run did not finish with a successful SDK result.")
        else:
            info_seen = True
            state.initialized = [{"session_id": "control-fixture"}]
            if selected["action"] == "switch":
                model = "claude-sonnet-5-5" if selected["target_model"] == "sonnet" else "fixture-model"
                turn_models = [["fixture-model"], [model]]
                turn_results = [{"session_id": "control-fixture", "subtype": "success", "is_error": False}] * 2
                markers = [BEFORE, AFTER]
                control_calls = [{"name": "set_model", "acknowledged": True}, {"name": "set_permission_mode", "acknowledged": True}]
            else:
                turn_models = [[]]
                turn_results = [{"session_id": "control-fixture", "subtype": "error_interrupt", "is_error": True}]
                control_calls = [{"name": "interrupt", "acknowledged": True}]
                interrupt_observed = True
            state.terminals = turn_results.copy()
            if request.scenario == "missing-evidence":
                state.initialized.clear()
            elif request.scenario == "wrong-identity":
                turn_results[-1]["session_id"] = "foreign"
            elif request.scenario == "missing-control":
                control_calls.clear()
            elif request.scenario == "wrong-model":
                turn_models[-1] = ["foreign-model"]
            elif request.scenario == "after-close":
                post_close_rejected = False
    finally:
        if client is not None:
            await client.disconnect()
            try:
                await client.query("After disconnect")
            except CLIConnectionError:
                post_close_rejected = True
        else:
            post_close_rejected = request.scenario != "after-close"
        closed = True
        report = control_report(state, selected, control_calls, turn_models, turn_results, markers, interrupt_observed, info_seen, post_close_rejected, closed)
        report["scenario"] = request.scenario
        report["expected_check"] = "passed" if report["experiment_passed"] else "needs-review"
        proof = {"experiment": report, "experiment_passed": report["experiment_passed"]}
        async with asyncio.timeout(1):
            await emit(Event(kind="evidence", data={"lesson_id": 26, "result": proof}))
    return proof


async def local_control(root: Path, request: RunRequest) -> dict:
    async def ignore(event: Event) -> None:
        pass

    return await execute_control(root, request.model_copy(update={"mode": "offline"}), Settings(), ignore)
