"""Install Lesson 51 offline host testing teaching and code tour."""

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
    item = next(row for row in lessons if row["id"] == 51)
    item.update({
        "prerequisites": [1, 5, 7],
        "concept_brief": "Unit tests can exercise agent host policy without calling a model. Lesson 51 injects fixed synthetic SDK-style envelopes into a real Python host consumer, then checks identity, tool correlation, scoped effects, budget, terminal state and cleanup. The complete 16-case suite is the graded criterion; filtered groups, mutation and individual replay are separate observations. Synthetic cost is never billed cost.",
        "lab_brief": "Run all 16 offline host assertions, inspect each returned case row and verify modelCalls=0 and actualBilledUsd=0. Then enable the mutation challenge: only denial-policy changes its observed code from 12 to 0, so exactly one unchanged assertion fails. Restore the normal suite. Replay success, budget, API error, invalid session, truncated stream and malformed tool fixtures through the real host consumer. The standalone command installs a controlled Python network guard before loading host suite modules.",
        "preparation": ["Read the fixed synthetic stream fixture and distinguish it from native SDK wire messages.", "Start the local app or run `uv run python scripts/offline_host.py`; no API key, live selector or provider credit is needed."],
        "steps": [
            {"title": "Understand the goal", "text": "Test actual host contracts with injected deterministic input while making zero model calls."},
            {"title": "Prepare your exercise", "text": "Choose All 16 assertions and leave the mutation challenge unchecked."},
            {"title": "Run one example", "text": "Run the offline suite, then replay the success and budget fixtures through the host consumer."},
            {"title": "Verify the evidence", "text": "Inspect 16 ordered assertion rows, 16/16 summary, zero model/network calls, matched tool result and closed fake query."},
            {"title": "Try the challenge", "text": "Enable the denial-policy mutation, explain its one failing assertion, then turn it off and rerun the normal suite."}],
        "inspect": "Compare `assertions`, `summary`, `modelCalls`, `actualBilledUsd`, `cleanup`, `experiment_passed` and replay `fixture`, `handler`, `terminalCount`, `simulatedCostUsd`, `closed`. The replay stream is synthetic; the scoped handler is real host code.",
        "expected": "All normal cases pass in manifest order, with 16/16, zero model calls, zero actual billing and owned cleanup. Contracts/Store/Replay groups show 6/2/8 passing assertions but do not earn complete-suite credit. Mutation shows 15/16 with only denial-policy failing. Six public replays produce success, budget, api-error, invalid, truncated and invalid-tool; no replay earns suite credit.",
        "evidence_criterion": "The complete, unmodified offline test suite finished with every case passing and zero model API calls. This does not grade the separate mutation challenge.",
        "evidence_checks": [{"key": "experiment_passed", "rule": "equals", "value": True}],
        "challenge": "Run with the mutation checkbox selected. `denial-policy` still expects host code 12 but observes 0; the single failure is intentional. Restore mutation off and confirm 16/16 again. In a shell, `uv run python scripts/offline_host.py --mutation` exits 1 while the normal command exits 0.",
        "hints": ["The mutation changes only the observed denial code inside one test case; the expected assertion remains 12.", "Inspect the `denial-policy` row: the unchanged host policy returns 12 for a permission denial, while the deliberately substituted policy returns 0. A separate normal rerun must still pass."],
        "reference": "The normal host suite calls real strict input, exit mapping, approval and scoped store contracts, then feeds fixed fake-query envelopes to the real host consumer. It counts returned results, checks terminal and call IDs, closes the query and reports zero model calls. The mutation replaces only the denial observation, so its one failure teaches why weakening an expectation is not a fix. Replay costs are simulated values, not API spend.",
        "recovery": ["If an offline assertion fails unexpectedly, inspect its bounded detail and the real host contract it called; run the standalone command to separate browser behavior from host behavior.", "If a replay needs review, inspect its synthetic fixture, status and cleanup. Invalid input is rejected before work. There is no live fallback for this lesson."],
        "quiz": [
            question("What does the complete offline suite establish?", "The host contracts passed deterministic tests with zero model calls.", "Claude would choose the same tools in a live conversation.", "The synthetic fixture is raw SDK wire compatibility.", "An injected stream tests host logic, not model choices."),
            question("How should the budget replay's 0.05 USD be labeled?", "Simulated cost; actual billed cost is zero.", "A real provider invoice.", "A discounted live model call.", "The fixture value triggers a host budget status without billing."),
            question("Why does foreign-result fail?", "Its tool-result ID differs from the admitted tool-call ID.", "Its answer text is too short.", "It uses the wrong visual guide.", "The host joins exact call and result identities."),
            question("What happens when a stream ends without a terminal?", "The host reports truncated and closes the fake query.", "The last text delta counts as success.", "The host invents a zero-cost terminal.", "A terminal is required evidence; prose is insufficient."),
            question("Why does the mutation challenge show one failure?", "It substitutes denial code 0 while the assertion still expects 12.", "The model refused the request.", "All 16 expectations were weakened.", "Only the denial-policy observation is deliberately changed."),
            question("Which path can earn the automatic check?", "The unmodified All group with 16 matched passing assertions and zero calls.", "Any filtered group with all selected cases passing.", "One successful synthetic replay.", "The exact complete suite, summary and owned cleanup are required."),
            question("What does the host-handler observation in the concept map represent?", "A real scoped DeskStore snapshot for Ada's owned order.", "A native Claude tool choice.", "A paid refund processor.", "The fixture drives the call but the host lookup uses the actual store contract.")],
        "concept_code": "from agent_lab.offline_lab import FakeQuery, run_offline_host, run_suite\n\n\nasync def test_without_a_model(root):\n    complete = await run_suite(root, group='all', mutation=False)\n    assert complete['summary']['passed'] == 16\n    assert complete['modelCalls'] == 0\n    assert complete['experiment_passed'] is True\n\n    fake = FakeQuery('success')  # fixed synthetic envelopes\n    observed = await run_offline_host(root, 'success')\n    assert observed['handlerCount'] == 1\n    assert observed['matchedResult'] is True\n    assert observed['actualBilledUsd'] == 0",
        "code_focus": "`run_suite` executes sixteen real host assertions in order, `FakeQuery` supplies fixed normalized envelopes and `run_offline_host` validates them while calling the real scoped store. `evaluate_suite` accepts only the complete unmodified 16/16/0 report.",
        "concept_points": [
            {"title": "Inject deterministic input", "text": "FakeQuery yields fixed envelopes. It is not a native SDK call and cannot prove model behavior."},
            {"title": "Assert real host outcomes", "text": "Tests call the actual exit mapping, approver and scoped store, then verify tool IDs, terminal states and cleanup."},
            {"title": "Keep grading exact", "text": "Only the complete unmodified 16-case suite with zero model calls passes. Mutation and replay stay separate."}],
        "misconception": {"claim": "A fake message stream proves the agent will behave the same way live.", "correction": "It proves the host handles those injected inputs. Live model choices and native SDK wire behavior require separate validation, which this intentionally offline lesson does not perform."},
    })
    LESSONS.write_text(json.dumps(lessons, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    source = item["concept_code"]
    tours = json.loads(TOURS.read_text(encoding="utf-8"))
    tours["51"] = {"source_sha256": hashlib.sha256(source.encode()).hexdigest(),
                   "sections": [
                       {"title": "Normal complete suite", "start": 1, "end": 8,
                        "text": "The complete normal suite checks sixteen real host cases and zero model calls."},
                       {"title": "Fixed fake query", "start": 10, "end": 11,
                        "text": "FakeQuery holds fixed normalized envelopes; the host consumer, not a provider, reads them."},
                       {"title": "Real host observation", "start": 12, "end": 14,
                        "text": "The host executes one scoped order lookup, matches its result and records no billed cost."}]}
    TOURS.write_text(json.dumps(tours, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
