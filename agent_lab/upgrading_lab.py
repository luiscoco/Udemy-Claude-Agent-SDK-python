"""Offline, synthetic SDK compatibility workshop. No dependency mutation or model use."""

import copy
import hashlib
import importlib
import importlib.metadata
import json
import math
import platform
import re
import sys
import tomllib
import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from agent_lab.config import ROOT

FIXTURE = ROOT / "fixtures/upgrading/candidates.json"
SCENARIOS = ("compatible", "removed-export", "renamed-result", "permission-drift",
             "quality-regression", "cost-regression", "latency-regression", "missing-evidence", "error-result")
Scenario = Literal["compatible", "removed-export", "renamed-result", "permission-drift",
                   "quality-regression", "cost-regression", "latency-regression", "missing-evidence", "error-result"]
State = Literal["baseline", "checked", "canary", "promoted", "rolled-back"]
Action = Literal["start-canary", "promote", "rollback"]
CRITERION = ("The offline compatibility gates agreed with the selected fixture: a compatible "
             "candidate passed every gate, or an incompatible candidate was blocked by a failing "
             "gate. This is a simulation, not a real SDK upgrade.")


class RunInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    scenario: Scenario = "compatible"


class TransitionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    scenario: Scenario
    state: State
    action: Action


def fixture() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def dependency_snapshot() -> dict[str, str]:
    project = (ROOT / "pyproject.toml").read_bytes()
    lock = (ROOT / "uv.lock").read_bytes()
    return {"projectSha256": hashlib.sha256(project).hexdigest(),
            "lockSha256": hashlib.sha256(lock).hexdigest(),
            "dependencySha256": hashlib.sha256(project + b"\n" + lock).hexdigest()}


def runtime_inventory() -> dict[str, Any]:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    pins = [item for item in project["project"]["dependencies"] if item.startswith("claude-agent-sdk")]
    locked = [item["version"] for item in lock["package"] if item["name"] == "claude-agent-sdk"]
    declared = pins[0] if len(pins) == 1 else None
    locked_version = locked[0] if len(locked) == 1 else None
    try:
        installed = importlib.metadata.version("claude-agent-sdk")
        sdk = importlib.import_module("claude_agent_sdk")
        exports = {name: callable(getattr(sdk, name, None)) for name in fixture()["baseline"]["requiredExports"]}
    except (ImportError, importlib.metadata.PackageNotFoundError):
        installed = None
        exports = {name: False for name in fixture()["baseline"]["requiredExports"]}
    exact = bool(declared and re.fullmatch(r"claude-agent-sdk==\d+\.\d+\.\d+", declared))
    consistent = bool(exact and locked_version and installed and
                      declared == f"claude-agent-sdk=={locked_version}" and
                      locked_version == installed and all(exports.values()))
    return {"python": platform.python_version(), "platform": sys.platform,
            "declaredPin": declared, "lockedVersion": locked_version,
            "installedVersion": installed, "publicExports": exports,
            "consistent": consistent, **dependency_snapshot()}


def candidate(scenario: Scenario) -> dict[str, Any]:
    data = fixture()
    spec = data["scenarios"][scenario]
    compatible = data["scenarios"]["compatible"]
    exports = list(spec.get("exports", compatible["exports"]))
    if name := spec.get("removeExport"):
        exports.remove(name)
    messages = copy.deepcopy(data["compatibleMessages"])
    if spec.get("renameResult"):
        terminal = next(row for row in messages if row["type"] == "result")
        terminal["answer"] = terminal.pop("result")
    if spec.get("removeTask"):
        messages = [row for row in messages if row.get("subtype") != "task_notification"]
    if spec.get("errorResult"):
        next(row for row in messages if row["type"] == "result")["is_error"] = True
    return {"label": spec["label"], "exports": exports, "messages": messages,
            "outsideWriteAllowed": spec.get("outsideWriteAllowed", False),
            "metrics": spec.get("metrics", compatible["metrics"])}


