"""One immutable catalog handler for direct, scripted, and native tool calls."""

import base64
import binascii
import hashlib
import json
import time
import uuid
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from agent_lab.config import ROOT

FIXTURE = ROOT / "fixtures/tool-design/catalog.json"
EXPECTED = ("SKU-101", "SKU-104")
DESCRIPTION = "Durable {name}. Materials, care, dimensions and shipping notes for a classroom catalog fixture."


class VagueInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    q: str = Field(min_length=1, max_length=80)

    @field_validator("q")
    @classmethod
    def trim_query(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Provide a nonempty query")
        return value


class SearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    category: Literal["camping", "office"]
    maxPriceCents: int = Field(ge=0, le=100_000)
    inStock: bool = True
    pageSize: int = Field(default=1, ge=1, le=2)
    cursor: str | None = Field(default=None, max_length=512)
    format: Literal["concise", "detailed"] = "concise"


class GetInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    sku: str = Field(pattern=r"^SKU-\d{3}$")
    format: Literal["concise", "detailed"] = "concise"


SCHEMAS: dict[str, type[BaseModel]] = {"lookup": VagueInput, "catalog_search": SearchInput, "catalog_get": GetInput}
PROFILE_TOOLS = {"vague": ("lookup",), "focused": ("catalog_search", "catalog_get")}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _cursor_encode(snapshot: str, filters: dict[str, Any], offset: int) -> str:
    payload = {"v": 1, "snapshot": snapshot, "filters": filters, "offset": offset}
    return base64.urlsafe_b64encode(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).decode().rstrip("=")


def _cursor_decode(value: str, snapshot: str, filters: dict[str, Any], total: int) -> int:
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        payload = json.loads(raw)
        offset = payload["offset"]
        if (set(payload) != {"v", "snapshot", "filters", "offset"} or payload["v"] != 1 or
                payload["snapshot"] != snapshot or payload["filters"] != filters or
                type(offset) is not int or not 0 < offset < total or
                offset % filters["pageSize"] != 0 or _cursor_encode(snapshot, filters, offset) != value):
            raise ValueError("cursor mismatch")
        return offset
    except (ValueError, KeyError, TypeError, UnicodeError, binascii.Error) as exc:
        raise ValueError("CURSOR_MISMATCH: clear cursor and start this search again") from exc


class Catalog:
    def __init__(self, path: Path = FIXTURE):
        self.path = path
        self.raw = path.read_bytes()
        self.snapshot_sha256 = sha(self.raw)
        data = json.loads(self.raw)
        if data.get("currency") != "EUR" or len(data.get("products", [])) != 5:
            raise ValueError("Invalid fixed catalog")
        self.products: list[dict[str, Any]] = []
        seen: set[str] = set()
        for product in data["products"]:
            if (set(product) != {"id", "name", "category", "priceCents", "stock", "tags"} or
                    not isinstance(product["id"], str) or product["id"] in seen or
                    not product["id"].startswith("SKU-") or
                    product["category"] not in {"camping", "office"} or
                    type(product["priceCents"]) is not int or product["priceCents"] < 0 or
                    type(product["stock"]) is not int or product["stock"] < 0 or
                    not isinstance(product["tags"], list)):
                raise ValueError("Invalid product in fixed catalog")
            seen.add(product["id"])
            item = dict(product)
            item["currency"] = "EUR"
            item["description"] = " ".join([DESCRIPTION.format(name=item["name"].lower())] * 6)
            item["supplierNotes"] = data["supplierNotes"]
            self.products.append(item)
        self.products.sort(key=lambda row: row["id"])

    def current_hash(self) -> str:
        return sha(self.path.read_bytes())

    @staticmethod
    def _present(item: dict[str, Any], format: str) -> dict[str, Any]:
        row = {"id": item["id"], "name": item["name"], "priceCents": item["priceCents"],
               "currency": item["currency"], "inStock": item["stock"] > 0}
        if format == "detailed":
            row.update({"category": item["category"], "description": item["description"],
                        "tags": item["tags"]})
        return row

    def invoke(self, profile: str, tool: str, arguments: Any, *, call_id: str | None = None) -> dict[str, Any]:
        """Validate first; only a valid request can execute the business handler."""
        if profile not in PROFILE_TOOLS or tool not in PROFILE_TOOLS[profile]:
            raise ValueError("Selected tool does not belong to the selected profile")
        started = time.perf_counter()
        call_id = call_id or str(uuid.uuid4())
        executed = False
        normalized: dict[str, Any] | None = None
        error_code: str | None = None
        try:
            parsed: Any = SCHEMAS[tool].model_validate(arguments)
            normalized = parsed.model_dump()
            if tool == "lookup":
                query = parsed.q.casefold()
                matched = [item for item in self.products if query in item["name"].casefold() or
                           query in item["category"] or any(query in tag for tag in item["tags"])]
                payload: dict[str, Any] = {"products": matched}
            elif tool == "catalog_search":
                filters = {key: normalized[key] for key in ("category", "maxPriceCents", "inStock", "pageSize", "format")}
                matched = [item for item in self.products if item["category"] == parsed.category and
                           item["priceCents"] <= parsed.maxPriceCents and
                           (not parsed.inStock or item["stock"] > 0)]
                offset = _cursor_decode(parsed.cursor, self.snapshot_sha256, filters, len(matched)) if parsed.cursor else 0
                page = matched[offset:offset + parsed.pageSize]
                next_offset = offset + len(page)
                payload = {"items": [self._present(item, parsed.format) for item in page],
                           "nextCursor": _cursor_encode(self.snapshot_sha256, filters, next_offset)
                           if next_offset < len(matched) else None}
            else:
                product = next((item for item in self.products if item["id"] == parsed.sku), None)
                if product is None:
                    executed = True
                    error_code = "NOT_FOUND"
                    payload = {"error": "NOT_FOUND", "recovery": "Search for an existing stable SKU ID, then retry catalog_get."}
                else:
                    payload = {"item": self._present(product, parsed.format)}
            executed = True
        except ValidationError as exc:
            error_code = "INVALID_INPUT"
            payload = {"error": error_code, "recovery": "Check required fields, units, SKU format and allowed values; remove unknown keys.",
                       "fields": sorted({str(row["loc"][0]) for row in exc.errors() if row["loc"]})}
        except ValueError as exc:
            error_code = "CURSOR_MISMATCH"
            payload = {"error": error_code, "recovery": str(exc)}
        payload = {"callId": call_id, **payload}
        envelope = {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, separators=(",", ":"))}],
                    "isError": error_code is not None}
        serialized = json.dumps(envelope, ensure_ascii=False, separators=(",", ":")).encode()
        return {"callId": call_id, "profile": profile, "tool": tool, "input": normalized,
                "executed": executed, "ok": error_code is None, "errorCode": error_code,
                "payload": payload, "envelope": envelope, "resultSha256": sha(serialized),
                "envelopeBytes": len(serialized), "handlerMs": round((time.perf_counter() - started) * 1000, 3),
                "returnedIds": [item["id"] for item in payload.get("items", payload.get("products", []))] or
                ([payload["item"]["id"]] if "item" in payload else []),
                "nextCursor": payload.get("nextCursor")}
