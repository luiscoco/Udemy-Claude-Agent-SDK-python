"""Lesson 51 host suite executes real contracts without a provider."""

import asyncio
import uuid

import pytest

from agent_lab.offline_lab import (
    CASES,
    Generation,
    evaluate_suite,
    replay,
    run_offline_host,
    run_suite,
)


@pytest.mark.asyncio
async def test_complete_mutated_filtered_and_forged_suite(tmp_path) -> None:
    complete = await run_suite(tmp_path)
    assert complete["summary"] == {"total": 16, "passed": 16, "failed": 0,
                                    "modelCalls": 0, "actualBilledUsd": 0}
    assert complete["experiment_passed"] and complete["cleanup"]
    assert [row["caseId"] for row in complete["assertions"]] == [case for case, _ in CASES]
    altered = await run_suite(tmp_path, mutation=True)
    assert altered["summary"]["passed"] == 15
    assert altered["summary"]["failed"] == 1
    assert [row["caseId"] for row in altered["assertions"] if not row["passed"]] == ["denial-policy"]
    assert not altered["experiment_passed"]
    for group, count in (("contracts", 6), ("store", 2), ("replay", 8)):
        selected = await run_suite(tmp_path, group=group)
        assert selected["summary"]["total"] == count
        assert selected["summary"]["failed"] == 0
        assert not selected["experiment_passed"]
    for change in ({"summary": {"total": 16, "passed": 15, "failed": 1,
                                "modelCalls": 0, "actualBilledUsd": 0}},
                   {"modelCalls": 1}, {"run": str(uuid.uuid4())},
                   {"assertions": complete["assertions"][:-1]}):
        assert not evaluate_suite(complete | change)
    generation = Generation()
    old, fresh = generation.issue(), generation.issue()
    assert not generation.accepts(old) and generation.accepts(fresh)


@pytest.mark.asyncio
async def test_all_synthetic_replay_outcomes_and_cleanup(tmp_path) -> None:
    expected = {"success": "success", "budget": "budget", "api-error": "api-error",
                "invalid": "invalid", "truncated": "truncated",
                "malformed-tool": "invalid-tool"}
    for scenario, status in expected.items():
        report = await replay(tmp_path, scenario)
        assert report["status"] == status and report["modelCalls"] == 0
        assert report["actualBilledUsd"] == 0 and report["closed"]
        assert not report["experiment_passed"]
        if scenario == "success":
            assert report["handler"] == [{"call": "call-1", "orderId": "order-ada",
                                          "source": "actual-DeskStore.snapshot"}]
        if scenario == "malformed-tool":
            assert report["handlerCount"] == 0
    for scenario in ("foreign-result", "duplicate-terminal"):
        assert (await run_offline_host(tmp_path, scenario))["status"] == "invalid"
    aborted = asyncio.Event()
    aborted.set()
    cancelled = await run_offline_host(tmp_path, "success", abort=aborted)
    assert cancelled["status"] == "cancelled" and cancelled["closed"]


@pytest.mark.asyncio
async def test_mid_suite_abort_suppresses_summary(tmp_path) -> None:
    stop = asyncio.Event()
    seen = []

    async def observe(frame):
        seen.append(frame)
        if frame["kind"] == "assertion" and len(seen) == 3:
            stop.set()

    result = await run_suite(tmp_path, abort=stop, emit=observe)
    assert result["status"] == "cancelled"
    assert "summary" not in result and len(result["assertions"]) == 3
    assert not result["experiment_passed"] and result["cleanup"]
