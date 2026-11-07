"""Lesson 50 synthetic effects must survive reload and stay scoped."""

import asyncio
import uuid

import pytest

from agent_lab.desk_approver import DeskApprover
from agent_lab.desk_store import CRM, DeskStore


@pytest.mark.asyncio
async def test_desk_store_scope_serialization_and_reopen(tmp_path) -> None:
    store = DeskStore(tmp_path / "lesson-50")
    conversation = await store.open("ada", "local")
    await store.append_message(conversation.id, "ada", "local", "customer", "Please inspect my orders.")
    calls = [str(uuid.uuid4()) for _ in range(20)]
    await asyncio.gather(*(store.orders(conversation.id, "ada", "local", call) for call in calls))
    snapshot = DeskStore(store.root).snapshot("ada")
    assert len(snapshot["audit"]) == 20
    assert {row["call"] for row in snapshot["audit"]} == set(calls)
    assert [row["id"] for row in snapshot["orders"]] == ["order-ada"]
    assert DeskStore(store.root).snapshot("bo")["audit"] == []
    with pytest.raises((LookupError, ValueError)):
        store.require_open(conversation.id, "bo", "local")
    with pytest.raises(ValueError):
        await store.ticket(conversation.id, "bo", "local", str(uuid.uuid4()), "Wrong scope")
    ticket_call = str(uuid.uuid4())
    ticket = await store.ticket(conversation.id, "ada", "local", ticket_call, "Delivery delay")
    assert ticket.call == ticket_call
    deny_call = str(uuid.uuid4())
    assert await store.refund(conversation.id, "ada", "local", deny_call,
                              "order-ada", 1000, False) is None
    assert DeskStore(store.root).snapshot("ada")["refunds"] == []
    wrong_call = str(uuid.uuid4())
    assert await store.refund(conversation.id, "ada", "local", wrong_call,
                              "order-bo", 1000, True) is None
    refund_call = str(uuid.uuid4())
    refund = await store.refund(conversation.id, "ada", "local", refund_call,
                                "order-ada", 1000, True)
    assert refund is not None and refund.call == refund_call
    assert await store.refund(conversation.id, "ada", "local", str(uuid.uuid4()),
                              "order-ada", 1000, True) is None
    before = DeskStore(store.root).state().conversations[0].messages
    await store.close(conversation.id, "ada", "local", CRM(
        customer="ada", conversationId=conversation.id,
        summary="Order inspected and refund recorded.", resolution="resolved"))
    reopened = DeskStore(store.root).state()
    assert reopened.conversations[0].status == "closed"
    assert reopened.conversations[0].messages == before
    assert len(reopened.refunds) == len(reopened.tickets) == 1


@pytest.mark.asyncio
async def test_approver_exact_one_shot_timeout_and_abort() -> None:
    approver = DeskApprover()
    run, conversation, call = uuid.uuid4(), uuid.uuid4(), str(uuid.uuid4())
    entry = approver.install(run, conversation, call)
    with pytest.raises(LookupError):
        approver.answer(uuid.uuid4(), conversation, call, entry.token, "approve")
    approver.answer(run, conversation, call, entry.token, "deny")
    with pytest.raises(LookupError):
        approver.answer(run, conversation, call, entry.token, "approve")
    assert await approver.wait(entry) == "deny"
    timeout_entry = approver.install(run, conversation, str(uuid.uuid4()))
    assert await approver.wait(timeout_entry, 0.01) == "deny"
    assert timeout_entry.call not in approver.pending
    abort_entry = approver.install(run, conversation, str(uuid.uuid4()))
    approver.abort(abort_entry.call)
    assert await approver.wait(abort_entry) == "deny"


@pytest.mark.asyncio
async def test_invalid_persisted_store_fails_closed(tmp_path) -> None:
    root = tmp_path / "lesson-50"
    root.mkdir()
    (root / "store.json").write_text('{"conversations":"not a list"}', encoding="utf-8")
    store = DeskStore(root)
    with pytest.raises(ValueError, match="Invalid synthetic desk store"):
        await store.open("ada", "local")
    assert (root / "store.json").read_text(encoding="utf-8").startswith('{"conversations"')


@pytest.mark.asyncio
async def test_atomic_store_retries_transient_replace_lock(tmp_path, monkeypatch) -> None:
    store = DeskStore(tmp_path / "lesson-50")
    path_type = type(store.path)
    original = path_type.replace
    attempts = 0

    def briefly_locked(source, target):
        nonlocal attempts
        if source.name.startswith("store-") and attempts < 2:
            attempts += 1
            raise PermissionError("simulated transient Windows file lock")
        return original(source, target)

    monkeypatch.setattr(path_type, "replace", briefly_locked)
    opened = await store.open("ada", "local")
    assert attempts == 2
    assert DeskStore(store.root).state().conversations[0].id == opened.id
