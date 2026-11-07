"""Lesson 49 uses real owned processes and independently checked machine reports."""

import asyncio
import json
import uuid

import pytest

from agent_lab.config import ROOT
from agent_lab.headless_lab import (
    ACTIONS,
    LIMIT_CODES,
    evaluate,
    local_action,
    mapped_exit,
    report_valid,
    worker_action,
)


@pytest.mark.asyncio
async def test_four_local_actions_and_negative_evidence() -> None:
    for action in ACTIONS:
        report = await local_action(action)
        assert report["experiment_passed"] and evaluate(report)
        assert report["native"] is False
        assert "ANTHROPIC_API_KEY" not in json.dumps(report)
    limits = await local_action("limits")
    assert [row["policy_exit"] for row in limits["outcomes"]] == list(LIMIT_CODES)
    assert limits["outcomes"][-2]["process"]["timed_out"]
    assert limits["outcomes"][-1]["process"]["missing"]
    ci = await local_action("ci")
    assert [row["ci_exit"] for row in ci["outcomes"]] == [0, 20]
    for scenario in ("missing", "foreign", "failed"):
        assert not (await local_action("headless", scenario))["experiment_passed"]
        assert not (await local_action("deploy", scenario))["experiment_passed"]


@pytest.mark.asyncio
async def test_worker_real_job_deadline_and_tcp_close() -> None:
    result = await worker_action(str(uuid.uuid4()),
                                 ROOT / ".lab-data/headless-worker-deadline" / uuid.uuid4().hex,
                                 release=False)
    assert result["job_status"] == 408
    assert result["job_response"]["status"] == 408
    assert result["exit"] == 0 and result["closed_tcp"]
    assert [item["kind"] for item in result["events"]] == [
        "listening", "job-start", "draining", "job-end", "closed"]


def test_exact_report_and_host_policy_mapping() -> None:
    run_id = str(uuid.uuid4())
    assert report_valid({"run": run_id, "verdict": "PASS", "issues": []}, run_id, "clean")
    assert not report_valid({"run": "foreign", "verdict": "PASS", "issues": []}, run_id, "clean")
    assert not report_valid({"run": run_id, "verdict": "PASS", "issues": [], "extra": 1}, run_id, "clean")
    base = {"actual_exit": 0, "cancelled": False, "timed_out": False,
            "missing": False, "overflow": False}
    terminal = {"is_error": False, "cost_usd": 0, "permission_denials": []}
    assert mapped_exit(base, terminal) == 0
    assert mapped_exit(base | {"cancelled": True}, terminal) == 130
    assert mapped_exit(base | {"timed_out": True}, terminal) == 124
    assert mapped_exit(base | {"missing": True}, terminal) == 127
    assert mapped_exit(base | {"actual_exit": 1}, terminal) == 10
    assert mapped_exit(base, None) == 11
    assert mapped_exit(base, terminal | {"permission_denials": ["denied"]}) == 12


@pytest.mark.asyncio
async def test_process_cancellation_propagates_and_ends_promptly() -> None:
    from agent_lab.headless_lab import environment, fixture, run_process

    owned = fixture(ROOT / ".lab-data/headless-cancel-test" / uuid.uuid4().hex)
    task = asyncio.create_task(run_process(
        __import__("pathlib").Path(__import__("sys").executable),
        [str(owned["child"]), "timeout", str(uuid.uuid4()), "PASS", "none"],
        cwd=owned["folder"], env=environment(owned["home"]), deadline_seconds=20))
    await asyncio.sleep(0.1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 3)
