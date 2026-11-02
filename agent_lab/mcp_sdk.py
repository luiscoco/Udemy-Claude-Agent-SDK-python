"""Lesson 13 live SDK configuration and actual parent/tool evidence."""

import asyncio
from pathlib import Path
from typing import Any, cast

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, SystemMessage

from agent_lab.config import Settings
from agent_lab.foundation_models import McpInputs
from agent_lab.foundations import Evidence
from agent_lab.hooks import lesson_hooks, permission_callback
from agent_lab.integrations.inventory_mcp import Inventory
from agent_lab.mcp_lab import server_config
from agent_lab.models import Event, LessonError, RunRequest, lesson_request
from agent_lab.policy import redact


async def run_mcp_sdk(
    request: RunRequest, work: Path, config: Path, settings: Settings, emit: Any
) -> None:
    from agent_lab.sdk import (
        ClaudeSDKClient,
        isolated_env,
        message_data,
        require_live_access,
        resolve_cli_path,
    )

    request = lesson_request(13, request)
    require_live_access(settings)
    selected = McpInputs.model_validate(request.lesson_options)
    inventory = Inventory(
        work / "inventory.json",
        reserve_limit=1,
        expected={"sku": selected.sku, "quantity": selected.quantity}
        if selected.tool == "reserve"
        else None,
    )
    await asyncio.to_thread(inventory.reset)
    await asyncio.to_thread(config.mkdir, parents=True, exist_ok=True)
    evidence = Evidence(
        13,
        work.parent.name,
        work,
        selected.model_dump(),
        "live SDK stream and actual host callbacks",
    )
    before = await asyncio.to_thread(inventory.read)
    statuses: list[dict] = []

    async def record(kind: str, data: dict) -> None:
        data = redact(data)
        event = Event(kind=kind, data=data)
        evidence.observe(event)
        if kind == "mcp_status":
            statuses.append(data)
        await emit(event)

    allowed = "mcp__inventory__" + selected.tool

    def permitted(name: str, arguments: dict) -> tuple[bool, str]:
        return (
            selected.enabled and name == allowed,
            "Only the selected owned inventory tool is available.",
        )

    try:
        async with server_config(inventory, selected.transport) as (server, echo):
            options = ClaudeAgentOptions(
                model=settings.model,
                cli_path=resolve_cli_path(settings),
                cwd=str(work),
                env=isolated_env(config),
                tools=[],
                setting_sources=[],
                strict_mcp_config=True,
                mcp_servers={"inventory": cast(Any, server)} if selected.enabled else {},
                allowed_tools=[allowed] if selected.enabled else [],
                can_use_tool=permission_callback(permitted),
                hooks=lesson_hooks(permitted, record),
                max_turns=request.max_turns,
                max_budget_usd=request.max_budget_usd,
            )
            evidence.configured = {
                "mcp_servers": {"inventory": echo} if selected.enabled else {},
                "allowed_tools": options.allowed_tools,
                "tools": [],
                "setting_sources": [],
                "max_turns": options.max_turns,
                "max_budget_usd": options.max_budget_usd,
            }
            await record("options", {"lesson_id": 13, "sdk_options": evidence.configured})
            async with ClaudeSDKClient(options=options) as client:
                status = await client.get_mcp_status()
                await record("mcp_status", {"phase": "before", "status": status})
                if selected.enabled and selected.lifecycle == "toggle":
                    await client.toggle_mcp_server("inventory", False)
                    await record(
                        "mcp_status", {"phase": "disabled", "status": await client.get_mcp_status()}
                    )
                    await client.toggle_mcp_server("inventory", True)
                elif selected.enabled and selected.lifecycle == "reconnect":
                    await client.reconnect_mcp_server("inventory")
                if selected.lifecycle != "none":
                    await record(
                        "mcp_status",
                        {"phase": "after-control", "status": await client.get_mcp_status()},
                    )
                instruction = (
                    f"Use {allowed} once"
                    + (
                        f" with sku={selected.sku}, quantity={selected.quantity}"
                        if selected.tool == "reserve"
                        else ""
                    )
                    + ". Report the result honestly. Student question: "
                    + request.prompt
                )
                await client.query(instruction)
                async for message in client.receive_response():
                    if (
                        isinstance(message, SystemMessage)
                        and message.subtype == "api_retry"
                        and message.data.get("error_status") == 401
                    ):
                        raise PermissionError(
                            "Claude rejected authentication (HTTP 401). Check the configured API key or cloud-provider credentials; no automatic retry is requested by this lab."
                        )
                    await record(
                        "result" if isinstance(message, ResultMessage) else "message",
                        message_data(message),
                    )
                    if isinstance(message, ResultMessage) and (
                        message.is_error or message.subtype != "success"
                    ):
                        raise LessonError(
                            "The SDK turn failed. Inspect the terminal subtype and MCP status; no automatic retry was made."
                        )
    finally:
        report = evidence.report()
        report["mcp_status_history"] = statuses
        report["scenario"] = request.scenario
        report["local_stock"] = {"before": before, "after": await asyncio.to_thread(inventory.read)}
        try:
            async with asyncio.timeout(1):
                await emit(
                    Event(
                        kind="evidence",
                        data={
                            "lesson_id": 13,
                            "source": evidence.source,
                            "result": {
                                "experiment": report,
                                "experiment_passed": report["experiment_passed"],
                            },
                        },
                    )
                )
        except TimeoutError:
            pass  # A disconnected consumer must not hold transport cleanup indefinitely.
