"""Run with: uv run python -m agent_lab.integrations.notes_mcp"""

from mcp.server.fastmcp import FastMCP

NOTES = {
    "welcome": "Welcome to the Python Claude Agent SDK lab.",
    "refunds": "Refund requests must arrive within 30 days of delivery.",
}


def build_server() -> FastMCP:
    """A fresh server per transport: an HTTP session manager can only run once."""
    server = FastMCP("python-notes")

    @server.tool()
    def read_note(name: str) -> str:
        """Read a named course note. Available names: welcome, refunds."""
        if name not in NOTES:
            raise ValueError("Unknown note. Choose welcome or refunds.")
        return NOTES[name]

    @server.resource("notes://welcome")
    def welcome_resource() -> str:
        """The course welcome note as an MCP resource."""
        return NOTES["welcome"]

    return server


mcp = build_server()

if __name__ == "__main__":
    mcp.run(transport="stdio")
