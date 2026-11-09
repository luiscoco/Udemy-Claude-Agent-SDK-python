"""Isolated offline team reducer for Lesson 56's exact fixture contracts."""

import copy
import hashlib
import json
import uuid
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from agent_lab.config import ROOT

FIXTURE = ROOT / "fixtures/teams/workshop.json"
MAX_COMMANDS = 100
MAX_MESSAGES = 20
Actor = Literal["researcher", "reviewer"]
Task = Literal["research", "review"]
MessageId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]{0,39}$")]
Body = Annotated[str, Field(min_length=1, max_length=500)]
CRITERION = "Simulated team replay completes evidence-gated tasks, acknowledgments and cleanup."


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    type: Literal["claim"]
    actor: Actor
    task: Task


class Send(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)
    type: Literal["send"]
    actor: Actor
    to: Actor
    id: MessageId
    body: Body


class Deliver(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    type: Literal["deliver"]
    actor: Actor


class Ack(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    type: Literal["ack"]
    actor: Actor
    id: MessageId


class Complete(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)
    type: Literal["complete"]
    actor: Actor
    task: Task
    evidence: Body


class Shutdown(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    type: Literal["shutdown"]
    actor: Actor


class Cleanup(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    type: Literal["cleanup"]
    actor: Literal["lead"]


Command = Annotated[Claim | Send | Deliver | Ack | Complete | Shutdown | Cleanup,
                    Field(discriminator="type")]


class ReplayInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    commands: list[Command] = Field(max_length=MAX_COMMANDS)


class LiveInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    consent: bool = False
    budget: float = Field(default=1, ge=0.15, le=1)


def fixture() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def walkthrough() -> list[dict[str, Any]]:
    return copy.deepcopy(fixture()["walkthrough"])


def replay_team(commands: list[dict[str, Any]]) -> dict[str, Any]:
    spec = fixture()
    state: dict[str, Any] = {
        "members": [{"id": member, "status": "idle"} for member in spec["members"]],
        "tasks": [{"id": task["id"], "dependsOn": list(task["dependsOn"]), "owner": None,
                   "status": "pending", "evidence": None} for task in spec["tasks"]],
        "messages": [], "closed": False, "receipts": [],
    }

    def receipt(command: dict[str, Any], accepted: bool, code: str) -> None:
        state["receipts"].append({"seq": len(state["receipts"]) + 1,
                                  "command": copy.deepcopy(command), "accepted": accepted, "code": code})

    for command in commands:
        kind, actor = command["type"], command["actor"]
        member = next((row for row in state["members"] if row["id"] == actor), None)
        if state["closed"]:
            receipt(command, False, "team-closed")
            continue
        if kind == "cleanup":
            ready = (all(task["status"] == "completed" for task in state["tasks"]) and
                     all(row["status"] == "shutdown" for row in state["members"]) and
                     bool(state["messages"]) and
                     all(row["status"] == "acknowledged" for row in state["messages"]))
            if ready:
                state["closed"] = True
            receipt(command, ready, "cleanup-accepted" if ready else "cleanup-premature")
            continue
        assert member is not None
        if kind == "claim":
            task = next(row for row in state["tasks"] if row["id"] == command["task"])
            if member["status"] != "idle":
                receipt(command, False, "member-not-idle")
            elif task["status"] != "pending" or task["owner"] is not None:
                receipt(command, False, "task-already-owned")
            elif any(next(row for row in state["tasks"] if row["id"] == dep)["status"] != "completed"
                     for dep in task["dependsOn"]):
                receipt(command, False, "dependency-incomplete")
            else:
                task.update(owner=actor, status="running")
                member["status"] = "busy"
                receipt(command, True, "claimed")
        elif kind == "send":
            recipient = next(row for row in state["members"] if row["id"] == command["to"])
            existing = next((row for row in state["messages"] if row["id"] == command["id"]), None)
            if existing is not None:
                same = all(existing[key] == command[value] for key, value in
                           (("from", "actor"), ("to", "to"), ("body", "body")))
                receipt(command, same, "duplicate-retained" if same else "message-id-conflict")
            elif actor == command["to"] or member["status"] == "shutdown" or recipient["status"] == "shutdown":
                receipt(command, False, "recipient-or-sender-inactive")
            elif len(state["messages"]) >= MAX_MESSAGES:
                receipt(command, False, "message-limit")
            else:
                state["messages"].append({"id": command["id"], "from": actor, "to": command["to"],
                                          "body": command["body"], "status": "queued"})
                receipt(command, True, "queued")
        elif kind == "deliver":
            pending = [row for row in state["messages"] if row["to"] == actor and row["status"] == "queued"]
            if member["status"] == "shutdown" or not pending:
                receipt(command, False, "nothing-to-deliver")
            else:
                for row in pending:
                    row["status"] = "delivered"
                receipt(command, True, "delivered")
        elif kind == "ack":
            message = next((row for row in state["messages"] if row["id"] == command["id"]), None)
            if (member["status"] == "shutdown" or message is None or message["to"] != actor or
                    message["status"] != "delivered"):
                receipt(command, False, "ack-requires-delivery")
            else:
                message["status"] = "acknowledged"
                receipt(command, True, "acknowledged")
        elif kind == "complete":
            task = next(row for row in state["tasks"] if row["id"] == command["task"])
            expected = next(row for row in spec["tasks"] if row["id"] == command["task"])["expectedEvidence"]
            acknowledged = any(row["from"] == "researcher" and row["to"] == "reviewer" and
                               row["body"] == "12 + 18 + 7 = 37" and row["status"] == "acknowledged"
                               for row in state["messages"])
            if task["owner"] != actor or task["status"] != "running" or member["status"] != "busy":
                receipt(command, False, "not-task-owner")
            elif command["evidence"] != expected or (task["id"] == "review" and not acknowledged):
                receipt(command, False, "evidence-rejected")
            else:
                task.update(status="completed", evidence=command["evidence"])
                member["status"] = "idle"
                receipt(command, True, "completed")
        elif kind == "shutdown":
            if member["status"] != "idle":
                receipt(command, False, "shutdown-busy")
            else:
                member["status"] = "shutdown"
                receipt(command, True, "shutdown")
    return state


def history_sha256(commands: list[dict[str, Any]]) -> str:
    return hashlib.sha256(json.dumps(commands, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode()).hexdigest()


def run_replay(selected: ReplayInput) -> dict[str, Any]:
    commands = copy.deepcopy([command.model_dump(mode="json") for command in selected.commands])
    return {"runId": str(uuid.uuid4()), "simulated": True, "source": "application-team-reducer",
            "commands": commands, "historySha256": history_sha256(commands),
            "state": replay_team(commands), "complete": True,
            "modelCalls": 0, "reportedSdkUsd": 0}


def grade(selected: ReplayInput, report: dict[str, Any]) -> bool:
    try:
        uuid.UUID(report["runId"])
        commands = [command.model_dump(mode="json") for command in selected.commands]
        state = replay_team(commands)
        messages = state["messages"]
        tasks = state["tasks"]
        return bool(report["simulated"] is True and report["source"] == "application-team-reducer" and
                    report["complete"] is True and report["modelCalls"] == 0 and
                    report["reportedSdkUsd"] == 0 and report["commands"] == commands and
                    report["historySha256"] == history_sha256(commands) and report["state"] == state and
                    state["closed"] and
                    [(task["id"], task["owner"], task["status"], task["evidence"]) for task in tasks] == [
                        ("research", "researcher", "completed", "12 + 18 + 7 = 37"),
                        ("review", "reviewer", "completed", "verified: 37")] and
                    all(row["status"] == "shutdown" for row in state["members"]) and
                    bool(messages) and all(row["status"] == "acknowledged" for row in messages) and
                    any(row["from"] == "researcher" and row["to"] == "reviewer" and
                        row["body"] == "12 + 18 + 7 = 37" for row in messages) and
                    state["receipts"][-1]["code"] == "cleanup-accepted")
    except (KeyError, TypeError, ValueError, IndexError):
        return False


def canonical_input(count: int = 16) -> ReplayInput:
    return ReplayInput.model_validate({"commands": walkthrough()[:count]})
