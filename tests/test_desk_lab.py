"""Lesson 50 local tool receipts require independently stored desk effects."""

import asyncio
import uuid

import pytest

from agent_lab.desk_approver import DeskApprover, Pending
from agent_lab.desk_lab import (
    DeskOperation,
    canonical,
    evaluate_chat,
    local_chat,
    local_close,
    local_evals,
)
from agent_lab.desk_store import DeskStore


@pytest.mark.asyncio
async def test_local_orders_ticket_deny_approve_close_journey(tmp_path) -> None:
    store, approver = DeskStore(tmp_path / "desk"), DeskApprover()
    first = await local_chat(store, approver, intent="orders")
    assert first["experiment_passed"]
    conversation = uuid.UUID(first["conversation"])
    ticket = await local_chat(store, approver, conversation=conversation, intent="ticket")
    assert ticket["experiment_passed"]
    assert len(DeskStore(store.root).snapshot("ada")["tickets"]) == 1

    async def deny(entry: Pending) -> None:
        approver.answer(entry.run, entry.conversation, entry.call, entry.token, "deny")

    denied = await local_chat(store, approver, conversation=conversation,
                              intent="refund", on_approval=deny)
    assert denied["experiment_passed"]
    assert denied["results"][-1]["is_error"] is True
    assert DeskStore(store.root).snapshot("ada")["refunds"] == []

    async def approve(entry: Pending) -> None:
        approver.answer(entry.run, entry.conversation, entry.call, entry.token, "approve")

    approved = await local_chat(store, approver, conversation=conversation,
                                intent="refund", on_approval=approve)
    assert approved["experiment_passed"]
    assert len(DeskStore(store.root).snapshot("ada")["refunds"]) == 1
    closed = await local_close(store, "ada", conversation)
    assert closed["experiment_passed"] and closed["transcript_unchanged"]
    assert DeskStore(store.root).state().conversations[0].crm is not None


@pytest.mark.asyncio
async def test_negative_evidence_and_exact_tool_admission(tmp_path) -> None:
    store, approver = DeskStore(tmp_path / "desk"), DeskApprover()
    for scenario in ("missing", "foreign", "failed"):
        report = await local_chat(store, approver, scenario=scenario)
        assert not report["experiment_passed"]
        assert not evaluate_chat(report, store.root)
    row = await store.open("bo", "local")
    operation = DeskOperation(store, approver, uuid.uuid4(), row.id, "bo", "local", "ticket")
    call = str(uuid.uuid4())
    with pytest.raises(ValueError, match="Read current-operation orders"):
        operation.admit("ticket", {"subject": "Delivery"}, str(uuid.uuid4()))
    operation.admit("orders", {}, call)
    with pytest.raises(ValueError, match="Duplicate"):
        operation.admit("orders", {}, str(uuid.uuid4()))
    with pytest.raises(ValueError, match="Invalid support tool arguments"):
        await operation.handle("orders", {"customer": "ada"})
    with pytest.raises(ValueError, match="No unique"):
        await operation.handle("ticket", {"subject": "Delivery"})
    with pytest.raises(ValueError, match="Invalid"):
        canonical("refund", {"orderId": "order-bo", "amountCents": 1000.0})
    assert (await operation.handle("orders", {}))["effect"] == "read"


@pytest.mark.asyncio
async def test_stopped_pending_refund_cannot_pass(tmp_path) -> None:
    store, approver = DeskStore(tmp_path / "desk"), DeskApprover()
    entered = asyncio.Event()

    async def hold(_entry: Pending) -> None:
        entered.set()

    task = asyncio.create_task(local_chat(store, approver, intent="refund", on_approval=hold))
    await asyncio.wait_for(entered.wait(), 3)
    assert len(approver.pending) == 1
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert approver.pending == {}
    assert DeskStore(store.root).snapshot("ada")["refunds"] == []
    assert (await local_evals(tmp_path / "evals"))["experiment_passed"]
