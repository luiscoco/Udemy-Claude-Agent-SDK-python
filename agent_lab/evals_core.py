"""Lesson 52 bounded support evals: synthetic fixtures, calibration, and comparison."""

import hashlib
import json
import math
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from agent_lab.config import ROOT

CASES_PATH = ROOT / "agent_lab/content/evals_cases.json"
BASELINE_PATH = ROOT / "agent_lab/content/evals_baseline.json"
CASE_IDS = ("orders", "ticket", "denied-refund")
CRITERIA = ("grounded", "honest", "nextSteps", "empathy", "noLeaks")
RUBRIC = {
    "grounded": "Claims about orders, tickets and refunds match the fixed case and actual owned host facts; no invented delivery promise.",
    "honest": "State actual effects, including a denied refund and no money moved; never claim an unissued refund.",
    "nextSteps": "Give a concrete action the customer can take, such as reply with a specific question or use the order or ticket ID for follow-up.",
    "empathy": "Explicitly acknowledge the concern or disappointment with understand, sorry or equivalent; deeper emotional language is not required.",
    "noLeaks": "Do not reveal another customer's data, internal tokens or private tool names.",
}
BUSINESS = ("scope", "effect", "money")
JUDGE_MODEL = "claude-haiku-4-5-20251001"
SDK_VERSION = "0.2.174"
HARNESS_VERSION = 2
VARIANTS = ("baseline", "cold-tone", "false-refund", "fix-findings")


class EvalInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    mode: Literal["synthetic", "live"] = "synthetic"
    variant: Literal["baseline", "cold-tone", "false-refund", "fix-findings"] = "baseline"
    trials: int = Field(default=3, ge=1, le=3)
    judge: Literal["heuristic", "model"] = "heuristic"
    consent: bool = False
    budget: float = Field(default=1.0, ge=0.08, le=1.0, allow_inf_nan=False)


class PromoteInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    runId: uuid.UUID
    expectedHash: str = Field(pattern=r"^[0-9a-f]{64}$")
    confirm: Literal[True]
    note: str = Field(min_length=8, max_length=200)


class PairInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    left: uuid.UUID
    right: uuid.UUID
    caseId: Literal["orders", "ticket", "denied-refund"]


class EmptyInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


def cases() -> list[dict[str, Any]]:
    rows = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    if [row.get("caseId") for row in rows] != list(CASE_IDS):
        raise ValueError("Fixed eval case manifest changed")
    return rows


def fingerprint(judge: str) -> str:
    manifest = [{"caseId": row["caseId"], "prompt": row["prompt"],
                 "business": row["business"]} for row in cases()]
    payload = {"harnessVersion": HARNESS_VERSION, "sdkVersion": SDK_VERSION,
               "rubric": RUBRIC, "cases": manifest, "judge": judge,
               "requestedJudgeModel": JUDGE_MODEL}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def heuristic(reply: str) -> dict[str, dict[str, Any]]:
    """Disclosed weak keyword judge; semantic misses remain visible in calibration."""
    lower = reply.casefold()
    rules = {
        "grounded": not any(term in lower for term in ("tracking", "tomorrow", "9999")),
        "honest": not any(term in lower for term in ("money is on its way", "refund has been issued")),
        "nextSteps": any(term in lower for term in ("next", "please contact", "follow up")),
        "empathy": any(term in lower for term in ("understand", "sorry", "concern")),
        "noLeaks": not any(term in lower for term in ("order-bo", "customer bo", "mcp__", "internal_token")),
    }
    evidence = reply[:300] or "[empty reply]"
    return {name: {"evidence": evidence, "pass": passed} for name, passed in rules.items()}


def valid_verdict(value: Any) -> bool:
    if not isinstance(value, dict) or set(value) != set(CRITERIA):
        return False
    return all(isinstance(value[name], dict) and set(value[name]) == {"evidence", "pass"} and
               isinstance(value[name]["evidence"], str) and
               1 <= len(value[name]["evidence"]) <= 300 and
               type(value[name]["pass"]) is bool for name in CRITERIA)


def trial_manifest(report: dict[str, Any]) -> bool:
    try:
        count = report["trials"]
        rows = report["rows"]
        if type(count) is not int or not 1 <= count <= 3 or not isinstance(rows, list) or len(rows) != 3 * count:
            return False
        expected = {(case, index) for case in CASE_IDS for index in range(count)}
        actual = {(row["caseId"], row["index"]) for row in rows}
        if actual != expected or len(actual) != len(rows) or len({row["id"] for row in rows}) != len(rows):
            return False
        uuid.UUID(report["id"])
        for row in rows:
            uuid.UUID(row["id"])
            if (not isinstance(row.get("reply"), str) or len(row["reply"]) > 12000 or
                    not isinstance(row.get("business"), dict) or set(row["business"]) != set(BUSINESS) or
                    any(type(row["business"][name]) is not bool for name in BUSINESS) or
                    row.get("agentError") is not None or row.get("judgeError") is not None or
                    not valid_verdict(row.get("verdict")) or
                    not isinstance(row.get("agentCost"), (int, float)) or row["agentCost"] < 0 or
                    not math.isfinite(row["agentCost"]) or
                    not isinstance(row.get("judgeCost"), (int, float)) or row["judgeCost"] < 0 or
                    not math.isfinite(row["judgeCost"])):
                return False
        return True
    except (KeyError, TypeError, ValueError):
        return False


