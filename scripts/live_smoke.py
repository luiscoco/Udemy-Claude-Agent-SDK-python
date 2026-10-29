"""Opt-in, sequential provider checks. No model calls without --live.

Run from the repository with `uv run python scripts/live_smoke.py --live`.
The four application checks use references, synthetic prompts, no external MCP,
and budget thresholds totaling $0.35. The optional elicitation probe adds $0.15.
Thresholds are checked between model calls, not hard billing caps. No script retries.
"""

import argparse
import asyncio
import importlib.metadata
import json
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Also work when invoked by path, without an editable installation.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402

from agent_lab.config import ROOT, Settings  # noqa: E402
from agent_lab.doctor import diagnose  # noqa: E402
from agent_lab.sdk import require_live_access  # noqa: E402

CHECKS = ("lesson1", "coach", "studio", "publish", "elicitation")


async def lesson1(settings: Settings) -> dict[str, Any]:
    from agent_lab.models import RunRequest
    from agent_lab.runtime import RunService

    service = RunService(settings)
    result: dict[str, Any] = {}
    status = "missing"
    try:
        handle = service.start(
            1,
            RunRequest(
                mode="live",
                prompt="Reply with exactly SDK-SMOKE-OK.",
                max_turns=1,
                max_budget_usd=0.05,
            ),
        )
        async for event in service.events(handle):
            if event.kind == "result":
                result = event.data
            if event.kind == "done":
                status = event.data["status"]
        passed = (
            status == "completed"
            and not result.get("is_error", True)
            and "SDK-SMOKE-OK" in (result.get("result") or "")
        )
        return {
            "passed": passed,
            "status": status,
            "subtype": result.get("subtype"),
            "cost_usd": result.get("total_cost_usd"),
        }
    finally:
        await service.close()


async def coach(settings: Settings) -> dict[str, Any]:
    from agent_lab.study_coach import CoachService

    service = CoachService(settings)
    submitted = service.submit("Reply with exactly COACH-SMOKE-OK.", "live", None, consent=True)
    # Await the owned tasks rather than polling or starting another paid request.
    await asyncio.gather(*service.tasks)
    turn = service.public_turn(submitted["turn_id"])
    conversation = service.conversations[submitted["conversation_id"]]
    return {
        "passed": (
            turn["status"] == "completed"
            and "COACH-SMOKE-OK" in turn["text"]
            and bool(conversation["session_id"])
        ),
        "status": turn["status"],
        "session_saved": bool(conversation["session_id"]),
        "cost_usd": None,  # The coach does not persist provider costs.
    }


async def studio(settings: Settings) -> dict[str, Any]:
    from agent_lab.evaluation_studio import StudioService, load_studio

    reference = load_studio("reference")
    options = reference.parse_run_options(
        "brief", 1, 0.05, question="Reply with exactly STUDIO-SMOKE-OK."
    )
    run = await StudioService(settings).live_run(
        reference,
        "first-query",
        "guided",
        options,
        reference.mcp_settings("none"),
        consent=True,
        mcp_consent=False,
    )
    return {
        "passed": (
            run["subtype"] == "success"
            and not run["is_error"]
            and "STUDIO-SMOKE-OK" in run["answer"]
        ),
        "subtype": run["subtype"],
        "cost_usd": run["cost_usd"],
    }


async def publish(settings: Settings) -> dict[str, Any]:
    from agent_lab.publishing_studio import NO_SOURCE, PublishingService, load_publisher

    reference = load_publisher("reference")
    request = reference.parse_answer_request(
        "Reply with exactly PUBLISH-SMOKE-OK.", settings.model, "live", 0.2, True
    )
    answer = await PublishingService(settings).live_answer(
        reference,
        request,
        [],
        NO_SOURCE,
        consent=True,
    )
    return {
        "passed": (answer["complete"] and "PUBLISH-SMOKE-OK" in answer["answer"]),
        "subtype": answer["subtype"],
        "cost_usd": answer["cost_usd"],
    }


async def elicitation(settings: Settings) -> dict[str, Any]:
    from agent_lab.curriculum import LESSONS
    from agent_lab.models import RunRequest
    from agent_lab.sdk import run_sdk

    observed: list[dict[str, Any]] = []
    result: dict[str, Any] = {}

    async def emit(event):
        nonlocal result
        if event.kind == "elicitation":
            observed.append(event.data)
        if event.kind == "result":
            result = event.data

    async def ask(arguments):
        # Explicit synthetic acceptance for this local demo smoke check only.
        return {arguments["questions"][0]["question"]: "Accept"}

    folder = settings.data_dir / "elicitation"
    folder.mkdir(parents=True, exist_ok=True)
    async with asyncio.timeout(90):
        await run_sdk(
            LESSONS[33],
            RunRequest(mode="live", max_turns=3, max_budget_usd=0.15),
            folder,
            folder / "config",
            settings,
            {},
            emit,
            ask,
        )
    return {
        "passed": (
            not result.get("is_error", True)
            and any(event == {"action": "accept", "known_demo": True} for event in observed)
        ),
        "elicitation_events": observed,
        "subtype": result.get("subtype"),
        "cost_usd": result.get("total_cost_usd"),
    }


async def main(arguments: argparse.Namespace) -> int:
    load_dotenv(ROOT / ".env", override=False)
    settings = Settings()
    diagnostics = diagnose(settings)
    if not arguments.live:
        print(
            json.dumps(
                {
                    "preflight": diagnostics,
                    "model_calls": 0,
                    "next_step": "Pass --live to authorize paid checks; --elicitation adds the experimental probe.",
                },
                indent=2,
            )
        )
        return 0
    require_live_access(settings)
    if not diagnostics["cli_available"]:
        raise RuntimeError("Native Claude Code CLI is unavailable.")
    root = ROOT / ".lab-data" / "live-smoke" / uuid.uuid4().hex
    root.mkdir(parents=True)
    settings = settings.model_copy(update={"data_dir": root})
    selected = [arguments.only] if arguments.only else list(CHECKS[:4])
    if arguments.elicitation and "elicitation" not in selected:
        selected.append("elicitation")
    report: dict[str, Any] = {
        "created": datetime.now(UTC).isoformat(),
        "sdk": importlib.metadata.version("claude-agent-sdk"),
        "model": settings.model,
        "checks": {},
        "note": "Per-call budget thresholds are not hard billing caps. No automatic script retries.",
    }
    report_path = root / "report.json"
    for name in selected:
        print(f"Running {name}...", flush=True)
        try:
            async with asyncio.timeout(180):
                result = await globals()[name](settings)
        except Exception as exc:
            # Exceptions can contain provider payloads: keep only the class in evidence.
            result = {"passed": False, "error_type": type(exc).__name__}
        report["checks"][name] = result
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps({"check": name, **result}), flush=True)
        if not result["passed"]:
            print("Stopped after a failed check. No further paid calls were started.", flush=True)
            break
    print(f"Report: {report_path}", flush=True)
    return 0 if all(report["checks"].get(name, {}).get("passed") for name in selected) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Authorize paid provider checks")
    parser.add_argument(
        "--elicitation", action="store_true", help="Include the experimental hook probe"
    )
    parser.add_argument(
        "--only", choices=CHECKS, help="Run only this check, without retrying others"
    )
    raise SystemExit(asyncio.run(main(parser.parse_args())))
