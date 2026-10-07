"""Python ticket MCP server for the trusted local plugin."""
import json
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("tickets")


def load_tickets() -> list[dict]:
    path = Path(os.getenv("TICKETS_FILE", str(Path(__file__).resolve().parent.parent / "data" / "tickets.json")))
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else data.get("tickets", [])


@mcp.tool()
def list_tickets() -> list[dict]:
    """List public tickets with id, title, priority and status."""
    return [{key: row[key] for key in ("id", "title", "priority", "status") if key in row}
            for row in load_tickets() if row.get("id", "").upper() != "ATM-999"]


@mcp.tool()
def server_info() -> dict:
    """Show non-secret runtime metadata for the local teaching plugin."""
    return {"team": os.getenv("ATMIRA_TEAM", "teaching"), "pid": os.getpid(), "language": "Python"}


@mcp.tool()
def get_ticket(id: str) -> str:
    """Read a ticket by id. Confidential ticket ATM-999 is never returned."""
    if id.upper() == "ATM-999":
        raise PermissionError("This ticket is confidential.")
    matches = [row for row in load_tickets() if row.get("id") == id.upper()]
    if not matches:
        raise ValueError("Ticket not found.")
    return json.dumps(matches[0])


if __name__ == "__main__":
    mcp.run(transport="stdio")
