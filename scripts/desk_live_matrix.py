"""Explicit bounded real-provider Lesson 50 support journey."""

import argparse
import asyncio
import json
import math
import sys
import uuid
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_lab.api import create_app  # noqa: E402
from agent_lab.config import ROOT, Settings  # noqa: E402
from agent_lab.runtime import RunService  # noqa: E402


async def pending(client: httpx.AsyncClient) -> dict[str, Any]:
    for _ in range(2000):
        response = await client.get("/api/c50/pending", params={"customer": "ada"})
        if response.status_code == 200:
            return response.json()
        await asyncio.sleep(0.01)
    raise ValueError("Native synthetic refund proposal did not arrive")


async def run(budget: float) -> dict[str, Any]:
    group = str(uuid.uuid4())
    folder = ROOT / ".lab-data/desk-api-live" / group
    folder.mkdir(parents=True)
    app = create_app(RunService(Settings(data_dir=folder, enable_live=True)), with_ui=False)
    rows: list[dict[str, Any]] = []
    conversation = None
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                 base_url="http://test", timeout=180) as client:
        for name, intent, choice in (("orders", "orders", None),
                                     ("ticket", "ticket", None),
                                     ("deny", "refund", "deny"),
                                     ("approve", "refund", "approve")):
            payload: dict[str, Any] = {"mode": "live", "consent": True,
                                       "customer": "ada", "intent": intent,
                                       "message": "Please handle the fixed synthetic " + name + " request."}
            if conversation:
                payload["conversationId"] = conversation
            task = asyncio.create_task(client.post("/api/c50/chat", json=payload))
            if choice:
                proposal = await pending(client)
                decision = {key: proposal[key] for key in
                            ("runId", "conversationId", "callId", "approvalToken")}
                answered = await client.post("/api/c50/approve", json=decision | {"choice": choice})
                if answered.status_code != 200:
                    raise ValueError("Exact synthetic approval route failed")
            response = await task
            report = response.json()
            target = folder / (name + ".json")
            target.write_text(json.dumps(report, indent=2), encoding="utf-8")
            if response.status_code != 200 or report.get("experiment_passed") is not True:
                raise ValueError(f"Native {name} failed; report: {target}")
            conversation = report["conversation"]
            terminal = next((row for row in report.get("frames", []) if row.get("kind") == "result"), {})
            cost = terminal.get("cost_usd")
            if not isinstance(cost, (int, float)) or not math.isfinite(cost) or not 0 <= cost <= 0.10:
                raise ValueError("Missing or excessive SDK terminal cost")
            delta = report.get("cost_delta_usd")
            if not isinstance(delta, (int, float)) or not math.isfinite(delta) or not 0 <= delta <= 0.10:
                raise ValueError("Missing or excessive native session cost delta")
            rows.append({"action": name, "run": report["run"], "conversation": conversation,
                         "reported_total_usd": cost, "delta_usd": delta,
                         "calls": [row["tool"] for row in report["calls"]]})
            if sum(row["delta_usd"] for row in rows) > budget:
                raise ValueError("Combined native cost ceiling exceeded")
        response = await client.post("/api/c50/close", json={"mode": "live", "consent": True,
                                                           "customer": "ada", "conversationId": conversation})
        closed = response.json()
        (folder / "close.json").write_text(json.dumps(closed, indent=2), encoding="utf-8")
        if response.status_code != 200 or closed.get("experiment_passed") is not True:
            raise ValueError("Native CRM close failed")
        closing = next((row for row in closed.get("frames", []) if row.get("kind") == "result"), {})
        close_cost = closing.get("cost_usd")
        if not isinstance(close_cost, (int, float)) or not 0 <= close_cost <= 0.10:
            raise ValueError("Native CRM cost missing or excessive")
        rows.append({"action": "close", "conversation": conversation,
                     "reported_total_usd": close_cost, "delta_usd": close_cost})
        evaluated = await client.post("/api/c50/evals", json={})
        if evaluated.status_code != 200 or evaluated.json().get("experiment_passed") is not True:
            raise ValueError("Free synthetic evaluations failed")
        state = await client.get("/api/c50/state", params={"customer": "ada"})
        snapshot = state.json()
        if (state.status_code != 200 or len(snapshot["tickets"]) != 1 or
                len(snapshot["refunds"]) != 1 or
                not any(row["id"] == conversation and row["status"] == "closed"
                        for row in snapshot["conversations"])):
            raise ValueError("Reloaded native desk effects did not match")
    total = sum(row["delta_usd"] for row in rows)
    if total > budget:
        raise ValueError("Combined native cost ceiling exceeded")
    summary = {"lesson": 50, "group": group, "passed": True,
               "conversation": conversation, "actions": rows,
               "total_cost_usd": total, "budget_usd": budget}
    (folder / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--budget", type=float, default=0)
    args = parser.parse_args()
    if not args.live or not math.isfinite(args.budget) or not 0.50 <= args.budget <= 1:
        parser.error("Use explicit --live and finite --budget 0.50..1")
    print(json.dumps(asyncio.run(run(args.budget)), indent=2))
