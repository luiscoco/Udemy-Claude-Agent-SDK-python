import sys

import pytest
from pydantic import ValidationError

from agent_lab.policy import decide, inside, redact
from agent_lab.services import (
    Approval,
    Board,
    Budget,
    Calculation,
    Orders,
    Plan,
    Refund,
    TaskSpec,
    execute_plan,
)


@pytest.mark.parametrize(
    "path",
    [
        "../outside",
        ".env",
        ".git/config",
        "src/../../outside",
        # An absolute path on this platform: on Linux "C:/..." is just a relative folder name.
        "C:/Windows/system.ini" if sys.platform == "win32" else "/etc/passwd",
    ],
)
def test_path_boundary_rejects_traversal_and_protected_files(tmp_path, path):
    with pytest.raises(ValueError):
        inside(tmp_path, path)


def test_policy_checks_absolute_paths_and_denies_writes(tmp_path):
    assert decide(tmp_path, "Read", {"file_path": str(tmp_path / "notes.txt")})[0]
    assert not decide(tmp_path, "Read", {"file_path": str(tmp_path.parent / "outside")})[0]
    assert not decide(tmp_path, "Bash", {"command": "preapproved"})[0]
    assert not decide(tmp_path, "Write", {"file_path": "notes.txt"})[0]


@pytest.mark.parametrize("value", [True, "1", None, float("nan"), float("inf"), 1000001])
def test_calculator_rejects_invalid_runtime_values(value):
    with pytest.raises(ValidationError):
        Calculation(a=value, b=1)


@pytest.mark.parametrize(
    "tasks",
    [
        [TaskSpec(id="T1", files=["src/a.py"], depends_on=["T1"])],
        [TaskSpec(id="T1", files=["src/a.py"], depends_on=["T2"])],
        [TaskSpec(id="T1", files=["src/a.py"]), TaskSpec(id="T2", files=["src/a.py"])],
        [TaskSpec(id="T1", files=["src/../../outside.py"])],
        [TaskSpec(id="T1", files=[".github/workflows/ci.yml"])],
    ],
)
def test_plan_rejects_bad_dependencies_and_scope(tasks):
    with pytest.raises(ValidationError):
        Plan(tasks=tasks)


async def test_dependency_waves_are_bounded_and_do_not_run_after_failure():
    plan = Plan(
        tasks=[
            TaskSpec(id="T1", files=["src/a.py"]),
            TaskSpec(id="T2", files=["src/b.py"], depends_on=["T1"]),
        ]
    )
    invoked = []

    async def worker(task):
        invoked.append(task.id)
        raise ValueError("Task failed")

    with pytest.raises(ExceptionGroup):
        await execute_plan(plan, worker)
    assert invoked == ["T1"]


def test_approval_is_bound_to_exact_action_and_cannot_be_reused():
    clock = [0.0]
    action = Refund(order_id="A-001", amount_cents=100, reason="Customer return")
    approval = Approval(action, clock=lambda: clock[0])
    with pytest.raises(PermissionError):
        approval.decide("wrong-token", True)
    approval.decide(approval.token, True)
    with pytest.raises(ValueError):
        approval.consume(action.model_copy(update={"amount_cents": 200}))
    approval.consume(action)
    with pytest.raises(ValueError):
        approval.consume(action)
    expired = Approval(action, ttl=10, clock=lambda: clock[0])
    clock[0] = 11
    with pytest.raises(ValueError):
        expired.decide(expired.token, True)
    assert expired.state == "expired"


def test_sqlite_isolates_tenant_and_uses_optimistic_version(tmp_path):
    orders = Orders(tmp_path / "orders.sqlite")
    try:
        assert orders.list("alice' OR 1=1 --") == []
        assert not orders.cancel("bob", "A-001", 1, approved=True)
        with pytest.raises(PermissionError):
            orders.cancel("alice", "A-001", 1, approved=False)
        assert orders.cancel("alice", "A-001", 1, approved=True)
        assert not orders.cancel("alice", "A-001", 1, approved=True)
    finally:
        orders.close()


def test_budget_board_and_redaction():
    budget = Budget(0.1)
    budget.record(0.09)
    with pytest.raises(ValueError):
        budget.before_call(0.02)
    board = Board({"T1", "T2"})
    with pytest.raises(ValueError):
        board.send("outsider", "T2", "hello")
    for _ in range(6):
        board.send("T1", "T2", "hello")
    with pytest.raises(ValueError):
        board.send("T1", "T2", "hello")
    assert redact({"api_key": "private", "nested": ["Bearer fixture"]}) == {
        "api_key": "[REDACTED]",
        "nested": ["[REDACTED]"],
    }
