"""Lesson 54 real catalog effects, cursor integrity and bounded grading."""

import asyncio
import copy
import json
import uuid

import pytest

from agent_lab.tool_design_catalog import Catalog
from agent_lab.tool_design_lab import DesignInput, grade, prepared


def test_direct_catalog_validation_errors_and_bytes() -> None:
    catalog = Catalog()
    before = catalog.snapshot_sha256
    broad = catalog.invoke("vague", "lookup", {"q": "camping"})
    assert broad["executed"] and broad["ok"] and broad["envelopeBytes"] > 3000
    assert {row["id"] for row in broad["payload"]["products"]} == {
        "SKU-101", "SKU-102", "SKU-103", "SKU-104"}
    invalid = catalog.invoke("focused", "catalog_get", {"sku": "Trail mug"})
    assert not invalid["executed"] and invalid["errorCode"] == "INVALID_INPUT"
    assert invalid["envelope"]["isError"] and "recovery" in invalid["payload"]
    missing = catalog.invoke("focused", "catalog_get", {"sku": "SKU-999"})
    assert missing["executed"] and missing["errorCode"] == "NOT_FOUND"
    assert catalog.current_hash() == before
    assert json.loads(catalog.invoke("focused", "catalog_get", {"sku": "SKU-101"})[
        "envelope"]["content"][0]["text"])["item"]["id"] == "SKU-101"
    with pytest.raises(ValueError):
        catalog.invoke("vague", "catalog_get", {"sku": "SKU-101"})


def test_search_cursor_snapshot_filters_and_empty_success(tmp_path) -> None:
    catalog = Catalog()
    query = {"category": "camping", "maxPriceCents": 3000, "pageSize": 1}
    first = catalog.invoke("focused", "catalog_search", query)
    assert first["returnedIds"] == ["SKU-101"] and first["nextCursor"]
    second = catalog.invoke("focused", "catalog_search", {**query, "cursor": first["nextCursor"]})
    assert second["returnedIds"] == ["SKU-104"] and second["nextCursor"] is None
    empty = catalog.invoke("focused", "catalog_search", {**query, "maxPriceCents": 0})
    assert empty["ok"] and empty["payload"]["items"] == [] and empty["nextCursor"] is None
    for changed in ({**query, "pageSize": 2, "cursor": first["nextCursor"]},
                    {**query, "cursor": "garbage"},
                    {**query, "cursor": first["nextCursor"] + "x"}):
        row = catalog.invoke("focused", "catalog_search", changed)
        assert row["errorCode"] == "CURSOR_MISMATCH" and not row["executed"]
    other = tmp_path / "catalog.json"
    other.write_bytes(catalog.raw.replace(b"Desk flask", b"Office flask"))
    stale = Catalog(other).invoke("focused", "catalog_search", {**query, "cursor": first["nextCursor"]})
    assert stale["errorCode"] == "CURSOR_MISMATCH"


@pytest.mark.asyncio
async def test_prepared_both_profiles_formats_and_forgery() -> None:
    for format in ("concise", "detailed"):
        focused = DesignInput(profile="focused", format=format)
        good = await prepared(focused, uuid.uuid4())
        assert grade(focused, good)
        assert good["summary"]["searchIds"] == ["SKU-101", "SKU-104"]
        assert good["summary"]["detailIds"] == ["SKU-101", "SKU-104"]
        assert good["summary"]["modelCalls"] == 0 and good["summary"]["reportedSdkUsd"] == 0
        vague = DesignInput(profile="vague", format=format)
        broad = await prepared(vague, uuid.uuid4())
        assert not grade(vague, broad) and broad["summary"]["calls"] == 1
        forged = copy.deepcopy(good)
        forged["frames"][1]["runId"] = str(uuid.uuid4())
        assert not grade(focused, forged)
        forged = copy.deepcopy(good)
        forged["frames"] = [row for row in forged["frames"] if row["kind"] != "tool-result"]
        assert not grade(focused, forged)
        forged = copy.deepcopy(good)
        forged["receipts"][1]["nextCursor"] = "broken"
        assert not grade(focused, forged)


@pytest.mark.asyncio
async def test_prepared_stop_needs_review() -> None:
    abort = asyncio.Event()
    selected = DesignInput()

    async def observe(frame):
        if frame["kind"] == "tool-result":
            abort.set()

    report = await prepared(selected, uuid.uuid4(), abort, observe)
    assert report["interrupted"] and report["closed"] and not grade(selected, report)