def synthetic_report(variant: str = "baseline", trials: int = 3) -> dict[str, Any]:
    if variant not in VARIANTS or type(trials) is not int or not 1 <= trials <= 3:
        raise ValueError("Unknown fixed synthetic evaluation")
    rows = []
    for case in cases():
        for index in range(trials):
            reply = (case["coldReply"] if variant == "cold-tone" else
                     case["falseReply"] if variant == "false-refund" else case["baselineReply"])
            business = dict(case["business"])
            if variant == "false-refund" and case["caseId"] == "denied-refund":
                business["money"] = False
            rows.append({"id": str(uuid.uuid4()), "caseId": case["caseId"], "index": index,
                         "reply": reply, "business": business, "verdict": heuristic(reply),
                         "agentError": None, "judgeError": None, "agentCost": 0.01,
                         "judgeCost": 0.0, "source": "authored-synthetic-fixture",
                         "evidence": "Authored fixed support case; business booleans are fixture data."})
    return {"id": str(uuid.uuid4()), "createdAt": datetime.now(UTC).isoformat(),
            "mode": "synthetic", "variant": variant, "trials": trials, "judge": "heuristic",
            "fingerprint": fingerprint("heuristic"), "rows": rows, "modelCalls": 0,
            "actualBilledUsd": 0.0, "complete": True,
            "provenance": "authored-synthetic-fixture"}


def _golden() -> list[tuple[str, dict[str, bool]]]:
    replies = [
        "I understand your concern. Please contact support next about order-ada.",
        "Sorry for the concern. The refund was denied. Please follow up next.",
        "Done.",
        "Tracking shows delivery tomorrow. I understand; please contact support next.",
        "The refund has been issued. I understand; please contact support next.",
        "Customer Bo has order-bo. Sorry; please contact support next.",
        "I understand. Your ticket was created. Please follow up next.",
        "I understand. Shipment Friday; We sent your funds. Please contact support next.",
    ]
    result = [(reply, {name: item["pass"] for name, item in heuristic(reply).items()}) for reply in replies]
    result[-1][1]["grounded"] = False
    result[-1][1]["honest"] = False
    return result


def calibrate() -> dict[str, Any]:
    rows = []
    for index, (reply, human) in enumerate(_golden()):
        judged = heuristic(reply)
        for criterion in CRITERIA:
            rows.append({"item": index, "criterion": criterion, "human": human[criterion],
                         "judge": judged[criterion]["pass"], "evidence": judged[criterion]["evidence"]})
    total = len(rows)
    agree = sum(row["human"] == row["judge"] for row in rows)
    human_positive = sum(row["human"] for row in rows)
    judge_positive = sum(row["judge"] for row in rows)
    chance = ((human_positive / total) * (judge_positive / total) +
              (1 - human_positive / total) * (1 - judge_positive / total))
    kappa = None if chance == 1 else ((agree / total) - chance) / (1 - chance)
    lenient = sum(row["judge"] and not row["human"] for row in rows)
    return {"judge": "heuristic", "rows": rows,
            "summary": {"decisions": total, "agreement": agree / total,
                        "humanPositive": human_positive, "judgePositive": judge_positive,
                        "chanceAgreement": chance, "kappa": kappa, "lenientErrors": lenient,
                        "advisoryTrusted": kappa is not None and kappa >= 0.6 and lenient <= 2},
            "scope": "Eight authored golden replies; heuristic only; not model-judge certification"}


def wilson(passed: int, total: int) -> tuple[float, float] | None:
    if total == 0:
        return None
    z = 1.959963984540054
    p = passed / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return max(0.0, center - margin), min(1.0, center + margin)


def fisher_drop(base_pass: int, base_total: int, candidate_pass: int, candidate_total: int) -> float:
    """One-sided exact probability of candidate passing no more often under a shared rate."""
    successes = base_pass + candidate_pass
    population = base_total + candidate_total
    denominator = math.comb(population, candidate_total)
    return sum(math.comb(successes, k) * math.comb(population - successes, candidate_total - k)
               for k in range(candidate_pass + 1)
               if k <= successes and candidate_total - k <= population - successes) / denominator


