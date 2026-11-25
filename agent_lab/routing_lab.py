"""Lesson 59 fixed routing workshop with independent answer keys.

Prepared receipts are authored teaching fixtures. They are never SDK observations.
"""

from __future__ import annotations

import math
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from itertools import permutations
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

LIGHT = "claude-haiku-4-5-20251001"
STANDARD = "claude-sonnet-5-5"
DEEP = "claude-opus-5-5"
MODELS = {"light": LIGHT, "standard": STANDARD, "deep": DEEP}
RATES = {"light": (1.0, 5.0), "standard": (2.0, 10.0), "deep": (4.0, 20.0)}
STRATEGIES = ("light", "standard", "deep", "deep-low", "rules", "classifier",
              "cascade", "review")


@dataclass(frozen=True)
class Task:
    id: str
    prompt: str
    tier: str
    numeric: bool = False


TASKS = (
    Task("invoice", "Extract the invoice ID: Customer paid invoice INV-2042 yesterday.", "light"),
    Task("sentiment", "Classify sentiment: I love this useful course.", "light"),
    Task("timezone", "Convert 2026-01-15 12:00 UTC to Europe/Madrid HH:MM.", "light"),
    Task("vowels", "How many a/e/i/o/u vowels are in education?", "light", True),
    Task("sort", "What is [10,9,1].sort().join(',') without a comparator?", "standard"),
    Task("weekday", "What English weekday is 2030-01-01?", "standard"),
    Task("primes", "Count primes below 100.", "standard", True),
    Task("multiply", "Multiply 48271 by 9377.", "deep", True),
    Task("power-mod", "What are the last 3 digits of 7^222?", "deep", True),
    Task("digit-sum", "How many integers 0 through 999 have digit sum 10?", "deep", True),
    Task("lineup", "A,B,C,D,E: D first, B last, A immediately before C, C immediately before E. Join letters.", "deep"),
    Task("positions", "Order Alex, Bea, Cal, Dee, Eli, Fay: Eli first, Alex second, Bea fifth, Fay sixth, Cal immediately before Dee. Return comma-separated names.", "deep"),
    Task("binomial", "How many six-person choices can be made from twenty?", "deep", True),
)
BY_ID = {task.id: task for task in TASKS}


def answer_key(task_id: str) -> str:
    """Calculate each key from the task's actual operation, including unique puzzles."""
    match task_id:
        case "invoice":
            return re.search(r"INV-\d+", BY_ID[task_id].prompt).group()  # type: ignore[union-attr]
        case "sentiment":
            return "positive" if "love" in BY_ID[task_id].prompt.lower() else "negative"
        case "timezone":
            # This fixed January date is CET (UTC+01:00); avoid depending on a
            # host IANA database, which is absent on stock Windows Python.
            return datetime(2026, 1, 15, 12, tzinfo=UTC).astimezone(
                timezone(timedelta(hours=1), "CET")).strftime("%H:%M")
        case "vowels":
            return str(sum(char in "aeiou" for char in "education"))
        case "sort":
            return ",".join(sorted(("10", "9", "1")))
        case "weekday":
            return datetime(2030, 1, 1, tzinfo=UTC).strftime("%A")
        case "primes":
            return str(sum(n > 1 and all(n % d for d in range(2, math.isqrt(n) + 1)) for n in range(100)))
        case "multiply":
            return str(48271 * 9377)
        case "power-mod":
            return f"{pow(7, 222, 1000):03d}"
        case "digit-sum":
            return str(sum(sum(int(d) for d in f"{n:03d}") == 10 for n in range(1000)))
        case "lineup":
            valid = [p for p in permutations("ABCDE") if p[0] == "D" and p[-1] == "B"
                     and p.index("C") == p.index("A") + 1
                     and p.index("E") == p.index("C") + 1]
            assert len(valid) == 1
            return "".join(valid[0])
        case "positions":
            names = ("Alex", "Bea", "Cal", "Dee", "Eli", "Fay")
            valid = [p for p in permutations(names) if p[0] == "Eli" and p[1] == "Alex"
                     and p[4] == "Bea" and p[5] == "Fay"
                     and p.index("Dee") == p.index("Cal") + 1]
            assert len(valid) == 1
            return ",".join(valid[0])
        case "binomial":
            return str(math.comb(20, 6))
        case _:
            raise ValueError("Unknown fixed task")


