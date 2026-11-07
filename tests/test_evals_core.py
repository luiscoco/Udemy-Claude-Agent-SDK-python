"""Lesson 52 decision boundaries and retained baseline effects."""

import copy
import uuid

import pytest

from agent_lab.evals_core import (
    calibrate,
    compare,
    fisher_drop,
    synthetic_criterion,
    synthetic_report,
    trial_manifest,
    wilson,
)
from agent_lab.evals_store import EvalStore, IneligibleRun, MissingRun


def test_synthetic_comparison_gates_and_uncertainty():
    baseline = synthetic_report()
    good = synthetic_report("fix-findings")
    result = compare(baseline, good)
    assert result["status"] == "pass" and len(result["metrics"]) == 24
    assert synthetic_criterion(baseline, good, result)
    assert compare(baseline, synthetic_report("cold-tone"))["status"] == "fail"
    money = compare(baseline, synthetic_report("false-refund"))
    assert money["status"] == "fail"
    assert next(row for row in money["metrics"] if row["caseId"] == "denied-refund" and row["criterion"] == "money")["status"] == "fail"
    assert fisher_drop(3, 3, 0, 3) == pytest.approx(0.05)
    assert wilson(3, 3) is not None and 0 <= wilson(3, 3)[0] < wilson(3, 3)[1] <= 1
    expensive = copy.deepcopy(good)
    for row in expensive["rows"]:
        row["agentCost"] = 0.02
    assert compare(baseline, expensive)["cost"]["regressed"] is True
    assert not synthetic_criterion(baseline, expensive, compare(baseline, expensive))
    missing = copy.deepcopy(good)
    missing["rows"].pop()
    assert not trial_manifest(missing) and compare(baseline, missing)["status"] == "error"
    foreign = copy.deepcopy(good)
    foreign["rows"][0]["caseId"] = "foreign"
    assert compare(baseline, foreign)["status"] == "error"
    stale = copy.deepcopy(good)
    stale["fingerprint"] = "0" * 64
    assert compare(baseline, stale)["status"] == "stale"
    assert compare(None, good)["status"] == "stale"


def test_calibration_keeps_known_semantic_misses_visible():
    result = calibrate()
    assert len(result["rows"]) == 40
    assert result["summary"]["lenientErrors"] == 2
    assert result["summary"]["kappa"] == pytest.approx(0.804878, abs=0.00001)
    assert result["summary"]["advisoryTrusted"] is True
    assert {(row["item"], row["criterion"]) for row in result["rows"]
            if row["judge"] and not row["human"]} == {(7, "grounded"), (7, "honest")}


def test_retained_restart_promotion_digest_conflicts_and_pairwise(tmp_path):
    store = EvalStore(tmp_path)
    baseline = synthetic_report()
    cold = synthetic_report("cold-tone")
    store.save(baseline)
    store.save(cold)
    reopened = EvalStore(tmp_path)
    assert reopened.load(uuid.UUID(baseline["id"])) == baseline
    assert reopened.baseline("live", "model") is None
    review = reopened.review(baseline)
    assert review["eligible"] is True
    with pytest.raises(IneligibleRun):
        reopened.promote(uuid.UUID(baseline["id"]), "0" * 64, "Reviewed baseline")
    with pytest.raises(MissingRun):
        reopened.load(uuid.uuid4())
    with pytest.raises(IneligibleRun):
        reopened.promote(uuid.UUID(cold["id"]), reopened.review(cold)["reviewHash"], "Cold is weaker")
    promoted = reopened.promote(uuid.UUID(baseline["id"]), review["reviewHash"], "Reviewed all trials")
    assert promoted["promoted"] and EvalStore(tmp_path).baseline("synthetic", "heuristic") == baseline
    pair = reopened.pairwise(uuid.UUID(baseline["id"]), uuid.UUID(cold["id"]), "orders")
    assert pair["ab"]["winner"] == "A" and pair["ba"]["winner"] == "B"
