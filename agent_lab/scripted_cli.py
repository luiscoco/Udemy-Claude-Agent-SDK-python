"""A scripted stand-in for the Claude Code process, for offline client lessons.

`ClaudeSDKClient` accepts a custom `Transport`. This one answers the SDK's real
stream-JSON control protocol (initialize, interrupt, set_model, set_permission_mode)
and replies to each user turn with scripted text instead of a model. The client code
the lesson exercises is the official SDK; only the process on the other side is a
fixture, so evidence from it is labelled as such.
"""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from claude_agent_sdk import Transport

STOP = object()


class ScriptedCLI(Transport):
    def __init__(self, replies: list[list[str]], chunk_delay: float = 0.0) -> None:
        # One list of text chunks per user turn; chunks arrive as separate assistant messages.
        self.replies = list(replies)
        self.chunk_delay = chunk_delay
        self.model = "scripted-model"
        self.permission_mode = "default"
        self.session_id = "scripted-session"
        self.received: list[dict[str, Any]] = []  # every message the SDK wrote, for evidence
        self.lifecycle: list[str] = []
        self._outbox: asyncio.Queue[Any] = asyncio.Queue()
        self._interrupted = asyncio.Event()
        self._turns: list[asyncio.Task[None]] = []
        self._ready = False

    async def connect(self) -> None:
        self._ready = True
        self.lifecycle.append("process started")

    def is_ready(self) -> bool:
        return self._ready

    async def write(self, data: str) -> None:
        for line in data.splitlines():
            if not line.strip():
                continue
            message = json.loads(line)
            self.received.append(message)
            if message.get("type") == "control_request":
                await self._control(message["request_id"], message["request"])
            elif message.get("type") == "user":
                self._interrupted.clear()
                self._turns.append(asyncio.create_task(self._turn()))

    async def _control(self, request_id: str, request: dict[str, Any]) -> None:
        subtype = request.get("subtype")
        response: dict[str, Any] = {}
        if subtype == "initialize":
            response = {"commands": [], "models": [], "account": {}, "pid": None}
        elif subtype == "interrupt":
            self._interrupted.set()
        elif subtype == "set_model":
            self.model = request.get("model") or "scripted-model"
        elif subtype == "set_permission_mode":
            self.permission_mode = request["mode"]
        else:
            await self._outbox.put(
                {
                    "type": "control_response",
                    "response": {
                        "subtype": "error",
                        "request_id": request_id,
                        "error": f"The scripted CLI does not support {subtype}.",
                    },
                }
            )
            return
        self.lifecycle.append(f"control: {subtype}")
        await self._outbox.put(
            {
                "type": "control_response",
                "response": {"subtype": "success", "request_id": request_id, "response": response},
            }
        )

    async def _turn(self) -> None:
        chunks = self.replies.pop(0) if self.replies else ["(no scripted reply)"]
        sent = 0
        for chunk in chunks:
            if self._interrupted.is_set():
                break
            await self._outbox.put(
                {
                    "type": "assistant",
                    "message": {
                        "model": self.model,
                        "content": [{"type": "text", "text": chunk}],
                    },
                    "parent_tool_use_id": None,
                    "session_id": self.session_id,
                }
            )
            sent += 1
            await asyncio.sleep(self.chunk_delay)
        interrupted = sent < len(chunks)
        await self._outbox.put(
            {
                "type": "result",
                "subtype": "error_during_execution" if interrupted else "success",
                "duration_ms": 0,
                "duration_api_ms": 0,
                "is_error": interrupted,
                "num_turns": 1,
                "session_id": self.session_id,
                "total_cost_usd": 0,
                "result": "" if interrupted else "".join(chunks),
            }
        )

    async def read_messages(self) -> AsyncIterator[dict[str, Any]]:
        while True:
            message = await self._outbox.get()
            if message is STOP:
                return
            yield message

    async def end_input(self) -> None:
        self.lifecycle.append("input closed")

    async def close(self) -> None:
        for task in self._turns:
            task.cancel()
        await asyncio.gather(*self._turns, return_exceptions=True)
        self._ready = False
        self.lifecycle.append("process stopped")
        await self._outbox.put(STOP)
