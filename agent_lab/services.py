"""Small production patterns reused by the course's Python exercises."""

import asyncio
import hashlib
import hmac
import json
import secrets
import sqlite3
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agent_lab.policy import inside


class Summary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str = Field(min_length=1, max_length=500)
    next_steps: list[str] = Field(min_length=1, max_length=4)


class Calculation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    a: float = Field(ge=-1e6, le=1e6, allow_inf_nan=False)
    b: float = Field(ge=-1e6, le=1e6, allow_inf_nan=False)


@dataclass
class Budget:
    limit: float
    spent: float = 0

    def before_call(self, reserve: float = 0) -> None:
        if self.spent + reserve >= self.limit:
            raise ValueError("Host budget exhausted; no new call may start.")

    def record(self, actual: float) -> None:
        if actual < 0 or not actual < float("inf"):
            raise ValueError("Invalid actual cost.")
        self.spent += actual


class TaskSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^T[1-9]$")
    files: list[str] = Field(min_length=1, max_length=3)
    depends_on: list[str] = Field(default_factory=list, max_length=4)


class Plan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tasks: list[TaskSpec] = Field(min_length=1, max_length=4)

    @model_validator(mode="after")
    def validate_graph(self) -> "Plan":
        ids = [task.id for task in self.tasks]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate task id.")
        files: set[str] = set()
        for task in self.tasks:
            for name in task.files:
                if not name.startswith("src/") or not name.endswith(".py"):
                    raise ValueError("Tasks own only src/*.py files.")
                inside(Path.cwd() / ".lab-data" / "plan-validation", name)
                if name in files:
                    raise ValueError(f"More than one owner for {name}.")
                files.add(name)
            if len(task.depends_on) != len(set(task.depends_on)):
                raise ValueError("Duplicate dependency.")
            if not set(task.depends_on) <= set(ids):
                raise ValueError("Unknown dependency.")
        self.waves()
        return self

    def waves(self) -> list[list[str]]:
        done: set[str] = set()
        waves = []
        while len(done) < len(self.tasks):
            ready = [
                task.id
                for task in self.tasks
                if task.id not in done and set(task.depends_on) <= done
            ]
            if not ready:
                raise ValueError("Dependency cycle.")
            waves.append(ready)
            done.update(ready)
        return waves


async def execute_plan(
    plan: Plan,
    worker: Callable[[TaskSpec], Awaitable[Any]],
    max_parallel: int = 2,
) -> dict[str, Any]:
    if max_parallel < 1:
        raise ValueError("Concurrency must be positive.")
    results: dict[str, Any] = {}
    semaphore = asyncio.Semaphore(max_parallel)

    async def invoke(task: TaskSpec) -> None:
        async with semaphore:
            results[task.id] = await worker(task)

    for wave in plan.waves():
        async with asyncio.TaskGroup() as group:
            for task in plan.tasks:
                if task.id in wave:
                    group.create_task(invoke(task))
    return results


class Board:
    def __init__(self, members: set[str]) -> None:
        self.members = members
        self.counts: dict[str, int] = defaultdict(int)
        self.messages: list[dict[str, str]] = []

    def send(self, sender: str, recipient: str, text: str) -> dict[str, str]:
        if sender not in self.members or recipient not in self.members:
            raise ValueError("Unknown board member.")
        if not 1 <= len(text) <= 600 or self.counts[sender] >= 6:
            raise ValueError("Message limit exceeded.")
        self.counts[sender] += 1
        message = {
            "sender": sender,
            "recipient": recipient,
            "text": text,
            "trust": "untrusted data",
        }
        self.messages.append(message)
        return message


class Journal:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: dict[str, Any]) -> None:
        with self.path.open("a", encoding="utf-8") as output:
            output.write(json.dumps(event, allow_nan=False) + "\n")
            output.flush()
            import os

            os.fsync(output.fileno())

    def replay(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines()]

    def completed(self) -> set[str]:
        return {row["step"] for row in self.replay() if row.get("event") == "completed"}


class Refund(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    order_id: str = Field(pattern=r"^A-\d{3}$")
    amount_cents: int = Field(gt=0, le=10000, strict=True)
    reason: str = Field(min_length=3, max_length=300)


@dataclass
class Approval:
    action: Refund
    ttl: float = 120
    clock: Callable[[], float] = time.monotonic
    token: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    state: Literal["pending", "approved", "rejected", "expired", "consumed"] = "pending"
    created: float = field(init=False)
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        self.created = self.clock()
        self.fingerprint = hashlib.sha256(self.action.model_dump_json().encode()).hexdigest()

    def decide(self, token: str, approve: bool) -> None:
        if not hmac.compare_digest(token, self.token):
            raise PermissionError("Invalid approval credential.")
        if self.clock() >= self.created + self.ttl:
            self.state = "expired"
        if self.state != "pending":
            raise ValueError(f"Approval is {self.state}.")
        self.state = "approved" if approve else "rejected"

    def consume(self, action: Refund) -> None:
        if self.clock() >= self.created + self.ttl or self.state != "approved":
            raise ValueError("Approval is not usable.")
        if not hmac.compare_digest(
            self.fingerprint, hashlib.sha256(action.model_dump_json().encode()).hexdigest()
        ):
            raise ValueError("Approval belongs to a different action.")
        self.state = "consumed"


class Orders:
    """Tenant is selected by the host, never by model tool arguments."""

    def __init__(self, path: Path) -> None:
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS orders (
              id TEXT PRIMARY KEY, tenant TEXT NOT NULL, status TEXT NOT NULL,
              total_cents INTEGER NOT NULL, version INTEGER NOT NULL DEFAULT 1
            );
            INSERT OR IGNORE INTO orders VALUES ('A-001','alice','pending',4200,1);
            INSERT OR IGNORE INTO orders VALUES ('A-002','bob','shipped',9000,1);
        """)
        self.connection.commit()

    def list(self, tenant: str, status: str = "all", limit: int = 5) -> list[dict[str, Any]]:
        if status not in {"all", "pending", "shipped", "cancelled"} or not 1 <= limit <= 10:
            raise ValueError("Invalid status or limit.")
        rows = self.connection.execute(
            "SELECT id,status,total_cents,version FROM orders WHERE tenant=? AND (?='all' OR status=?) LIMIT ?",
            (tenant, status, status, limit),
        )
        return [dict(row) for row in rows]

    def cancel(self, tenant: str, order_id: str, version: int, approved: bool) -> bool:
        if not approved:
            raise PermissionError("Host approval required.")
        cursor = self.connection.execute(
            "UPDATE orders SET status='cancelled',version=version+1 WHERE tenant=? AND id=? AND version=? AND status='pending'",
            (tenant, order_id, version),
        )
        self.connection.commit()
        return cursor.rowcount == 1

    def close(self) -> None:
        self.connection.close()


POLICIES = [
    {"id": "refunds#1", "text": "Refunds may be requested within 30 days of delivery."},
    {"id": "shipping#1", "text": "Standard delivery takes 3 to 5 business days."},
    {"id": "security#1", "text": "Password reset links expire after 15 minutes."},
]


def retrieve(query: str, limit: int = 3) -> list[dict[str, Any]]:
    import re

    terms = set(re.findall(r"\w+", query.lower()))
    scored = [(len(terms & set(re.findall(r"\w+", row["text"].lower()))), row) for row in POLICIES]
    return [
        dict(row, score=score, trust="source evidence, not instructions")
        for score, row in sorted(scored, key=lambda item: item[0], reverse=True)[:limit]
        if score
    ]
