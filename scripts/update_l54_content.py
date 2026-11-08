"""Install Lesson 54 catalog teaching, seven questions and a source tour."""

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
    item = next(row for row in lessons if row["id"] == 54)
    source = ("from agent_lab.tool_design_catalog import Catalog\n"
              "from agent_lab.tool_design_lab import DesignInput, prepared, grade\n"
              "import asyncio\nimport uuid\n\n"
              "catalog = Catalog()  # one immutable synthetic source\n"
              "invalid = catalog.invoke('focused', 'catalog_get', {'sku': 'Trail mug'})\n"
              "assert invalid['errorCode'] == 'INVALID_INPUT'\n"
              "selected = DesignInput(profile='focused', format='concise')\n"
              "report = asyncio.run(prepared(selected, uuid.uuid4(), catalog=catalog))\n"
              "assert report['summary']['searchIds'] == ['SKU-101', 'SKU-104']\n"
              "assert grade(selected, report)\n")
    item.update({
        "prerequisites": [5, 51],
        "concept_brief": "A useful tool contract narrows the model's choice and makes recovery possible. The vague lookup and focused search/get tools read one immutable synthetic catalog. Focused search filters integer EUR cents and real stock, returns stable IDs and a snapshot-bound cursor, and measures actual handler-envelope bytes.",
        "lab_brief": "Call a valid and invalid tool directly, then compare scripted vague and focused consumers. The scripted cursor loop demonstrates the host contract with zero model calls; optional native mode observes one bounded model choice per profile. Handler receipts and unchanged fixture hashes, not assistant prose, support the automatic check.",
        "preparation": ["Complete Lessons 5 and 51 and open the local portal.",
                        "Free direct calls and prepared comparisons need no API key or network request."],
        "steps": [{"title": "Understand the goal", "text": "Compare vague lookup with focused search and get over the same five-product fixture."},
                  {"title": "Prepare your exercise", "text": "Call catalog_get with SKU-101, then try an invalid product name instead of an ID."},
                  {"title": "Run one example", "text": "Compare both prepared profiles in concise format, then repeat detailed format."},
                  {"title": "Verify the evidence", "text": "Inspect schema rejection versus executed NOT_FOUND, cursor chain, call/result IDs, host receipts, actual envelope bytes and unchanged fixture hash."},
                  {"title": "Try the challenge", "text": "Rewrite the vague input description with category, price units, stock semantics and cursor recovery. Predict how the model's choice might improve without claiming the scripted run proves it."}],
        "inspect": "Direct invalid arguments return INVALID_INPUT without executing the business handler. A syntactically valid missing SKU executes and returns NOT_FOUND. Focused search pages contain SKU-101 then SKU-104 under pageSize 1; each returned nextCursor is used with unchanged filters. Compare the actual serialized envelope bytes and the same before/after fixture SHA-256.",
        "expected": "Prepared vague produces one broad lookup and no lesson credit. Prepared focused makes two successful search pages and two successful get calls, returns exactly SKU-101 and SKU-104, no handler errors, zero model calls/cost, and unchanged fixture bytes. Concise envelopes are smaller than detailed envelopes for this fixture; they are not token or transport measurements.",
        "evidence_criterion": "Explicit tool-contract run completed without handler errors; fixture/live scope retained.",
        "evidence_checks": [{"key": "experiment_passed", "rule": "equals", "value": True}],
        "challenge": "Rewrite 'Look things up. Pass q.' to name category filters, integer EUR cents, positive stock, stable IDs, nextCursor and recovery. Predict a more reliable choice, then compare actual native receipts instead of claiming certainty from a scripted replay.",
        "hints": ["Start with the direct call error: distinguish schema rejection before handler execution from an executed missing-ID result.",
                  "Follow each nextCursor with the same category, ceiling, stock flag, page size and format; then get the IDs returned by the final complete chain."],
        "reference": "The vague lookup returns broad verbose camping records, including an over-budget tent and out-of-stock lantern. The focused contract explicitly filters camping, <=3000 EUR cents and stock>0, then returns two stable IDs over two pages and retrieves each. A missing syntactically valid SKU gives NOT_FOUND with a search recovery; a product name gives INVALID_INPUT before the business handler. The real envelope byte count describes handler output only. Prepared behavior is scripted; a native run measures one model attempt, not general reliability.",
        "recovery": ["If the direct call rejects your JSON, inspect the field list and recovery text, then retry with a valid object.",
                     "If a cursor mismatches, clear it and restart with unchanged filters. A stopped or partial run needs review; fresh paid consent is required for another native call."],
        "quiz": [
            question("Which price unit does focused search accept?", "Integer EUR cents.", "Floating-point euros.", "A currency symbol string.", "The bounded schema makes the unit unambiguous."),
            question("What proves a camping item is available?", "Its actual fixture stock is greater than zero after filtering.", "The item name contains Trail.", "The assistant says it is available.", "The host handler applies the real stock field."),
            question("A valid SKU is absent. What should catalog_get return?", "Executed NOT_FOUND with instructions to search for an existing ID.", "A guessed matching SKU.", "An input-schema error for any missing record.", "The input shape is valid but no record matches."),
            question("What must stay unchanged when following nextCursor?", "The category, ceiling, stock flag, page size and format, plus the snapshot version.", "Only the category.", "Only the model prompt.", "A cursor binds the exact normalized search and snapshot."),
            question("Which metric is the reported byte value?", "UTF-8 bytes of the serialized handler envelope.", "Model tokens.", "Full network traffic.", "The host measures JSON bytes after the handler returns."),
            question("What does a passing prepared cursor loop prove?", "The scripted host consumer can follow the contract and verify returned IDs.", "Any model will paginate unaided.", "The native SDK was called.", "Prepared runs make zero model calls and are explicitly scripted."),
            question("Why inspect pre-handler schema rejections separately?", "The SDK may reject an input before the business handler receives it.", "They prove the handler executed successfully.", "They are always billed as zero tokens.", "Handler error counts cannot include calls blocked before execution.")],
        "concept_code": source,
        "code_focus": "`Catalog.invoke` is shared by direct calls and consumers. Strict validation precedes execution; the prepared consumer follows returned cursors and the grade checks correlated receipts and fixture hashes.",
        "concept_points": [{"title": "One immutable source", "text": "Both profiles read the same five synthetic products and the host hashes the raw bytes."},
                           {"title": "Focused recoverable contract", "text": "Typed filters, stable IDs, bounded pages and actionable errors reduce ambiguity."},
                           {"title": "Evidence before prose", "text": "Handler receipts, exact call/result IDs and known cost determine the check."}],
        "misconception": {"claim": "A shorter tool response proves the model used the tool correctly.",
                        "correction": "Response bytes measure only serialized handler output. Correct tool use also needs valid calls, complete cursor and detail receipts, unchanged host fixture and a successful closed run."},
    })
    LESSONS.write_text(json.dumps(lessons, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tours = json.loads(TOURS.read_text(encoding="utf-8"))
    tours["54"] = {"source_sha256": hashlib.sha256(source.encode()).hexdigest(), "sections": [
        {"title": "Validate direct input", "start": 6, "end": 7,
         "text": "A product name is rejected before catalog_get executes."},
        {"title": "Follow the scripted cursor", "start": 8, "end": 10,
         "text": "The prepared consumer obtains the two qualifying IDs from real handler pages."},
        {"title": "Check correlated evidence", "start": 11, "end": 11,
         "text": "The grade checks host receipts and closure instead of assistant prose."}]}
    TOURS.write_text(json.dumps(tours, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