def grade_answer(task_id: str, answer: str) -> dict[str, Any]:
    expected = answer_key(task_id)
    return {"source": "independent-computed-answer-key", "taskId": task_id,
            "expected": expected, "actual": answer,
            "accepted": "".join(answer.lower().split()) == "".join(expected.lower().split())}


def rule_tier(task_id: str) -> str:
    task = BY_ID[task_id]
    prompt = task.prompt.lower()
    if any(word in prompt for word in ("how many", "order ", "immediately", "choices")):
        return "deep"
    if any(word in prompt for word in ("extract", "classify", "convert")):
        return "light"
    return "standard"


def needs_escalation(task_id: str, output: dict[str, Any] | None) -> bool:
    if not isinstance(output, dict) or set(output) != {"answer", "confidence"}:
        return True
    answer, confidence = output["answer"], output["confidence"]
    if not isinstance(answer, str) or not 1 <= len(answer.strip()) <= 200:
        return True
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not math.isfinite(confidence) or confidence < 0.8 or confidence > 1:
        return True
    if BY_ID[task_id].numeric and not answer.isdecimal():
        return True
    return task_id == "power-mod" and len(answer) != 3


class RoutingInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    mode: Literal["prepared", "live"] = "prepared"
    strategies: list[str] = Field(default_factory=lambda: ["rules"], min_length=1, max_length=8)
    taskIds: list[str] = Field(default_factory=lambda: list(BY_ID), min_length=1, max_length=13)
    consent: bool = False
    budget: float = Field(default=1, ge=0.1, le=1)

    @model_validator(mode="after")
    def unique_and_bounded(self) -> RoutingInput:
        if len(set(self.strategies)) != len(self.strategies) or len(set(self.taskIds)) != len(self.taskIds):
            raise ValueError("Strategies and tasks must be unique")
        if any(item not in STRATEGIES for item in self.strategies) or any(item not in BY_ID for item in self.taskIds):
            raise ValueError("Only fixed strategies and tasks are accepted")
        if self.mode == "live" and (len(self.strategies) != 1 or len(self.taskIds) > 3):
            raise ValueError("Live runs allow one strategy and at most three tasks")
        return self


def fixture_output(task_id: str, tier: str) -> dict[str, Any]:
    if tier == "light" and BY_ID[task_id].tier == "deep":
        if task_id == "power-mod":
            return {"answer": "001", "confidence": 0.99}
        return {"answer": "0" if BY_ID[task_id].numeric else "unknown", "confidence": 0.55}
    return {"answer": answer_key(task_id), "confidence": 0.94}


