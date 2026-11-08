"""Install Lesson 55 synthetic upgrade teaching and seven explained questions."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LESSONS = ROOT / "agent_lab/content/lessons.json"
TOURS = ROOT / "agent_lab/content/code_tours.json"


def question(prompt: str, right: str, wrong_a: str, wrong_b: str, explanation: str) -> dict:
    return {"prompt": prompt, "options": [
        {"text": right, "explanation": "Correct. " + explanation},
        {"text": wrong_a, "explanation": "No. " + explanation},
        {"text": wrong_b, "explanation": "No. " + explanation}], "correct": 0}


def main() -> None:
    lessons = json.loads(LESSONS.read_text(encoding="utf-8"))
    item = next(row for row in lessons if row["id"] == 55)
    source = ("from agent_lab.upgrading_lab import RunInput, TransitionInput, run_upgrade, criterion, transition\n"
              "\n"
              "selected = RunInput(scenario='compatible')\n"
              "report = run_upgrade(selected)  # synthetic fixture, observed installed inventory\n"
              "assert report['modelCalls'] == report['networkAttempts'] == 0\n"
              "assert criterion(selected, report)\n"
              "canary = transition(TransitionInput(scenario='compatible', state='checked', action='start-canary'))\n"
              "assert canary['newState'] == 'canary'\n"
              "blocked = run_upgrade(RunInput(scenario='renamed-result'))\n"
              "assert blocked['decision'] == 'blocked'\n")
    item.update({
        "prerequisites": [51, 52],
        "concept_brief": "An SDK version number alone cannot establish application compatibility. Compare observed installed inventory with four independent synthetic candidate contracts: exports, correlated stream events, denied outside Write and quality/cost/latency limits. This workshop rehearses decisions offline; it installs and deploys nothing.",
        "lab_brief": "Run all nine fixed candidate fixtures. A compatible candidate must pass every gate; each incompatible one must fail a concrete gate. Rehearse checked, canary, promoted and rolled-back states without changing dependencies. Synthetic records are not real candidate SDK transcripts or benchmarks.",
        "preparation": ["Complete Lessons 51 and 52 and open the local portal.",
                        "This lesson needs no API key, model call, network request or SDK installation."],
        "steps": [{"title": "Understand the goal", "text": "Inspect the actual pin, lock and installed SDK, then the four independent synthetic gates."},
                  {"title": "Prepare your exercise", "text": "Select compatible and predict why every gate should pass."},
                  {"title": "Run one example", "text": "Run compatibility gates, start the simulated canary, promote, then roll back."},
                  {"title": "Verify the evidence", "text": "Inspect gate observations, unchanged dependency SHA-256, zero model/network/cost counters and the simulation label."},
                  {"title": "Try the challenge", "text": "Select renamed-result or another failing fixture and verify that promotion is blocked by a specific contract."}],
        "inspect": "The compatible fixture has init, exact owned Read and matching result, completed task notification, additive event and nonerror terminal. Each incompatible fixture changes one independent contract. Observe failed gate evidence and recovery, not only an eligible label.",
        "expected": "Observed declared, locked and installed SDK versions agree. Compatible passes exports, stream, permissions and eval gates and can be simulated through canary, promotion and rollback. Eight incompatible fixtures are blocked by concrete failures. Dependency bytes remain unchanged and model/network/cost counters are zero.",
        "evidence_criterion": "The offline compatibility gates agreed with the selected fixture: a compatible candidate passed every gate, or an incompatible candidate was blocked by a failing gate. This is a simulation, not a real SDK upgrade.",
        "evidence_checks": [{"key": "experiment_passed", "rule": "equals", "value": True}],
        "challenge": "Select the renamed-result fixture, inspect its failed stream gate, and explain why an additive future event is tolerated while a missing required result field blocks promotion.",
        "hints": ["Compare the fixture's terminal fields with what the application adapter requires.",
                  "The adapter needs a nonempty terminal `result`, matched session and call IDs, a successful owned Read and a completed task notification. `answer` cannot replace `result`; an unknown additive event may be counted and ignored."],
        "reference": "The compatible candidate passes all four independent synthetic gates and may enter a simulated canary from checked state. Renamed-result changes the required terminal field, so the stream gate fails even though an unknown additive event is harmless. An ineligible candidate cannot start canary or promote. Rollback is allowed from a simulated canary or promoted state. Real upgrade work still needs isolated candidate installation, release-note review, real SDK behavior tests, comparable evaluations and a measured canary.",
        "recovery": ["If inventory is inconsistent, restore the exact pyproject pin, lock and installed environment before interpreting candidate eligibility.",
                     "If a fixture is blocked, read each failed gate's observed evidence and recovery instruction. Stop or edit the scenario before running fresh gates."],
        "quiz": [
            question("Does a newer SDK version alone make a candidate eligible?", "No; every application contract and observed inventory must pass.", "Yes; newer means compatible.", "Yes, if it imports.", "Version order does not prove stream, permission or metric behavior."),
            question("Which artifacts should be retained for a real rollback?", "Known-good package/lock, configuration, evaluation baseline and data snapshots.", "Only the latest SDK version string.", "Only the synthetic fixture report.", "Rollback must restore code and data that the old runtime can read."),
            question("What happens to an unknown additive stream event?", "It is counted but does not replace required evidence.", "It automatically passes the stream gate.", "It always fails the gate.", "The adapter tolerates additions while requiring exact init, call, task and terminal evidence."),
            question("Why does renamed-result block the synthetic candidate?", "The required nonempty terminal result field is absent.", "The candidate is older.", "The unknown event appears.", "An `answer` field does not satisfy the application adapter's `result` contract."),
            question("What does permission-drift change?", "The simulated decision allows an outside Write that must be denied.", "It changes the operating system sandbox.", "It removes the Read fixture.", "The fixed permission probe evaluates actual simulated decisions, not an OS Write."),
            question("Which transition can promote a compatible candidate?", "Canary to promoted after an eligible checked run.", "Baseline directly to promoted.", "Rolled-back directly to promoted.", "The state machine requires an eligible checked-to-canary step first."),
            question("What does a 20% synthetic cost limit compare?", "Candidate cost against the positive baseline cost, inclusively.", "Actual vendor billing.", "A model token count.", "The metric gate uses fixed authored values, not billed usage.")],
        "concept_code": source,
        "code_focus": "`run_upgrade` observes the installed environment and applies four actual evaluators to authored candidate records. `criterion` recomputes the evidence, while `transition` enforces simulated state order.",
        "concept_points": [{"title": "Observed environment", "text": "Read pyproject, uv.lock, installed metadata and public exports without installing or querying."},
                           {"title": "Independent contracts", "text": "Required stream evidence and permission boundaries cannot be offset by a higher quality score."},
                           {"title": "Simulated rollout", "text": "Eligibility permits checked-to-canary-to-promoted state teaching; rollback restores only the demonstration state."}],
        "misconception": {"claim": "A passing synthetic canary proves a real SDK upgrade is safe.",
                        "correction": "The workshop tests authored fixture contracts. A real candidate needs isolated installation, release review, native SDK behavior checks, repeated evaluation and measured rollout evidence."},
    })
    LESSONS.write_text(json.dumps(lessons, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tours = json.loads(TOURS.read_text(encoding="utf-8"))
    tours["55"] = {"source_sha256": hashlib.sha256(source.encode()).hexdigest(), "sections": [
        {"title": "Observe a fixed candidate", "start": 3, "end": 4,
         "text": "The workshop reads actual installed inventory while assessing an authored synthetic candidate."},
        {"title": "Check the bounded evidence", "start": 5, "end": 6,
         "text": "The criterion requires a complete zero-call report matching the selected fixture."},
        {"title": "Rehearse and challenge", "start": 7, "end": 10,
         "text": "Only an eligible checked candidate can start canary; the renamed terminal is blocked."}]}
    TOURS.write_text(json.dumps(tours, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
