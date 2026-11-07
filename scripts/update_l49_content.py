"""Install authored Lesson 49 headless and CI teaching in course JSON."""

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
    lesson = next(item for item in lessons if item["id"] == 49)
    lesson.update({
        "prerequisites": [15, 28, 48],
        "concept_brief": "A headless CI job needs a machine result, an actual process outcome and an explicit host policy code. Text alone is insufficient. This Python edition runs owned subprocesses with EOF stdin and separately bounded stdout and stderr. Native CLI and SDK queries use schema-constrained reports; the SDK exit code is a host mapping after its successful terminal, while the CLI has a real operating-system close code. A local loopback worker demonstrates one slot, drain and deadline behavior without deploying a container or cloud service.",
        "lab_brief": "Headless compares CLI and SDK clean-fixture reports. CI compares separate clean PASS/[] and buggy FAIL/[EVAL,PERCENT] reports. Limits runs six actual owned child cases with policy codes 0, 11, 11, 12, 124 and 127. Deploy starts one local Python worker, checks HTTP health and readiness, one admitted job, a second 429, draining 503, job completion and closed TCP. Local machine reports are authored fixture data. Only Headless and CI have paid native modes, capped at $0.10 per query.",
        "preparation": ["Inspect the fixed clean and buggy pricing source and the offline CI example.",
                        "Predict which process outcomes should fail a job. Paid modes need a private key, live access and fresh consent."],
        "steps": [
            {"title": "Understand the goal", "text": "Separate child exit, host policy code, machine report and CI verdict."},
            {"title": "Prepare your exercise", "text": "Inspect the supplied source and configuration examples; predict PASS/[] and FAIL/[EVAL,PERCENT]."},
            {"title": "Run one example", "text": "Run local Headless and inspect separate stdout/stderr and the stdin EOF observation."},
            {"title": "Verify the evidence", "text": "Compare exact run ID, fixture digest, result shape, exit codes and close receipt."},
            {"title": "Try the challenge", "text": "Run Limits or CI and explain why successful model text can still fail a CI job."}],
        "inspect": "Compare actual process close codes, host policy codes, CI codes, machine reports, HTTP results and generated summaries. Check source hashes before and after.",
        "expected": "Headless has exactly CLI and SDK with zero policy codes and exact clean PASS reports. CI has clean PASS/0 and buggy FAIL/20 after two successful model runs. Limits shows actual failures and Deploy shows one local worker drain, not a cloud deployment.",
        "evidence_criterion": "CLI and SDK headless paths both exit successfully.",
        "evidence_checks": [{"key": "experiment_passed", "rule": "truthy"}],
        "challenge": "Which of the six process outcomes should fail CI, and why does a correct buggy-fixture FAIL verdict still produce CI code 20?",
        "hints": ["Start with actual close code, whether a machine terminal exists, error and permission-denial fields.",
                  "The host maps process failures first. A valid model classification of buggy source is successful inference but failing source quality."],
        "reference": "The local child always receives EOF on stdin and writes separate pipes. The host maps cancellation 130, timeout 124, missing executable 127, nonzero child close 10, missing or unsuccessful machine terminal 11, permission denial 12 and successful terminal 0. These are lab policy codes, not native Claude CLI exit conventions. A verified buggy source report is FAIL with EVAL and PERCENT; its model process can succeed while the CI code is 20. The source is only read and hashed, never executed. The local worker has one slot: an admitted job holds it, a second returns 429, drain makes readiness 503, release completes the job, and a fresh TCP connection fails after exit. Example Dockerfile and offline workflow are teaching files, not deployment evidence.",
        "recovery": ["If headless fails, inspect actual CLI close, stderr and the unique machine result before changing the host mapping.",
                     "If CI reports the wrong issues, compare schema output with the exact owned source digest; do not run or eval the buggy file.",
                     "If the worker check fails, match listening, job-start, draining, job-end and closed receipts to the same run and job IDs."],
        "quiz": [
            question("What proves a headless CLI result?", "Actual zero close plus one matching successful machine result", "Assistant prose saying PASS", "An empty stderr alone", "The host checks both process and structured terminal evidence."),
            question("How is the SDK exit code obtained?", "The host maps the SDK terminal after iteration", "It is a second observed OS exit", "It is copied from model prose", "Only the CLI process has a native OS close code."),
            question("What is the policy code for a real timeout?", "124", "0", "20", "The host killed and awaited the owned child after its deadline."),
            question("A child exits zero but has no machine terminal. What happens?", "Policy code 11", "CI passes", "The last text becomes a result", "A zero process close cannot substitute for a terminal result."),
            question("Why is buggy CI code 20?", "The valid model report identifies failing fixed source", "The model process crashed", "The worker did not drain", "Successful inference and passing source quality are separate decisions."),
            question("On the concept map, what does the host join?", "Process close, result identity and fixture digest", "Only model text", "Only a Dockerfile", "Independent host observations establish the bounded check."),
            question("On the walkthrough, what follows the second job's 429?", "Drain readiness 503 and release of the held job", "Automatic cloud publication", "A second worker slot", "The one-slot local worker must reject new work while draining."),
        ],
        "concept_code": "from agent_lab.headless_lab import mapped_exit, report_valid\n\n\ndef ci_decision(process: dict, terminal: dict | None, run_id: str) -> int:\n    code = mapped_exit(process, terminal)\n    if code != 0:\n        return code\n    if terminal is None:\n        return 11\n    report = terminal['structured_output']\n    if not report_valid(report, run_id, 'buggy'):\n        return 11\n    return 20  # Valid FAIL classification still fails the CI job.\n",
        "code_focus": "mapped_exit is a host policy over real process and terminal facts. report_valid checks exact run identity and fixed fixture truth; a buggy source can have successful inference and a failing CI code.",
        "concept_points": [
            {"title": "Real process boundary", "text": "EOF stdin, separate bounded pipes, deadline and actual close are observed facts."},
            {"title": "Exact machine result", "text": "Schema output, run ID, fixture digest and expected verdict must agree."},
            {"title": "Local deployment demonstration", "text": "A one-slot worker handles health, readiness, job, drain and closure over loopback."}],
        "misconception": {"claim": "A model saying PASS or a Dockerfile proves a CI deployment succeeded.",
                          "correction": "The host requires actual process and machine-result evidence. The worker is local; the configuration files are teaching examples, not deployed infrastructure."},
    })
    LESSONS.write_text(json.dumps(lessons, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tours = json.loads(TOURS.read_text(encoding="utf-8"))
    code = lesson["concept_code"]
    tours["49"] = {"source_sha256": hashlib.sha256(code.encode()).hexdigest(), "sections": [
        {"title": "Use host evidence checks", "start": 1, "end": 1,
         "text": "The concept imports the real process policy and exact report checker."},
        {"title": "Map process outcomes first", "start": 4, "end": 7,
         "text": "The host code decides whether a process and terminal are valid before considering fixture quality."},
        {"title": "Fail buggy source quality", "start": 8, "end": 11,
         "text": "A valid FAIL classification still yields CI code 20 for the fixed buggy source."},
    ]}
    TOURS.write_text(json.dumps(tours, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
