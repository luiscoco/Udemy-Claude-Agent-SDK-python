"""Stop one provider-backed Lesson 50 refund at its exact approval boundary."""

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_lab.api import create_app  # noqa: E402
from agent_lab.config import ROOT, Settings  # noqa: E402
from agent_lab.runtime import RunService  # noqa: E402


async def run() -> dict:
    folder = ROOT / ".lab-data/desk-api-live-cancel" / str(uuid.uuid4())
    folder.mkdir(parents=True)
    app = create_app(RunService(Settings(data_dir=folder, enable_live=True)), with_ui=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                 base_url="http://test", timeout=180) as client:
        task = asyncio.create_task(client.post("/api/c50/chat", json={
            "mode": "live", "consent": True, "customer": "ada", "intent": "refund",
            "message": "Inspect the synthetic order and propose the fixed refund."}))
        proposal = None
        for _ in range(2000):
            response = await client.get("/api/c50/pending", params={"customer": "ada"})
            if response.status_code == 200:
                proposal = response.json()
                break
            await asyncio.sleep(0.01)
        if proposal is None:
            task.cancel()
            raise ValueError("Provider-backed refund did not reach approval")
        stopped = await client.post("/api/c50/stop", json={"runId": proposal["runId"]})
        try:
            await task
        except asyncio.CancelledError:
            pass
        state = await client.get("/api/c50/state", params={"customer": "ada"})
        pending = await client.get("/api/c50/pending", params={"customer": "ada"})
        passed = (stopped.status_code == 200 and stopped.json() ==
                  {"stopped": True, "pending": 0} and state.status_code == 200 and
                  state.json()["refunds"] == [] and pending.status_code == 404)
        report = {"lesson": 50, "source": "provider-backed SDK stopped at host approval",
                  "run": proposal["runId"], "conversation": proposal["conversationId"],
                  "passed": passed, "refund_count": len(state.json().get("refunds", [])),
                  "pending_after": 0 if pending.status_code == 404 else 1,
                  "cost_usd": None, "cost_note": "Cancellation yielded no SDK terminal cost receipt."}
        (folder / "summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        if not passed:
            raise ValueError("Native support stop did not leave a clean ledger")
        return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--budget", type=float, default=0)
    args = parser.parse_args()
    if not args.live or args.budget != 0.10:
        parser.error("Use explicit --live --budget 0.10; native chat caps itself at $0.10.")
    print(json.dumps(asyncio.run(run()), indent=2))
