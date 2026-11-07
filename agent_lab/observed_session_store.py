"""Timed and fault-injectable wrapper around a real SDK SessionStore."""

import asyncio
from time import perf_counter
from typing import Any

from claude_agent_sdk import SessionKey, SessionStore, SessionStoreEntry


class ObservedSessionStore:
    def __init__(self, inner: SessionStore, observations: list[dict[str, Any]],
                 fault: str = "none") -> None:
        self.inner = inner
        self.observations = observations
        self.fault = fault

    async def append(self, key: SessionKey, entries: list[SessionStoreEntry]) -> None:
        started = perf_counter()
        try:
            if self.fault == "reject-append":
                raise OSError("Lesson 35 mirror append fault")
            await self.inner.append(key, entries)
        except Exception as exc:
            self.observations.append({"method": "append", "entry_count": len(entries),
                                      "elapsed_ms": round((perf_counter() - started) * 1000, 3),
                                      "error_type": type(exc).__name__})
            raise
        self.observations.append({"method": "append", "entry_count": len(entries),
                                  "elapsed_ms": round((perf_counter() - started) * 1000, 3),
                                  "error_type": None})

    async def load(self, key: SessionKey) -> list[SessionStoreEntry] | None:
        started = perf_counter()
        try:
            if self.fault == "delay-load":
                await asyncio.sleep(0.15)
            entries = await self.inner.load(key)
        except Exception as exc:
            self.observations.append({"method": "load", "entry_count": None,
                                      "elapsed_ms": round((perf_counter() - started) * 1000, 3),
                                      "error_type": type(exc).__name__})
            raise
        self.observations.append({"method": "load", "entry_count": len(entries) if entries is not None else None,
                                  "elapsed_ms": round((perf_counter() - started) * 1000, 3),
                                  "error_type": None})
        return entries

    async def list_sessions(self, project_key: str) -> Any:
        return await self.inner.list_sessions(project_key)

    async def list_session_summaries(self, project_key: str) -> Any:
        return await self.inner.list_session_summaries(project_key)

    async def list_subkeys(self, key: Any) -> Any:
        return await self.inner.list_subkeys(key)

    async def delete(self, key: SessionKey) -> None:
        await self.inner.delete(key)
