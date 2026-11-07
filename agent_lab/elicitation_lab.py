"""Provider-backed SDK call bridged to an owned Python MCP elicitation session."""

import asyncio
import json
from pathlib import Path
from typing import Any, Literal, cast

from claude_agent_sdk import (
    ClaudeAgentOptions,
    ClaudeSDKClient,
    SystemMessage,
    create_sdk_mcp_server,
    tool,
)
from mcp import types
from mcp.shared.memory import create_connected_server_and_client_session

from agent_lab.config import Settings
from agent_lab.foundations import Evidence, record_call
from agent_lab.integrations.rooms_mcp import mcp as rooms_server
from agent_lab.models import Event, RunRequest, lesson_request

TOOL = "mcp__rooms__book_room"
FORM_MESSAGE = "Provide your booking details and confirm this local reservation."
ACCEPT_CONTENT: dict[str, str | int | float | bool | list[str] | None] = {"name": "Student", "attendees": 2, "confirmed": True}


def known_request(params: Any) -> bool:
    """Only the owned room form can receive the selected host answer."""
    schema = getattr(params, "requestedSchema", None)
    if schema is None:
        schema = getattr(params, "requested_schema", None)
    properties = schema.get("properties") if isinstance(schema, dict) else None
    return bool(getattr(params, "message", None) == FORM_MESSAGE
                and isinstance(properties, dict)
                and set(properties) == set(ACCEPT_CONTENT))


async def owned_booking(action: str, callbacks: list[dict[str, Any]]) -> dict[str, Any]:
    """Call the actual FastMCP server; the Python MCP client answers its form."""
    async def answer(context: Any, params: Any) -> types.ElicitResult:
        known = known_request(params)
        chosen = action if known else "decline"
        callbacks.append({"known_demo": known, "action": chosen,
                          "content": ACCEPT_CONTENT.copy() if chosen == "accept" else None})
        if chosen == "accept":
            return types.ElicitResult(action="accept", content=ACCEPT_CONTENT.copy())
        return types.ElicitResult(action=cast(Literal["decline", "cancel"], chosen))

    async with asyncio.timeout(20):
        async with create_connected_server_and_client_session(
            rooms_server, elicitation_callback=answer
        ) as session:
            result = await session.call_tool("book_room", {"room": "Blue"})
    if result.isError or len(result.content) != 1 or not isinstance(result.content[0], types.TextContent):
        raise ValueError("The owned rooms MCP tool did not return one successful text result.")
    outcome = json.loads(result.content[0].text)
    if not isinstance(outcome, dict):
        raise ValueError("The owned rooms MCP result was not an object.")
    return outcome


def elicitation_options(root: Path, config: Path, request: RunRequest, settings: Settings, handler: Any) -> ClaudeAgentOptions:
    from agent_lab.sdk import isolated_env, resolve_cli_path

    return ClaudeAgentOptions(
        cwd=str(root.resolve()), model=settings.model,
        cli_path=resolve_cli_path(settings) if request.mode == "live" else None,
        mcp_servers={"rooms": create_sdk_mcp_server(name="rooms", tools=[handler])},
        tools=[TOOL], allowed_tools=[TOOL], setting_sources=[], strict_mcp_config=True,
        env=isolated_env(config.resolve()),
        system_prompt={"type": "preset", "preset": "claude_code", "append": "Call the single rooms tool exactly once with room Blue. The host answers the owned MCP form; report its result. Do not retry or call other tools."},
        max_turns=request.max_turns, max_budget_usd=request.max_budget_usd,
    )


def elicitation_report(state: Evidence, selected: dict[str, str], callbacks: list[dict[str, Any]],
                       outcomes: list[dict[str, Any]], closed: bool) -> dict[str, Any]:
    base = state.report()
    expected = ({"room": "Blue", "name": "Student", "attendees": 2,
                 "booked": True, "external_calendar": False}
                if selected["action"] == "accept"
                else {"state": selected["action"], "booked": False})
    calls = [row for row in state.calls if row.get("name") == TOOL and not row.get("parent_tool_use_id")]
    paired = bool(len(calls) == len(state.calls) == len(state.results) == 1
                  and calls[0].get("arguments") == {"room": "Blue"}
                  and state.results[0].get("id") == calls[0].get("id")
                  and state.results[0].get("is_error") is False)
    callback_ok = callbacks == [{"known_demo": True, "action": selected["action"],
                                 "content": ACCEPT_CONTENT if selected["action"] == "accept" else None}]
    outcome_ok = outcomes == [expected]
    init = state.initialized[-1] if state.initialized else {}
    terminal = state.terminals[-1] if state.terminals else {}
    session_ok = bool(init.get("session_id") and terminal.get("session_id") == init["session_id"])
    passed = bool(base["experiment_passed"] and paired and callback_ok and outcome_ok and session_ok and closed)
    return {**base, "selected": selected, "mcp_elicitation_callbacks": callbacks,
            "mcp_server_outcomes": outcomes, "mcp_call_result_correlated": paired,
            "callback_verified": callback_ok, "server_outcome_verified": outcome_ok,
            "terminal_session_verified": session_ok, "connection_closed": closed,
            "observation_passed": passed, "experiment_passed": passed,
            "check_scope": "One provider-backed SDK tool call and result must match the host handler. The handler calls the actual owned FastMCP rooms server through the Python MCP client. Its form callback returns the selected simulated accept, decline or cancel action, and the server outcome must match. The SDK terminal shares its initialized session. No external calendar is contacted."}


