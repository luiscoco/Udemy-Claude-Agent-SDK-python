"""Lesson 51: real host assertions over injected, synthetic query envelopes."""

import asyncio
import copy
import json
import math
import shutil
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from agent_lab.config import ROOT
from agent_lab.desk_approver import DeskApprover
from agent_lab.desk_store import DeskStore
from agent_lab.headless_lab import mapped_exit

FIXTURES = ROOT / "agent_lab/content/lesson_51_streams.json"
CASES: tuple[tuple[str, str], ...] = (
    ("strict-input", "contracts"), ("result-policy", "contracts"),
    ("denial-policy", "contracts"), ("generation", "contracts"),
    ("approval-once", "contracts"), ("approval-timeout", "contracts"),
    ("scoped-store", "store"), ("serialized-store", "store"),
    ("success-stream", "replay"), ("budget-stream", "replay"),
    ("api-error-stream", "replay"), ("invalid-stream", "replay"),
    ("truncated-stream", "replay"), ("malformed-tool-stream", "replay"),
    ("foreign-result-stream", "replay"), ("duplicate-terminal-stream", "replay"),
)
PUBLIC_SCENARIOS = ("success", "budget", "api-error", "invalid", "truncated", "malformed-tool")
EXPECTED = {"success": "success", "budget": "budget", "api-error": "api-error",
            "invalid": "invalid", "truncated": "truncated",
            "malformed-tool": "invalid-tool", "foreign-result": "invalid",
            "duplicate-terminal": "invalid"}
Emit = Callable[[dict[str, Any]], Awaitable[None]]


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SuiteInput(StrictInput):
    group: Literal["all", "contracts", "store", "replay"] = "all"
    mutation: bool = False


class ReplayInput(StrictInput):
    scenario: Literal["success", "budget", "api-error", "invalid", "truncated", "malformed-tool"] = "success"


class Generation:
    """A small real host ticket gate: only the newest ticket may commit."""

    def __init__(self) -> None:
        self.current = 0

    def issue(self) -> int:
        self.current += 1
        return self.current

    def accepts(self, ticket: int) -> bool:
        return ticket == self.current


class SyntheticApiError(Exception):
    pass


class InvalidTool(Exception):
    pass


class InvalidStream(Exception):
    pass


class FakeQuery:
    """An async producer with an observable close, never a native SDK client."""

    def __init__(self, scenario: str) -> None:
        fixtures = json.loads(FIXTURES.read_text(encoding="utf-8"))
        if scenario not in fixtures or not isinstance(fixtures[scenario], list):
            raise ValueError("Unknown fixed synthetic stream")
        self.frames: list[dict[str, Any]] = copy.deepcopy(fixtures[scenario])
        self.closed = False

    async def __aiter__(self) -> AsyncIterator[dict[str, Any]]:
        for envelope in self.frames:
            await asyncio.sleep(0)
            if envelope.get("type") == "throw" and envelope.get("marker") == "synthetic-api-error":
                raise SyntheticApiError("synthetic-api-error")
            yield envelope

    async def close(self) -> None:
        self.closed = True