def _receipt(query_id: str, session_id: str, stage: str, tier: str, output: dict[str, Any],
             previous: float = 0, effort: str | None = None,
             previous_models: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    input_tokens, output_tokens = 1000, 200
    rate_in, rate_out = RATES[tier]
    increment = (input_tokens * rate_in + output_tokens * rate_out) / 1_000_000
    cumulative = round(previous + increment, 8)
    models = list(previous_models or []) + [{"rawModel": MODELS[tier],
                                              "canonicalModel": MODELS[tier],
                                              "inputTokens": input_tokens,
                                              "outputTokens": output_tokens,
                                              "cacheReadTokens": 0,
                                              "cacheCreationTokens": 0,
                                              "costUsd": increment}]
    return {"queryId": query_id, "sessionId": session_id, "resultId": str(uuid.uuid4()),
            "stage": stage, "source": "scripted-fixture", "status": "success", "closed": True,
            "subtype": "success", "isError": False, "model": MODELS[tier], "effort": effort,
            "output": output, "durationMs": {"light": 12, "standard": 25, "deep": 45}[tier],
            "billing": {"valid": True, "costBasis": "synthetic-authored-fixture",
                        "cumulativeCostUsd": cumulative,
                        "models": models}}


def prepared_task(task_id: str, strategy: str) -> dict[str, Any]:
    task = BY_ID[task_id]
    query_id, session_id = str(uuid.uuid4()), str(uuid.uuid4())
    history: list[dict[str, Any]] = []
    if strategy == "classifier":
        classifier_query, classifier_session = str(uuid.uuid4()), str(uuid.uuid4())
        history.append(_receipt(classifier_query, classifier_session, "classifier", "light",
                                {"tier": task.tier}))
        tier = task.tier
    elif strategy in ("light", "cascade", "review"):
        tier = "light"
    elif strategy == "rules":
        tier = rule_tier(task_id)
    else:
        tier = "deep" if strategy == "deep-low" else strategy
    first = _receipt(query_id, session_id, "solve", tier, fixture_output(task_id, tier),
                     effort="low" if strategy == "deep-low" else None)
    history.append(first)
    escalated = strategy == "review" or (strategy == "cascade" and needs_escalation(task_id, first["output"]))
    if escalated:
        history.append(_receipt(query_id, session_id, "review", "deep",
                                fixture_output(task_id, "deep"),
                                previous=first["billing"]["cumulativeCostUsd"],
                                previous_models=first["billing"]["models"]))
        history[-1]["modelSwitch"] = {"source": "scripted-setModel", "acknowledged": True,
                                      "model": DEEP}
    output = history[-1]["output"]
    return {"taskId": task_id, "strategy": strategy, "intendedTier": task.tier,
            "selectedTier": tier, "history": history, "output": output,
            "grade": grade_answer(task_id, output["answer"]), "status": "success",
            "escalated": escalated, "durationMs": sum(item["durationMs"] for item in history)}


def metrics(rows: list[dict[str, Any]], source: str) -> dict[str, Any]:
    cost = 0.0
    unknown = 0
    classifier_cost = 0.0
    classifier_ms = 0
    model_costs: dict[str, float] = {}
    for row in rows:
        by_query: dict[str, dict[str, Any]] = {}
        for call in row["history"]:
            by_query[call["queryId"]] = call
            if call["stage"] == "classifier":
                classifier_ms += call["durationMs"]
        for call in by_query.values():
            billing = call.get("billing", {})
            value = billing.get("cumulativeCostUsd")
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                unknown += 1
                continue
            cost += value
            if call["stage"] == "classifier":
                classifier_cost += value
            for model in billing.get("models", []):
                key = model.get("canonicalModel") or model["rawModel"]
                model_costs[key] = model_costs.get(key, 0) + model["costUsd"]
    correct = sum(row["status"] == "success" and grade_answer(row["taskId"], row["output"]["answer"])["accepted"] for row in rows)
    durations = sorted(row["durationMs"] for row in rows)
    middle = len(durations) // 2
    median = durations[middle] if len(durations) % 2 else (durations[middle - 1] + durations[middle]) / 2
    return {"tasks": len(rows), "accepted": correct, "failed": len(rows) - correct,
            "totalKnownCostUsd": round(cost, 8), "unknownCostQueries": unknown,
            "costPerCorrectUsd": round(cost / correct, 8) if correct and not unknown else None,
            "medianTaskDurationMs": median, "classifierCostUsd": round(classifier_cost, 8),
            "classifierDurationMs": classifier_ms, "modelCostsUsd": model_costs,
            "provenance": source, "reportedSdkUsd": 0 if source == "synthetic-authored-fixture" else round(cost, 8)}


def check_suite(report: dict[str, Any], selected: RoutingInput) -> dict[str, Any]:
    errors: list[str] = []
    mode = selected.mode
    if report.get("runId") != report.get("config", {}).get("runId") or report.get("config", {}).get("taskIds") != selected.taskIds or report.get("config", {}).get("strategies") != selected.strategies:
        errors.append("Current run and exact configuration required")
    if report.get("mode") != mode or report.get("source") != ("scripted-fixture" if mode == "prepared" else "native-sdk"):
        errors.append("Truthful mode and source required")
    if report.get("status") != "success" or report.get("errors") or report.get("interrupted"):
        errors.append("Complete uninterrupted workshop required")
    rows = report.get("rows", [])
    if [(r.get("strategy"), r.get("taskId")) for r in rows] != [(s, t) for s in selected.strategies for t in selected.taskIds]:
        errors.append("Exact ordered strategy and task coverage required")
    queries: dict[str, dict[str, Any]] = {}
    query_owner: dict[str, tuple[str, str]] = {}
    result_ids: set[str] = set()
    for row in rows:
        task_id, strategy = row.get("taskId"), row.get("strategy")
        if task_id not in BY_ID or strategy not in STRATEGIES:
            errors.append("Unknown task or strategy")
            continue
        if row.get("status") != "success" or not isinstance(row.get("durationMs"), (int, float)) or not math.isfinite(row["durationMs"]) or row["durationMs"] < 0:
            errors.append(f"{row.get('taskId')}: successful timed execution required")
            continue
        output = row.get("output")
        if not isinstance(output, dict) or not isinstance(output.get("answer"), str):
            errors.append(f"{task_id}: final structured output required")
            continue
        grade = grade_answer(task_id, output["answer"])
        if not grade["accepted"] or row.get("grade") != grade:
            errors.append(f"{task_id}: independent grade rejected")
        history = row.get("history")
        if not isinstance(history, list) or not history:
            errors.append(f"{task_id}: terminal history required")
            continue
        expected_tier = ("light" if strategy in {"light", "cascade", "review"} else
                         rule_tier(task_id) if strategy == "rules" else
                         BY_ID[task_id].tier if strategy == "classifier" else
                         "deep" if strategy == "deep-low" else strategy)
        if row.get("selectedTier") != expected_tier:
            errors.append(f"{task_id}: route policy mismatch")
        first_solver = next((call for call in history if call.get("stage") in {"solve", "review"}), None)
        if first_solver is None or first_solver.get("model") != MODELS[expected_tier]:
            errors.append(f"{task_id}: requested solver model mismatch")
        if strategy == "deep-low" and (first_solver or {}).get("effort") != "low":
            errors.append(f"{task_id}: low effort baseline required")
        if strategy == "classifier":
            if len(history) != 2 or history[0].get("stage") != "classifier" or history[0].get("model") != LIGHT or history[0].get("output", {}).get("tier") != expected_tier:
                errors.append(f"{task_id}: separate classifier route required")
        else:
            if any(call.get("stage") == "classifier" for call in history):
                errors.append(f"{task_id}: unexpected classifier stage")
        should_escalate = (strategy == "review" or
                           strategy == "cascade" and first_solver is not None and
                           needs_escalation(task_id, first_solver.get("output")))
        reviews = [call for call in history if call.get("stage") == "review"]
        expected_reviews = 1 if should_escalate else 0
        if len(reviews) != expected_reviews or row.get("escalated") != should_escalate:
            errors.append(f"{task_id}: escalation decision mismatch")
        if should_escalate and (not history[-1].get("modelSwitch", {}).get("acknowledged") or history[-1].get("model") != DEEP):
            errors.append(f"{task_id}: model switch receipt required")
        if history[-1].get("output") != output:
            errors.append(f"{task_id}: final terminal output mismatch")
        if abs(sum(call.get("durationMs", 0) for call in history) - row["durationMs"]) > .001:
            errors.append(f"{task_id}: duration mismatch")
        for call in history:
            query_id, session_id, result_id = call.get("queryId"), call.get("sessionId"), call.get("resultId")
            try:
                uuid.UUID(query_id)
                uuid.UUID(session_id)
                uuid.UUID(result_id)
            except (TypeError, ValueError, AttributeError):
                errors.append(f"{task_id}: valid query/session/result IDs required")
                continue
            if result_id in result_ids:
                errors.append(f"{task_id}: reused result ID")
            result_ids.add(result_id)
            owner = (strategy, task_id)
            if query_id in query_owner and query_owner[query_id] != owner:
                errors.append(f"{task_id}: reused query ID across tasks")
            query_owner[query_id] = owner
            previous = queries.get(query_id)
            if previous and (previous.get("sessionId") != session_id or
                             call.get("billing", {}).get("cumulativeCostUsd", -1) <
                             previous.get("billing", {}).get("cumulativeCostUsd", 0)):
                errors.append(f"{task_id}: same-query identity or cumulative cost mismatch")
            queries[query_id] = call
            if (call.get("source") != ("scripted-fixture" if mode == "prepared" else "native-sdk")
                    or call.get("status") != "success" or not call.get("closed")
                    or call.get("subtype") != "success" or call.get("isError")
                    or not call.get("billing", {}).get("valid")):
                errors.append(f"{task_id}: closed successful terminal and usage required")
            billing = call.get("billing", {})
            cost = billing.get("cumulativeCostUsd")
            models = billing.get("models", [])
            if (not isinstance(cost, (int, float)) or not math.isfinite(cost) or cost < 0
                    or not isinstance(models, list) or not models
                    or any(not isinstance(m.get("costUsd"), (int, float)) or
                           not math.isfinite(m["costUsd"]) or m["costUsd"] < 0 for m in models)
                    or abs(sum(m["costUsd"] for m in models) - cost) > 1e-6):
                errors.append(f"{task_id}: billing snapshot mismatch")
            if mode == "live" and (not call.get("toolEvidence", {}).get("inits") or
                                   any(init.get("sessionId") != session_id for init in call["toolEvidence"]["inits"])):
                errors.append(f"{task_id}: native session init mismatch")
            if mode == "live":
                from agent_lab.routing_native import usage_snapshot

                observed = usage_snapshot(call.get("rawTerminal"))
                if not observed["valid"] or observed != billing:
                    errors.append(f"{task_id}: recomputed terminal usage mismatch")
    if mode == "prepared":
        if report.get("sdkQueries") != 0 or report.get("reportedSdkUsd") != 0:
            errors.append("Prepared fixtures cannot claim actual SDK usage")
    else:
        known = [call.get("billing", {}).get("cumulativeCostUsd") for call in queries.values()]
        total = sum(known) if all(isinstance(x, (int, float)) for x in known) else None
        if (report.get("sdkQueries") != len(queries) or total is None or
                report.get("reportedSdkUsd") is None or
                abs(total - report["reportedSdkUsd"]) > 1e-6 or
                total > selected.budget + 1e-6 or
                any(cost > .100001 for cost in known)):
            errors.append("Known bounded SDK query totals required")
    return {"status": "pass" if not errors else "needs-review", "criterion": "Routing suite returns a graded, successful result for every selected task.", "errors": errors}


def prepared(selected: RoutingInput, run_id: str | None = None) -> dict[str, Any]:
    run_id = run_id or str(uuid.uuid4())
    rows = [prepared_task(task_id, strategy) for strategy in selected.strategies for task_id in selected.taskIds]
    by_strategy = {strategy: metrics([row for row in rows if row["strategy"] == strategy],
                                     "synthetic-authored-fixture") for strategy in selected.strategies}
    report = {"lesson": 59, "runId": run_id, "config": {**selected.model_dump(), "runId": run_id},
              "mode": "prepared", "source": "scripted-fixture", "status": "success",
              "rows": rows, "metrics": by_strategy, "errors": [], "interrupted": False,
              "sdkQueries": 0, "reportedSdkUsd": 0,
              "projection": {"inputTokensPerTask": 1000, "outputTokensPerTask": 200,
                             "source": "illustrative-assumption", "ratesUsdPerMillion": RATES,
                             "limits": "Ignores quality, classifier overhead, thinking, failures, caching and actual latency."}}
    report["check"] = check_suite(report, selected)
    return report


def facts() -> dict[str, Any]:
    return {"lesson": 59, "tasks": [{"id": t.id, "prompt": t.prompt, "intendedTier": t.tier,
                                     "ruleTier": rule_tier(t.id), "answerSource": "independent-computed-answer-key"} for t in TASKS],
            "strategies": STRATEGIES, "models": MODELS, "ratesUsdPerMillion": RATES,
            "fixtureProvenance": "synthetic-authored-fixture",
            "note": "Configured IDs and rates are teaching assumptions, not account availability, live prices or measured benchmarks."}
