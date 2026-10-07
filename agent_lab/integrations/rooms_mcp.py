"""An actual Python MCP elicitation example, independent of Agent SDK callback parity."""

from mcp.server.fastmcp import Context, FastMCP
from pydantic import BaseModel, ConfigDict, Field

mcp = FastMCP("python-rooms")


class BookingDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)
    attendees: int = Field(ge=1, le=8)
    confirmed: bool


@mcp.tool()
async def book_room(room: str, ctx: Context) -> dict:
    """Request a local demonstration booking after eliciting the person's details."""
    if room not in {"Blue", "Green"}:
        raise ValueError("Choose Blue or Green.")
    response = await ctx.elicit(
        "Provide your booking details and confirm this local reservation.", BookingDetails
    )
    if response.action != "accept":
        return {"state": response.action, "booked": False}
    if not response.data.confirmed:
        return {"state": "not confirmed", "booked": False}
    return {
        "room": room,
        "name": response.data.name,
        "attendees": response.data.attendees,
        "booked": True,
        "external_calendar": False,
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