async def run_offline_host(root: Path, scenario: str, *,
                           abort: asyncio.Event | None = None,
                           emit: Emit | None = None) -> dict[str, Any]:
    """Consume the injected producer and execute a real scoped host lookup."""
    query = FakeQuery(scenario)
    captured: list[dict[str, Any]] = []
    handler: list[dict[str, Any]] = []
    init = terminal = 0
    selected_session: str | None = None
    call_id: str | None = None
    matched = False
    simulated: float | None = None
    text_size = 0
    status = "host-error"
    try:
        async with asyncio.timeout(5):
            async for frame in query:
                if abort is not None and abort.is_set():
                    raise asyncio.CancelledError
                if len(captured) >= 30 or len(json.dumps(captured)) > 20_000:
                    raise InvalidStream("Synthetic frame limit")
                frame = copy.deepcopy(frame)
                captured.append(frame)
                if emit is not None:
                    await emit({"kind": "fixture", "frame": frame})
                kind = frame.get("type")
                if terminal and kind != "result":
                    raise InvalidStream("Frame followed terminal")
                if kind == "init":
                    if init or frame != {"type": "init", "session": "owned"}:
                        raise InvalidStream("Initialization is missing or foreign")
                    init += 1
                    selected_session = frame["session"]
                elif kind == "delta":
                    value = frame.get("text")
                    if not init or not isinstance(value, str) or not value or len(value) > 2000:
                        raise InvalidStream("Invalid synthetic text delta")
                    text_size += len(value)
                    if text_size > 4000:
                        raise InvalidStream("Synthetic text overflow")
                    if emit is not None:
                        await emit({"kind": "delta", "text": value})
                elif kind == "tool-call":
                    arguments = frame.get("input")
                    if (not init or call_id is not None or frame.get("name") != "lookup_order" or
                            not isinstance(frame.get("id"), str) or not 1 <= len(frame["id"]) <= 80 or
                            not isinstance(arguments, dict) or set(arguments) != {"orderId"} or
                            not isinstance(arguments.get("orderId"), str) or
                            not 1 <= len(arguments["orderId"]) <= 80 or arguments["orderId"] != "order-ada"):
                        raise InvalidTool("Malformed or unowned lookup_order call")
                    call_id = frame["id"]
                    owned = next((row for row in DeskStore(root).snapshot("ada")["orders"]
                                  if row["id"] == arguments["orderId"]), None)
                    if owned is None:
                        raise ValueError("Owned order missing from the real store")
                    observation = {"call": call_id, "orderId": owned["id"],
                                   "source": "actual-DeskStore.snapshot"}
                    handler.append(observation)
                    if emit is not None:
                        await emit({"kind": "host-handler", **observation})
                elif kind == "tool-result":
                    if not init or call_id is None or matched or frame.get("id") != call_id or frame.get("ok") is not True:
                        raise InvalidStream("Unmatched synthetic tool result")
                    matched = True
                    if emit is not None:
                        await emit({"kind": "matched-result", "call": call_id})
                elif kind == "result":
                    cost = frame.get("cost")
                    if (not init or terminal or frame.get("session") != selected_session or
                            frame.get("success") is not True or isinstance(cost, bool) or
                            not isinstance(cost, (int, float)) or not math.isfinite(cost) or cost < 0 or
                            (call_id is not None and not matched)):
                        raise InvalidStream("Missing or invalid terminal evidence")
                    terminal += 1
                    simulated = float(cost)
                else:
                    raise InvalidStream("Unknown synthetic envelope")
        if not init:
            raise InvalidStream("No owned initialization")
        status = "truncated" if terminal == 0 else "budget" if simulated is not None and simulated > 0.02 else "success"
    except asyncio.CancelledError:
        status = "cancelled"
    except SyntheticApiError:
        status = "api-error"
    except InvalidTool:
        status = "invalid-tool"
    except InvalidStream:
        status = "invalid"
    except Exception:
        status = "host-error"
    finally:
        await query.close()
        if emit is not None:
            await emit({"kind": "cleanup", "closed": query.closed})
    return {"scenario": scenario, "status": status, "fixture": captured,
            "handler": handler, "terminalCount": terminal,
            "handlerCount": len(handler), "matchedResult": matched,
            "simulatedCostUsd": simulated, "actualBilledUsd": 0,
            "modelCalls": 0, "closed": query.closed, "synthetic": True}


def _assert(condition: bool, detail: str) -> None:
    if not condition:
        raise AssertionError(detail)


