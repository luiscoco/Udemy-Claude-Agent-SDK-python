"""Lesson 37's actual stdio MCP gate and owned file effects."""

from pathlib import Path

import pytest

from agent_lab.models import RunRequest
from agent_lab.permission_gate_lab import GateState, local_gate, permission_rule


@pytest.mark.parametrize("action,passed", [("allow", True), ("edit", True),
                                           ("remember", True), ("deny", False),
                                           ("interrupt", False), ("malformed", False),
                                           ("missing-effect", False)])
async def test_prepared_gate_effects(tmp_path: Path, action: str, passed: bool) -> None:
    proof = await local_gate(tmp_path / "work", RunRequest(lesson_options={"action": action}))
    report = proof["experiment"]
    assert proof["experiment_passed"] is passed
    assert report["gate_correlated"]
    assert report["connection_closed"]
    assert bool(report["file_effect_verified"]) is (action in {"allow", "edit", "remember"})


def test_gate_rejects_wrong_identity_and_double_answer(tmp_path: Path) -> None:
    gate = GateState(tmp_path, "run", "gate", "token", "allow")
    body = {"run_id": "run", "gate_id": "gate", "capability": "owned-write",
            "tool_name": "Write", "tool_input": {"file_path": str(gate.expected_path()),
                                                   "content": "GATE_ORIGINAL_37"}}
    with pytest.raises(ValueError):
        gate.decide({**body, "gate_id": "other"}, "token")
    with pytest.raises(ValueError):
        gate.decide(body, "wrong")
    assert gate.decide(body, "token") == '{"behavior": "allow"}'
    with pytest.raises(ValueError):
        gate.decide(body, "token")


def test_bash_rule_preview_scopes_first_word() -> None:
    assert permission_rule("Bash", {"command": "git status --short"}) == {
        "toolName": "Bash", "ruleContent": "git"}
    with pytest.raises(ValueError):
        permission_rule("Bash", {"command": "  "})
