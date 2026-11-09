"""Lesson 58: bounded catalog, transparent local search, and owned refund ledger."""

from __future__ import annotations

import hashlib
import json
import math
import re
import threading
import uuid
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from agent_lab.config import ROOT

FIXTURE = ROOT / "fixtures/tool-search/catalog.json"
CRITERION = "A native ToolSearch reference precedes an exactly admitted refund, and the host verifies one owned ledger entry."
IGNORED = {"the", "a", "an", "to", "for", "and", "or", "of", "in", "with", "please", "tool", "tools"}
REFUND_ARGS = {"invoiceId": "INV-2042", "amountCents": 4900,
               "currency": "EUR", "reason": "duplicate-charge"}
_LOCK = threading.Lock()


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    metadata: Literal["clear", "vague"] = "clear"
    searchMode: str = "true"
    alwaysLoad: bool = False

    @field_validator("searchMode")
    @classmethod
    def valid_mode(cls, value: str) -> str:
        if value not in {"true", "false", "auto"} and not (
            re.fullmatch(r"auto:(?:100|[1-9]?\d)", value)
        ):
            raise ValueError("searchMode must be true, false, auto, or auto:N for N=0..100")
        return value


class SearchInput(Config):
    query: str = Field(default="refund duplicate charge", min_length=1, max_length=200)
    limit: int = Field(default=5, ge=1, le=10)

    @field_validator("query")
    @classmethod
    def trimmed(cls, value: str) -> str:
        if value != value.strip() or not value:
            raise ValueError("query must be nonempty and trimmed")
        return value


class PlanInput(Config):
    contextWindow: int = Field(default=200000, ge=1000, le=1000000)


class RunInput(Config):
    mode: Literal["prepared", "live"] = "prepared"
    query: str = Field(default="refund duplicate charge", min_length=1, max_length=200)
    consent: bool = False
    budget: float = Field(default=1, ge=0.15, le=1)

    @field_validator("query")
    @classmethod
    def trimmed(cls, value: str) -> str:
        return SearchInput.trimmed(value)


class MeasureInput(Config):
    consent: bool = False


def catalog(config: Config) -> list[dict[str, Any]]:
    base = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert len(base) == 64
    rows = []
    for item in base:
        row = dict(item)
        if row["name"] == "billing_refund_invoice" and config.metadata == "vague":
            row["name"] = "billing_op_7"
            row["description"] = "Billing operation."
            row.pop("searchHint", None)
        row["fullName"] = f"mcp__ops__{row['name']}"
        row["alwaysLoad"] = bool(config.alwaysLoad and row["name"] in {
            "billing_refund_invoice", "billing_op_7"})
        rows.append(row)
    assert len({r["name"] for r in rows}) == 64
    return rows


def tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", value.lower())) - IGNORED


def search(selected: SearchInput) -> dict[str, Any]:
    rows = catalog(selected)
    if selected.query.startswith("select:"):
        requested = [value.strip() for value in selected.query[7:].split(",")]
        hits = [(100, row) for row in rows if row["name"] in requested or row["fullName"] in requested]
    else:
        words = tokens(selected.query)
        hits = []
        for row in rows:
            name, hint, description = (row["name"].lower(), row.get("searchHint", "").lower(),
                                       row["description"].lower())
            score = sum(3 * (word in name) + 2 * (word in hint) + (word in description)
                        for word in words)
            if score > 0:
                hits.append((score, row))
    hits.sort(key=lambda pair: (-pair[0], pair[1]["name"]))
    top = hits[:selected.limit]
    return {"kind": "local-heuristic", "query": selected.query,
            "results": [{"name": row["name"], "fullName": row["fullName"], "score": score,
                         "definition": row} for score, row in top],
            "references": [row["fullName"] for _, row in top], "catalogCount": len(rows)}


