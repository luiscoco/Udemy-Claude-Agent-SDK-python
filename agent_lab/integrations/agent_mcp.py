"""An MCP server wrapping the Python Agent SDK. Disabled unless LAB_ENABLE_LIVE=true."""

from mcp.server.fastmcp import FastMCP

from agent_lab.config import Settings
from agent_lab.models import RunRequest
from agent_lab.runtime import RunService


def build_server(settings: Settings | None = None) -> FastMCP:
    """Settings are injectable so offline lessons can call the tool without a paid run."""
    server = FastMCP("python-agent")

    @server.tool()
    async def explain_python_agent(prompt: str) -> dict:
        """Ask a bounded, tool-free teaching agent. Requires explicitly enabled live SDK access."""
        service = RunService(settings)
        try:
            handle = service.start(
                1, RunRequest(mode="live", prompt=prompt, max_turns=1, max_budget_usd=0.05)
            )
            events = []
            async for event in service.events(handle):
                if event.kind not in {"started", "evidence"}:
                    events.append(event.model_dump())
            return {"events": events}
        finally:
            await service.close()

    return server


mcp = build_server()

if __name__ == "__main__":
    mcp.run(transport="stdio")
