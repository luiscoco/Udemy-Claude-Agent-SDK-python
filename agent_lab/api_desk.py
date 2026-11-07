"""Strict Lesson 50 synthetic support desk routes."""

import asyncio
import json
import uuid
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from agent_lab.desk_approver import DeskApprover, Pending
from agent_lab.desk_lab import local_chat, local_close, local_evals
from agent_lab.desk_store import DeskStore
from agent_lab.runtime import RunService


class StrictBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ChatBody(StrictBody):
    mode: Literal["local", "live"] = "local"
    consent: bool = False
    customer: Literal["ada", "bo"] = "ada"
    conversationId: uuid.UUID | None = None
    intent: Literal["orders", "ticket", "refund"] = "orders"
    message: str = Field(default="Please inspect my orders.", min_length=1, max_length=500)
    scenario: Literal["normal", "missing", "foreign", "failed"] = "normal"

    @field_validator("message")
    @classmethod
    def trimmed_message(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Support message is blank")
        return stripped


class CloseBody(StrictBody):
    mode: Literal["local", "live"] = "local"
    consent: bool = False
    customer: Literal["ada", "bo"] = "ada"
    conversationId: uuid.UUID


class ApproveBody(StrictBody):
    runId: uuid.UUID
    conversationId: uuid.UUID
    callId: str = Field(min_length=1, max_length=200)
    approvalToken: uuid.UUID
    choice: Literal["approve", "deny"]


class StopBody(StrictBody):
    runId: uuid.UUID


class ResetBody(StrictBody):
    confirm: Literal[True]


class EvalsBody(StrictBody):
    mode: Literal["local", "live"] = "local"


async def body(request: Request, model: type[StrictBody]) -> Any:
    try:
        raw = await request.json()
        return model.model_validate_json(json.dumps(raw))
    except (ValueError, ValidationError) as exc:
        raise HTTPException(400, "Invalid Lesson 50 request") from exc


def desk_code() -> list[dict[str, Any]]:
    from agent_lab.config import ROOT

    sources = (("agent_lab/desk_store.py", "    def snapshot(", 15,
                "Which records are loaded independently for this customer?"),
               ("agent_lab/desk_approver.py", "    async def wait(", 18,
                "How is a pending one-shot decision removed on timeout or cancellation?"),
               ("agent_lab/desk_lab.py", "async def local_close(", 18,
                "Which stored CRM and transcript facts prove local closure?"))
    output = []
    for path, marker, length, question in sources:
        lines = (ROOT / path).read_text(encoding="utf-8").splitlines()
        start = next(index for index, line in enumerate(lines, 1) if line.startswith(marker))
        end = min(len(lines), start + length - 1)
        output.append({"file": path, "start_line": start, "end_line": end,
                       "code": "\n".join(lines[start - 1:end]), "question": question})
    return output


def install_desk_routes(app: FastAPI, runner: RunService) -> None:
    storage = runner.settings.data_dir / "lesson-50"
    store, approver = DeskStore(storage), DeskApprover()
    active: dict[str, Any] = {}

    def reserve(action: str) -> None:
        if active:
            raise HTTPException(409, "Lesson 50 operation active")
        active.update({"action": action, "task": asyncio.current_task()})

    def release() -> None:
        approver.abort_all()
        active.clear()

    @app.get("/api/c50/facts")
    async def facts() -> dict[str, Any]:
        return {"lesson": 50, "customers": ["ada", "bo"],
                "intents": ["orders", "ticket", "refund"],
                "criterion": "Support conversation completed a successful matched desk-tool call.",
                "synthetic_only": True, "local_source": "authored lifecycle with real owned effects",
                "live_enabled": runner.settings.enable_live}

    @app.get("/api/c50/code")
    @app.get("/api/c50/source")
    async def source() -> list[dict[str, Any]]:
        return desk_code()

    @app.get("/api/c50/state")
    async def state(customer: str = "ada") -> dict[str, Any]:
        if active:
            raise HTTPException(409, "Lesson 50 operation active")
        try:
            return store.snapshot(customer)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/c50/conversation/{identifier}")
    async def conversation(identifier: str, customer: str = "ada") -> dict[str, Any]:
        if customer not in {"ada", "bo"}:
            raise HTTPException(400, "Unknown customer")
        try:
            selected = uuid.UUID(identifier)
        except ValueError as exc:
            raise HTTPException(400, "Invalid conversation UUID") from exc
        row = next((item for item in store.state().conversations
                    if item.id == selected and item.customer == customer), None)
        if row is None:
            raise HTTPException(404, "Scoped conversation not found")
        return row.model_dump(mode="json")

    @app.get("/api/c50/pending")
    async def pending(customer: str = "ada") -> dict[str, Any]:
        if customer not in {"ada", "bo"}:
            raise HTTPException(400, "Unknown customer")
        selected = next((entry for entry in approver.pending.values()
                         if active.get("customer") == customer), None)
        if selected is None:
            raise HTTPException(404, "No pending synthetic proposal")
        return {"runId": str(selected.run), "conversationId": str(selected.conversation),
                "callId": selected.call, "approvalToken": str(selected.token),
                "orderId": "order-" + customer, "amountCents": 1000}

    @app.post("/api/c50/approve")
    async def approve(request: Request) -> dict[str, Any]:
        selected: ApproveBody = await body(request, ApproveBody)
        try:
            approver.answer(selected.runId, selected.conversationId, selected.callId,
                            selected.approvalToken, selected.choice)
        except LookupError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"settled": True, "choice": selected.choice}

    @app.post("/api/c50/chat")
    async def chat(request: Request) -> dict[str, Any]:
        selected: ChatBody = await body(request, ChatBody)
        if selected.mode == "live" and (not runner.settings.enable_live or
                                        not selected.consent or selected.scenario != "normal"):
            raise HTTPException(403, "Confirm this bounded native support action")
        reserve("chat")
        active["customer"] = selected.customer

        async def signal(entry: Pending) -> None:
            active["run"] = entry.run
            active["conversation"] = entry.conversation

        try:
            async with asyncio.timeout(180):
                if selected.conversationId is not None:
                    store.require_open(selected.conversationId, selected.customer, selected.mode)
                if selected.mode == "live":
                    from agent_lab.desk_native import native_chat

                    return await native_chat(store, approver, customer=selected.customer,
                                             conversation=selected.conversationId,
                                             intent=selected.intent, message=selected.message,
                                             on_approval=signal)
                return await local_chat(store, approver, customer=selected.customer,
                                        conversation=selected.conversationId,
                                        intent=selected.intent, message=selected.message,
                                        scenario=selected.scenario, on_approval=signal)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        finally:
            release()

    @app.post("/api/c50/close")
    async def close(request: Request) -> dict[str, Any]:
        selected: CloseBody = await body(request, CloseBody)
        if selected.mode == "live" and (not runner.settings.enable_live or not selected.consent):
            raise HTTPException(403, "Confirm this bounded native CRM close")
        reserve("close")
        try:
            if selected.mode == "live":
                from agent_lab.desk_native import native_close

                return await native_close(store, selected.customer, selected.conversationId)
            return await local_close(store, selected.customer, selected.conversationId)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        finally:
            release()

    @app.post("/api/c50/evals")
    async def evals(request: Request) -> dict[str, Any]:
        selected: EvalsBody = await body(request, EvalsBody)
        if selected.mode != "local":
            raise HTTPException(403, "Synthetic evaluations are local only")
        reserve("evals")
        try:
            return await local_evals(storage / ("evals-" + uuid.uuid4().hex))
        finally:
            release()

    @app.post("/api/c50/reset")
    async def reset(request: Request) -> dict[str, Any]:
        await body(request, ResetBody)
        reserve("reset")
        try:
            await store.reset()
            return {"reset": True, "synthetic_only": True}
        finally:
            release()

    @app.post("/api/c50/stop")
    async def stop(request: Request) -> dict[str, Any]:
        selected: StopBody = await body(request, StopBody)
        if active.get("run") != selected.runId or active.get("task") is None:
            raise HTTPException(409, "Active support run does not match")
        task: asyncio.Task[Any] = active["task"]
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        return {"stopped": True, "pending": len(approver.pending)}
