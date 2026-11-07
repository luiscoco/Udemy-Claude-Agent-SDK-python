"""Install the authored Lesson 47 orchestration teaching in shared course JSON."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LESSONS = ROOT / "agent_lab/content/lessons.json"
TOURS = ROOT / "agent_lab/content/code_tours.json"


def question(prompt: str, correct: str, wrong_a: str, wrong_b: str, reason: str) -> dict:
    return {"prompt": prompt, "options": [
        {"text": correct, "explanation": "Correct. " + reason},
        {"text": wrong_a, "explanation": "No. " + reason},
        {"text": wrong_b, "explanation": "No. " + reason}], "correct": 0}


def main() -> None:
    rows = json.loads(LESSONS.read_text(encoding="utf-8"))
    lesson = next(item for item in rows if item["id"] == 47)
    lesson.update({
        "prerequisites": [8, 10],
        "concept_brief": "An orchestrator arranges fixed workers, but a parent summary is not child evidence. The host records each worker's start, ownership, depth, completion, report and independent verdict. Native Agent delegation and host-controlled separate queries are different scheduling sources. A fair limiter bounds simultaneous host jobs, not shared model spend.",
        "lab_brief": "Compare five patterns: native orchestrator and hierarchy, then host-controlled pipeline, regional fan-out and one writer/critic pass. Local mode authors lifecycle rows while reading owned CSV files. Live mode uses isolated SDK queries and joins actual native task and hook identities. The sales fixture totals are north 55/P2, south 69/P1 and east 86/P2.",
        "preparation": ["Inspect the fixed north, south and east CSV rows and predict each total and best product.",
                        "Start with local mode. Paid live actions require a private Anthropic key, enabled live access and fresh consent."],
        "steps": [
            {"title": "Understand the goal", "text": "Distinguish native Agent delegation from separate queries scheduled by the host."},
            {"title": "Prepare your exercise", "text": "Predict the worker tree, file owner, and which completions are required for one pattern."},
            {"title": "Run one example", "text": "Run the authored host fixture, then inspect start/end IDs and independent host verdicts."},
            {"title": "Verify the evidence", "text": "With fresh consent, join native task IDs, owned Read hooks, reports and SDK terminal costs."},
            {"title": "Try the challenge", "text": "Stop the north fan-out worker and explain why south/east can finish while the dependent merge is skipped."}],
        "inspect": "Compare delegation, worker depth, task outcomes and total cost. Match each worker completion to its start and a host verdict.",
        "expected": "A completed worker has the same identity as its start, a valid owned report and an independent passing host verdict. Parent prose alone cannot pass.",
        "evidence_criterion": "Orchestration has a completed worker correlated to its start and a host verdict.",
        "evidence_checks": [{"key": "experiment_passed", "rule": "truthy"}],
        "challenge": "Stop one regional worker and explain what happens to its dependent merge. Check which other workers complete and whether their reports remain individually valid.",
        "hints": ["Start with each worker ID, parent, depth and owner. A parent answer is not a worker completion.",
                  "Find the cancelled north end record and compare it with south/east. A dependent merge needs every required passing regional report; the limiter must still release its slot."],
        "reference": "In fan-out, north, south and east own separate CSVs. Each successful worker needs an owned Read, matching start/end identity, a report line and a host verdict derived from fixture truth. When north is cancelled, south and east may still complete, but the aggregate is skipped because one required region is missing. The host limiter releases a slot even when a worker fails or is cancelled. Native Agent task depth is distinct from host query dependency depth, and SDK cost ceilings are per query rather than one shared spend pool.",
        "recovery": ["If a worker is absent, inspect its native task start, completion notification and SubagentStop report before trusting the parent answer.",
                     "If the report is wrong, compare the anchored region line with the fixture rows and verify the owned file hash.",
                     "If a live action fails, inspect the first sanitized hook denial, terminal subtype and reserved cost without broadening tool or path access."],
        "quiz": [
            question("What proves a delegated analyst finished?", "A matched native start, completion and host verdict", "A parent summary mentioning the analyst", "An Agent tool name by itself", "Child lifecycle and the independent verdict must join by stable identity."),
            question("What does the host limiter bound?", "Concurrent host jobs", "A shared model token budget", "Total monetary spend automatically", "The limiter transfers one reserved slot; query budgets remain separate."),
            question("A completion has a foreign worker ID. What should the checker do?", "Reject the run", "Use the closest role name", "Trust the parent answer", "Starts and ends must match the same unique worker ID."),
            question("The analyst gate lets a second stop through with wrong numbers. Is the report valid?", "No; the host still compares fixture truth", "Yes; the gate passed", "Yes; the parent summarized it", "A second-stop bypass prevents a loop and is not proof of arithmetic."),
            question("East.csv is missing in fan-out. What is valid?", "Record the real file error and skip the dependent merge", "Invent east totals from prose", "Use north's file as east", "All required regional reports must pass independently."),
            question("On the concept map, which arrow denotes native nested delegation?", "Lead to manager to analyst", "Three independent regional queries", "The host limiter queue", "Only the native tree has child task depth beyond the host root."),
            question("On the lab walkthrough, what follows a checked extractor report?", "A digest-bound handoff to specialist", "An unchecked parent summary", "An automatic shared budget", "The host verifies a report before allowing its dependent query to start."),
        ],
        "concept_code": "from agent_lab.orchestra_lab import FairLimiter, check_report\n\n\nasync def run_owned_worker(limiter: FairLimiter, report: str) -> bool:\n    await limiter.acquire()\n    try:\n        valid, _reason = check_report(report, \"north\")\n        return valid\n    finally:\n        limiter.release()\n",
        "code_focus": "FairLimiter transfers a reserved slot to one waiter and releases after failure. check_report compares one anchored line with fixture totals, while native child hooks and terminal evidence establish actual delegated work.",
        "concept_points": [
            {"title": "Identity before summary", "text": "Join worker start, end, owner, report and verdict by one ID."},
            {"title": "Two scheduling sources", "text": "Native Agent children and host-controlled separate queries have different depth and cost meanings."},
            {"title": "Verified dependencies", "text": "A pipeline or evaluator handoff starts only after its predecessor passes the host check."}],
        "misconception": {"claim": "A plausible parent summary proves every child completed correctly.",
                          "correction": "The host requires each worker's lifecycle, owned Read, report and independent verdict. Missing or foreign child evidence fails even if the parent answer is correct."},
    })
    LESSONS.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tours = json.loads(TOURS.read_text(encoding="utf-8"))
    code = lesson["concept_code"]
    tours["47"] = {"source_sha256": hashlib.sha256(code.encode()).hexdigest(), "sections": [
        {"title": "Import the host checks", "start": 1, "end": 1,
         "text": "The concept uses the actual fair limiter and report checker from this Python package."},
        {"title": "Reserve one host slot", "start": 4, "end": 5,
         "text": "The worker waits until the limiter grants a reserved slot before it checks the report."},
        {"title": "Release even after failure", "start": 6, "end": 10,
         "text": "The finally clause releases or transfers the slot regardless of the report outcome."},
    ]}
    TOURS.write_text(json.dumps(tours, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