async def execute_elicitation(root: Path, request: RunRequest, settings: Settings, emit: Any,
                              config: Path | None = None) -> dict[str, Any]:
    from agent_lab.sdk import message_data, require_live_access

    request = lesson_request(33, request)
    root = await asyncio.to_thread(root.resolve)
    config = config or root.parent / "config"
    selected = request.lesson_options
    state = Evidence(33, root.parent.name, root, selected,
        "live SDK stream and actual host callbacks" if request.mode == "live" else "actual MCP callback and server result plus labelled SDK fixtures",
        request.max_turns, request.max_budget_usd)
    callbacks: list[dict[str, Any]] = []
    outcomes: list[dict[str, Any]] = []

    @tool("book_room", "Book the fixed Blue room through an owned MCP elicitation session.", {"room": str})
    async def book_room(arguments: dict[str, Any]) -> dict[str, Any]:
        if arguments != {"room": "Blue"}:
            return {"content": [{"type": "text", "text": "Only room Blue is enabled."}], "is_error": True}
        outcome = await owned_booking(selected["action"], callbacks)
        outcomes.append(outcome)
        return {"content": [{"type": "text", "text": json.dumps(outcome)}]}

    if request.mode == "live":
        require_live_access(settings)
    options = elicitation_options(root, config, request, settings, book_room)
    state.configured = {"tools": options.tools, "allowed_tools": options.allowed_tools,
                        "mcp_servers": ["rooms"], "strict_mcp_config": options.strict_mcp_config,
                        "transport": "owned SDK MCP tool to Python MCP client/server"}
    await emit(Event(kind="options", data={"lesson_id": 33, "sdk_options": state.configured}))
    client = None
    closed = False
    try:
        if request.mode == "live":
            config.mkdir(parents=True, exist_ok=True)
            client = ClaudeSDKClient(options=options)
            await client.connect()
            await client.query(f"Call {TOOL} exactly once with room Blue. The host will supply a simulated MCP form response. Do not invent the result or retry.")
            async for message in client.receive_response():
                if isinstance(message, SystemMessage) and message.subtype == "api_retry" and message.data.get("error_status") == 401:
                    raise PermissionError("Claude rejected authentication (HTTP 401). No host retry was attempted.")
                data = message_data(message)
                event = Event(kind="result" if data["message_class"] == "ResultMessage" else "message", data=data)
                state.observe(event)
                await emit(event)
        else:
            outcome = await owned_booking(selected["action"], callbacks)
            outcomes.append(outcome)
            state.initialized = [{"session_id": "elicitation-fixture"}]
            record_call(state, TOOL, {"room": "Blue"}, "room-1")
            state.results = [{"id": "room-1", "run_id": state.run_id, "is_error": False}]
            state.terminals = [{"session_id": "elicitation-fixture", "subtype": "success", "is_error": False}]
            if request.scenario == "missing-evidence":
                state.terminals.clear()
            elif request.scenario == "wrong-identity":
                state.results[0]["id"] = "foreign"
            elif request.scenario == "missing-hook":
                callbacks.clear()
            elif request.scenario == "wrong-action":
                callbacks[0]["action"] = "cancel" if selected["action"] != "cancel" else "accept"
            elif request.scenario == "wrong-content":
                callbacks[0]["content"] = {"name": "Other"}
            elif request.scenario == "wrong-server":
                callbacks[0]["known_demo"] = False
    finally:
        if client is not None:
            await client.disconnect()
        closed = True
        report = elicitation_report(state, selected, callbacks, outcomes, closed)
        report["scenario"] = request.scenario
        report["expected_check"] = "passed" if report["experiment_passed"] else "needs-review"
        proof = {"experiment": report, "experiment_passed": report["experiment_passed"]}
        await emit(Event(kind="evidence", data={"lesson_id": 33, "result": proof}))
    return proof


async def local_elicitation(root: Path, request: RunRequest) -> dict[str, Any]:
    async def ignore(event: Event) -> None:
        pass

    return await execute_elicitation(root, request.model_copy(update={"mode": "offline"}), Settings(), ignore)
