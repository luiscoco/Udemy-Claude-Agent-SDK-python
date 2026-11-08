"""Lesson 53 fixed collector, reload, causal diagnosis and bounded log boundaries."""

import asyncio
import copy
import json
import uuid

import pytest

from agent_lab.debug_lab import (
    LOG_LIMIT,
    SCENARIOS,
    DebugInput,
    bounded_debug_log,
    comparison,
    criterion,
    prepared_run,
)
from agent_lab.debug_store import DebugStore, MissingBundle


@pytest.mark.asyncio
async def test_all_seven_prepared_replays_have_owned_saved_evidence(tmp_path):
    store = DebugStore(tmp_path / "lesson-53")
    expected = {"success": [], "denied": ["permission-denied"], "missing": ["missing-file"],
                "max-turns": ["max-turns"], "startup": ["startup"],
                "api-error": ["api-error", "iterator-exception"], "truncated": ["missing-terminal"]}
    for name in SCENARIOS:
        selected = DebugInput.model_validate({"scenario": name})
        identifier = uuid.uuid4()
        bundle = await prepared_run(selected, store.root, identifier)
        loaded = store.save(bundle)
        assert criterion(str(identifier), selected, bundle, loaded)
        assert [row["code"] for row in bundle["findings"]] == expected[name]
        assert bundle["modelCalls"] == 0 and bundle["reportedSdkUsd"] == 0
        assert loaded["source"] == "persisted-file-reload"
        assert "sk-ant-synthetic" not in json.dumps(bundle)
        assert store.load(identifier) == loaded


@pytest.mark.asyncio
async def test_tampering_and_one_variable_scope(tmp_path):
    store = DebugStore(tmp_path / "lesson-53")
    denied = DebugInput(scenario="denied")
    denied_id = uuid.uuid4()
    original = await prepared_run(denied, store.root, denied_id)
    loaded = store.save(original)
    forged = copy.deepcopy(original)
    forged["rows"][1]["data"]["allowed"] = True
    assert not criterion(str(denied_id), denied, forged, loaded)
    forged = copy.deepcopy(original)
    forged["rows"][2]["data"]["callId"] = "foreign"
    assert not criterion(str(denied_id), denied, forged, loaded)
    assert not criterion(str(uuid.uuid4()), denied, original, loaded)
    with pytest.raises(MissingBundle):
        store.load(uuid.uuid4())

    success = DebugInput(scenario="success")
    success_id = uuid.uuid4()
    candidate = await prepared_run(success, store.root, success_id)
    one = comparison(original, candidate)
    assert one["oneVariable"] and one["changed"] == ["policy"]
    two = copy.deepcopy(candidate)
    two["effectiveConfig"]["captureLog"] = False
    assert not comparison(original, two)["oneVariable"]
    assert not comparison({**original, "mode": "live"}, candidate)["oneVariable"]


def test_bounded_log_missing_truncation_redaction_and_descriptor_close(tmp_path, monkeypatch):
    path = tmp_path / "raw-debug.log"
    assert bounded_debug_log(path, tmp_path)["found"] is False
    path.write_bytes(b"ANTHROPIC_API_KEY=sk-ant-synthetic-secret\n" + b"x" * (LOG_LIMIT + 200))
    result = bounded_debug_log(path, tmp_path)
    assert result["found"] and result["truncated"]
    assert "sk-ant-synthetic-secret" not in result["text"]
    assert len(result["text"].encode()) <= LOG_LIMIT
    opened: list[int] = []
    real_close = __import__("os").close

    def close(descriptor: int) -> None:
        opened.append(descriptor)
        real_close(descriptor)

    monkeypatch.setattr("agent_lab.debug_lab.os.close", close)
    bounded_debug_log(path, tmp_path)
    assert len(opened) == 1
    with pytest.raises(ValueError):
        bounded_debug_log(path, tmp_path / "foreign")


@pytest.mark.asyncio
async def test_cancelled_prepared_run_saves_partial_nonpassing_bundle(tmp_path):
    abort = asyncio.Event()
    selected = DebugInput(scenario="success")
    identifier = uuid.uuid4()
    rows = []

    async def on_row(row):
        rows.append(row)
        abort.set()

    store = DebugStore(tmp_path / "lesson-53")
    bundle = await prepared_run(selected, store.root, identifier, abort, on_row)
    loaded = store.save(bundle)
    assert len(rows) == 1 and bundle["interrupted"] and bundle["closed"]
    assert not criterion(str(identifier), selected, bundle, loaded)
