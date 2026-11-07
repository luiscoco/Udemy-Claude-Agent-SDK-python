"""Install reviewed Lesson 50 teaching content and source tour."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LESSONS = ROOT / "agent_lab/content/lessons.json"
TOURS = ROOT / "agent_lab/content/code_tours.json"


def question(prompt: str, right: str, wrong1: str, wrong2: str, reason: str) -> dict:
    return {"prompt": prompt, "options": [
        {"text": right, "explanation": "Correct. " + reason},
        {"text": wrong1, "explanation": "No. " + reason},
        {"text": wrong2, "explanation": "No. " + reason}], "correct": 0}


def main() -> None:
    lessons = json.loads(LESSONS.read_text(encoding="utf-8"))
    lesson = next(row for row in lessons if row["id"] == 50)
    lesson.update({
        "prerequisites": [15, 28, 49],
        "concept_brief": "A full support desk connects conversation, scoped tools, durable records, one-shot approval and CRM closure. The host chooses the synthetic customer, admits exact tool calls and owns every effect. Each ticket or refund turn must read current orders first. A resumed native SDK session keeps conversation context; a restricted fork produces the CRM record. Passing evidence joins native call/result IDs with saved host effects.",
        "lab_brief": "Use Ada or Bo classroom records. Inspect orders, resume the same conversation to create a ticket, then try a denied and an approved 1000-cent refund. Close the conversation into strict CRM data and run local evaluations. The browser and /api/c50 routes share persisted synthetic data. Live mode requires explicit consent for each paid SDK action; offline mode is an authored lifecycle with real local effects.",
        "preparation": ["Read the synthetic customer and order fixtures; no real identity or payment account is connected.", "Start with Local mode and inspect the separate orders, tickets, refunds and audit evidence. Enable live access and confirm each paid action only when ready."],
        "steps": [
            {"title": "Understand the goal", "text": "Trace a customer-bound conversation from order read through close and distinguish proposals from host-owned effects."},
            {"title": "Prepare your exercise", "text": "Choose Ada or Bo, Local or Live, an intent and a message. Select an open saved conversation to resume it."},
            {"title": "Run one example", "text": "Send Orders. Resume it for Ticket and Refund; deny one proposal, approve another, then close to CRM."},
            {"title": "Verify the evidence", "text": "Inspect exact matched call IDs, persisted ticket/refund/audit rows, approval outcome, stable transcript and closed CRM record."},
            {"title": "Try the challenge", "text": "Run Missing evidence, Foreign call or Failed locally; the host must withhold the success verdict even if a tool effect happened."}],
        "inspect": "Check `calls`, `results`, `snapshot`, `refunds_before`, `pending_after`, `experiment_passed` and the CRM close report. Live reports also contain native init, assistant tool calls, tool results, terminal and cost delta.",
        "expected": "Orders reads Ada's order only. Ticket saves exactly one ticket after a fresh orders read. Denied refund adds an audit denial and no refund row. Approved refund adds exactly one 1000-cent row. CRM close stores structured data without editing the transcript.",
        "evidence_criterion": "The selected operation has successful matched tool evidence and the corresponding scoped host effects. A denied refund passes only as an explicit denied outcome with no refund effect.",
        "evidence_checks": [{"key": "experiment_passed", "rule": "equals", "value": True}],
        "challenge": "Choose Foreign call in Local mode after an orders operation. The evaluator must reject a result whose call ID is not the admitted ID; inspect the persisted audit separately from the intentionally corrupted report.",
        "hints": ["The selected ticket or refund tool needs a successful orders result in the same operation.", "One-shot approval binds run, conversation, call and token; denial and cancellation clear pending state."],
        "reference": "The host loads only the selected customer's records, admits a fresh orders call, checks the selected tool's exact arguments and ID, and writes scoped effects. Refund authorization is a one-shot exact decision. Native session evidence and the persisted ledger are checked separately; the CRM fork has no desk tools.",
        "recovery": ["If a support operation needs review, inspect the first failed call and the saved audit. A negative local scenario is expected to fail its success criterion.", "If live access fails, check the private provider key and LAB_ENABLE_LIVE, restart the app, and use Local mode while resolving the connection. Each live action requires fresh consent."],
        "quiz": [
            question("Who chooses the customer scope for a desk tool?", "The host session selects Ada or Bo before the tool call.", "The model supplies a customerId in each call.", "The customer's message supplies the id.", "Model text cannot grant a different customer's scope."),
            question("Why read orders again on a resumed ticket turn?", "The ticket operation needs current orders evidence of its own.", "The old orders result is deleted.", "The CRM fork needs an order list.", "The host admits the selected write only after a fresh successful read."),
            question("What makes refund approval one use?", "The decision is bound to the exact pending call and consumed.", "A general approve flag stays set on the account.", "The model says a staff member approved it.", "Run, conversation, call and token must match before settlement."),
            question("What should a denied refund change?", "An audit denial, with no refund row.", "A refund row marked pending.", "The customer's order total.", "The host records the refusal while leaving the ledger untouched."),
            question("Why compare native call and result IDs?", "It ties provider-backed tool evidence to the host effect.", "It proves the answer text sounds helpful.", "It replaces persisted audit checks.", "A report needs both a matched SDK lifecycle and saved host facts."),
            question("What can the restricted CRM fork do?", "Return schema-constrained CRM data without desk tools.", "Issue another refund during close.", "Rewrite prior customer messages.", "Closure stores the validated record while preserving the transcript."),
            question("Why does a Foreign call local case need review?", "Its result ID differs from the admitted call ID.", "It uses Bo instead of Ada automatically.", "It always times out.", "A local effect by itself does not prove the selected operation's evidence.")],
        "concept_code": "import uuid\n\nfrom agent_lab.desk_approver import DeskApprover\nfrom agent_lab.desk_lab import local_chat\nfrom agent_lab.desk_store import DeskStore\n\n\nasync def example(root):\n    store = DeskStore(root)\n    approver = DeskApprover()\n    orders = await local_chat(store, approver, customer='ada', intent='orders')\n    ticket = await local_chat(store, approver, customer='ada',\n                              conversation=uuid.UUID(orders['conversation']), intent='ticket')\n    return orders, ticket",
        "code_focus": "`DeskStore` owns scoped persisted effects, `DeskApprover` settles one exact pending refund, and `local_chat` admits a fresh orders call before the selected ticket or refund. The native path uses the same host operation and evaluator.",
        "concept_points": [
            {"title": "Scope every operation", "text": "The host-selected Ada or Bo scope determines which orders and conversation a tool can touch."},
            {"title": "Own each effect", "text": "Tool calls enter a host admission path; tickets and refunds are written to a persisted ledger with audit rows."},
            {"title": "Join evidence before success", "text": "Success requires exact call/result pairs and saved effects. A CRM fork closes a conversation with validated structured data."}],
        "misconception": {"claim": "A helpful final answer proves a refund was safely completed.", "correction": "The host checks the approval decision, exact tool call and persisted refund row. Assistant text is only part of the conversation."},
    })
    LESSONS.write_text(json.dumps(lessons, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tours = json.loads(TOURS.read_text(encoding="utf-8"))
    source = lesson["concept_code"]
    tours["50"] = {"source_sha256": hashlib.sha256(source.encode()).hexdigest(),
                   "sections": [
                       {"title": "The persisted host", "start": 1, "end": 6,
                        "text": "The host has a persisted scoped store and a separate one-shot approver."},
                       {"title": "Open and read", "start": 8, "end": 11,
                        "text": "The first operation opens an Ada conversation and reads current orders."},
                       {"title": "Resume for a ticket", "start": 12, "end": 14,
                        "text": "The second operation resumes the saved UUID and reads orders again before a ticket."}]}
    TOURS.write_text(json.dumps(tours, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
