"""Lesson 50 fixed support actions and independently checked local effects."""

import json
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agent_lab.desk_approver import DeskApprover, Pending
from agent_lab.desk_store import CRM, DeskStore

Intent = Literal["orders", "ticket", "refund"]
DecisionCallback = Callable[[Pending], Awaitable[None]]


class ToolArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class OrdersArgs(ToolArgs):
    pass


class TicketArgs(ToolArgs):
    subject: str = Field(min_length=1, max_length=120)


class RefundArgs(ToolArgs):
    orderId: Literal["order-ada", "order-bo"]
    amountCents: int = Field(ge=1, le=10000)


SCHEMAS: dict[str, type[ToolArgs]] = {"orders": OrdersArgs, "ticket": TicketArgs,
                                      "refund": RefundArgs}


def canonical(name: str, arguments: Any) -> str:
    model = SCHEMAS.get(name)
    if model is None:
        raise ValueError("Unknown support tool")
    try:
        parsed = model.model_validate(arguments)
    except ValidationError as exc:
        raise ValueError("Invalid support tool arguments") from exc
    if name == "ticket" and not parsed.model_dump()["subject"].strip():
        raise ValueError("Ticket subject is blank")
    return json.dumps(parsed.model_dump(), sort_keys=True, separators=(",", ":"))


class DeskOperation:
    def __init__(self, store: DeskStore, approver: DeskApprover, run: uuid.UUID,
                 conversation: uuid.UUID, customer: str, mode: str, intent: Intent,
                 on_approval: DecisionCallback | None = None) -> None:
        self.store, self.approver = store, approver
        self.run, self.conversation = run, conversation
        self.customer, self.mode, self.intent = customer, mode, intent
        self.on_approval = on_approval
        self.calls: dict[str, dict[str, Any]] = {}
        self.results: list[dict[str, Any]] = []
        self.refunds_before = len(store.snapshot(customer)["refunds"])

    def admit(self, tool: str, arguments: Any, call: str) -> None:
        if tool not in {"orders", self.intent} or not isinstance(call, str) or not 1 <= len(call) <= 200:
            raise ValueError("Tool is not admitted for this support request")
        if tool != "orders" and not any(row["tool"] == "orders" and
                                        row["is_error"] is False for row in self.results):
            raise ValueError("Read current-operation orders before the selected support tool")
        encoded = canonical(tool, arguments)
        if tool == "refund":
            proposal = json.loads(encoded)
            if proposal != {"orderId": "order-" + self.customer, "amountCents": 1000}:
                raise ValueError("Only the fixed synthetic refund proposal is admitted")
        if call in self.calls or any(row["tool"] == tool for row in self.calls.values()):
            raise ValueError("Duplicate support tool attempt")
        self.calls[call] = {"tool": tool, "arguments": encoded,
                            "used": False}

    async def handle(self, tool: str, arguments: Any) -> dict[str, Any]:
        encoded = canonical(tool, arguments)
        candidates = [(call, row) for call, row in self.calls.items()
                      if row["tool"] == tool and row["arguments"] == encoded and not row["used"]]
        if len(candidates) != 1:
            raise ValueError("No unique admitted support call for handler")
        call, row = candidates[0]
        row["used"] = True
        self.store.require_open(self.conversation, self.customer, self.mode)
        if tool == "orders":
            result = await self.store.orders(self.conversation, self.customer, self.mode, call)
            outcome = {"call": call, "tool": tool, "is_error": False,
                       "effect": "read", "value": result}
        elif tool == "ticket":
            subject = TicketArgs.model_validate(arguments).subject.strip()
            item = await self.store.ticket(self.conversation, self.customer, self.mode, call, subject)
            outcome = {"call": call, "tool": tool, "is_error": False,
                       "effect": "ticket", "value": item.model_dump(mode="json")}
        else:
            parsed = RefundArgs.model_validate(arguments)
            entry = self.approver.install(self.run, self.conversation, call)
            if self.on_approval is not None:
                await self.on_approval(entry)
            decision = await self.approver.wait(entry)
            refund_item = await self.store.refund(self.conversation, self.customer, self.mode,
                                                  call, parsed.orderId, parsed.amountCents,
                                                  decision == "approve")
            outcome = {"call": call, "tool": tool, "is_error": refund_item is None,
                       "effect": "refund" if refund_item is not None else "denied",
                       "decision": decision,
                       "value": refund_item.model_dump(mode="json") if refund_item else None}
        self.results.append(outcome)
        return outcome

    def report(self, scenario: str = "normal", status: str = "completed") -> dict[str, Any]:
        calls = [{"id": call, "tool": row["tool"], "arguments": json.loads(row["arguments"]),
                  "used": row["used"]} for call, row in self.calls.items()]
        results = [dict(row) for row in self.results]
        if scenario == "missing" and results:
            results.pop()
        elif scenario == "foreign" and results:
            results[0]["call"] = "foreign-call"
        elif scenario == "failed":
            status = "failed"
        snapshot = DeskStore(self.store.root).snapshot(self.customer)
        report = {"lesson": 50, "run": str(self.run), "conversation": str(self.conversation),
                  "customer": self.customer, "mode": self.mode, "intent": self.intent,
                  "scenario": scenario, "status": status, "native": False,
                  "source": "authored-local-lifecycle/real-host-effects",
                  "calls": calls, "results": results, "snapshot": snapshot,
                  "refunds_before": self.refunds_before,
                  "pending_after": len(self.approver.pending)}
        report["experiment_passed"] = evaluate_chat(report, self.store.root)
        return report


