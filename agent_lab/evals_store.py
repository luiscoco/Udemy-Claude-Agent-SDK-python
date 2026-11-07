"""Retained Lesson 52 reports, scoped baselines, promotion and pairwise review."""

import json
import os
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agent_lab.evals_core import (
    BASELINE_PATH,
    CASE_IDS,
    compare,
    fingerprint,
    heuristic,
    review_digest,
    trial_manifest,
)


class MissingRun(LookupError):
    pass


class IneligibleRun(ValueError):
    pass


def _replace(source: Path, target: Path) -> None:
    for attempt in range(8):
        try:
            os.replace(source, target)
            return
        except PermissionError as exc:
            if getattr(exc, "winerror", None) not in {5, 32, 33} or attempt == 7:
                raise
            time.sleep(0.02 * (attempt + 1))


class EvalStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.runs = root / "runs"
        self.baselines = root / "baselines"

    def save(self, report: dict[str, Any]) -> None:
        identifier = uuid.UUID(report["id"])
        self.runs.mkdir(parents=True, exist_ok=True)
        path = self.runs / f"{identifier}.json"
        with path.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
            stream.write("\n")

    def load(self, identifier: uuid.UUID) -> dict[str, Any]:
        path = self.runs / f"{identifier}.json"
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise MissingRun("Retained eval run was not found") from exc
        if report.get("id") != str(identifier):
            raise IneligibleRun("Retained run identity differs from its owned file")
        return report

    def _baseline_path(self, mode: str, judge: str) -> Path:
        if mode not in {"synthetic", "live"} or judge not in {"heuristic", "model"}:
            raise ValueError("Unknown baseline scope")
        return self.baselines / f"{mode}-{judge}.json"

    def baseline(self, mode: str, judge: str) -> dict[str, Any] | None:
        path = self._baseline_path(mode, judge)
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
        if mode == "synthetic" and judge == "heuristic":
            return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        return None

    def review(self, report: dict[str, Any]) -> dict[str, Any]:
        return {"runId": report["id"], "reviewHash": review_digest(report),
                "eligible": promotion_error(report) is None,
                "promotionError": promotion_error(report),
                "comparison": compare(self.baseline(report["mode"], report["judge"]), report)}

    def promote(self, identifier: uuid.UUID, expected_hash: str, note: str) -> dict[str, Any]:
        report = self.load(identifier)
        reason = promotion_error(report)
        if reason is not None:
            raise IneligibleRun(reason)
        if review_digest(report) != expected_hash:
            raise IneligibleRun("Reviewed report digest changed")
        path = self._baseline_path(report["mode"], report["judge"])
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + f".{uuid.uuid4().hex}.tmp")
        try:
            temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            _replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
        audit = {"runId": str(identifier), "reviewHash": expected_hash,
                 "mode": report["mode"], "judge": report["judge"],
                 "note": note, "at": datetime.now(UTC).isoformat()}
        with (self.baselines / "promotion-audit.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(audit, ensure_ascii=False) + "\n")
        return {"promoted": True, "baseline": report, "audit": audit}

    def pairwise(self, left_id: uuid.UUID, right_id: uuid.UUID, case_id: str) -> dict[str, Any]:
        if case_id not in CASE_IDS:
            raise IneligibleRun("Unknown fixed case")
        left, right = self.load(left_id), self.load(right_id)
        if (not trial_manifest(left) or not trial_manifest(right) or
                not left.get("complete") or not right.get("complete") or
                left.get("mode") != right.get("mode") or left.get("judge") != right.get("judge") or
                left.get("fingerprint") != right.get("fingerprint")):
            raise IneligibleRun("Pairwise runs are incomplete or incompatible")
        a = next(row for row in left["rows"] if row["caseId"] == case_id and row["index"] == 0)
        b = next(row for row in right["rows"] if row["caseId"] == case_id and row["index"] == 0)
        score_a = sum(item["pass"] for item in heuristic(a["reply"]).values())
        score_b = sum(item["pass"] for item in heuristic(b["reply"]).values())
        preferred = "left" if score_a > score_b else "right" if score_b > score_a else "tie"
        return {"caseId": case_id, "left": str(left_id), "right": str(right_id),
                "ab": {"A": str(left_id), "B": str(right_id), "winner": "A" if preferred == "left" else "B" if preferred == "right" else "tie"},
                "ba": {"A": str(right_id), "B": str(left_id), "winner": "B" if preferred == "left" else "A" if preferred == "right" else "tie"},
                "consistent": True, "scores": {"left": score_a, "right": score_b},
                "scope": "Disclosed local keyword preference; position reversal is diagnostic only"}


def promotion_error(report: dict[str, Any]) -> str | None:
    if report.get("fingerprint") != fingerprint(str(report.get("judge"))):
        return "Harness fingerprint changed; re-measure the baseline"
    if not report.get("complete") or report.get("trials") != 3 or not trial_manifest(report):
        return "Only complete three-trial-per-case reports are eligible"
    if report.get("mode") == "live" and report.get("judge") != "model":
        return "A live baseline requires a model judge"
    if report.get("mode") not in {"synthetic", "live"}:
        return "Unknown report provenance"
    if report.get("actualBilledUsd") is None:
        return "Actual cost is unknown"
    for row in report["rows"]:
        if not all(row["business"].values()) or not all(item["pass"] for item in row["verdict"].values()):
            return "A trial failed a business or rubric criterion"
    return None
