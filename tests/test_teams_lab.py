"""Lesson 56 offline evidence is a fresh reducer state, not message prose."""

import copy

import pytest
from pydantic import ValidationError

from agent_lab.teams_lab import (
    ReplayInput,
    canonical_input,
    grade,
    replay_team,
    run_replay,
    walkthrough,
)


def test_walkthrough_prefixes_and_five_refusals() -> None:
    commands = walkthrough()
    assert len(commands) == 16
    for count in range(17):
        selected = canonical_input(count)
        report = run_replay(selected)
        assert len(report["state"]["receipts"]) == count
        assert report["modelCalls"] == report["reportedSdkUsd"] == 0
        assert grade(selected, report) is (count == 16)
    state = replay_team(commands)
    assert [row["code"] for row in state["receipts"] if not row["accepted"]] == [
        "dependency-incomplete", "task-already-owned", "shutdown-busy",
        "ack-requires-delivery", "evidence-rejected"]
    assert len(state["messages"]) == 1 and state["messages"][0]["status"] == "acknowledged"
    assert state["closed"]


def test_ownership_delivery_conflict_and_cleanup_refusals() -> None:
    send = {"type": "send", "actor": "researcher", "to": "reviewer", "id": "custom-1", "body": "peer evidence"}
    state = replay_team([send, send, {**send, "body": "changed"}])
    assert len(state["messages"]) == 1
    assert [row["code"] for row in state["receipts"]] == ["queued", "duplicate-retained", "message-id-conflict"]
    assert state["messages"][0]["body"] == "peer evidence"
    state = replay_team([send, {"type": "ack", "actor": "reviewer", "id": "custom-1"},
                         {"type": "deliver", "actor": "researcher"},
                         {"type": "deliver", "actor": "reviewer"},
                         {"type": "ack", "actor": "reviewer", "id": "custom-1"},
                         {"type": "cleanup", "actor": "lead"}])
    assert [row["accepted"] for row in state["receipts"]] == [True, False, False, True, True, False]
    assert not state["closed"] and all(task["status"] == "pending" for task in state["tasks"])
    closed = replay_team([*walkthrough(), send])
    assert closed["receipts"][-1]["code"] == "team-closed"
    assert len(closed["messages"]) == 1


def test_request_isolation_and_forgery() -> None:
    selected = canonical_input()
    report = run_replay(selected)
    other = run_replay(canonical_input(0))
    assert other["state"]["messages"] == []
    modified = run_replay(selected)
    modified["state"]["tasks"][1]["dependsOn"].append("foreign")
    modified["commands"].pop()
    assert walkthrough()[11]["task"] == "review"
    assert run_replay(canonical_input(0))["state"]["tasks"][1]["dependsOn"] == ["research"]
    for mutate in (lambda row: row.update(runId="invalid"),
                   lambda row: row["commands"].pop(),
                   lambda row: row["state"]["tasks"][0].update(owner="reviewer"),
                   lambda row: row["state"]["messages"][0].update(status="queued"),
                   lambda row: row["state"]["receipts"][0].update(accepted=True),
                   lambda row: row.update(modelCalls=1),
                   lambda row: row.update(complete=False)):
        forged = copy.deepcopy(report)
        mutate(forged)
        assert not grade(selected, forged)
    assert not grade(canonical_input(15), report)


def test_strict_command_shapes() -> None:
    bad = ([{"type": "exec", "actor": "lead"}],
           [{"type": "claim", "actor": "other", "task": "research"}],
           [{"type": "send", "actor": "researcher", "to": "reviewer", "id": "../oops", "body": "e"}],
           [{"type": "cleanup", "actor": "researcher"}],
           [{"type": "send", "actor": "researcher", "to": "reviewer", "id": "good", "body": "x" * 501}],
           [{"type": "deliver", "actor": "reviewer", "path": "secret"}],
           [{"type": "deliver", "actor": "reviewer"}] * 101)
    for commands in bad:
        with pytest.raises(ValidationError):
            ReplayInput.model_validate({"commands": commands})
    with pytest.raises(ValidationError):
        ReplayInput.model_validate({"commands": [], "mode": "live"})
