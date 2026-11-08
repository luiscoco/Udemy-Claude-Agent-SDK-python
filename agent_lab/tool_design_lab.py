"""Lesson 54 bounded prepared consumer and evidence-based contract grading."""

import asyncio
import json
import math
import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from agent_lab.tool_design_catalog import EXPECTED, Catalog, sha

ROW_LIMIT = 160
BYTE_LIMIT = 360_000


class DesignInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    mode: Literal["prepared", "live"] = "prepared"
    profile: Literal["vague", "focused"] = "focused"
    format: Literal["concise", "detailed"] = "concise"
    consent: bool = False
    budget: float = Field(default=0.5, ge=0.25, le=1.0, allow_inf_nan=False)


class DirectInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    profile: Literal["vague", "focused"]
    tool: Literal["lookup", "catalog_search", "catalog_get"]
    input: dict[str, Any]


def summarize(receipts: list[dict[str, Any]], *, model_calls: int, cost: float | None) -> dict[str, Any]:
    searches = [row for row in receipts if row["tool"] == "catalog_search" and row["ok"]]
    gets = [row for row in receipts if row["tool"] == "catalog_get" and row["ok"]]
    return {"calls": len(receipts), "successfulExecutions": sum(bool(row["executed"] and row["ok"]) for row in receipts),
            "errors": sum(bool(not row["ok"]) for row in receipts),
            "envelopeBytes": sum(row["envelopeBytes"] for row in receipts),
            "searchIds": sorted({sku for row in searches for sku in row["returnedIds"]}),
            "detailIds": sorted({sku for row in gets for sku in row["returnedIds"]}),
            "modelCalls": model_calls, "reportedSdkUsd": cost}


def grade(selected: DesignInput, report: dict[str, Any]) -> bool:
    """Check host receipts and provenance; assistant prose cannot satisfy this gate."""
    run = report.get("runId")
    frames = report.get("frames", [])
    receipts = report.get("receipts", [])
    if (not isinstance(run, str) or not isinstance(frames, list) or not frames or
            not isinstance(receipts, list) or not receipts or len(frames) > ROW_LIMIT or
            len(json.dumps(report, default=str)) > 500_000 or
            any(row.get("runId") != run for row in frames) or
            report.get("mode") != selected.mode or report.get("profile") != selected.profile or
            report.get("format") != selected.format or report.get("interrupted") or
            report.get("closed") is not True or report.get("overflow") or
            report.get("error") or report.get("beforeSha256") != Catalog().snapshot_sha256 or
            report.get("afterSha256") != report.get("beforeSha256") or
            len([row for row in frames if row.get("kind") == "operation" and
                 row.get("mode") == selected.mode and row.get("profile") == selected.profile and
                 row.get("format") == selected.format]) != 1 or
            len([row for row in frames if row.get("kind") == "cleanup" and row.get("closed") is True]) != 1 or
            len([row for row in frames if row.get("kind") == "done" and row.get("ok") is True]) != 1):
        return False
    if any(not row.get("ok") or not row.get("executed") or row.get("envelopeBytes", 0) <= 0 or
           row.get("profile") != selected.profile for row in receipts):
        return False
    ids = [row.get("callId") for row in receipts]
    if len(set(ids)) != len(ids) or not all(isinstance(item, str) and item for item in ids):
        return False
    for receipt in receipts:
        envelope = receipt.get("envelope")
        if (not isinstance(envelope, dict) or envelope.get("isError") is not False or
                not isinstance(envelope.get("content"), list) or len(envelope["content"]) != 1 or
                envelope["content"][0].get("type") != "text"):
            return False
        serialized = json.dumps(envelope, ensure_ascii=False, separators=(",", ":")).encode()
        try:
            payload = json.loads(envelope["content"][0]["text"])
        except (TypeError, ValueError):
            return False
        if (receipt.get("envelopeBytes") != len(serialized) or receipt.get("resultSha256") != sha(serialized) or
                receipt.get("payload") != payload or payload.get("callId") != receipt["callId"]):
            return False
    admissions = [row.get("callId") for row in frames if row.get("kind") == "admitted"]
    results = [row for row in frames if row.get("kind") == "tool-result"]
    receipt_frames = [row for row in frames if row.get("kind") == "receipt"]
    if (sorted(admissions) != sorted(ids) or sorted(row.get("callId") for row in results) != sorted(ids) or
            sorted(row.get("callId") for row in receipt_frames) != sorted(ids) or
            any(row.get("isError") is not False or (selected.mode == "live" and row.get("containsReceipt") is not True)
                for row in results)):
        return False
    summary = report.get("summary")
    if summary != summarize(receipts, model_calls=summary.get("modelCalls", -1) if isinstance(summary, dict) else -1,
                            cost=summary.get("reportedSdkUsd") if isinstance(summary, dict) else None):
        return False
    if selected.mode == "prepared":
        if (report.get("native") is not False or report.get("scripted") is not True or
                summary["modelCalls"] != 0 or summary["reportedSdkUsd"] != 0):
            return False
    else:
        cost = summary["reportedSdkUsd"]
        terminal = report.get("terminal")
        if (report.get("native") is not True or report.get("scripted") is not False or summary["modelCalls"] != 1 or
                not isinstance(cost, (int, float)) or not math.isfinite(cost) or not 0 <= cost <= 0.25 or
                not isinstance(terminal, dict) or terminal.get("subtype") != "success" or
                terminal.get("isError") is not False or terminal.get("costUsd") != cost or
                not terminal.get("sessionId") or not terminal.get("resultUuid") or
                report.get("exception") or
                len([row for row in frames if row.get("kind") == "terminal" and
                     row.get("sessionId") == terminal.get("sessionId") and
                     row.get("resultUuid") == terminal.get("resultUuid")]) != 1):
            return False
        initialization = [row for row in frames if row.get("kind") == "init"]
        if len(initialization) != 1 or initialization[0].get("sessionId") != terminal["sessionId"]:
            return False
    if selected.profile != "focused":
        return False
    searches = [row for row in receipts if row["tool"] == "catalog_search"]
    details = [row for row in receipts if row["tool"] == "catalog_get"]
    if not searches or not details or any(row["input"]["format"] != selected.format for row in searches + details):
        return False
    filters = {key: searches[0]["input"][key] for key in ("category", "maxPriceCents", "inStock", "pageSize", "format")}
    if (filters["category"] != "camping" or filters["maxPriceCents"] != 3000 or
            filters["inStock"] is not True or filters["format"] != selected.format or
            filters["pageSize"] not in ({1} if selected.mode == "prepared" else {1, 2})):
        return False
    expected_cursor = None
    for row in searches:
        if row["input"]["cursor"] != expected_cursor or any(row["input"][key] != value for key, value in filters.items()):
            return False
        expected_cursor = row["nextCursor"]
        if expected_cursor is None and row is not searches[-1]:
            return False
    if expected_cursor is not None or tuple(summary["searchIds"]) != EXPECTED or tuple(summary["detailIds"]) != EXPECTED:
        return False
    if sorted(row["input"]["sku"] for row in details) != sorted(EXPECTED):
        return False
    return True


