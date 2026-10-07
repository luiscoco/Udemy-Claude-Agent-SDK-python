"""Run with: uv run python -m agent_lab.integrations.notes_mcp"""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("python-notes")
NOTES = {
    "welcome": "Welcome to the Python Claude Agent SDK lab.",
    "refunds": "Refund requests must arrive within 30 days of delivery.",
}


@mcp.tool()
def read_note(name: str) -> str:
    """Read a named course note. Available names: welcome, refunds."""
    if name not in NOTES:
        raise ValueError("Unknown note. Choose welcome or refunds.")
    return NOTES[name]


@mcp.resource("notes://welcome")
def welcome_resource() -> str:
    """The course welcome note as an MCP resource."""
    return NOTES["welcome"]


if __name__ == "__main__":
    mcp.run(transport="stdio")
