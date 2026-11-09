"""Install Lesson 56 coordination teaching and seven explained questions."""

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
    item = next(row for row in lessons if row["id"] == 56)
    source = ("from agent_lab.teams_lab import canonical_input, run_replay, grade\n"
              "\n"
              "partial = canonical_input(15)\n"
              "assert not grade(partial, run_replay(partial))  # cleanup is not accepted yet\n"
              "selected = canonical_input(16)\n"
              "report = run_replay(selected)\n"
              "assert [row['code'] for row in report['state']['receipts'] if not row['accepted']] == [\n"
              "    'dependency-incomplete', 'task-already-owned', 'shutdown-busy',\n"
              "    'ack-requires-delivery', 'evidence-rejected']\n"
              "assert grade(selected, report)  # exact tasks, ack and cleanup\n")
    item.update({
        "prerequisites": [8, 47],
        "concept_brief": "A team coordinator must track membership, exclusive task ownership, dependencies, message delivery and exact completion evidence independently. Sending or acknowledging text does not complete work. The free workshop is an application reducer; optional native Agent/SendMessage observes named SDK tools, not an interactive native team.",
        "lab_brief": "Step through sixteen fixed commands or run the whole reducer. Five deliberate refusals expose a dependency, competing claim, busy shutdown, early acknowledgment and wrong evidence. Only exact completed tasks, one acknowledged peer message, two shutdown members and lead cleanup pass. The optional paid observation makes one bounded SDK query with two turns and separate evidence.",
        "preparation": ["Complete Lessons 8 and 47 and open the local portal.",
                        "The team replay and guide are free; native observation requires fresh consent, live access and a private Anthropic key."],
        "steps": [{"title": "Understand the goal", "text": "Separate ownership, inbox state and task completion evidence."},
                  {"title": "Prepare your exercise", "text": "Select the first walkthrough step and predict why reviewer cannot claim review early."},
                  {"title": "Run one example", "text": "Step through or run all sixteen canonical commands; then try a custom command and reset."},
                  {"title": "Verify the evidence", "text": "Inspect every receipt, the five refusals, one acknowledged envelope, exact task owners and accepted cleanup."},
                  {"title": "Try the challenge", "text": "Explain why a sent message does not prove the task was completed, and test premature cleanup."}],
        "inspect": "A reviewer claim before research is complete is refused. The duplicate evidence-1 send retains one envelope, an ack before delivery is refused, and the wrong research evidence 30 is refused. The exact peer message is acknowledged, then research and review complete, both members shut down and lead cleanup is accepted.",
        "expected": "The canonical replay has sixteen ordered receipts, exactly five deliberate refusals, one acknowledged message, research owned/completed by researcher with `12 + 18 + 7 = 37`, review owned/completed by reviewer with `verified: 37`, both workers shutdown and closed true. Prefixes 0–15 need review. Free counters are zero.",
        "evidence_criterion": "Simulated team replay completes evidence-gated tasks, acknowledgments and cleanup.",
        "evidence_checks": [{"key": "experiment_passed", "rule": "equals", "value": True}],
        "challenge": "Send a custom peer message, then attempt cleanup before delivery, acknowledgment and exact task completion. Explain which state facts are missing even though a send receipt exists.",
        "hints": ["Find the message status and task statuses separately in the reducer state.",
                  "Send creates a queued envelope only. Deliver and ack change inbox status; complete still requires actual ownership, exact fixture evidence and, for review, acknowledged researcher evidence. Cleanup also requires shutdown members."],
        "reference": "The canonical replay first refuses a dependent review claim and a competing research claim. It keeps the duplicate ID as one envelope, refuses ack before delivery and wrong evidence 30, then accepts exact research evidence and the dependent review evidence. Sending alone changes no task status. Cleanup succeeds only after both exact completions, acknowledgment and shutdown. The optional native SDK observation can show Agent and SendMessage tool results but cannot independently prove the worker received or completed a message.",
        "recovery": ["If a command is refused, read its receipt code and verify member state, task owner, dependency and message status before retrying.",
                     "Reset after custom commands to resume the canonical sequence. Stop a partial native observation and inspect its bounded frames; another paid run needs fresh consent."],
        "quiz": [
            question("What does the free team reducer represent?", "Application-owned coordination state, not an interactive native team.", "A real Claude team process.", "A distributed durable mailbox.", "Each replay computes a fresh local state from authored commands."),
            question("Does sending evidence complete the research task?", "No; the owner must submit the exact completion evidence.", "Yes, after transport accepts it.", "Yes, after reviewer reads it.", "Messages and task status are independent transitions."),
            question("Why is reviewer claiming research refused?", "Researcher already owns the running task.", "The arithmetic is wrong.", "Reviewer lacks an API key.", "Ownership is exclusive until completion."),
            question("Can reviewer acknowledge a queued message?", "No; it must first be delivered to reviewer.", "Yes, any known ID can be acknowledged.", "Only lead can acknowledge.", "Ack requires the exact recipient and delivered status."),
            question("What happens if the same message ID has a changed body?", "The conflict is refused and the original envelope remains.", "The new text overwrites it.", "Both envelopes are retained.", "Idempotence applies only to identical sender, recipient and body."),
            question("When can lead cleanup succeed?", "After exact task completion, worker shutdown and all messages acknowledged.", "Immediately after a send.", "Whenever the answer contains 37.", "Cleanup checks independent task, member and inbox state."),
            question("What does a native SendMessage result establish here?", "An observed tool response, not independent worker delivery or completion.", "A durable worker acknowledgment.", "A verified interactive team.", "The lab has no independent worker-side delivery audit."),
        ],
        "concept_code": source,
        "code_focus": "`replay_team` reduces bounded command history into fresh state. `grade` recomputes exact ownership, evidence, acknowledgments and cleanup. Native observations keep tool IDs and result limits separate.",
        "concept_points": [{"title": "Exclusive ownership", "text": "Claims require active idle members, unowned tasks and completed dependencies."},
                           {"title": "Inbox is not completion", "text": "Send, deliver and ack have distinct receipts; none marks a task complete."},
                           {"title": "Evidence-gated cleanup", "text": "Exact owners and evidence, both shutdown workers and acknowledged messages close the simulation."}],
        "misconception": {"claim": "The model sent a message and answered 37, so the worker finished the task.",
                        "correction": "A send attempt and visible answer do not independently establish delivery or worker completion. The application reducer requires exact task evidence and acknowledgments; the native observer reports its limits."},
    })
    LESSONS.write_text(json.dumps(lessons, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tours = json.loads(TOURS.read_text(encoding="utf-8"))
    tours["56"] = {"source_sha256": hashlib.sha256(source.encode()).hexdigest(), "sections": [
        {"title": "Refuse partial cleanup", "start": 3, "end": 4,
         "text": "The first fifteen commands cannot meet the final cleanup gate."},
        {"title": "Replay all commands", "start": 5, "end": 6,
         "text": "The sixteenth command produces a fresh replay with all receipts."},
        {"title": "Check refusals and final state", "start": 7, "end": 10,
         "text": "Five deliberate refusals remain visible while exact final evidence passes."}]}
    TOURS.write_text(json.dumps(tours, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