async def _case(case: str, root: Path, mutation: bool) -> str:
    if case == "strict-input":
        for invalid in ({"group": "bad"}, {"url": "https://invalid.example"}, {"live": True}):
            try:
                SuiteInput.model_validate(invalid)
            except ValueError:
                continue
            raise AssertionError("Strict suite input admitted a foreign field")
        return "Group and mutation schema rejected foreign input"
    if case in {"result-policy", "denial-policy"}:
        outcome = {"actual_exit": 0}
        terminal = {"is_error": False, "cost_usd": 0.01, "permission_denials": []}
        if case == "result-policy":
            _assert(mapped_exit(outcome, terminal) == 0 and
                    mapped_exit(outcome, None) == 11 and
                    mapped_exit({"timed_out": True}, None) == 124,
                    "Host exit mapping differed from 0/11/124")
            return "Real mapped_exit returned 0, 11 and 124"
        terminal["permission_denials"] = [{"tool": "Write"}]
        observed = 0 if mutation else mapped_exit(outcome, terminal)
        _assert(observed == 12, f"Expected denial code 12; observed {observed}")
        return "Real mapped_exit rejected a permission denial with code 12"
    if case == "generation":
        gate = Generation()
        old, current = gate.issue(), gate.issue()
        _assert(not gate.accepts(old) and gate.accepts(current), "Stale generation ticket was accepted")
        return "Newest host generation accepted; old ticket rejected"
    if case in {"approval-once", "approval-timeout"}:
        approver = DeskApprover()
        run, conversation, call = uuid.uuid4(), uuid.uuid4(), str(uuid.uuid4())
        pending = approver.install(run, conversation, call)
        if case == "approval-timeout":
            _assert(await approver.wait(pending, 0.01) == "deny" and not approver.pending,
                    "Timed-out approval did not deny and clear")
            return "Real one-shot approver denied after 10 ms and cleared pending"
        try:
            approver.answer(run, conversation, call, uuid.uuid4(), "approve")
        except LookupError:
            pass
        else:
            raise AssertionError("Wrong approval token was accepted")
        approver.answer(run, conversation, call, pending.token, "deny")
        _assert(await approver.wait(pending) == "deny", "Settled decision changed")
        try:
            approver.answer(run, conversation, call, pending.token, "approve")
        except LookupError:
            pass
        else:
            raise AssertionError("A consumed decision was reused")
        return "Real approver denied once and rejected token mismatch/reuse"
    if case in {"scoped-store", "serialized-store"}:
        store = DeskStore(root / case)
        owned_conversation = await store.open("ada", "local")
        if case == "scoped-store":
            rejected = await store.refund(owned_conversation.id, "ada", "local", str(uuid.uuid4()),
                                          "order-bo", 1000, True)
            view = DeskStore(store.root).snapshot("ada")
            _assert(rejected is None and view["refunds"] == [] and
                    [item["id"] for item in view["orders"]] == ["order-ada"],
                    "Real DeskStore crossed customer scope")
            return "Real store rejected Bo refund and exposed Ada order only"
        calls = [str(uuid.uuid4()) for _ in range(8)]
        await asyncio.gather(*(store.orders(owned_conversation.id, "ada", "local", call) for call in calls))
        view = DeskStore(store.root).snapshot("ada")
        _assert({row["call"] for row in view["audit"]} == set(calls),
                "Concurrent real audit mutations were lost")
        return "Eight concurrent real audit writes survived reopen"
    scenario = case.removesuffix("-stream")
    report = await run_offline_host(root / case, scenario)
    _assert(report["status"] == EXPECTED[scenario] and report["closed"] is True and
            report["modelCalls"] == 0 and report["actualBilledUsd"] == 0,
            f"Host replay status/cleanup differed for {scenario}")
    if scenario == "success":
        _assert(report["handlerCount"] == 1 and report["matchedResult"] is True and
                report["handler"][0]["orderId"] == "order-ada", "Owned handler/result join missing")
    if scenario == "malformed-tool":
        _assert(report["handlerCount"] == 0, "Malformed tool executed host handler")
    if scenario == "truncated":
        _assert(report["terminalCount"] == 0, "Truncated producer supplied a terminal")
    if scenario == "budget":
        _assert(report["simulatedCostUsd"] == 0.05, "Synthetic budget cost differed")
    return f"Actual host consumer returned {report['status']} and closed the fake query"