def adapt_stream(messages: list[dict[str, Any]]) -> dict[str, Any]:
    init = [row for row in messages if row.get("type") == "system" and row.get("subtype") == "init"]
    calls = [row for row in messages if row.get("type") == "assistant" and row.get("tool") == "Read"]
    returns = [row for row in messages if row.get("type") == "user" and "callId" in row]
    tasks = [row for row in messages if row.get("subtype") == "task_notification"]
    terminals = [row for row in messages if row.get("type") == "result"]
    known = {"system", "assistant", "user", "result"}
    unknown = sum(row.get("type") not in known for row in messages)
    session = init[0].get("session_id") if len(init) == 1 else None
    call = calls[0] if len(calls) == 1 else {}
    returned = returns[0] if len(returns) == 1 else {}
    terminal = terminals[0] if len(terminals) == 1 else {}
    valid = bool(session == "fixture-session" and len(terminals) == 1 and
                 call.get("callId") == "call-read" and call.get("path") == "fixture.txt" and
                 returned.get("callId") == call.get("callId") and returned.get("is_error") is False and
                 "fixture-evidence" in str(returned.get("content", "")) and
                 len(tasks) == 1 and tasks[0].get("task_id") == "task-1" and
                 tasks[0].get("status") == "completed" and terminal.get("session_id") == session and
                 terminal.get("subtype") == "success" and terminal.get("is_error") is False and
                 isinstance(terminal.get("result"), str) and bool(terminal["result"].strip()))
    return {"passed": valid, "initCount": len(init), "callCount": len(calls),
            "returnCount": len(returns), "taskCount": len(tasks), "terminalCount": len(terminals),
            "unknownAdditiveCount": unknown, "sessionId": session, "callId": call.get("callId"),
            "terminalHasResult": isinstance(terminal.get("result"), str)}


def permission_probe(outside_write_allowed: bool) -> dict[str, Any]:
    def decide(tool: str, path: str) -> bool:
        return (tool == "Read" and path == "fixture.txt") or (
            tool == "Write" and path == "../outside.txt" and outside_write_allowed)
    allowed_read = decide("Read", "fixture.txt")
    denied_write = not decide("Write", "../outside.txt")
    return {"passed": allowed_read and denied_write,
            "probes": [{"tool": "Read", "path": "fixture.txt", "allowed": allowed_read},
                       {"tool": "Write", "path": "../outside.txt", "allowed": not denied_write}]}


