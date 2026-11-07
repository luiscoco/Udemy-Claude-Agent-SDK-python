"""Install the authored Lesson 46 cache teaching in the shared course JSON."""

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
    lesson = next(item for item in rows if item["id"] == 46)
    lesson.update({
        "prerequisites": [15, 25],
        "concept_brief": "Prompt caching is measured from per-turn input, five-minute write, one-hour write, read and output counters. A cache_control breakpoint requests reuse; it is not evidence of a hit. Compare complete native SDK usage with the owned observer's upstream response and keep dated cost estimates separate from SDK cumulative cost.",
        "lab_brief": "Run exactly two turns in one lane. Anatomy inspects breakpoint locations; Switches measures TTL; Breakers changes the owned prefix or tool layout; Model switch uses real pre/post hooks to cap or allow a warm-cache rewrite. Local rows are authored HTTP fixtures. Live rows require fresh consent and match native SDK message IDs and independent counters to the fixed upstream.",
        "preparation": ["Open Lesson 46 after Lessons 15 and 25. Inspect the two-turn criterion and the source excerpts.",
                        "Keep the first run local. Enable live only with a private ANTHROPIC_API_KEY and LAB_ENABLE_LIVE=true; each paid click needs fresh consent."],
        "steps": [
            {"title": "Understand the goal", "text": "Find cache_control on the request and distinguish instructions from observed cache reads."},
            {"title": "Prepare your exercise", "text": "Select Anatomy and keep the first run local. Predict whether the second turn will read cached tokens."},
            {"title": "Run one example", "text": "Run the authored HTTP producer. It returns two finite counter rows without a provider call."},
            {"title": "Verify the evidence", "text": "With fresh consent, compare each SDK assistant and result to the corresponding authenticated wire receipt and upstream usage."},
            {"title": "Try the challenge", "text": "Change a prefix, then compare actual second-turn reads and writes. Zero reads can still satisfy a complete measurement."}],
        "inspect": "Compare cache breakpoints and per-run cost calculations. Inspect input, five-minute write, one-hour write, read and output counts for each turn.",
        "expected": "Two successful turns in one lane with finite counters and matching native/wire identities. No guaranteed cache saving.",
        "evidence_criterion": "Two successful distinct turns in one lane expose finite cache and usage counters; no guaranteed cache saving.",
        "evidence_checks": [{"key": "experiment_passed", "rule": "truthy"}],
        "challenge": "Change a prefix and predict which cache entries remain reusable. Then compare the actual second-turn read and write counters; a changed prefix need not destroy every earlier cache segment.",
        "hints": ["First identify the explicit cache_control locations and TTL. A breakpoint is only a request instruction; look at cache_read_input_tokens for a hit.",
                  "Follow the same operation and session across both turns. Compare message IDs, system/tools hashes, usage counters and cumulative cost deltas before claiming reuse or a rewrite."],
        "reference": "A passing Anatomy run shows two successful ordered turns and independent per-turn counters. A stable long handbook can yield a second-turn read, but zero reads still meet the measurement criterion. A one-hour breakpoint changes write pricing, and the estimate uses write5m, write1h and read exactly once. A changed prefix may leave earlier blocks reusable. The cap hook's estimated rewrite cost is a decision input; after an allowed switch, compare the actual Sonnet usage and last cumulative SDK cost.",
        "recovery": ["If usage is absent, inspect the upstream SSE message_start, message_delta and message_stop sequence; never turn missing counters into zero.",
                     "If identity differs, match the current operation, turn, native assistant message ID and observer receipt; discard stale rows.",
                     "If live is refused, restore the fixed prompt, normal scenario, private host key and fresh consent, then inspect the first sanitized error."],
        "quiz": [
            question("Does cache_control prove a cache hit?", "No; a read counter is required", "Yes; the breakpoint itself proves reuse", "Yes; identical text always hits", "Only response usage can establish a read."),
            question("Which cost counter is separate from the dated list estimate?", "SDK cumulative total_cost_usd", "The current prompt length", "The number of breakpoints", "The SDK total is session cumulative and must not be summed across snapshots."),
            question("A message_delta lacks output_tokens. What should the parser do?", "Reject incomplete usage", "Treat output as zero", "Reuse a prior run's output", "Primary counters must be finite safe integers."),
            question("The second assistant ID differs from its wire receipt. What should happen?", "Fail the correlation check", "Trust the assistant text", "Match only the model label", "Each turn needs its own upstream message ID and matching native assistant."),
            question("A warm-cache cap hook denies a model switch. What confirms denial?", "A native pre-hook deny and no post-hook or Sonnet wire turn", "A configured zero-dollar cap alone", "A lower estimated price", "The actual hook and next-model observations establish the outcome."),
            question("On the concept map, which value demonstrates reuse?", "Observed cache-read tokens", "The handbook title", "A cache breakpoint icon", "A positive read count is observation; the breakpoint is instruction."),
            question("On the lab walkthrough, what follows an allowed model switch?", "A post-hook and a Sonnet second-turn wire receipt", "Only a pre-hook estimate", "A local fixture label", "The completed hook and actual second-turn model and usage close the chain."),
        ],
        "concept_code": "from agent_lab.cache_wire import normalized_usage, estimate_usd\n\n\ndef measure_turn(model: str, response_usage: dict) -> dict:\n    counters = normalized_usage(response_usage)\n    estimate = estimate_usd(model, counters)\n    return {\"counters\": counters, \"list_estimate_usd\": estimate}\n\n\ndef compare_turns(first: dict, second: dict) -> dict:\n    return {\"first_read\": first[\"counters\"][\"read\"],\n            \"second_read\": second[\"counters\"][\"read\"],\n            \"saving_guaranteed\": False}\n",
        "code_focus": "normalized_usage requires all primary counters, separates one-hour writes from other writes, and estimate_usd applies the dated rate table without double counting cache creation.",
        "concept_points": [
            {"title": "Instructions versus hits", "text": "A cache breakpoint requests reuse; response counters prove any hit."},
            {"title": "Complete usage", "text": "The usage parser requires complete per-turn counters and separates five-minute from one-hour writes."},
            {"title": "Switch decision versus result", "text": "Model-switch estimates guide hooks; actual next-turn usage and SDK cumulative cost measure the result."}],
        "misconception": {"claim": "Identical prompts or enabled caching always save money.",
                          "correction": "A breakpoint is an instruction, and a cache hit must appear in actual response counters. Zero reads may still be a valid complete measurement."},
    })
    LESSONS.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tours = json.loads(TOURS.read_text(encoding="utf-8"))
    code = lesson["concept_code"]
    tours["46"] = {"source_sha256": hashlib.sha256(code.encode()).hexdigest(), "sections": [
        {"title": "Import measured counters", "start": 1, "end": 1,
         "text": "The lesson uses the actual cache usage parser and dated estimator from this Python package."},
        {"title": "Normalize one turn", "start": 4, "end": 8,
         "text": "A response must contain finite primary counters before the host calculates a price estimate."},
        {"title": "Compare two turns", "start": 10, "end": 13,
         "text": "The comparison reports observed reads and explicitly avoids promising a saving."},
    ]}
    TOURS.write_text(json.dumps(tours, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
