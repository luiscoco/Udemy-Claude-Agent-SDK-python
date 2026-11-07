"""Install Lesson 52 evaluation teaching content and code tour."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LESSONS = ROOT / "agent_lab/content/lessons.json"
TOURS = ROOT / "agent_lab/content/code_tours.json"


def question(prompt: str, answer: str, wrong_a: str, wrong_b: str, reason: str) -> dict:
    return {"prompt": prompt, "options": [
        {"text": answer, "explanation": "Correct. " + reason},
        {"text": wrong_a, "explanation": "No. " + reason},
        {"text": wrong_b, "explanation": "No. " + reason}], "correct": 0}


def main() -> None:
    lessons = json.loads(LESSONS.read_text(encoding="utf-8"))
    item = next(row for row in lessons if row["id"] == 52)
    item.update({
        "prerequisites": [51],
        "concept_brief": "An eval combines fixed cases, business checks and a judge. Lesson 52 compares three Ada support cases across retained trials. The free demo is authored synthetic fixture data with zero model calls. A measured live report uses fresh isolated DeskStore effects and separate SDK costs. A judge label is not a reliability certificate; inspect calibration before using a score for promotion.",
        "lab_brief": "Run the synthetic baseline comparison. Inspect the three cases, business scope/effect/money checks, five rubric criteria, Wilson intervals, Fisher exact evidence and agent-versus-judge cost. Try cold tone and false refund, then calibrate the heuristic against forty human-labelled decisions. Review a retained report and its digest before any synthetic baseline promotion. Optional paid runs require fresh consent, a bounded budget and an isolated native SDK measurement.",
        "preparation": ["Complete Lesson 51 and distinguish synthetic authored trials from measured model behavior.", "Start the local portal; the first evaluation needs no provider key or credit."],
        "steps": [
            {"title": "Understand the goal", "text": "Separate business effects, heuristic judgement and statistical uncertainty."},
            {"title": "Prepare your exercise", "text": "Select baseline, three trials per case and the free synthetic route."},
            {"title": "Run one example", "text": "Run the baseline comparison, then calibrate the heuristic."},
            {"title": "Verify the evidence", "text": "Inspect nine exact trial rows, twenty-four metric rows, zero model calls and the calibration's two semantic misses."},
            {"title": "Try the challenge", "text": "Change the candidate to cold tone or false refund and decide whether the regression gate passes."}],
        "inspect": "Inspect caseId and index for every trial, source, complete, modelCalls, actualBilledUsd, scope/effect/money, five structured verdicts, calibration kappa and lenient errors, comparison status and cost. A missing live baseline is stale; a weak drop without enough Fisher evidence is suspect; missing manifest or cost is error.",
        "expected": "Baseline and fix-findings synthetic candidates pass. Cold tone fails empathy and next-step metrics; false refund fails the hard money gate. The fixed heuristic calibrates at 38/40 agreement, kappa about 0.805 and two visible lenient semantic misses. Each normal comparison has 24 case/criterion rows. Live runs remain measured observations until a compatible reviewed baseline exists.",
        "evidence_criterion": "Distinct complete authored synthetic baseline and candidate reports have exact trial manifests, matching heuristic fingerprint, zero model calls and zero actual billing; a recomputed comparison passes. Paid reports never satisfy this automatic check.",
        "evidence_checks": [{"key": "experiment_passed", "rule": "equals", "value": True}],
        "challenge": "Run cold tone and false refund separately. Explain why the first loses empathy and next-step points and why the second fails the hard money rule. Try one trial per case and observe the narrower Wilson intervals and weaker statistical evidence. Restore a three-trial baseline run before asking for automatic credit.",
        "hints": ["Compare each candidate row against the exact case and inspect business checks before judge prose.", "A 3/3 to 0/3 pass-rate drop has one-sided Fisher p=0.05; money and scope fail on any measured candidate miss. A missing baseline is stale, not a pass."],
        "reference": "The host stores exact case/index trial rows with isolated provenance. A business failure is measured even if a reply sounds reassuring. The heuristic uses disclosed keyword rules and misses invented Friday shipment and funds-sent claims; calibration reports those lenient errors. Comparison uses one-sided Fisher, Wilson intervals, hard money/scope gates and a 1.5× agent-cost limit. Promotion reads a retained eligible report, checks its current harness fingerprint and reviewed digest, then writes only that provenance/judge baseline. This classroom harness cannot certify production reliability.",
        "recovery": ["If a report is stale, re-measure the baseline under the current harness and judge; synthetic and live reports cannot be compared.", "If a run has unknown terminal cost, malformed judge output, interruption or missing rows, inspect the retained partial report before retrying with fresh consent."],
        "quiz": [
            question("What does a passing synthetic comparison establish?", "The fixed host report contract passed using authored fixture rows and zero model calls.", "The live model improved across deployment traffic.", "The model judge is production certified.", "Synthetic trials teach interpretation without measuring a model."),
            question("Why calibrate a judge before using it for promotion?", "A label alone cannot show agreement or lenient mistakes against human gold items.", "Calibration makes every future reply correct.", "A heuristic score is the same as a business effect.", "The forty decisions expose disagreement, marginals, kappa and leniency."),
            question("Why is a new live report called stale when no live baseline exists?", "There is no compatible retained measurement to compare yet.", "The agent always failed its support tools.", "A synthetic baseline can automatically substitute.", "Live and synthetic provenance must remain separate."),
            question("What does an unknown terminal cost do to a comparison?", "It produces an error rather than a silent tie or pass.", "It counts as zero dollars.", "It improves the agent-cost mean.", "The comparison needs known costs for each measured row."),
            question("Why can a reassuring false-refund reply fail?", "The hard money check uses the actual denied host effect, not the reply claim.", "Empathy is always forbidden.", "A model judge cannot read English.", "Business checks are grounded in independently reloaded effects."),
            question("Which diagram path reaches baseline promotion?", "Retained run, eligibility gate, reviewed digest, then scoped baseline write.", "Button click, then automatic live release.", "Synthetic demo, then production certification.", "A click is separate from successful promotion."),
            question("What do the two known calibration misses show?", "A keyword heuristic can pass semantic inventions despite high aggregate agreement.", "The human labels must be rewritten to match the heuristic.", "The model judge is calibrated by the heuristic set.", "The invented Friday and funds-sent replies remain visible lenient errors.")],
        "concept_code": "from agent_lab.evals_core import calibrate, compare, synthetic_criterion, synthetic_report\n\n\nbase = synthetic_report('baseline', trials=3)\ncandidate = synthetic_report('cold-tone', trials=3)\nresult = compare(base, candidate)\nassert len(result['metrics']) == 24\nassert result['status'] == 'fail'\n\ncalibration = calibrate()\nassert calibration['summary']['lenientErrors'] == 2\n\nfixed = synthetic_report('fix-findings', trials=3)\npassing = compare(base, fixed)\nassert synthetic_criterion(base, fixed, passing)",
        "code_focus": "`synthetic_report` creates explicitly authored rows, `compare` applies measured hard and statistical gates, `calibrate` exposes the heuristic's known semantic misses and `synthetic_criterion` requires exact zero-call evidence.",
        "concept_points": [
            {"title": "Keep provenance visible", "text": "Authored synthetic replies and business booleans teach report reading. Live trials require fresh isolated host effects and SDK receipts."},
            {"title": "Separate checkers", "text": "Business scope/effect/money checks read host facts. The heuristic or optional model judge scores the reply under five named criteria."},
            {"title": "Compare with uncertainty", "text": "Wilson intervals, Fisher evidence, hard gates and cost limits produce pass, fail, suspect, stale or error."}],
        "misconception": {"claim": "A synthetic improvement or a high judge agreement score proves the deployed agent is better.", "correction": "The synthetic values are authored, and eight golden replies are a small calibration set. Promotion requires compatible retained measurements and still is not production certification."},
    })
    LESSONS.write_text(json.dumps(lessons, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    source = item["concept_code"]
    tours = json.loads(TOURS.read_text(encoding="utf-8"))
    tours["52"] = {"source_sha256": hashlib.sha256(source.encode()).hexdigest(),
                   "sections": [
                       {"title": "Compare authored candidates", "start": 4, "end": 8,
                        "text": "The fixed cold-tone candidate loses rubric criteria across exact trials."},
                       {"title": "Inspect judge calibration", "start": 10, "end": 11,
                        "text": "Two semantic inventions are deliberately missed by the keyword heuristic."},
                       {"title": "Require complete evidence", "start": 13, "end": 15,
                        "text": "Only the authored zero-call passing comparison earns the automatic check."}]}
    TOURS.write_text(json.dumps(tours, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