def metric_gate(metrics: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    names = ("correctness", "costUsd", "latencyMs")
    valid = all(isinstance(metrics.get(name), (int, float)) and
                not isinstance(metrics.get(name), bool) and math.isfinite(metrics[name]) and
                metrics[name] >= 0 for name in names)
    valid = bool(valid and metrics["correctness"] <= 1) if valid else False
    passed = bool(valid and metrics["correctness"] >= baseline["correctness"] - 0.02 - 1e-9 and
                  metrics["costUsd"] <= baseline["costUsd"] * 1.2 + 1e-9 and
                  metrics["latencyMs"] <= baseline["latencyMs"] * 1.25 + 1e-9)
    return {"passed": passed, "valid": valid, "candidate": metrics,
            "limits": {"minCorrectness": baseline["correctness"] - 0.02,
                       "maxCostUsd": baseline["costUsd"] * 1.2,
                       "maxLatencyMs": baseline["latencyMs"] * 1.25}}


def assess_candidate(scenario: Scenario) -> dict[str, Any]:
    data = fixture()
    selected = candidate(scenario)
    required = data["baseline"]["requiredExports"]
    missing = [name for name in required if name not in selected["exports"]]
    stream = adapt_stream(selected["messages"])
    permissions = permission_probe(selected["outsideWriteAllowed"])
    metrics = metric_gate(selected["metrics"], data["baseline"])
    gates = [
        {"name": "exports", "passed": not missing, "observed": {"available": selected["exports"], "missing": missing},
         "explanation": "Required callable names are present." if not missing else f"Missing: {', '.join(missing)}.",
         "recovery": "Restore the required public interface or adapt the app before promotion."},
        {"name": "stream", "passed": stream["passed"], "observed": stream,
         "explanation": "Required correlated adapter events are present." if stream["passed"] else "Required stream evidence is missing or inconsistent.",
         "recovery": "Update the adapter and repeat real candidate stream tests."},
        {"name": "permissions", "passed": permissions["passed"], "observed": permissions,
         "explanation": "Owned Read allowed; outside Write denied." if permissions["passed"] else "The simulated outside Write boundary changed.",
         "recovery": "Restore and test the denied outside Write decision."},
        {"name": "eval", "passed": metrics["passed"], "observed": metrics,
         "explanation": "Synthetic quality, cost and latency are within limits." if metrics["passed"] else "Synthetic metrics are absent, invalid or beyond a limit.",
         "recovery": "Collect comparable candidate evidence and resolve every threshold failure."},
    ]
    eligible = all(gate["passed"] for gate in gates)
    return {"scenario": scenario, "candidate": selected["label"], "gates": gates,
            "eligible": eligible, "decision": "eligible" if eligible else "blocked"}


def run_upgrade(selected: RunInput) -> dict[str, Any]:
    before = dependency_snapshot()
    inventory = runtime_inventory()
    assessment = assess_candidate(selected.scenario)
    after = dependency_snapshot()
    eligible = bool(inventory["consistent"] and assessment["eligible"] and before == after)
    return {"runId": str(uuid.uuid4()), "scenario": selected.scenario, "simulated": True,
            "source": "executed-fixture-contracts", "candidate": assessment["candidate"],
            "gates": assessment["gates"], "eligible": eligible,
            "decision": "eligible" if eligible else "blocked", "inventory": inventory,
            "before": before, "after": after, "complete": True, "closed": True,
            "modelCalls": 0, "networkAttempts": 0, "reportedSdkUsd": 0}


def criterion(selected: RunInput, report: dict[str, Any]) -> bool:
    try:
        uuid.UUID(report["runId"])
        inventory = runtime_inventory()
        assessment = assess_candidate(selected.scenario)
        expected = bool(assessment["eligible"] and inventory["consistent"])
        return bool(report["scenario"] == selected.scenario and report["simulated"] is True and
                    report["source"] == "executed-fixture-contracts" and report["complete"] is True and
                    report["closed"] is True and report["modelCalls"] == report["networkAttempts"] ==
                    report["reportedSdkUsd"] == 0 and report["candidate"] == assessment["candidate"] and
                    report["gates"] == assessment["gates"] and report["eligible"] is expected and
                    report["decision"] == ("eligible" if expected else "blocked") and
                    report["inventory"] == inventory and report["before"] == report["after"] ==
                    dependency_snapshot() and inventory["consistent"] and
                    (all(gate["passed"] for gate in report["gates"]) if selected.scenario == "compatible" else
                     any(not gate["passed"] for gate in report["gates"])))
    except (KeyError, TypeError, ValueError):
        return False


def transition(selected: TransitionInput) -> dict[str, Any]:
    report = run_upgrade(RunInput(scenario=selected.scenario))
    permitted = {("checked", "start-canary"): "canary", ("canary", "promote"): "promoted",
                 ("canary", "rollback"): "rolled-back", ("promoted", "rollback"): "rolled-back"}
    new_state = permitted.get((selected.state, selected.action))
    if new_state is None or (selected.action != "rollback" and not report["eligible"]):
        raise ValueError("Invalid transition order or candidate eligibility")
    return {"previousState": selected.state, "newState": new_state, "action": selected.action,
            "scenario": selected.scenario, "simulated": True, "scope": "stateless teaching input; no deployment",
            "assessment": report}
