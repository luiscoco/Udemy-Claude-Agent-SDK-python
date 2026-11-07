"""Fixed stdio MCP permission gate for lesson 37."""

import asyncio
import json
import os
from pathlib import Path
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, TextContent

gate = FastMCP("gate")


@gate.tool()
async def approve(tool_name: str, input: dict[str, Any]) -> CallToolResult:
    """Request a host decision for one proposed SDK tool call."""
    body = {
        "run_id": os.environ["LAB_GATE_RUN"],
        "gate_id": os.environ["LAB_GATE_ID"],
        "capability": os.environ["LAB_GATE_CAPABILITY"],
        "tool_name": tool_name,
        "tool_input": input,
    }
    async with httpx.AsyncClient(timeout=65, trust_env=False) as client:
        response = await client.post(os.environ["LAB_GATE_URL"], json=body,
                                     headers={"X-Gate-Token": os.environ["LAB_GATE_TOKEN"]})
        response.raise_for_status()
    receipt = {"run_id": body["run_id"], "gate_id": body["gate_id"],
               "tool_name": tool_name, "response_status": response.status_code}
    log = Path(os.environ["LAB_GATE_LOG"])

    def record() -> None:
        with log.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(receipt) + "\n")

    await asyncio.to_thread(record)
    return CallToolResult(content=[TextContent(type="text", text=response.json()["response"])])


if __name__ == "__main__":
    gate.run(transport="stdio")
