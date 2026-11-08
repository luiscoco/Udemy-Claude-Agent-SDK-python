"""Lesson 55 evidence comes from fixed offline contracts and unchanged dependencies."""

import copy
import subprocess
import sys

import pytest
from pydantic import ValidationError

from agent_lab.upgrading_lab import (
    SCENARIOS,
    RunInput,
    TransitionInput,
    adapt_stream,
    assess_candidate,
    candidate,
    criterion,
    dependency_snapshot,
    metric_gate,
    permission_probe,
    run_upgrade,
    runtime_inventory,
    transition,
)


def test_all_fixed_scenarios_and_dependency_identity() -> None:
    before = dependency_snapshot()
    inventory = runtime_inventory()
    assert inventory["consistent"]
    assert inventory["declaredPin"] == "claude-agent-sdk==0.2.174"
    assert all(inventory["publicExports"].values())
    for scenario in SCENARIOS:
        selected = RunInput(scenario=scenario)
        report = run_upgrade(selected)
        assert criterion(selected, report)
        assert [gate["name"] for gate in report["gates"]] == ["exports", "stream", "permissions", "eval"]
        assert report["eligible"] is (scenario == "compatible")
        assert report["before"] == report["after"] == before
        if scenario != "compatible":
            assert any(not gate["passed"] for gate in report["gates"])
    assert dependency_snapshot() == before


def test_stream_adapter_requires_correlated_evidence() -> None:
    messages = candidate("compatible")["messages"]
    assert adapt_stream(messages)["passed"]
    assert adapt_stream(messages)["unknownAdditiveCount"] == 1
    for mutation in (lambda rows: rows.pop(0),
                     lambda rows: rows.append(copy.deepcopy(rows[-1])),
                     lambda rows: rows[-1].update(session_id="foreign"),
                     lambda rows: rows[1].update(callId="foreign"),
                     lambda rows: rows[2].update(is_error=True),
                     lambda rows: rows[3].update(status="failed")):
        changed = copy.deepcopy(messages)
        mutation(changed)
        assert not adapt_stream(changed)["passed"]


def test_permission_and_metric_boundaries() -> None:
    assert permission_probe(False)["passed"]
    assert not permission_probe(True)["passed"]
    baseline = {"correctness": 0.94, "costUsd": 0.01, "latencyMs": 1000}
    assert metric_gate({"correctness": 0.92, "costUsd": 0.012, "latencyMs": 1250}, baseline)["passed"]
    assert metric_gate({"correctness": 1, "costUsd": 0, "latencyMs": 0}, baseline)["passed"]
    for value in (None, float("nan"), float("inf"), -1, True, "0.94"):
        assert not metric_gate({"correctness": value, "costUsd": 0.01, "latencyMs": 1000}, baseline)["passed"]
    assert not metric_gate({"correctness": 0.919, "costUsd": 0.01, "latencyMs": 1000}, baseline)["passed"]
    assert not metric_gate({"correctness": 0.94, "costUsd": 0.0121, "latencyMs": 1000}, baseline)["passed"]


def test_transition_order_and_forged_evidence() -> None:
    assert transition(TransitionInput(scenario="compatible", state="checked", action="start-canary"))["newState"] == "canary"
    assert transition(TransitionInput(scenario="compatible", state="canary", action="promote"))["newState"] == "promoted"
    assert transition(TransitionInput(scenario="compatible", state="promoted", action="rollback"))["newState"] == "rolled-back"
    assert transition(TransitionInput(scenario="removed-export", state="canary", action="rollback"))["newState"] == "rolled-back"
    for selected in (TransitionInput(scenario="compatible", state="baseline", action="promote"),
                     TransitionInput(scenario="compatible", state="rolled-back", action="promote"),
                     TransitionInput(scenario="removed-export", state="checked", action="start-canary")):
        with pytest.raises(ValueError):
            transition(selected)
    selected = RunInput(scenario="compatible")
    report = run_upgrade(selected)
    for mutation in (lambda row: row.update(scenario="removed-export"),
                     lambda row: row.update(complete=False),
                     lambda row: row["gates"][1].update(passed=False),
                     lambda row: row["before"].update(lockSha256="forged"),
                     lambda row: row.update(modelCalls=1)):
        forged = copy.deepcopy(report)
        mutation(forged)
        assert not criterion(selected, forged)
    assert assess_candidate("missing-evidence")["eligible"] is False


def test_strict_offline_inputs() -> None:
    for payload in ({"scenario": "unknown"}, {"scenario": "compatible", "live": True},
                    {"scenario": "compatible", "command": "uv sync"}, {"scenario": "compatible", "eligible": True}):
        with pytest.raises(ValidationError):
            RunInput.model_validate(payload)
    with pytest.raises(ValidationError):
        TransitionInput.model_validate({"scenario": "compatible", "state": "baseline", "action": "install"})


def test_standalone_guarded_cli_rejects_paid_flags() -> None:
    result = subprocess.run([sys.executable, "scripts/upgrading_check.py", "--live"],
                            capture_output=True, text=True, check=False)
    assert result.returncode == 2
    assert "accepts no arguments" in result.stderr
