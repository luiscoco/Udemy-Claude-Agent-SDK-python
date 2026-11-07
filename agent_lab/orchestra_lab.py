"""Lesson 47 orchestration: owned sales fixtures and correlated host evidence."""

import asyncio
import hashlib
import json
import re
import uuid
from collections import deque
from pathlib import Path
from typing import Any

from agent_lab.config import ROOT

ACTIONS = ("orchestrator", "hierarchy", "pipeline", "fanout", "evaluator")
SCENARIOS = ("normal", "missing", "foreign", "failed", "cancel-worker", "missing-file", "wrong-report")
ROWS = {"north": (("P1", 12), ("P2", 34), ("P3", 9)),
        "south": (("P1", 41), ("P2", 5), ("P3", 23)),
        "east": (("P1", 7), ("P2", 61), ("P3", 18))}
TOPOLOGY = {
    "orchestrator": (("lead", "host", 0, "handoff"), ("analyst", "lead", 1, "north.csv")),
    "hierarchy": (("lead", "host", 0, "handoff"), ("manager", "lead", 1, "handoff"),
                  ("analyst", "manager", 2, "north.csv")),
    "pipeline": (("extractor", "host", 1, "north.csv"),
                 ("specialist", "extractor", 1, "handoff"),
                 ("editor", "specialist", 1, "handoff")),
    "fanout": (("north", "host", 1, "north.csv"), ("south", "host", 1, "south.csv"),
               ("east", "host", 1, "east.csv")),
    "evaluator": (("writer", "host", 1, "north.csv"), ("critic", "writer", 1, "handoff")),
}
REPORT_RE = re.compile(r"^REGION=(north|south|east); TOTAL=(\d+); BEST=(P[1-3])$")


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def sales_text(region: str) -> str:
    return "product,units\n" + "".join(f"{product},{units}\n" for product, units in ROWS[region])


def truth(region: str) -> tuple[int, str]:
    values = ROWS[region]
    return sum(units for _, units in values), max(values, key=lambda row: row[1])[0]


def expected_report(region: str) -> str:
    total, best = truth(region)
    return f"REGION={region}; TOTAL={total}; BEST={best}"


def check_report(value: str, region: str) -> tuple[bool, str]:
    """Find one report line and compare its fixed values with fixture truth."""
    matches = [match for line in value.splitlines()
               if (match := REPORT_RE.fullmatch(line.strip())) is not None]
    if len(matches) != 1:
        return False, "Exactly one formatted region report line is required"
    match = matches[0]
    if match.group(1) != region:
        return False, "Report region does not match worker ownership"
    if (int(match.group(2)), match.group(3)) != truth(region):
        return False, "Report totals or best product differ from fixture truth"
    return True, "Host checked fixture totals and best product"


def analyst_gate(value: str, *, stop_hook_active: bool = False) -> dict[str, Any]:
    """A second active stop is allowed through; the host still checks the result."""
    if stop_hook_active:
        return {"decision": "second-stop-bypass", "accepted": False}
    if value.strip() == expected_report("north"):
        return {"decision": "allow", "accepted": True}
    return {"decision": "block", "accepted": False,
            "reason": "Read north.csv if needed, then return only REGION=north; TOTAL=55; BEST=P2 without Markdown or explanation."}


class FairLimiter:
    """Reserve a slot before waking one waiter; always release in finally."""

    def __init__(self, limit: int) -> None:
        if limit not in (1, 2):
            raise ValueError("Host concurrency limit must be 1 or 2")
        self.limit = limit
        self.active = 0
        self.waiters: deque[asyncio.Future[None]] = deque()
        self.closed = False
        self.observations: list[dict[str, int]] = []

    def _observe(self) -> None:
        self.observations.append({"active": self.active, "queued": len(self.waiters)})

    async def acquire(self) -> None:
        if self.closed:
            raise asyncio.CancelledError
        if self.active < self.limit:
            self.active += 1
            self._observe()
            return
        waiter: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self.waiters.append(waiter)
        self._observe()
        try:
            await waiter
        except BaseException:
            if not waiter.done():
                self.waiters.remove(waiter)
            elif not waiter.cancelled() and self.active:
                self.release()
            self._observe()
            raise

    def release(self) -> None:
        while self.waiters:
            waiter = self.waiters.popleft()
            if not waiter.done():
                waiter.set_result(None)
                self._observe()
                return
        self.active -= 1
        self._observe()

    def cancel_waiters(self) -> None:
        self.closed = True
        while self.waiters:
            self.waiters.popleft().cancel()
        self._observe()


def prepare_files(work: Path, *, missing_east: bool = False) -> dict[str, str]:
    work.mkdir(parents=True, exist_ok=True)
    hashes: dict[str, str] = {}
    for region in ROWS:
        if region == "east" and missing_east:
            continue
        value = sales_text(region)
        (work / f"{region}.csv").write_bytes(value.encode("utf-8"))
        hashes[region] = digest(value)
    return hashes


