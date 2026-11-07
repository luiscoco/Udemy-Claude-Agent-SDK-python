"""One-shot, call-bound decisions for synthetic support refunds."""

import asyncio
import uuid
from dataclasses import dataclass
from typing import Literal


@dataclass
class Pending:
    run: uuid.UUID
    conversation: uuid.UUID
    call: str
    token: uuid.UUID
    future: asyncio.Future[Literal["approve", "deny"]]


class DeskApprover:
    def __init__(self) -> None:
        self.pending: dict[str, Pending] = {}

    def install(self, run: uuid.UUID, conversation: uuid.UUID, call: str) -> Pending:
        if call in self.pending:
            raise ValueError("Duplicate pending tool call")
        entry = Pending(run, conversation, call, uuid.uuid4(),
                        asyncio.get_running_loop().create_future())
        self.pending[call] = entry
        return entry

    def answer(self, run: uuid.UUID, conversation: uuid.UUID, call: str,
               token: uuid.UUID, choice: Literal["approve", "deny"]) -> None:
        entry = self.pending.get(call)
        if (entry is None or entry.run != run or entry.conversation != conversation or
                entry.token != token or entry.future.done()):
            raise LookupError("Pending approval not found or already settled")
        self.pending.pop(call)
        entry.future.set_result(choice)

    async def wait(self, entry: Pending, seconds: float = 20) -> Literal["approve", "deny"]:
        try:
            return await asyncio.wait_for(entry.future, seconds)
        except TimeoutError:
            return "deny"
        finally:
            if self.pending.get(entry.call) is entry:
                self.pending.pop(entry.call)
            if not entry.future.done():
                entry.future.cancel()

    def abort(self, call: str) -> None:
        entry = self.pending.pop(call, None)
        if entry is not None and not entry.future.done():
            entry.future.set_result("deny")

    def abort_all(self) -> None:
        for call in tuple(self.pending):
            self.abort(call)
