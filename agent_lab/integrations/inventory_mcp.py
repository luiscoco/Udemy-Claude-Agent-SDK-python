"""Owned inventory fixture. Run as a stdio child using host-supplied environment paths."""

import json
import os
import threading
from pathlib import Path
from typing import Annotated, Any, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field

INITIAL_STOCK = {"notebook": 12, "pen": 20}


class Reservation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    sku: Literal["notebook", "pen"]
    quantity: int = Field(ge=1, le=5)


class Inventory:
    def __init__(self, path: Path, reserve_limit: int = 20, expected: dict | None = None) -> None:
        self.path = path
        self.reserve_limit = reserve_limit
        self.expected = expected
        self.lock = threading.Lock()

    def read(self) -> dict:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, data: dict) -> None:
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data), encoding="utf-8")
        temporary.replace(self.path)

    def reset(self, stock: dict[str, int] | None = None) -> dict:
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            data = {"stock": dict(INITIAL_STOCK if stock is None else stock), "reservations": []}
            self._write(data)
            return data

    def reserve(self, arguments: dict) -> dict:
        parsed = Reservation.model_validate(arguments)
        if self.expected is not None and parsed.model_dump() != self.expected:
            raise ValueError("Use exactly the reservation authorized for this run.")
        with self.lock:
            data = self.read()
            if len(data["reservations"]) >= self.reserve_limit:
                raise ValueError("This owned fixture's reservation limit is reached.")
            if data["stock"][parsed.sku] < parsed.quantity:
                raise ValueError("Insufficient stock; the inventory was not changed.")
            data["stock"][parsed.sku] -= parsed.quantity
            data["reservations"].append(parsed.model_dump())
            self._write(data)
            return data


def build_server(inventory: Inventory) -> FastMCP:
    server = FastMCP("lesson-inventory", log_level="WARNING")

    @server.tool()
    def stock() -> dict:
        """Inspect stock without changing it."""
        return inventory.read()

    @server.tool()
    def reserve(
        sku: Literal["notebook", "pen"], quantity: Annotated[int, Field(strict=True, ge=1, le=5)]
    ) -> dict:
        """Reserve 1 to 5 units of notebook or pen in this owned teaching fixture."""
        return inventory.reserve({"sku": sku, "quantity": quantity})

    return server


def sdk_server(inventory: Inventory) -> Any:
    from claude_agent_sdk import create_sdk_mcp_server, tool

    @tool(
        "stock",
        "Inspect the owned inventory without changing it.",
        {"type": "object", "properties": {}, "additionalProperties": False},
    )
    async def stock(arguments: dict) -> dict:
        return {"content": [{"type": "text", "text": json.dumps(inventory.read())}]}

    @tool(
        "reserve", "Reserve 1 to 5 units in the owned inventory.", Reservation.model_json_schema()
    )
    async def reserve(arguments: dict) -> dict:
        try:
            result = inventory.reserve(arguments)
        except ValueError as exc:
            return {"content": [{"type": "text", "text": str(exc)}], "is_error": True}
        return {"content": [{"type": "text", "text": json.dumps(result)}]}

    return create_sdk_mcp_server(name="inventory", tools=[stock, reserve])


if __name__ == "__main__":
    # Browser inputs never supply command lines or filesystem paths.
    build_server(
        Inventory(
            Path(os.environ["LAB_INVENTORY_PATH"]),
            int(os.environ.get("LAB_INVENTORY_LIMIT", "20")),
            json.loads(os.environ.get("LAB_INVENTORY_EXPECTED", "null")),
        )
    ).run(transport="stdio")
