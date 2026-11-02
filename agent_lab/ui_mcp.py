"""No-model MCP workshop controls, separate from the graded agent experiment."""

import asyncio
from typing import Any

from nicegui import ui

from agent_lab.integrations.inventory_mcp import Reservation
from agent_lab.mcp_lab import McpWorkshops, Workshop
from agent_lab.models import LessonError
from agent_lab.output import render_value


def mcp_workshop_controls(registry: McpWorkshops, client: Any) -> None:
    workshop: Workshop | None = None
    stock: dict = {}
    busy = False
    buttons: list[Any] = []
    with ui.column().classes("w-full gap-3 mcp-workshop"):
        ui.label("MCP transport workshop · no model calls").classes("text-lg font-bold")
        ui.label(
            "This separate workshop stores inventory under an application handle. Each action opens and closes its owned transport. It does not run an agent or complete the automatic check."
        ).classes("text-sm text-slate-600")
        transport = (
            ui.select(
                {
                    "sdk": "In-process SDK server",
                    "stdio": "Child process (stdio)",
                    "http": "Loopback HTTP server",
                },
                value="sdk",
                label="Workshop transport",
            )
            .props("outlined")
            .classes("w-full")
        )
        sku = (
            ui.select(
                {"notebook": "notebook", "pen": "pen"}, value="notebook", label="Workshop item"
            )
            .props("outlined")
            .classes("w-full")
        )
        quantity = (
            ui.number("Workshop quantity", value=2, min=1, max=5, precision=0)
            .props("outlined")
            .classes("w-full")
        )
        feedback = ui.label("Open a workshop to inspect its tools and inventory.").classes(
            "w-full break-words"
        )

        @ui.refreshable
        def observations() -> None:
            if workshop is None:
                return
            state = workshop.snapshot()
            ui.label(
                f"Transport: {state['transport']} · Enabled: {state['enabled']} · Connection open: {state['connection_open']} · Last probe connected: {state['last_probe_connected']} · Workshop closed: {state['closed']}"
            ).classes("w-full break-words")
            ui.label(f"Application handle: {workshop.id}").classes(
                "w-full text-sm font-mono break-all"
            )
            ui.table(
                columns=[
                    {"name": "sku", "label": "Item", "field": "sku", "align": "left"},
                    {
                        "name": "available",
                        "label": "Available",
                        "field": "available",
                        "align": "left",
                    },
                ],
                rows=[
                    {"sku": key, "available": value}
                    for key, value in stock.get("stock", {}).items()
                ],
                row_key="sku",
            ).props("dense hide-bottom wrap-cells").classes("w-full")
            with ui.expansion("Workshop tools and timeline").classes("w-full"):
                render_value(
                    {"discovered_tools": state["discovered_tools"], "timeline": state["timeline"]}
                )

        async def action(name: str) -> None:
            nonlocal workshop, stock, busy
            if busy:
                return
            busy = True
            for button in buttons:
                button.disable()
            try:
                if name == "open":
                    if workshop is not None and not workshop.closed:
                        await workshop.operation("end")
                    workshop = await registry.start(transport.value)
                    await workshop.operation("status")
                    feedback.set_text(
                        "Connected and listed tools; the probe's transport is now closed."
                    )
                else:
                    if workshop is None or workshop.closed:
                        raise LessonError("Open a new workshop first.")
                    if name in {"reserve", "stock"}:
                        payload = {}
                        if name == "reserve":
                            if quantity.value != int(quantity.value):
                                raise ValueError("Choose a whole quantity from 1 to 5.")
                            payload = Reservation.model_validate(
                                {"sku": sku.value, "quantity": int(quantity.value)}
                            ).model_dump()
                        result = await workshop.operation(
                            "call", {"tool": name, "arguments": payload}
                        )
                        feedback.set_text(
                            "The inventory server rejected the tool call; inspect its result."
                            if result["is_error"]
                            else "MCP tool returned successfully. Inspect the host inventory and timeline."
                        )
                    elif name in {"disable", "enable"}:
                        await workshop.operation("toggle", {"enabled": name == "enable"})
                        feedback.set_text(
                            "Server enabled for the next connection."
                            if name == "enable"
                            else "Server disabled. Further probes and tool calls are blocked before connecting."
                        )
                    elif name == "set-servers":
                        await workshop.operation(name, {"transport": transport.value})
                        feedback.set_text(
                            "Configuration selected. Check status to establish a new connection."
                        )
                    else:
                        await workshop.operation(name)
                        feedback.set_text(
                            {
                                "status": "Connection and tool discovery observed; transport closed.",
                                "reconnect": "A fresh connection and handshake succeeded; transport closed.",
                                "reset": "Only this workshop's inventory was reset.",
                                "end": "Workshop ended. Its inventory remains available for inspection.",
                            }[name]
                        )
            except (LessonError, ValueError) as exc:
                feedback.set_text(str(exc))
            finally:
                if workshop is not None:
                    stock = await asyncio.to_thread(workshop.inventory.read)
                observations.refresh()
                busy = False
                for index, button in enumerate(buttons):
                    button.set_enabled(index == 0 or (workshop is not None and not workshop.closed))

        with ui.row().classes("w-full flex-wrap gap-2"):
            for key, label in (
                ("open", "Open MCP workshop"),
                ("status", "Check MCP status"),
                ("stock", "Read inventory"),
                ("reserve", "Reserve inventory"),
                ("disable", "Disable MCP server"),
                ("enable", "Enable MCP server"),
                ("reconnect", "Reconnect MCP server"),
                ("set-servers", "Apply workshop transport"),
                ("reset", "Reset workshop inventory"),
                ("end", "End MCP workshop"),
            ):
                button = ui.button(label, on_click=lambda action_name=key: action(action_name))
                buttons.append(button)
                if key != "open":
                    button.disable()
        observations()

    async def close() -> None:
        if workshop is not None:
            async with workshop.lock:
                workshop.closed = True

    client.on_disconnect(close)
