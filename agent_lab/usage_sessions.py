"""Token-scoped usage sessions with one task owning the SDK client and its controls."""

import asyncio
import secrets
import uuid
from dataclasses import dataclass, field
from typing import Any

from agent_lab.config import Settings
from agent_lab.models import Event, LessonError, RunRequest, lesson_request
from agent_lab.runtime import BusyError
from agent_lab.usage import UsageMeter, UsageObservation, collect_usage, usage_options


@dataclass
class UsageSession:
    id: str
    token: str
    request: RunRequest
    queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=4))
    task: asyncio.Task | None = None
    closed: bool = False
    connection_closed: bool = False
    busy: bool = False
    sends: int = 0
    initialized: list[str] = field(default_factory=list)
    meter: UsageMeter = field(default_factory=UsageMeter)
    reports: list[dict] = field(default_factory=list)
    error: str | None = None

    def snapshot(self) -> dict:
        return {
            "application_handle": self.id,
            "mode": self.request.mode,
            "closed": self.closed,
            "connection_closed": self.connection_closed,
            "busy": self.busy,
            "sends": self.sends,
            "send_limit": 4,
            "meter": self.meter.samples,
            "reports": self.reports,
            "error": self.error,
            "scope": "One owned SDK connection; meter updates on completed results, not individual streamed blocks. Inspection sends no prompt. Separate from the automatic lesson check.",
        }


class UsageSessions:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.sessions: dict[str, UsageSession] = {}

    def lookup(self, identity: str, token: str) -> UsageSession:
        session = self.sessions.get(identity)
        if session is None or not secrets.compare_digest(session.token.encode(), token.encode()):
            raise PermissionError("Unknown usage session or invalid control token.")
        return session

    async def open(self, request: RunRequest) -> UsageSession:
        request = lesson_request(15, request)
        if request.mode == "live":
            from agent_lab.sdk import require_live_access

            require_live_access(self.settings)
        if sum(not s.closed for s in self.sessions.values()) >= 4:
            raise BusyError("All four usage session slots are occupied.")
        if len(self.sessions) >= 32:
            oldest = next(
                (key for key, s in self.sessions.items() if s.closed and s.task and s.task.done()),
                None,
            )
            if oldest is None:
                raise BusyError("The usage session archive is full.")
            del self.sessions[oldest]
        session = UsageSession(uuid.uuid4().hex, secrets.token_urlsafe(24), request)
        self.sessions[session.id] = session
        ready = asyncio.get_running_loop().create_future()
        session.task = asyncio.create_task(self._owner(session, ready))
        try:
            await asyncio.shield(ready)
        except BaseException:
            await self.end(session)
            raise
        return session

    async def command(self, session: UsageSession, action: str, prompt: str = "") -> dict:
        if session.closed or session.busy:
            raise LessonError("This usage session is closed or busy.")
        if action == "send" and session.sends >= 4:
            raise LessonError("The four-message usage session limit is reached.")
        if action == "send" and (not prompt.strip() or len(prompt) > 10000):
            raise LessonError("Send a nonempty message of at most 10000 characters.")
        session.busy = True
        future = asyncio.get_running_loop().create_future()
        session.queue.put_nowait((action, prompt.strip(), future))
        try:
            result = await asyncio.shield(future)
            if session.closed and session.task:
                await asyncio.shield(session.task)
            if "session" in result:
                result["session"] = session.snapshot()
            return result
        except asyncio.CancelledError:
            await self.end(session)
            raise

    async def end(self, session: UsageSession) -> dict:
        session.closed = True
        if session.task and not session.task.done():
            session.task.cancel()
            await asyncio.gather(session.task, return_exceptions=True)
        return session.snapshot()

    async def close(self) -> None:
        await asyncio.gather(*(self.end(s) for s in list(self.sessions.values())))

    async def _owner(self, session: UsageSession, ready: asyncio.Future) -> None:
        from agent_lab.sdk import ClaudeSDKClient

        client = None
        pending = None
        error = None
        try:
            async with asyncio.timeout(self.settings.timeout_seconds):
                work = self.settings.data_dir / ("usage-session-" + session.id)
                await asyncio.to_thread(work.mkdir, parents=True, exist_ok=True)
                options = usage_options(session.request, work, work / "config", self.settings)
                if session.request.mode == "live":
                    client = ClaudeSDKClient(options=options)
                    await client.connect()
            ready.set_result(None)
            while not session.closed:
                async with asyncio.timeout(600):
                    action, prompt, pending = await session.queue.get()
                try:
                    async with asyncio.timeout(self.settings.timeout_seconds):
                        result: dict[str, Any]
                        if action == "context":
                            value = (
                                await client.get_context_usage()
                                if client
                                else {
                                    "source": "recorded context fixture; no model",
                                    "used_tokens": 14 * session.sends,
                                }
                            )
                            result = {
                                "context": value,
                                "prompt_sent": False,
                                "source": "SDK context inspection"
                                if client
                                else "recorded context fixture",
                            }
                        else:
                            session.sends += 1
                            observation = UsageObservation(
                                session.id,
                                session.request.mode == "live",
                                identities=list(session.initialized),
                            )
                            events: list[dict] = []

                            async def emit(event: Event, events: list = events) -> None:
                                events.append(event.model_dump())

                            if client:
                                await client.query(prompt)
                            await collect_usage(
                                observation, session.request, client, emit, session.sends
                            )
                            session.initialized = observation.identities
                            report = observation.report()
                            report["scope"] = (
                                "Turn observations; the session connection remains open until End. Not a completed standalone-run check."
                            )
                            final = report["final"]
                            report["meter"] = session.meter.observe(
                                report.get("correlated_identity"), final.get("total_cost_usd")
                            )
                            session.reports.append(report)
                            result = {"events": events, "session": session.snapshot()}
                            if (
                                not final
                                or final.get("is_error") is not False
                                or final.get("subtype") != "success"
                            ):
                                session.closed = (
                                    True  # No retry or later paid send after terminal failure.
                                )
                    if not pending.done():
                        pending.set_result(result)
                finally:
                    session.busy = False
                pending = None
        except asyncio.CancelledError:
            error = LessonError("The usage session was ended; its active operation was cancelled.")
        except Exception:
            error = LessonError(
                "Usage session failed or expired. Inspect CLI setup, credentials and reported evidence; no retry was attempted."
            )
        finally:
            session.closed = True
            try:
                if client:
                    await client.disconnect()
                session.connection_closed = True
            except Exception:
                error = LessonError("Usage connection cleanup could not be confirmed.")
            session.error = str(error) if error else None
            if not ready.done():
                ready.set_exception(
                    error or LessonError("Usage session closed during initialization.")
                )
            if pending and not pending.done():
                pending.set_exception(error or LessonError("Usage session ended."))
            session.busy = False
            while not session.queue.empty():
                _, _, future = session.queue.get_nowait()
                if not future.done():
                    future.set_exception(error or LessonError("Usage session ended."))
