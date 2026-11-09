"""Refresh the Lesson 58 guide for the 64-tool native catalog lab."""

import hashlib
import json
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "agent_lab/content/lessons.json"
data = json.loads(path.read_text(encoding="utf-8"))
item = next(row for row in data if row["id"] == 58)
item.update({
    "concept_brief": "ToolSearch defers a large MCP catalog until the model discovers a relevant definition. A local scorer and character estimate help explain the idea, while native context usage and a real ToolSearch result show what this SDK actually did.",
    "lab_brief": "Search 64 synthetic tools across eight domains. Compare clear and vague refund metadata, deferred and eager plans, then run an owned duplicate-charge refund. The optional native run must show an actual ToolSearch reference before an exact refund call and a host-verified ledger receipt.",
    "preparation": ["Open Lesson 58 in the browser and use Local search, Estimate load, and Prepared refund without a provider call.",
                    "For native discovery, enable LAB_ENABLE_LIVE and configure ANTHROPIC_API_KEY in the private .env, then give fresh consent in the lab.",
                    "CLI: python scripts/tool_search_check.py; optional paid run: python scripts/live_tool_search_check.py --live --budget 1; silent measurements: python scripts/measure_tool_search_context.py --live."],
    "steps": [
        {"title": "Understand the goal", "text": "Search refund duplicate charge with Clear metadata, then Vague. The local scorer finds the clear refund but needs select:billing_op_7 for the vague tool."},
        {"title": "Prepare your exercise", "text": "Compare true, false, auto and alwaysLoad. These are serialized-character estimates, not billed tokens."},
        {"title": "Run one example", "text": "With consent, measure true and false in separate silent SDK sessions. Read MCP connected status, category tokens and per-tool isLoaded flags."},
        {"title": "Verify the evidence", "text": "Prepared mode writes one synthetic ledger entry. Native mode must discover the refund with ToolSearch, pass both permission gates, and produce one exact receipt."},
        {"title": "Try the challenge", "text": "Compare the ordered ToolSearch result, refund call/result, host ledger hash and terminal cost. A prose mention of a tool is not discovery evidence."}],
    "inspect": "Look at /api/c58/code for the scorer, exact refund ledger and native admission. Inspect the structured reference, ledger and actual SDK context categories separately.",
    "expected": "64 distinct tools; clear refund matches; vague refund needs exact select; deferred local plan loads zero or one pinned definition; eager loads 64. Native success needs a structured ToolSearch reference before one exact refund and a matching ledger receipt.",
    "evidence_criterion": "A native ToolSearch reference precedes an exactly admitted refund, and the host verifies one owned ledger entry.",
    "evidence_checks": [{"key": "check", "rule": "equals", "value": "pass"}],
    "challenge": "Pin the refund with alwaysLoad, then explain how this changes the loaded count while the other 63 tools stay deferred.",
    "hints": ["Local search uses token substrings and deterministic weights; it is not the SDK ranking.", "Use select:billing_op_7 to find vague metadata; the ledger lives under .lab-data/lesson-58/<run UUID>."],
    "reference": "The MCP server advertises 64 bounded tools. ToolSearch supplies a structured tool_reference for the synthetic refund. The model calls exactly mcp__ops__billing_refund_invoice with invoiceId INV-2042, amountCents 4900, currency EUR and reason duplicate-charge. Both permission gates admit the exact call; the handler writes RF-2042-1 once, and the host reloads the owned ledger. Silent SDK context usage is measured separately with no model input turns.",
    "recovery": ["If native access is unavailable, complete the local search, plan and prepared run and retain the native gap.", "If a run fails, inspect call order, reference structure, admission and ledger before another paid attempt."],
    "concept_code": "from agent_lab.tool_search_lab import SearchInput, PlanInput, search, plan\n\nprint(search(SearchInput(query='refund duplicate charge'))['references'])\nprint(plan(PlanInput(searchMode='true'))['loadedCount'])\nprint(plan(PlanInput(searchMode='false'))['loadedCount'])\n# Native discovery uses tools=['ToolSearch'] and an in-process 64-tool MCP server.\n",
    "code_focus": "search() explains local relevance. plan() estimates serialized characters. tool_search_native.live() uses actual ToolSearch and verifies the owned ledger; measure() asks the SDK for context categories in a separate silent session.",
    "concept_points": [{"title": "Deferred definitions", "text": "ToolSearch discovers a definition when needed; alwaysLoad can pin one critical tool."},
                       {"title": "Different measurements", "text": "Local scores and character counts are explanations. Native context categories and isLoaded flags are SDK observations."},
                       {"title": "Discovery is evidence", "text": "A successful tool_reference result must precede the exact refund admission and ledger mutation."}],
    "misconception": {"claim": "A local search score proves native ToolSearch selected the same tool.",
                      "correction": "The local scorer is deterministic teaching code. Native discovery requires the actual ToolSearch result and ordered tool call evidence."},
})

questions = [
    ("Why defer definitions in a large catalog?", ["Reduce tool-definition context until relevant tools are discovered.", "Prevent all MCP calls.", "Replace host permission checks."], 0),
    ("What does alwaysLoad do?", ["Pins a selected tool definition in context.", "Executes the tool automatically.", "Grants mutation permission."], 0),
    ("The clear refund matches locally but the vague operation does not. What changed?", ["Its descriptive name and search hint were removed.", "The ledger was deleted.", "The SDK charged more."], 0),
    ("Why does a second refund return already-recorded?", ["The owned ledger allows one exact synthetic refund.", "ToolSearch blocks all later queries.", "The invoice amount changed."], 0),
    ("A run prints the refund name in prose but no tool_reference. Is native discovery proven?", ["No; inspect the structured ToolSearch result.", "Yes; any text is enough.", "Yes, if local search found it."], 0),
    ("In a deferred plan, one pinned refund is loaded. How many remain deferred?", ["63", "64", "0"], 0),
    ("In the native timeline, which event must occur before the refund handler?", ["A successful ToolSearch reference result.", "A terminal success frame.", "A duplicate ledger entry."], 0),
]
item["quiz"] = [{"prompt": q, "options": [{"text": option, "explanation": ("Correct. " if i == answer else "Review the catalog and evidence order. ") + option}
                                           for i, option in enumerate(options)], "correct": answer}
                for q, options, answer in questions]
path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

tour_path = path.with_name("code_tours.json")
tours = json.loads(tour_path.read_text(encoding="utf-8"))
tours["58"] = {"source_sha256": hashlib.sha256(item["concept_code"].encode()).hexdigest(),
               "sections": [
                   {"title": "Import bounded teaching controls", "start": 1, "end": 1,
                    "text": "The local search and plan are host teaching functions. Their output is separate from native SDK ToolSearch and context usage."},
                   {"title": "Compare local discovery", "start": 2, "end": 3,
                    "text": "A clear refund query returns a catalog reference from the deterministic local scorer, not from a model."},
                   {"title": "Compare estimated load", "start": 4, "end": 6,
                    "text": "The local plan contrasts deferred and eager definition counts. Native discovery keeps ToolSearch available and obtains real SDK evidence in a separate bounded run."}]}
tour_path.write_text(json.dumps(tours, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
