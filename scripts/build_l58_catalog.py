"""Regenerate the reviewed 64-entry synthetic Lesson 58 catalog."""

import json
from pathlib import Path

domains = ("billing", "crm", "shipping", "inventory", "hr", "analytics", "support", "marketing")
actions = ("get", "search", "create", "update", "archive", "list", "audit", "export")
schema = {"type": "object", "properties": {"recordId": {"type": "string", "minLength": 1,
          "maxLength": 50}}, "required": ["recordId"], "additionalProperties": False}
refund_schema = {"type": "object", "properties": {
    "invoiceId": {"type": "string", "const": "INV-2042"},
    "amountCents": {"type": "integer", "const": 4900},
    "currency": {"type": "string", "const": "EUR"},
    "reason": {"type": "string", "const": "duplicate-charge"}},
    "required": ["invoiceId", "amountCents", "currency", "reason"], "additionalProperties": False}
rows = []
for domain in domains:
    for action in actions:
        row = {"name": f"{domain}_{action}_record",
               "description": f"{action.title()} one synthetic {domain} record by record ID. This fixture operation returns unsupported and changes nothing.",
               "inputSchema": schema}
        if domain == "billing" and action == "export":
            row = {"name": "billing_refund_invoice",
                   "description": "Refund the duplicate invoice charge for the exact EUR cent amount on synthetic invoice INV-2042.",
                   "searchHint": "refund duplicate charge invoice billing payment reimbursement",
                   "inputSchema": refund_schema}
        rows.append(row)
target = Path(__file__).resolve().parents[1] / "fixtures/tool-search/catalog.json"
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
