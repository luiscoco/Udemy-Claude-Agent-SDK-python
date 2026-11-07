"""Lesson 47 host ownership, correlation, and limiter checks."""

import asyncio
from copy import deepcopy

import pytest

from agent_lab.orchestra_lab import (
    ACTIONS,
    FairLimiter,
    analyst_gate,
    check_report,
    evaluate,
    expected_report,
    local_action,
    truth,
)


def test_sales_truth_and_two_report_checks() -> None:
    assert [truth(region) for region in ("north", "south", "east")] == [
        (55, "P2"), (69, "P1"), (86, "P2")]
    assert check_report("Introduction\n" + expected_report("north"), "north")[0]
    assert not check_report("REGION=north; TOTAL=54; BEST=P2", "north")[0]
    assert analyst_gate("**" + expected_report("north") + "**")["decision"] == "block"
    assert analyst_gate(expected_report("north"))["accepted"]
    assert analyst_gate("wrong", stop_hook_active=True)["decision"] == "second-stop-bypass"
    assert not check_report("wrong", "north")[0]


@pytest.mark.asyncio
async def test_all_local_patterns_match_worker_evidence(tmp_path) -> None:
    for action in ACTIONS:
        report = await local_action(action, base=tmp_path / action)
        assert report["experiment_passed"], action
        assert report["native"] is False
        assert all(row["source"] == "host-checker" for row in report["verdicts"])
        assert evaluate(report, tmp_path / action / "work")
        mutated = deepcopy(report)
        mutated["ends"][-1]["id"] = "other"
        assert not evaluate(mutated, tmp_path / action / "work")
        if action == "fanout":
            assert max(row["active"] for row in report["limiter"]) <= 2


@pytest.mark.asyncio
async def test_failures_do_not_become_passing_work(tmp_path) -> None:
    cases = (("fanout", "missing-file"), ("fanout", "cancel-worker"),
             ("fanout", "wrong-report"), ("pipeline", "missing"),
             ("hierarchy", "foreign"), ("evaluator", "failed"))
    for index, (action, scenario) in enumerate(cases):
        report = await local_action(action, scenario=scenario, base=tmp_path / str(index))
        assert not report["experiment_passed"]
    missing = await local_action("fanout", scenario="missing-file", base=tmp_path / "missing")
    assert not (tmp_path / "missing" / "work" / "east.csv").exists()
    assert missing["errors"] == [{"role": "east", "type": "FileNotFoundError"}]
    cancelled = await local_action("fanout", scenario="cancel-worker", base=tmp_path / "cancel")
    assert {row["role"] for row in cancelled["ends"] if row["status"] == "completed"} == {"south", "east"}


@pytest.mark.asyncio
async def test_limiter_queues_and_releases_after_failure() -> None:
    limiter = FairLimiter(1)
    await limiter.acquire()
    order: list[str] = []

    async def queued() -> None:
        await limiter.acquire()
        try:
            order.append("started")
            raise ValueError("intentional")
        finally:
            limiter.release()

    task = asyncio.create_task(queued())
    await asyncio.sleep(0)
    assert limiter.active == 1 and len(limiter.waiters) == 1
    limiter.release()
    with pytest.raises(ValueError):
        await task
    assert order == ["started"]
    assert limiter.active == 0 and not limiter.waiters
    await limiter.acquire()
    waiting = asyncio.create_task(limiter.acquire())
    await asyncio.sleep(0)
    limiter.cancel_waiters()
    with pytest.raises(asyncio.CancelledError):
        await waiting
    limiter.release()
    assert limiter.active == 0
