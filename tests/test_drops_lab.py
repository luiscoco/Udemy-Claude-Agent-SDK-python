"""Lesson 40 active-chain, persisted fork and guard evidence checks."""

import uuid
from pathlib import Path

import pytest
from claude_agent_sdk._errors import ResultError

from agent_lab.config import Settings
from agent_lab.drops_lab import (
    active_chain,
    build_prepared,
    cases_prepared,
    classify_refusal,
    dry,
    local,
    session_file,
    state,
    terminal_from_result_error,
    undo,
)
from agent_lab.models import RunRequest


async def test_prepared_chain_excludes_inactive_branch_and_keeps_queued_attachment(tmp_path: Path) -> None:
    built = await build_prepared(tmp_path)
    assert built["build_passed"]
    snapshot = state(tmp_path)
    summary = snapshot["summary"]
    assert len(summary["turns"]) == 4 and summary["inactive_records"] == 1
    assert len(summary["turns"][2]["queued"]) == 1
    assert summary["turns"][2]["queued"][0]["prompt"] == built["queued"]["text"]
    assert not summary["turns"][2]["prompt"].startswith("QUEUED_")
    assert dry(Settings())["all_serialized"]


@pytest.mark.parametrize("recover", [False, True])
async def test_prepared_exact_and_unsafe_comparison(tmp_path: Path, recover: bool) -> None:
    built = await build_prepared(tmp_path)
    report = await cases_prepared(tmp_path, built["build_id"], recover)
    assert report["experiment_passed"]
    assert report["exact_drop_verified"] and report["unsafe_refusal_verified"]
    assert report["source_unchanged"] and report["ordered_evidence"]
    assert report["recovery_verified"]


@pytest.mark.parametrize("scenario", ["missing", "foreign", "duplicate", "interrupted", "tampered"])
async def test_prepared_negative_comparison(tmp_path: Path, scenario: str) -> None:
    built = await build_prepared(tmp_path)
    report = await cases_prepared(tmp_path, built["build_id"], True, scenario)
    assert not report["experiment_passed"]
    assert report["expected_check"] == "needs-review"


async def test_failed_build_does_not_replace_latest_pointer(tmp_path: Path) -> None:
    good = await build_prepared(tmp_path)
    failed = await build_prepared(tmp_path, "missing")
    assert not failed["build_passed"]
    assert state(tmp_path)["manifest"]["build_id"] == good["build_id"]


async def test_source_hash_tampering_refused(tmp_path: Path) -> None:
    built = await build_prepared(tmp_path)
    manifest = built["manifest"]
    path = session_file(tmp_path / built["build_id"] / "home", manifest["session_id"])
    raw = path.read_bytes()
    assert b"Oslo" in raw
    path.write_bytes(raw.replace(b"Oslo", b"Rome", 1))
    with pytest.raises(ValueError, match="changed"):
        state(tmp_path, built["build_id"])


@pytest.mark.parametrize("fault", ["duplicate", "missing-parent", "cycle"])
def test_chain_rejects_corrupt_ancestry(fault: str) -> None:
    first, second = str(uuid.uuid4()), str(uuid.uuid4())
    rows = [{"type": "user", "uuid": first, "parentUuid": None,
             "message": {"role": "user", "content": "first"}},
            {"type": "assistant", "uuid": second, "parentUuid": first,
             "message": {"role": "assistant", "content": "done"}}]
    if fault == "duplicate":
        rows.append(dict(rows[1]))
    elif fault == "missing-parent":
        rows[1]["parentUuid"] = str(uuid.uuid4())
    else:
        rows[0]["parentUuid"] = second
    with pytest.raises(ValueError):
        active_chain(rows)


async def test_undo_is_one_experiment_and_never_full_comparison(tmp_path: Path) -> None:
    built = await build_prepared(tmp_path)
    single = await undo(tmp_path, built["build_id"], "prepared", 4, "last", Settings())
    assert not single["full_comparison_claimed"]
    assert single["single_experiment"]["fork"]
    refused = await undo(tmp_path, built["build_id"], "prepared", 3, "last", Settings())
    assert classify_refusal(refused["single_experiment"])[0]


def test_connection_error_is_not_typed_guard_result() -> None:
    assert classify_refusal({"startup_error": "Resume rejected by --resume-drops-turn: queued content"}) == (False, None)
    typed = {"result": {"uuid": str(uuid.uuid4()), "session_id": str(uuid.uuid4()),
                        "subtype": "error_during_execution", "cost_usd": 0.0,
                        "errors": ["Resume rejected by --resume-drops-turn: queued content"]}}
    assert classify_refusal(typed) == (True, "queued content")


def test_only_a_real_cli_result_frame_in_result_error_can_be_typed() -> None:
    uid, sid = str(uuid.uuid4()), str(uuid.uuid4())
    raw = {"type": "result", "uuid": uid, "session_id": sid,
           "subtype": "error_during_execution", "is_error": True,
           "errors": ["Resume rejected by --resume-drops-turn: queued content"],
           "total_cost_usd": 0, "duration_ms": 1, "duration_api_ms": 0, "num_turns": 0}
    parsed = terminal_from_result_error(ResultError("startup error", data=raw, exit_code=1))
    assert parsed and parsed["evidence_origin"].startswith("CLI result frame")
    assert classify_refusal({"result": parsed}) == (True, "queued content")
    assert terminal_from_result_error(ResultError("same exception text")) is None


async def test_local_exercise_labels_authored_evidence(tmp_path: Path) -> None:
    proof = await local(tmp_path, RunRequest())
    assert proof["experiment_passed"]
    assert proof["experiment"]["source_label"].startswith("owned persisted")
    assert proof["experiment"]["build"]["mode"] == "prepared"