def plan(selected: PlanInput) -> dict[str, Any]:
    rows = catalog(selected)
    estimates = {row["name"]: math.ceil(len(json.dumps(row, sort_keys=True, ensure_ascii=False,
                                                         separators=(",", ":"))) / 4) for row in rows}
    total = sum(estimates.values())
    threshold = None
    if selected.searchMode.startswith("auto"):
        percent = int(selected.searchMode[5:]) if ":" in selected.searchMode else 10
        threshold = selected.contextWindow * percent / 100
    deferred = selected.searchMode == "true" or (threshold is not None and total >= threshold)
    loaded = [row["name"] for row in rows if not deferred or row["alwaysLoad"]]
    waiting = [row["name"] for row in rows if row["name"] not in loaded]
    return {"kind": "local-character-estimate", "contextWindow": selected.contextWindow,
            "threshold": threshold, "estimatedTotal": total,
            "estimatedLoaded": sum(estimates[name] for name in loaded),
            "loaded": loaded, "deferred": waiting, "loadedCount": len(loaded),
            "deferredCount": len(waiting), "catalogCount": len(rows),
            "note": "ceil(serialized definition characters / 4); excludes ToolSearch and system overhead"}


def owned_dir(root: Path, run_id: str) -> Path:
    uuid.UUID(run_id)
    root = root.resolve()
    base_path = root / "lesson-58"
    base = base_path.resolve()
    if base_path.is_symlink() or base.parent != root:
        raise PermissionError("Lesson directory escaped owned root")
    target = base / run_id
    if target.parent != base or target.is_symlink():
        raise ValueError("Invalid owned path")
    return target


def new_ledger(root: Path, run_id: str) -> Path:
    owned = owned_dir(root, run_id)
    owned.mkdir(parents=True, exist_ok=False)
    (owned / ".owner").write_text(run_id, encoding="ascii")
    ledger = owned / "ledger.json"
    ledger.write_text('{"refunds":[]}', encoding="utf-8")
    return ledger


def verify_ledger(root: Path, run_id: str) -> tuple[dict[str, Any], str]:
    owned = owned_dir(root, run_id)
    marker = owned / ".owner"
    if (not owned.is_dir() or owned.is_symlink() or marker.is_symlink() or
            not marker.is_file() or marker.stat().st_nlink != 1 or
            marker.read_text(encoding="ascii") != run_id):
        raise PermissionError("Owned marker mismatch")
    path = owned / "ledger.json"
    stat = path.lstat()
    if not path.is_file() or path.is_symlink() or stat.st_nlink != 1 or stat.st_size > 4096:
        raise PermissionError("Invalid ledger")
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict) or not isinstance(value.get("refunds"), list):
        raise ValueError("Invalid ledger schema")
    return value, hashlib.sha256(raw).hexdigest()


def refund(root: Path, run_id: str, call_id: str, args: dict[str, Any]) -> dict[str, Any]:
    if args != REFUND_ARGS or type(args.get("amountCents")) is not int:
        return {"ok": False, "error": "exact synthetic invoice and refund arguments required"}
    with _LOCK:
        value, _ = verify_ledger(root, run_id)
        if value["refunds"]:
            return {"ok": False, "error": "already-recorded"}
        receipt = {"refundId": "RF-2042-1", "callId": call_id, "args": dict(args)}
        value["refunds"].append(receipt)
        path = owned_dir(root, run_id) / "ledger.json"
        temp = path.with_name(f".ledger-{uuid.uuid4()}.tmp")
        with temp.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(value, sort_keys=True, separators=(",", ":")))
        temp.replace(path)
        return {"ok": True, **receipt}


def prepared(selected: RunInput, root: Path, run_id: str | None = None) -> dict[str, Any]:
    run_id = run_id or str(uuid.uuid4())
    new_ledger(root, run_id)
    found = search(SearchInput(metadata=selected.metadata, searchMode=selected.searchMode,
                               alwaysLoad=selected.alwaysLoad, query=selected.query))
    target = "billing_op_7" if selected.metadata == "vague" else "billing_refund_invoice"
    discovered = f"mcp__ops__{target}" in found["references"]
    receipt = refund(root, run_id, "prepared-refund", REFUND_ARGS) if discovered else None
    ledger, digest = verify_ledger(root, run_id)
    # The ledger intentionally omits the transport-only `ok` flag.
    checked = bool(discovered and receipt and receipt.get("ok") and
                   ledger["refunds"] == [{k: receipt[k] for k in ("refundId", "callId", "args")}])
    return {"runId": run_id, "mode": "prepared", "metadata": selected.metadata,
            "search": found, "receipt": receipt, "ledger": ledger, "ledgerSha256": digest,
            "check": "pass" if checked else "needs-review", "native": False,
            "sdkQueries": 0, "costUsd": 0}
