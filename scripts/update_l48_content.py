"""Install the authored Lesson 48 security lesson in shared course JSON."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LESSONS = ROOT / "agent_lab/content/lessons.json"
TOURS = ROOT / "agent_lab/content/code_tours.json"


def question(prompt: str, answer: str, distractor_a: str, distractor_b: str,
             explanation: str) -> dict:
    return {"prompt": prompt, "options": [
        {"text": answer, "explanation": "Correct. " + explanation},
        {"text": distractor_a, "explanation": "No. " + explanation},
        {"text": distractor_b, "explanation": "No. " + explanation}], "correct": 0}


def main() -> None:
    rows = json.loads(LESSONS.read_text(encoding="utf-8"))
    lesson = next(row for row in rows if row["id"] == 48)
    lesson.update({
        "prerequisites": [4, 7, 18],
        "concept_brief": "Security hardening combines a small child environment, fixed tool admission, known-marker output rewriting and independent effect checks. A tool denial is a control observation, while a protected file remaining unread, an outside file remaining unchanged and a collector receiving no known marker are separate outcome observations. The local lab performs real effects on synthetic owned fixtures. Live mode needs native SDK calls and a host-owned model observer. These checks cover only the fixed probes and known markers; they are not a universal security guarantee.",
        "lab_brief": "Choose permissions, lockdown, secrets or injection. Each action runs a contrast lane and a guarded lane with fresh synthetic file, outside and environment canaries. The host records fixed Read, Write and Bash call decisions, result identities, collector receipts, the outside file digest and whether a known marker entered model context. Negative scenarios alter recorded evidence offline. A paid live action has a $0.10 cap per lane and $0.20 total cap.",
        "preparation": ["Predict which fixed probes the guarded policy denies and which safe read remains allowed.",
                        "Run local mode first. A live run needs a private Anthropic key, enabled access and fresh consent."],
        "steps": [
            {"title": "Understand the goal", "text": "Identify the file, outside path, child environment and collector as separate trust boundaries."},
            {"title": "Prepare your exercise", "text": "Choose one of four fixed patterns and predict the contrast and guarded results."},
            {"title": "Run one example", "text": "Inspect the local real file and process effects, hook decisions and call/result IDs."},
            {"title": "Verify the evidence", "text": "Check the guarded denial, output rewrite, unchanged outside digest, collector and closure observations."},
            {"title": "Try the challenge", "text": "Run the leaked negative scenario and explain which independent flag invalidates it."}],
        "inspect": "Compare both lanes' fixed calls, hook decisions, result IDs, known-marker flags, outside digest, collector hits and source labels.",
        "expected": "The guarded lane denies protected reads, outside writes and owned egress; a safe diagnostic read can be rewritten. No known canary enters its observed model context or collector, and the outside file stays unchanged.",
        "evidence_criterion": "A guarded fixed probe has correlated denial and independent containment and file-effect checks.",
        "evidence_checks": [{"key": "experiment_passed", "rule": "truthy"}],
        "challenge": "Run the leaked scenario. Explain why a passing denial alone cannot override a collector leak flag, and which concrete observation should be investigated.",
        "hints": ["Match the assistant tool ID to the pre-hook decision and returned tool result ID.",
                  "Compare the guarded collector hits and outside digest after the process ends."],
        "reference": "The host admits only four fixed owned read paths, one exact outside marker write and one literal Python probe command with a fixed target. Guarded policy denies the .env and outside read, outside write and egress target. The child receives an owned home, fake API credential and only selected OS plumbing; the guarded lane omits the synthetic application secret. PostToolUse replaces exact known marker values in a serialized response. Independent checks inspect real outside bytes, marker creation, collector receipts and model-bound request bytes. Encoded or unknown secrets remain outside this exact rewrite guarantee. A prompt-injection ticket is treated as untrusted content while the host retains the same tool policy.",
        "recovery": ["If a tool call is absent, inspect the fixed prompt, SDK assistant tool ID and pre-hook row; do not invent a result.",
                     "If the guarded lane leaks, inspect the model observer and collector receipts without displaying marker values.",
                     "If the provider rejects a live run, keep the live acceptance pending and inspect its sanitized status and terminal result."],
        "quiz": [
            question("What does the guarded PreToolUse decision control?", "Admission of one exact tool input", "All future model text", "The provider billing account", "The host checks one tool name and literal arguments against the fixed owned set."),
            question("Why inspect the outside file after a denial?", "It independently checks the disk effect", "The hook already proves disk state", "The model summary is enough", "A hook row and real file bytes are different observations."),
            question("Which value enters the guarded child environment?", "An owned fake API credential", "The host's real API credential", "The synthetic application secret", "The host constructs a fresh small environment for the child."),
            question("What can the known-marker rewrite guarantee?", "Exact known marker replacement in that tool response", "Removal of every unknown secret", "Safe interpretation of all file instructions", "The rewrite is deliberately bounded to registered exact values."),
            question("What invalidates a guarded run after a denied egress call?", "A collector receipt containing a known marker", "A contrast-lane collector receipt", "A safe diagnostic read", "The guarded collector must remain free of known marker bodies."),
            question("In the concept map, where does the untrusted ticket lead?", "A host tool-admission decision", "Automatic execution of its instruction", "The provider credential store", "File content is data; later tool calls still pass through host admission."),
            question("In the walkthrough, what follows a PostToolUse rewrite?", "Check model-bound request bytes and independent effects", "Trust a local hook log alone", "Assume unknown encodings are covered", "The observer and fresh file/collector checks establish the bounded outcome."),
        ],
        "concept_code": "from pathlib import Path\nfrom agent_lab.hardening_policy import admission, rewrite_known_output\n\n\ndef guarded_probe(tool: str, arguments: dict, work: Path, outside: Path, script: Path, collector_url: str, known: tuple[str, ...]) -> bool:\n    allowed, _code, _reason = admission(tool, arguments, guarded=True, work=work, outside=outside, executable=Path(__import__('sys').executable), script=script, collector_url=collector_url)\n    if not allowed:\n        return False\n    _output, proof = rewrite_known_output({'content': 'safe diagnostic'}, known)\n    return not proof['after_contains']\n",
        "code_focus": "The host admits exact tool arguments before execution. The known-marker rewrite is a separate output boundary; neither replaces independent file, collector or wire checks.",
        "concept_points": [
            {"title": "Small child environment", "text": "Pass owned configuration and a generated credential, then verify which synthetic variables reached the child."},
            {"title": "Exact admission", "text": "Match a fixed tool name, path, command and content before allowing an effect."},
            {"title": "Independent outcome", "text": "Inspect output rewrite, model request, outside bytes and collector receipts separately."}],
        "misconception": {"claim": "A denied tool call proves the entire agent run is secure.",
                          "correction": "The host also checks actual file, collector and model-bound effects for the fixed synthetic probes. These observations do not cover arbitrary unknown secrets or attacks."},
    })
    LESSONS.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tours = json.loads(TOURS.read_text(encoding="utf-8"))
    code = lesson["concept_code"]
    tours["48"] = {"source_sha256": hashlib.sha256(code.encode()).hexdigest(), "sections": [
        {"title": "Use the real host policy", "start": 1, "end": 2,
         "text": "The teaching example imports the package's actual admission and rewrite functions."},
        {"title": "Admit the exact call", "start": 5, "end": 8,
         "text": "The guarded host policy checks tool input before any effect."},
        {"title": "Check rewritten output", "start": 9, "end": 11,
         "text": "A safe response is checked for registered marker forms after rewriting."},
    ]}
    TOURS.write_text(json.dumps(tours, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