def save_passing(report: dict[str, Any], storage: Path) -> None:
    if not report.get("experiment_passed"):
        return
    summary = {key: report[key] for key in ("lesson", "operation", "action", "mode", "limit")}
    data = json.dumps(summary, separators=(",", ":")).encode()
    if len(data) > 4096:
        raise ValueError("Orchestration summary exceeds limit")
    storage.mkdir(parents=True, exist_ok=True)
    target = storage / "latest.json"
    if target.is_symlink():
        raise ValueError("Unsafe saved orchestration summary")
    if target.exists():
        stat = target.lstat()
        if not target.is_file() or stat.st_nlink != 1 or stat.st_size > 4096:
            raise ValueError("Unsafe saved orchestration summary")
    temporary = storage / ("latest-" + uuid.uuid4().hex + ".tmp")
    temporary.write_bytes(data)
    temporary.replace(target)


def evaluate(report: dict[str, Any], work: Path) -> bool:
    """Reject absent, foreign, duplicated or unverified worker evidence."""
    action = report.get("action")
    if (action not in TOPOLOGY or report.get("status") != "completed" or
            report.get("operation") is None or report.get("source_label") not in
            {"authored host fixture", "native SDK and host checks"}):
        return False
    expected = TOPOLOGY[action]
    if not all(isinstance(report.get(key), list) and len(report[key]) == len(expected)
               for key in ("starts", "ends", "verdicts", "reports")):
        return False
    starts: list[dict[str, Any]] = report["starts"]
    ends: list[dict[str, Any]] = report["ends"]
    verdicts: list[dict[str, Any]] = report["verdicts"]
    reports: list[dict[str, Any]] = report["reports"]
    ids = [row.get("id") for row in starts]
    if len(set(ids)) != len(expected) or not all(isinstance(value, str) and value for value in ids):
        return False
    for role, parent, depth, owner in expected:
        selected = [row for row in starts if row.get("role") == role]
        if len(selected) != 1:
            return False
        start = selected[0]
        worker_id = start["id"]
        if (start.get("operation") != report["operation"] or start.get("parent") != parent or
                start.get("depth") != depth or start.get("owner") != owner or
                start.get("source") != report["source_label"]):
            return False
        if (len([row for row in ends if row.get("id") == worker_id and row.get("role") == role and
                 row.get("status") == "completed" and row.get("source") == report["source_label"]]) != 1 or
                len([row for row in verdicts if row.get("id") == worker_id and row.get("passed") is True and
                     row.get("source") == "host-checker"]) != 1):
            return False
        matches = [row for row in reports if row.get("id") == worker_id]
        if len(matches) != 1 or not isinstance(matches[0].get("text"), str):
            return False
        region = role if action == "fanout" else "north"
        if role == "critic":
            if matches[0]["text"] != "PASS":
                return False
        elif not check_report(matches[0]["text"], region)[0]:
            return False
        if owner.endswith(".csv"):
            path = work / owner
            if not path.is_file() or path.is_symlink():
                return False
            try:
                actual = digest(path.read_text(encoding="utf-8"))
            except OSError:
                return False
            if (report.get("hashes", {}).get(region) != actual or
                    not any(row.get("id") == worker_id and row.get("sha256") == actual
                            and row.get("source") == "owned-file-read" for row in report.get("reads", []))):
                return False
    if action == "fanout":
        observations = report.get("limiter", [])
        if (not observations or any(not 0 <= row.get("active", -1) <= report.get("limit", 0)
                                    for row in observations) or observations[-1] != {"active": 0, "queued": 0}):
            return False
    if action in {"pipeline", "evaluator"}:
        handoffs = report.get("handoffs", [])
        if len(handoffs) != len(expected) - 1:
            return False
        for left, right in zip(expected, expected[1:], strict=False):
            predecessor = next(row for row in starts if row["role"] == left[0])
            successor = next(row for row in starts if row["role"] == right[0])
            content = next(row for row in reports if row["id"] == predecessor["id"])["text"]
            if not any(row.get("from") == predecessor["id"] and row.get("to") == successor["id"]
                       and row.get("sha256") == digest(content) for row in handoffs):
                return False
    return True