def evaluate_chat(report: dict[str, Any], root: Path) -> bool:
    if (report.get("lesson") != 50 or report.get("status") != "completed" or
            report.get("scenario") != "normal" or report.get("pending_after") != 0 or
            report.get("intent") not in SCHEMAS):
        return False
    try:
        run = uuid.UUID(report["run"])
        conversation = uuid.UUID(report["conversation"])
        snapshot = DeskStore(root).snapshot(report["customer"])
    except (KeyError, TypeError, ValueError):
        return False
    if not run or snapshot != report.get("snapshot"):
        return False
    rows = [row for row in snapshot["conversations"] if row["id"] == str(conversation)]
    if len(rows) != 1 or rows[0]["customer"] != report["customer"] or rows[0]["mode"] != report["mode"]:
        return False
    calls, results = report.get("calls", []), report.get("results", [])
    required = ["orders"] + ([] if report["intent"] == "orders" else [report["intent"]])
    if ([row.get("tool") for row in calls] != required or
            len({row.get("id") for row in calls}) != len(required) or
            any(row.get("used") is not True for row in calls) or
            len(results) != len(calls)):
        return False
    for call, result in zip(calls, results, strict=True):
        if call.get("id") != result.get("call") or call.get("tool") != result.get("tool"):
            return False
    if results[0].get("is_error") is not False or results[0].get("effect") != "read":
        return False
    audits = snapshot["audit"]
    if not any(row["call"] == calls[0]["id"] and row["action"] == "orders" and
               row["outcome"] == "read" for row in audits):
        return False
    if report["intent"] == "ticket":
        return (results[1].get("is_error") is False and
                any(row["call"] == calls[1]["id"] for row in snapshot["tickets"]))
    if report["intent"] == "refund":
        result = results[1]
        count = len(snapshot["refunds"])
        if result.get("decision") == "deny":
            return (result.get("is_error") is True and result.get("effect") == "denied" and
                    count == report.get("refunds_before") and
                    not any(row["call"] == calls[1]["id"] for row in snapshot["refunds"]) and
                    any(row["call"] == calls[1]["id"] and row["outcome"] == "denied"
                        for row in audits))
        return (result.get("decision") == "approve" and result.get("is_error") is False and
                result.get("effect") == "refund" and count == report.get("refunds_before", -1) + 1 and
                any(row["call"] == calls[1]["id"] for row in snapshot["refunds"]))
    return True


async def local_chat(store: DeskStore, approver: DeskApprover, *, customer: str = "ada",
                     conversation: uuid.UUID | None = None, intent: Intent = "orders",
                     message: str = "Please inspect my orders.", scenario: str = "normal",
                     on_approval: DecisionCallback | None = None) -> dict[str, Any]:
    if intent not in SCHEMAS or scenario not in {"normal", "missing", "foreign", "failed"}:
        raise ValueError("Unknown fixed support option")
    message = message.strip()
    if not 1 <= len(message) <= 500:
        raise ValueError("Support message must be 1 to 500 characters")
    row = await store.open(customer, "local") if conversation is None else store.require_open(conversation, customer, "local")
    run = uuid.uuid4()
    operation = DeskOperation(store, approver, run, row.id, customer, "local", intent, on_approval)
    await store.append_message(row.id, customer, "local", "customer", message)
    try:
        for tool, args in (("orders", {}),) + (() if intent == "orders" else (
                ("ticket", {"subject": "Delivery follow-up"}) if intent == "ticket" else
                ("refund", {"orderId": "order-" + customer, "amountCents": 1000}),)):
            call = str(uuid.uuid4())
            operation.admit(tool, args, call)
            await operation.handle(tool, args)
        await store.append_message(row.id, customer, "local", "assistant",
                                   "I inspected the synthetic support records.")
        return operation.report(scenario)
    finally:
        for call in tuple(approver.pending):
            if approver.pending[call].run == run:
                approver.abort(call)


async def local_close(store: DeskStore, customer: str, conversation: uuid.UUID) -> dict[str, Any]:
    row = store.require_open(conversation, customer, "local")
    before = [item.model_dump() for item in row.messages]
    crm = CRM(customer=cast(Literal["ada", "bo"], customer), conversationId=conversation,
              summary="Synthetic support request reviewed.", resolution="resolved")
    await store.close(conversation, customer, "local", crm)
    after = DeskStore(store.root).state()
    closed = next(item for item in after.conversations if item.id == conversation)
    return {"lesson": 50, "conversation": str(conversation), "customer": customer,
            "mode": "local", "source": "authored-local-crm/real-host-store",
            "crm": crm.model_dump(mode="json"), "transcript_unchanged": before ==
            [item.model_dump() for item in closed.messages],
            "closed": closed.status == "closed", "experiment_passed":
            closed.status == "closed" and closed.crm == crm and before ==
            [item.model_dump() for item in closed.messages]}


async def local_evals(root: Path) -> dict[str, Any]:
    store, approver = DeskStore(root), DeskApprover()
    row = await store.open("ada", "local")
    foreign = await store.refund(row.id, "ada", "local", str(uuid.uuid4()),
                                 "order-bo", 1000, True)
    async def deny(entry: Pending) -> None:
        approver.answer(entry.run, entry.conversation, entry.call, entry.token, "deny")
    report = await local_chat(store, approver, customer="ada", conversation=row.id,
                              intent="refund", on_approval=deny)
    reopened = DeskStore(root).snapshot("ada")
    return {"lesson": 50, "source": "authored-local-evals/real-host-effects",
            "foreign_rejected": foreign is None, "deny_passed": report["experiment_passed"],
            "refund_count": len(reopened["refunds"]), "reopened_audit": len(reopened["audit"]),
            "experiment_passed": foreign is None and report["experiment_passed"] and
            len(reopened["refunds"]) == 0}