def evaluate_suite(report: dict[str, Any]) -> bool:
    """Exact complete-suite evidence; partial, mutation and replay never earn credit."""
    if (report.get("lesson") != 51 or report.get("action") != "run" or
            report.get("status") != "completed" or report.get("group") != "all" or
            report.get("mutation") is not False or report.get("modelCalls") != 0 or
            report.get("actualBilledUsd") != 0 or report.get("syntheticQueries") is not True or
            report.get("cleanup") is not True or not isinstance(report.get("run"), str)):
        return False
    try:
        uuid.UUID(report["run"])
    except ValueError:
        return False
    rows = report.get("assertions")
    summary = report.get("summary")
    if not isinstance(rows, list) or len(rows) != len(CASES) or not isinstance(summary, dict):
        return False
    if (set(summary) != {"total", "passed", "failed", "modelCalls", "actualBilledUsd"} or
            summary != {"total": 16, "passed": 16, "failed": 0,
                        "modelCalls": 0, "actualBilledUsd": 0}):
        return False
    return all(isinstance(row, dict) and row.get("caseId") == case and
               row.get("group") == group and row.get("sequence") == index and
               row.get("run") == report["run"] and row.get("passed") is True and
               row.get("modelCalls") == 0 and row.get("source") == "actual-host-assertion"
               for index, (row, (case, group)) in enumerate(zip(rows, CASES, strict=True), 1))


async def run_suite(root: Path, *, group: str = "all", mutation: bool = False,
                    abort: asyncio.Event | None = None,
                    emit: Emit | None = None,
                    run_id: uuid.UUID | None = None) -> dict[str, Any]:
    selected = SuiteInput.model_validate({"group": group, "mutation": mutation})
    run = str(run_id or uuid.uuid4())
    owned = root / run
    owned.mkdir(parents=True, exist_ok=False)
    rows: list[dict[str, Any]] = []
    status = "completed"
    clean = False
    try:
        async with asyncio.timeout(15):
            for sequence, (case, case_group) in enumerate(CASES, 1):
                if case_group != selected.group and selected.group != "all":
                    continue
                if abort is not None and abort.is_set():
                    status = "cancelled"
                    break
                await asyncio.sleep(0.02)
                try:
                    detail = await _case(case, owned, selected.mutation)
                    passed = True
                except AssertionError as exc:
                    detail, passed = str(exc)[:200], False
                row = {"run": run, "caseId": case, "group": case_group,
                       "sequence": sequence, "passed": passed,
                       "detail": detail, "modelCalls": 0,
                       "source": "actual-host-assertion"}
                rows.append(row)
                if emit is not None:
                    await emit({"kind": "assertion", **row})
    except (asyncio.CancelledError, TimeoutError):
        status = "cancelled"
    except Exception:
        status = "failed"
    finally:
        base, target, linked = await asyncio.gather(asyncio.to_thread(root.resolve),
                                                     asyncio.to_thread(owned.resolve),
                                                     asyncio.to_thread(owned.is_symlink))
        if target.is_relative_to(base) and target != base and not linked:
            await asyncio.to_thread(shutil.rmtree, target)
            clean = not await asyncio.to_thread(owned.exists)
    report: dict[str, Any] = {"lesson": 51, "run": run, "action": "run",
                              "group": selected.group, "mutation": selected.mutation,
                              "status": status, "assertions": rows,
                              "modelCalls": 0, "actualBilledUsd": 0,
                              "syntheticQueries": True, "cleanup": clean}
    if status == "completed":
        report["summary"] = {"total": len(rows), "passed": sum(row["passed"] for row in rows),
                             "failed": sum(not row["passed"] for row in rows),
                             "modelCalls": 0, "actualBilledUsd": 0}
        if emit is not None:
            await emit({"kind": "summary", "run": run, **report["summary"]})
    report["experiment_passed"] = evaluate_suite(report)
    return report


async def replay(root: Path, scenario: str, *, abort: asyncio.Event | None = None,
                 emit: Emit | None = None, run_id: uuid.UUID | None = None) -> dict[str, Any]:
    selected = ReplayInput.model_validate({"scenario": scenario})
    run = str(run_id or uuid.uuid4())
    result = await run_offline_host(root / run, selected.scenario, abort=abort, emit=emit)
    return {"lesson": 51, "run": run, "action": "replay", **result,
            "experiment_passed": False}
