"""Owned synthetic support desk ledger; no payment or production customer access."""

import asyncio
import json
import math
import time
import uuid
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agent_lab.config import ROOT

FIXTURE = json.loads((ROOT / "agent_lab/content/desk_customers.json").read_text(encoding="utf-8"))
CUSTOMERS = {row["id"]: row for row in FIXTURE["customers"]}
ORDERS = {row["id"]: row for row in FIXTURE["orders"]}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class Message(StrictModel):
    role: Literal["customer", "assistant"]
    text: str = Field(min_length=1, max_length=4000)


class CRM(StrictModel):
    customer: Literal["ada", "bo"]
    conversationId: uuid.UUID
    summary: str = Field(min_length=1, max_length=500)
    resolution: Literal["resolved", "needs-follow-up"]


class Conversation(StrictModel):
    id: uuid.UUID
    customer: Literal["ada", "bo"]
    mode: Literal["local", "live"]
    status: Literal["open", "closed"] = "open"
    messages: list[Message] = Field(default_factory=list, max_length=40)
    nativeSession: str | None = Field(default=None, max_length=200)
    nativeReported: float | None = Field(default=None, ge=0)
    costUsd: float = Field(default=0, ge=0)
    crm: CRM | None = None


class Refund(StrictModel):
    id: uuid.UUID
    conversation: uuid.UUID
    customer: Literal["ada", "bo"]
    call: str = Field(min_length=1, max_length=200)
    order: Literal["order-ada", "order-bo"]
    amountCents: int = Field(ge=1, le=10000)


class Ticket(StrictModel):
    id: uuid.UUID
    conversation: uuid.UUID
    customer: Literal["ada", "bo"]
    call: str = Field(min_length=1, max_length=200)
    subject: str = Field(min_length=1, max_length=120)


class Audit(StrictModel):
    conversation: uuid.UUID
    customer: Literal["ada", "bo"]
    call: str = Field(min_length=1, max_length=200)
    action: Literal["orders", "ticket", "refund"]
    outcome: Literal["read", "created", "approved", "denied", "rejected"]


class DeskData(StrictModel):
    conversations: list[Conversation] = Field(default_factory=list, max_length=100)
    refunds: list[Refund] = Field(default_factory=list, max_length=100)
    tickets: list[Ticket] = Field(default_factory=list, max_length=100)
    audit: list[Audit] = Field(default_factory=list, max_length=500)


class DeskStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.path = root / "store.json"
        self.lock = asyncio.Lock()

    def _load(self) -> DeskData:
        if not self.path.exists() and not self.path.is_symlink():
            return DeskData()
        stat = self.path.lstat()
        if self.path.is_symlink() or not self.path.is_file() or stat.st_nlink != 1 or stat.st_size > 1_000_000:
            raise ValueError("Unsafe synthetic desk store")
        try:
            return DeskData.model_validate_json(self.path.read_bytes())
        except ValidationError as exc:
            raise ValueError("Invalid synthetic desk store") from exc

    def _save(self, data: DeskData) -> None:
        encoded = data.model_dump_json().encode("utf-8")
        if len(encoded) > 1_000_000:
            raise ValueError("Synthetic desk store exceeds 1 MB")
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = self.root / ("store-" + uuid.uuid4().hex + ".tmp")
        temporary.write_bytes(encoded)
        for attempt in range(10):
            try:
                temporary.replace(self.path)
                break
            except PermissionError:
                if attempt == 9:
                    raise
                # Windows can briefly hold the replaced file open during scanning.
                time.sleep(0.03 * (attempt + 1))

    async def mutate(self, change: Any) -> Any:
        async with self.lock:
            data = self._load()
            result = change(data)
            DeskData.model_validate(data.model_dump())
            self._save(data)
            return result

    def state(self) -> DeskData:
        return self._load()

    def snapshot(self, customer: str) -> dict[str, Any]:
        if customer not in CUSTOMERS:
            raise ValueError("Unknown synthetic customer")
        data = self._load()
        return {"customer": customer,
                "orders": [row for row in ORDERS.values() if row["customer"] == customer],
                "conversations": [row.model_dump(mode="json") for row in data.conversations if row.customer == customer],
                "refunds": [row.model_dump(mode="json") for row in data.refunds if row.customer == customer],
                "tickets": [row.model_dump(mode="json") for row in data.tickets if row.customer == customer],
                "audit": [row.model_dump(mode="json") for row in data.audit if row.customer == customer][-30:]}

    async def open(self, customer: str, mode: str) -> Conversation:
        if customer not in CUSTOMERS or mode not in {"local", "live"}:
            raise ValueError("Unknown synthetic desk context")
        def change(data: DeskData) -> Conversation:
            if len(data.conversations) >= 100:
                raise ValueError("Synthetic conversation limit reached")
            row = Conversation(id=uuid.uuid4(),
                               customer=cast(Literal["ada", "bo"], customer),
                               mode=cast(Literal["local", "live"], mode))
            data.conversations.append(row)
            return row
        return await self.mutate(change)

    def require_open(self, identifier: uuid.UUID, customer: str, mode: str) -> Conversation:
        row = next((item for item in self._load().conversations if item.id == identifier), None)
        if row is None or row.customer != customer:
            raise LookupError("Scoped conversation not found")
        if row.mode != mode or row.status != "open":
            raise ValueError("Conversation mode or status does not match")
        return row

    async def append_message(self, identifier: uuid.UUID, customer: str, mode: str,
                             role: Literal["customer", "assistant"], text: str) -> None:
        message = Message(role=role, text=text)
        def change(data: DeskData) -> None:
            row = next((item for item in data.conversations if item.id == identifier), None)
            if row is None or row.customer != customer or row.mode != mode or row.status != "open":
                raise ValueError("Conversation is not open for this customer")
            if len(row.messages) >= 40:
                raise ValueError("Conversation message limit reached")
            row.messages.append(message)
        await self.mutate(change)

    async def orders(self, identifier: uuid.UUID, customer: str, mode: str, call: str) -> list[dict[str, Any]]:
        def change(data: DeskData) -> list[dict[str, Any]]:
            row = next((item for item in data.conversations if item.id == identifier), None)
            if row is None or row.customer != customer or row.mode != mode or row.status != "open":
                raise ValueError("Conversation is not open for this customer")
            data.audit.append(Audit(conversation=identifier, customer=customer, call=call,
                                    action="orders", outcome="read"))
            data.audit[:] = data.audit[-500:]
            return [order for order in ORDERS.values() if order["customer"] == customer]
        return await self.mutate(change)

    async def ticket(self, identifier: uuid.UUID, customer: str, mode: str,
                     call: str, subject: str) -> Ticket:
        subject = subject.strip()
        def change(data: DeskData) -> Ticket:
            row = next((item for item in data.conversations if item.id == identifier), None)
            if row is None or row.customer != customer or row.mode != mode or row.status != "open":
                raise ValueError("Conversation is not open for this customer")
            if len(data.tickets) >= 100:
                raise ValueError("Synthetic ticket limit reached")
            item = Ticket(id=uuid.uuid4(), conversation=identifier, customer=customer,
                          call=call, subject=subject)
            data.tickets.append(item)
            data.audit.append(Audit(conversation=identifier, customer=customer, call=call,
                                    action="ticket", outcome="created"))
            data.audit[:] = data.audit[-500:]
            return item
        return await self.mutate(change)

    async def refund(self, identifier: uuid.UUID, customer: str, mode: str, call: str,
                     order_id: str, amount_cents: int, approved: bool) -> Refund | None:
        def change(data: DeskData) -> Refund | None:
            row = next((item for item in data.conversations if item.id == identifier), None)
            order = ORDERS.get(order_id)
            if row is None or row.customer != customer or row.mode != mode or row.status != "open":
                raise ValueError("Conversation is not open for this customer")
            if (order is None or order["customer"] != customer or type(amount_cents) is not int or
                    not 1 <= amount_cents <= min(10000, order["paidCents"]) or
                    any(item.order == order_id for item in data.refunds)):
                data.audit.append(Audit(conversation=identifier, customer=customer, call=call,
                                        action="refund", outcome="rejected"))
                data.audit[:] = data.audit[-500:]
                return None
            if not approved:
                data.audit.append(Audit(conversation=identifier, customer=customer, call=call,
                                        action="refund", outcome="denied"))
                data.audit[:] = data.audit[-500:]
                return None
            if len(data.refunds) >= 100:
                raise ValueError("Synthetic refund limit reached")
            item = Refund(id=uuid.uuid4(), conversation=identifier, customer=customer,
                          call=call, order=cast(Literal["order-ada", "order-bo"], order_id),
                          amountCents=amount_cents)
            data.refunds.append(item)
            data.audit.append(Audit(conversation=identifier, customer=customer, call=call,
                                    action="refund", outcome="approved"))
            data.audit[:] = data.audit[-500:]
            return item
        return await self.mutate(change)

    async def close(self, identifier: uuid.UUID, customer: str, mode: str, crm: CRM) -> None:
        def change(data: DeskData) -> None:
            row = next((item for item in data.conversations if item.id == identifier), None)
            if row is None or row.customer != customer or row.mode != mode or row.status != "open":
                raise ValueError("Conversation is not open for this customer")
            if crm.customer != customer or crm.conversationId != identifier or not row.messages:
                raise ValueError("CRM summary identity or transcript missing")
            row.crm = crm
            row.status = "closed"
        await self.mutate(change)

    async def record_native(self, identifier: uuid.UUID, customer: str,
                            session: str, reported: float) -> float:
        if not isinstance(session, str) or not 1 <= len(session) <= 200 or not math.isfinite(reported) or reported < 0:
            raise ValueError("Invalid native session or cost")
        def change(data: DeskData) -> float:
            row = next((item for item in data.conversations if item.id == identifier), None)
            if row is None or row.customer != customer or row.mode != "live" or row.status != "open":
                raise ValueError("Native conversation context does not match")
            if row.nativeSession is not None and row.nativeSession != session:
                raise ValueError("Native session identity changed")
            prior = row.nativeReported or 0.0
            delta = reported - prior
            if delta < -1e-8:
                raise ValueError("Native cumulative cost moved backwards")
            row.nativeSession = session
            row.nativeReported = reported
            row.costUsd += max(0.0, delta)
            return max(0.0, delta)
        return await self.mutate(change)

    async def close_native(self, identifier: uuid.UUID, customer: str,
                           parent_session: str, crm: CRM, fork_cost: float) -> None:
        if not math.isfinite(fork_cost) or not 0 <= fork_cost <= 0.10:
            raise ValueError("Invalid native close cost")
        def change(data: DeskData) -> None:
            row = next((item for item in data.conversations if item.id == identifier), None)
            if (row is None or row.customer != customer or row.mode != "live" or
                    row.status != "open" or row.nativeSession != parent_session or
                    row.nativeReported is None or not row.messages or
                    crm.customer != customer or crm.conversationId != identifier):
                raise ValueError("Native close context does not match")
            row.crm = crm
            row.status = "closed"
            row.costUsd += fork_cost
        await self.mutate(change)

    async def reset(self) -> None:
        await self.mutate(lambda data: (data.conversations.clear(), data.refunds.clear(),
                                        data.tickets.clear(), data.audit.clear()))