async def local_action(action: str, *, limit: int = 2, scenario: str = "normal",
                       base: Path | None = None) -> dict[str, Any]:
    if action not in ACTIONS or limit not in (1, 2) or scenario not in SCENARIOS:
        raise ValueError("Unknown fixed orchestration option")
    operation = str(uuid.uuid4())
    work = (base or ROOT / ".lab-data" / "orchestra-local" / operation) / "work"
    hashes = prepare_files(work, missing_east=action == "fanout" and scenario == "missing-file")
    report: dict[str, Any] = {"lesson": 47, "operation": operation, "action": action,
        "mode": "local", "source_label": "authored host fixture", "native": False,
        "limit": limit, "scenario": scenario, "status": "completed", "hashes": hashes,
        "starts": [], "ends": [], "reads": [], "reports": [], "verdicts": [],
        "handoffs": [], "limiter": [], "errors": [], "work": str(work)}
    id_by_role: dict[str, str] = {}
    limiter = FairLimiter(limit)

    async def worker(role: str, parent: str, depth: int, owner: str) -> None:
        worker_id = str(uuid.uuid4())
        id_by_role[role] = worker_id
        report["starts"].append({"id": worker_id, "operation": operation, "role": role,
                                 "parent": parent, "depth": depth, "owner": owner,
                                 "source": report["source_label"]})
        if action == "fanout":
            await limiter.acquire()
        try:
            await asyncio.sleep(0)
            if scenario == "cancel-worker" and action == "fanout" and role == "north":
                report["ends"].append({"id": worker_id, "role": role, "status": "cancelled",
                                       "source": report["source_label"]})
                return
            if scenario == "failed" and role == TOPOLOGY[action][-1][0]:
                raise RuntimeError("Authored worker failure")
            region = role if action == "fanout" else "north"
            if owner.endswith(".csv"):
                path = work / owner
                value = path.read_text(encoding="utf-8")
                report["reads"].append({"id": worker_id, "sha256": digest(value),
                                        "source": "owned-file-read"})
            value = "PASS" if role == "critic" else expected_report(region)
            if scenario == "wrong-report" and role == TOPOLOGY[action][-1][0]:
                value = "FAIL" if role == "critic" else value.replace(
                    f"TOTAL={truth(region)[0]}", f"TOTAL={truth(region)[0] - 1}")
            report["reports"].append({"id": worker_id, "text": value})
            passed = value == "PASS" if role == "critic" else check_report(value, region)[0]
            report["verdicts"].append({"id": worker_id, "passed": passed,
                                       "source": "host-checker"})
            report["ends"].append({"id": worker_id, "role": role, "status": "completed",
                                   "source": report["source_label"]})
        except (OSError, RuntimeError) as exc:
            report["errors"].append({"role": role, "type": type(exc).__name__})
            report["ends"].append({"id": worker_id, "role": role, "status": "failed",
                                   "source": report["source_label"]})
        finally:
            if action == "fanout":
                limiter.release()

    if action == "fanout":
        await asyncio.gather(*(worker(*spec) for spec in TOPOLOGY[action]))
        report["limiter"] = limiter.observations
    else:
        for spec in TOPOLOGY[action]:
            await worker(*spec)
            role = spec[0]
            if report["ends"][-1]["status"] != "completed" or report["verdicts"][-1]["passed"] is not True:
                break
            if action in {"pipeline", "evaluator"}:
                next_index = len(id_by_role)
                if next_index < len(TOPOLOGY[action]):
                    current_id = id_by_role[role]
                    text = next(row["text"] for row in report["reports"] if row["id"] == current_id)
                    report["handoffs"].append({"from": current_id,
                        "to_role": TOPOLOGY[action][next_index][0], "sha256": digest(text)})
        for handoff in report["handoffs"]:
            handoff["to"] = id_by_role.get(handoff.pop("to_role"))
    if scenario == "missing" and report["ends"]:
        report["ends"].pop()
    if scenario == "foreign" and report["ends"]:
        report["ends"][-1]["id"] = "foreign-worker"
    if report["errors"] or any(row["status"] != "completed" for row in report["ends"]):
        report["status"] = "failed"
    report["experiment_passed"] = evaluate(report, work)
    (work.parent / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


async def execute_lesson(root: Path, request: Any, settings: Any, emit: Any) -> dict[str, Any]:
    from agent_lab.models import Event, lesson_request

    request = lesson_request(47, request)
    choices = request.lesson_options
    if request.mode == "live":
        if not settings.enable_live:
            raise PermissionError("Enable bounded paid calls with LAB_ENABLE_LIVE=true")
        from agent_lab.orchestra_native import live_action

        report = await live_action(choices["action"], limit=choices["limit"])
        costs = [row["cost_usd"] for row in report.get("queries", [])
                 if isinstance(row.get("cost_usd"), (int, float))]
        if costs:
            await emit(Event(kind="result", data={"lesson_id": 47,
                                                   "total_cost_usd": sum(costs)}))
    else:
        scenario = {"success": "normal", "missing-evidence": "missing",
                    "wrong-identity": "foreign"}.get(request.scenario, request.scenario)
        report = await local_action(choices["action"], limit=choices["limit"], scenario=scenario,
                                    base=root / "owned-orchestra" / uuid.uuid4().hex)
    save_passing(report, root / "owned-orchestra-summary")
    proof = {"experiment": report, "experiment_passed": report["experiment_passed"]}
    await emit(Event(kind="evidence", data={"lesson_id": 47, "result": proof}))
    return proof


async def local(root: Path, request: Any) -> dict[str, Any]:
    from agent_lab.config import Settings
    from agent_lab.models import Event

    async def ignore(event: Event) -> None:
        pass

    return await execute_lesson(root, request.model_copy(update={"mode": "offline"}),
                                Settings(), ignore)