async def prepared(selected: DesignInput, run_id: uuid.UUID, abort: asyncio.Event | None = None,
                   on_frame: Any = None, catalog: Catalog | None = None) -> dict[str, Any]:
    catalog = catalog or Catalog()
    before = catalog.snapshot_sha256
    frames: list[dict[str, Any]] = []
    receipts: list[dict[str, Any]] = []
    interrupted = False
    overflow = False
    error: str | None = None

    async def emit(kind: str, **data: Any) -> None:
        nonlocal overflow
        frame = {"runId": str(run_id), "seq": len(frames) + 1, "kind": kind, **data}
        if len(frames) >= ROW_LIMIT or len(json.dumps(frames, default=str)) + len(json.dumps(frame, default=str)) > BYTE_LIMIT:
            overflow = True
            raise OverflowError("Bounded tool trace exceeded")
        frames.append(frame)
        if on_frame is not None:
            await on_frame(frame)

    async def invoke(tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if abort is not None and abort.is_set():
            raise asyncio.CancelledError
        call_id = str(uuid.uuid4())
        await emit("admitted", tool=tool, callId=call_id)
        row = catalog.invoke(selected.profile, tool, arguments, call_id=call_id)
        receipts.append(row)
        await emit("receipt", tool=tool, callId=row["callId"], envelopeBytes=row["envelopeBytes"],
                   executed=row["executed"], errorCode=row["errorCode"])
        await emit("tool-result", tool=tool, callId=row["callId"], isError=row["envelope"]["isError"],
                   resultSha256=row["resultSha256"])
        await asyncio.sleep(0.01)
        return row

    await emit("operation", mode="prepared", profile=selected.profile, format=selected.format)
    try:
        if selected.profile == "vague":
            await invoke("lookup", {"q": "camping"})
        else:
            arguments: dict[str, Any] = {"category": "camping", "maxPriceCents": 3000,
                                         "inStock": True, "pageSize": 1, "format": selected.format}
            cursor: str | None = None
            seen: set[str] = set()
            found: list[str] = []
            for _ in range(8):
                row = await invoke("catalog_search", {**arguments, **({"cursor": cursor} if cursor else {})})
                found.extend(row["returnedIds"])
                cursor = row["nextCursor"]
                if cursor is None:
                    break
                if cursor in seen:
                    raise ValueError("Repeated cursor")
                seen.add(cursor)
            else:
                raise ValueError("Page cap reached")
            for sku in found:
                await invoke("catalog_get", {"sku": sku, "format": selected.format})
    except asyncio.CancelledError:
        interrupted = True
    except Exception as exc:
        error = type(exc).__name__
    after = catalog.current_hash()
    summary = summarize(receipts, model_calls=0, cost=0.0)
    await emit("summary", **summary)
    await emit("cleanup", closed=True)
    await emit("done", ok=not interrupted and not error and not overflow)
    return {"runId": str(run_id), "mode": "prepared", "profile": selected.profile,
            "format": selected.format, "native": False, "frames": frames,
            "receipts": receipts, "summary": summary, "beforeSha256": before,
            "afterSha256": after, "closed": True, "interrupted": interrupted,
            "overflow": overflow, "error": error, "scripted": True}
