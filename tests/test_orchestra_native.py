"""Injected native records test the Lesson 47 joins without provider calls."""

from copy import deepcopy
from pathlib import Path

import pytest

from agent_lab.orchestra_lab import local_action
from agent_lab.orchestra_native import _join_native_children, evaluate_native


def _promote(report: dict, role: str, cost: float = 0.01) -> None:
    report["mode"] = "live"
    report["native"] = True
    report["source_label"] = "native SDK and host checks"
    for key in ("starts", "ends"):
        for row in report[key]:
            row["source"] = report["source_label"]
    text = next(row["text"] for row in report["reports"] if
                row["id"] == next(start["id"] for start in report["starts"] if start["role"] == role))
    report["queries"] = [{"role": role, "budget_usd": 0.20, "passed": True,
                          "session_id": "session-47", "uuid": "result-47",
                          "cost_usd": cost, "text": text}]
    report["native_frames"] = [
        {"node": role, "kind": "system", "subtype": "init", "session_id": "session-47"},
        {"node": role, "kind": "result", "subtype": "success", "is_error": False,
         "session_id": "session-47", "uuid": "result-47", "cost_usd": cost, "text": text},
    ]
    report["native_hooks"] = []


@pytest.mark.asyncio
async def test_native_tree_requires_real_child_task_join(tmp_path: Path) -> None:
    report = await local_action("orchestrator", base=tmp_path)
    child = report["starts"][1]["id"]
    _promote(report, "lead")
    for key in ("starts", "ends", "reports", "verdicts", "reads"):
        report[key] = [row for row in report[key] if row.get("id") != child]
    tool = "tool-47"
    report["native_frames"].extend([
        {"node": "lead", "kind": "assistant", "tools": [{"name": "Agent", "id": tool,
                                                        "target_role": "analyst"}]},
        {"node": "lead", "kind": "system", "subtype": "task_started",
         "task_id": "child-47", "tool_use_id": tool, "subagent_type": "analyst", "spawn_depth": 1},
        {"node": "lead", "kind": "system", "subtype": "task_notification",
         "task_id": "child-47", "tool_use_id": tool, "status": "completed"},
    ])
    report["native_hooks"] = [
        {"kind": "pre", "tool": "Agent", "id": tool, "caller": "lead",
         "allowed": True},
        {"kind": "agent-start", "role": "analyst", "id": "child-47"},
        {"kind": "read", "caller_id": "child-47", "id": "read-47", "path_ok": True,
         "sha256": report["hashes"]["north"]},
        {"kind": "agent-stop", "role": "analyst", "id": "child-47",
         "text": "REGION=north; TOTAL=55; BEST=P2", "decision": "allow"},
    ]
    _join_native_children(report)
    assert evaluate_native(report, tmp_path / "work")
    mutated = deepcopy(report)
    mutated["native_frames"][-1]["status"] = "failed"
    assert not evaluate_native(mutated, tmp_path / "work")
    mutated = deepcopy(report)
    mutated["native_hooks"][-1]["text"] = "REGION=north; TOTAL=54; BEST=P2"
    assert not evaluate_native(mutated, tmp_path / "work")


@pytest.mark.asyncio
async def test_native_query_cost_and_terminal_cannot_be_forged(tmp_path: Path) -> None:
    report = await local_action("evaluator", base=tmp_path)
    _promote(report, "writer")
    second = next(row for row in report["reports"] if row["text"] == "PASS")
    report["queries"].append({"role": "critic", "budget_usd": 0.05,
                              "passed": True, "session_id": "critic-session",
                              "uuid": "critic-result", "cost_usd": 0.001, "text": "PASS"})
    report["native_frames"].extend([
        {"node": "critic", "kind": "system", "subtype": "init", "session_id": "critic-session"},
        {"node": "critic", "kind": "result", "subtype": "success", "is_error": False,
         "session_id": "critic-session", "uuid": "critic-result", "cost_usd": 0.001,
         "text": second["text"]},
    ])
    assert evaluate_native(report, tmp_path / "work")
    report["queries"][0]["cost_usd"] = 0.25
    assert not evaluate_native(report, tmp_path / "work")