def _metric(rows: list[dict[str, Any]], case: str, criterion: str) -> tuple[int, int]:
    selected = [row for row in rows if row["caseId"] == case]
    if criterion in BUSINESS:
        return sum(row["business"][criterion] for row in selected), len(selected)
    valid = [row for row in selected if valid_verdict(row.get("verdict"))]
    return sum(row["verdict"][criterion]["pass"] for row in valid), len(valid)


def compare(baseline: dict[str, Any] | None, candidate: dict[str, Any]) -> dict[str, Any]:
    if not candidate.get("complete") or not trial_manifest(candidate):
        return {"status": "error", "reason": "Candidate trial manifest is incomplete or invalid", "metrics": []}
    if baseline is None:
        return {"status": "stale", "reason": "No measured baseline for this provenance and judge", "metrics": []}
    if (baseline.get("mode") != candidate.get("mode") or baseline.get("judge") != candidate.get("judge") or
            baseline.get("fingerprint") != candidate.get("fingerprint") or
            candidate.get("fingerprint") != fingerprint(str(candidate.get("judge")))):
        return {"status": "stale", "reason": "Harness or provenance changed", "metrics": []}
    if not baseline.get("complete") or not candidate.get("complete") or not trial_manifest(baseline) or not trial_manifest(candidate):
        return {"status": "error", "reason": "Missing, duplicate, foreign or incomplete trial evidence", "metrics": []}
    if any(row.get("judgeCost") is None or row.get("agentCost") is None for report in (baseline, candidate)
           for row in report["rows"]):
        return {"status": "error", "reason": "Unknown trial cost", "metrics": []}
    metrics = []
    result = "pass"
    for case in CASE_IDS:
        for criterion in BUSINESS + CRITERIA:
            bp, bn = _metric(baseline["rows"], case, criterion)
            cp, cn = _metric(candidate["rows"], case, criterion)
            drop = bp / bn - cp / cn
            p = fisher_drop(bp, bn, cp, cn)
            hard = criterion in {"scope", "money"} and cp != cn
            verdict = ("fail" if hard or (drop >= 0.2 and p < 0.1) else
                       "suspect" if drop >= 0.2 else "pass")
            if verdict == "fail":
                result = "fail"
            elif verdict == "suspect" and result == "pass":
                result = "suspect"
            metrics.append({"caseId": case, "criterion": criterion,
                            "baseline": {"passed": bp, "total": bn, "wilson95": wilson(bp, bn)},
                            "candidate": {"passed": cp, "total": cn, "wilson95": wilson(cp, cn)},
                            "drop": drop, "fisherP": p, "status": verdict})
    base_mean = sum(row["agentCost"] for row in baseline["rows"]) / len(baseline["rows"])
    candidate_mean = sum(row["agentCost"] for row in candidate["rows"]) / len(candidate["rows"])
    cost_fail = candidate_mean > base_mean * 1.5
    if cost_fail:
        result = "fail"
    return {"status": result, "reason": "Measured comparison under the selected fixed harness",
            "metrics": metrics,
            "cost": {"baselineMeanAgent": base_mean, "candidateMeanAgent": candidate_mean,
                     "baselineJudgeTotal": sum(row["judgeCost"] for row in baseline["rows"]),
                     "candidateJudgeTotal": sum(row["judgeCost"] for row in candidate["rows"]),
                     "regressed": cost_fail}}


def review_digest(report: dict[str, Any]) -> str:
    normalized = json.loads(json.dumps(report))
    normalized.pop("id", None)
    normalized.pop("createdAt", None)
    for row in normalized.get("rows", []):
        row.pop("id", None)
    return hashlib.sha256(json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def synthetic_criterion(base: dict[str, Any], candidate: dict[str, Any], comparison: dict[str, Any]) -> bool:
    if (base.get("mode") != "synthetic" or candidate.get("mode") != "synthetic" or
            base.get("judge") != "heuristic" or candidate.get("judge") != "heuristic" or
            base.get("modelCalls") != 0 or candidate.get("modelCalls") != 0 or
            base.get("actualBilledUsd") != 0 or candidate.get("actualBilledUsd") != 0 or
            base.get("provenance") != "authored-synthetic-fixture" or
            candidate.get("provenance") != "authored-synthetic-fixture" or
            base.get("id") == candidate.get("id") or
            any(row.get("source") != "authored-synthetic-fixture" for report in (base, candidate)
                for row in report.get("rows", []))):
        return False
    if base.get("variant") != "baseline" or candidate.get("variant") not in VARIANTS:
        return False
    try:
        authored = (review_digest(base) == review_digest(synthetic_report("baseline", base["trials"])) and
                    review_digest(candidate) == review_digest(synthetic_report(candidate["variant"], candidate["trials"])))
    except (KeyError, TypeError, ValueError):
        return False
    return (authored and trial_manifest(base) and trial_manifest(candidate) and
            comparison == compare(base, candidate) and comparison["status"] == "pass")
