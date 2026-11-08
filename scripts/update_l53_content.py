"""Install Lesson 53 diagnostic teaching, questions and source tour."""

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
    item = next(row for row in lessons if row["id"] == 53)
    item.update({
        "prerequisites": [28, 51],
        "concept_brief": "A diagnostic trace is a causal record, not a summary of assistant prose. Lesson 53 tags host, hook, permission, SDK and stderr observations with one run UUID, correlates Read calls to results and independent fixture hashes, then persists a redacted bounded bundle. Prepared rows are authored; native rows are measured provider evidence.",
        "lab_brief": "Replay an offline diagnostic, then compare a changed configuration. Follow the causal sequence from the initial failure to the terminal state. Inspect the first useful finding before downstream symptoms. One changed effective field can clarify a hypothesis, but fresh IDs and model variation prevent a statistical causal claim. Optional native scenarios require fresh paid consent and a bounded isolated query.",
        "preparation": ["Complete Lessons 28 and 51 and start the local portal.",
                        "The prepared replays require no provider key, model call or network request."],
        "steps": [
            {"title": "Understand the goal", "text": "Locate the first actionable evidence, not the last visible symptom."},
            {"title": "Prepare your exercise", "text": "Select a prepared fault and leave log capture on."},
            {"title": "Run one example", "text": "Replay an offline diagnostic, then compare a changed configuration."},
            {"title": "Verify the evidence", "text": "Inspect the start UUID, contiguous trace rows, first finding, Read call/result ID, independent fixture hashes, saved digest and bounded redacted log."},
            {"title": "Try the challenge", "text": "Change one variable and explain whether it fixes the cause. Compare denied with success by changing only policy, then inspect both retained first findings."}],
        "inspect": "Follow the causal sequence from the initial failure to the terminal state. Denial is a policy decision before execution; missing-file has an admitted Read plus actual error. An API error can have a success subtype and isError true, and a later iterator exception does not erase that terminal. A missing log is unavailable evidence, not proof of no errors. Check run UUID and persisted SHA before judging.",
        "expected": "Seven fixed prepared replay shapes produce first findings: success none, denied permission-denied, missing missing-file, max-turns max-turns, startup startup, api-error api-error then iterator-exception, truncated missing-terminal. Prepared mode reports zero model calls and zero real cost. The saved bundle reloads by UUID with an exact digest; one-variable comparison names the changed effective field.",
        "evidence_criterion": "Saved diagnostic bundle correlates trace rows and actionable findings to this run.",
        "evidence_checks": [{"key": "experiment_passed", "rule": "equals", "value": True}],
        "challenge": "Change one effective variable between two retained runs. For example, compare a denied run with a success run by changing only policy. Explain whether the first permission-denied finding disappears, and why this local comparison does not prove general model reliability.",
        "hints": ["Start with the earliest finding row and its nextCheck, then follow the matching call ID through the trace.",
                  "Compare the five effective fields: policy, fixture, maxTurns, captureLog and producerFault. A one-variable comparison needs exactly one changed field and the same prepared/live provenance."],
        "reference": "The denied replay's first useful evidence is the false pre-read decision; a later error result and success-subtype terminal do not undo the denial. Changing only policy to allow can remove that cause in the authored success replay, whose exact Read result matches an unchanged independently hashed fixture. The store reloads the redacted bundle and hashes serialized bytes before the check. This is a fixed classroom contrast, not a controlled model experiment.",
        "recovery": ["If a run stops, use Recover saved bundle with its recorded UUID after cleanup; an interrupted bundle never earns automatic credit.",
                     "If live mode is denied, confirm the private backend key, enable_live, fresh consent and a supported fixed scenario. Prepared replays remain free."],
        "quiz": [
            question("What is the first useful evidence in a denied Read?", "The false pre-use policy decision for the exact call ID.", "The assistant's final apology.", "A higher max-turn setting.", "Authorization happens before execution."),
            question("Why keep a result followed by an iterator exception?", "Both observations occurred and may explain different parts of the run.", "The later exception makes the result imaginary.", "Only the assistant text matters.", "The collector preserves arrival order and a known terminal cost."),
            question("What proves a missing-file diagnosis?", "An admitted matching Read error plus independent absence of the owned fixture.", "The selected scenario label alone.", "A missing debug log.", "The host checks the actual file and correlated result."),
            question("How is an API-error terminal distinguished?", "It can have success subtype with isError true.", "Any success subtype proves task success.", "Only stderr determines it.", "Subtype and isError are separate SDK facts."),
            question("What does a missing raw log establish?", "The log evidence is unavailable; it does not establish no errors.", "The agent had no errors.", "The provider was never called.", "The bounded reader reports found false explicitly."),
            question("Which concept-map path produces a shareable bundle?", "Captured rows, bounded redaction, causal findings, then persisted reload and digest.", "Assistant prose straight to a bug report.", "A selected fault label straight to pass.", "Each boundary contributes independently checked evidence."),
            question("What does the walkthrough's one-variable comparison show?", "Exactly one effective field changed under the same provenance, with both first findings retained.", "A statistically controlled model experiment.", "The earlier bundle was overwritten.", "Fresh UUIDs and model variation remain limitations.")],
        "concept_code": "from agent_lab.debug_lab import DebugInput, diagnose, prepared_run, criterion\nfrom agent_lab.debug_store import DebugStore\nimport asyncio\nimport uuid\nfrom pathlib import Path\n\nroot = Path('.lab-data/lesson-53-example')\nselected = DebugInput(scenario='denied')\nrun_id = uuid.uuid4()\nbundle = asyncio.run(prepared_run(selected, root, run_id))\nloaded = DebugStore(root).save(bundle)\nassert bundle['findings'][0]['code'] == 'permission-denied'\nassert loaded['source'] == 'persisted-file-reload'\nassert criterion(str(run_id), selected, bundle, loaded['bundle'])",
        "code_focus": "`prepared_run` owns the fixture, collects normalized rows and closes before saving. `diagnose` names the first supported cause; `DebugStore` reloads the exact redacted bundle and `criterion` checks its run identity and rows.",
        "concept_points": [
            {"title": "Keep one run identity", "text": "Tag every host and SDK observation with a UUID and pair Read results with their call ID."},
            {"title": "Find the first cause", "text": "A denied policy decision or missing owned file can precede a later terminal symptom."},
            {"title": "Bound before sharing", "text": "Read at most 128,001 log bytes, label truncation, redact the exported text and reload a persisted digest."}],
        "misconception": {"claim": "A successful terminal subtype means every tool operation succeeded.",
                        "correction": "A denied or missing Read can have an error result and still be followed by a success-subtype terminal. Inspect call/result IDs, isError, host effects and any later exception."},
    })
    LESSONS.write_text(json.dumps(lessons, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    source = item["concept_code"]
    tours = json.loads(TOURS.read_text(encoding="utf-8"))
    tours["53"] = {"source_sha256": hashlib.sha256(source.encode()).hexdigest(),
                   "sections": [
                       {"title": "Create a fixed prepared run", "start": 7, "end": 10,
                        "text": "The selected fixed fault and owned UUID determine this classroom replay."},
                       {"title": "Reload the saved bundle", "start": 11, "end": 12,
                        "text": "The store writes a bounded redacted file, then independently reloads it."},
                       {"title": "Check causal evidence", "start": 13, "end": 14,
                        "text": "The first finding is a policy decision, and the automatic check verifies the run identity and saved rows."}]}
    TOURS.write_text(json.dumps(tours, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
