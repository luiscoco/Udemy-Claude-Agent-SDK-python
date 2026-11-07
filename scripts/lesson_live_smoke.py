"""Explicitly opted-in, sequential live acceptance for the latest lesson workflows."""

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_lab.config import ROOT, Settings  # noqa: E402
from agent_lab.models import RunRequest  # noqa: E402
from agent_lab.runtime import RunService  # noqa: E402

CASES = {
    44: [("signals", {"action": "signals", "consent": True}, True),
         ("privacy", {"action": "privacy", "consent": True}, True),
         ("tracing", {"action": "tracing", "consent": True}, True),
         ("rich", {"action": "rich", "consent": True}, True),
         ("exporters", {"action": "exporters", "consent": True}, True),
         ("collector", {"action": "collector", "consent": True}, True)],
    43: [("tool-http", {"action": "live", "step": "tool", "transport": "http"}, True),
         ("tool-sse", {"action": "live", "step": "tool", "transport": "sse"}, True),
         ("resource-http", {"action": "live", "step": "resource", "transport": "http"}, True),
         ("resource-sse", {"action": "live", "step": "resource", "transport": "sse"}, True),
         ("reconnect-http", {"action": "reconnect", "transport": "http"}, True),
         ("reconnect-sse", {"action": "reconnect", "transport": "sse"}, True),
         ("rotate-http", {"action": "live", "step": "rotate", "transport": "http"}, True),
         ("rotate-sse", {"action": "live", "step": "rotate", "transport": "sse"}, True)],
    42: [("basics", {"action": "basics"}, True),
         ("fetch-page", {"action": "fetch-lab", "page": "page"}, True),
         ("fetch-json", {"action": "fetch-lab", "page": "json"}, True),
         ("fetch-redirect", {"action": "fetch-lab", "page": "redirect"}, True),
         ("fetch-missing", {"action": "fetch-lab", "page": "missing"}, False),
         ("injection", {"action": "injection"}, True),
         ("guard", {"action": "guard"}, True),
         ("research", {"action": "research"}, True)],
    41: [("python-client-and-resume", {}, True)],
    40: [("guarded-compare", {"recover": True}, True)],
    39: [("where-trusted", {}, True),
         ("where-omitted", {"root": "omitted"}, True),
         ("where-branch", {"root": "branch"}, True),
         ("where-docs-omitted", {"cwd": "docs", "root": "omitted"}, False),
         ("where-no-sources", {"sources": "none"}, True),
         ("takeover-trusted", {"action": "takeover"}, True),
         ("takeover-omitted", {"action": "takeover", "root": "omitted"}, True)],
    38: [("enabled", {}, True), ("edited", {"edited": True}, True),
         ("omitted", {"variant": "omitted"}, False),
         ("env-off", {"variant": "env-off"}, False)],
    37: [("allow", {}, True), ("edit", {"action": "edit"}, True),
         ("remember", {"action": "remember"}, True), ("deny", {"action": "deny"}, False),
         ("malformed", {"action": "malformed"}, False),
         ("interrupt", {"action": "interrupt"}, False)],
    36: [("success-a", {}, True), ("stderr-b", {"action": "stderr", "location": "machine-b"}, True), ("failed-launch", {"action": "failed-launch"}, False), ("timeout", {"action": "timeout"}, False), ("cancel", {"action": "cancel"}, False)],
    35: [("commit", {}, True), ("interrupted", {"action": "interrupted"}, True), ("resume", {"action": "resume"}, True), ("durable-resume", {"action": "durable-resume"}, True), ("batched-resume", {"action": "durable-resume", "flush": "batched"}, True), ("delayed-load", {"action": "durable-resume", "fault": "delay-load"}, True), ("mirror-disabled", {"enabled": False}, False), ("append-rejected", {"fault": "reject-append"}, False)],
    34: [("teaching-project", {}, True), ("brief-project", {"style": "brief"}, True), ("project-disabled", {"source": "none"}, True)],
    33: [("accept", {}, True), ("decline", {"action": "decline"}, True), ("cancel", {"action": "cancel"}, True)],
    32: [("valid-approved", {}, True), ("valid-review-only", {"approve": False}, True), ("duplicate-rejected", {"proposal": "duplicate"}, True)],
    31: [("concise-answer", {}, True), ("detailed-answer", {"answer": "Detailed"}, True)],
    30: [("valid-progress", {}, True), ("skip-rejected", {"sequence": "skip"}, True), ("parallel-rejected", {"sequence": "parallel"}, True), ("reopen-rejected", {"sequence": "reopen"}, True)],
    29: [("red-image", {}, True), ("blue-image", {"color": "blue"}, True)],
    28: [("recover", {}, True), ("permanent-stop", {"outcome": "permanent"}, True), ("transient-exhausted", {"outcome": "exhausted"}, True)],
    27: [("cancel-await", {}, True), ("release-await", {"ending": "finish"}, True)],
    26: [("current-plan", {}, True), ("sonnet-default", {"target_model": "sonnet", "permission_mode": "default"}, True), ("interrupt", {"action": "interrupt"}, True)],
    25: [("default-bound", {}, True), ("tight-bound", {"limit": 200}, True), ("summary-omitted", {"retain_summary": False}, False)],
    24: [("valid-execute", {}, True), ("valid-review-only", {"approve": False}, True), ("duplicate-rejected", {"proposal": "duplicate"}, True), ("cycle-rejected", {"proposal": "cycle"}, True), ("outside-rejected", {"proposal": "outside"}, True)],
    23: [("explain-command", {}, True), ("quiz-command", {"action": "quiz"}, True), ("skill", {"action": "skill"}, True), ("plugin-disabled", {"enabled": False}, True)],
    22: [("project-alpha", {}, True), ("project-beta", {"rule": "beta"}, True), ("no-project", {"source": "none"}, True), ("custom-prompt", {"system_mode": "custom"}, True), ("custom-beta", {"system_mode": "custom", "rule": "beta"}, True), ("no-project-custom", {"source": "none", "system_mode": "custom"}, True)],
    21: [("summary", {}, True), ("quiz", {"template": "quiz"}, True), ("project-disabled", {"source": "none"}, False)],
    20: [("allow-audit", {}, True), ("deny", {"behavior": "deny"}, True), ("rewrite", {"behavior": "rewrite"}, True), ("tool-error", {"behavior": "tool-error"}, True), ("callback-error", {"behavior": "callback-error"}, True), ("nonmatching-matcher", {"behavior": "deny", "matcher": "Write|Edit"}, True), ("success-audit-disabled", {"post_hook": False}, False)],
    19: [("inspect-page", {"page_size": 1, "offset": 1}, True), ("rename-tag", {"action": "rename-tag", "title": "Live reviewed session", "tag": "practice"}, True), ("fork", {"action": "fork", "title": "Live branch"}, True), ("delete-owned", {"action": "delete"}, True)],
    18: [("inside-read", {"target": "inside"}, True), ("outside-denied", {"target": "outside"}, True), ("protected-denied", {"target": "protected"}, True)],
    16: [
        ("isolated", {}, True),
        ("project", {"sources": "project"}, True),
        ("project-local", {"sources": "project-local"}, True),
        ("inherited-demo", {"env_override": False}, True),
    ],
    17: [
        ("rewind", {}, True),
        ("inspect", {"action": "inspect"}, False),
        ("checkpointing-disabled", {"checkpointing": False}, False),
        ("replay-disabled", {"replay_messages": False}, False),
    ],
}


async def run(lesson: int, live: bool, selected_case: str | None = None) -> int:
    cases = [case for case in CASES[lesson] if selected_case is None or case[0] == selected_case]
    if not cases:
        raise ValueError(f"Unknown live case for lesson {lesson}: {selected_case}")
    if not live:
        print("No model calls made. Use --live to explicitly authorize the listed scenarios.")
        print(json.dumps(cases))
        return 0
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=False)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    folder = ROOT / ".lab-data" / "lesson-live-smoke" / f"lesson-{lesson}-{stamp}"
    folder.mkdir(parents=True)
    service = RunService(Settings(data_dir=folder, timeout_seconds=120))
    records = []
    try:
        for name, options, expected_check in cases:
            handle = service.start(
                lesson,
                RunRequest(mode="live", lesson_options=options, max_turns=4, max_budget_usd=0.10),
            )
            record = {
                "case": name,
                "expected_automatic_check": expected_check,
                "passed": False,
                "cost_usd": None,
            }
            async for event in service.events(handle):
                if event.kind == "evidence":
                    record["experiment"] = event.data["result"].get("experiment", {})
                elif event.kind == "result":
                    record["cost_usd"] = event.data.get("total_cost_usd")
                elif event.kind == "error":
                    record["error"] = event.data.get("message")
                elif event.kind == "done":
                    record["status"] = event.data.get("status")
            proof = record.get("experiment", {})
            terminal = proof.get("terminal", {})
            if not terminal:
                terminals = proof.get("terminal_results", [])
                terminal = terminals[-1] if terminals else {}
            initialized = proof.get("initialization", [])
            valid_turn = bool(
                initialized
                and terminal.get("session_id") == initialized[-1].get("session_id")
                and terminal.get("subtype") == "success"
                and terminal.get("is_error") is False
            )
            base = (
                record.get("status") == "completed"
                and proof.get("connection_closed") is True
                and proof.get("experiment_passed") is expected_check
            )
            if lesson == 17:
                changed = proof.get("changed_hash") is not None and proof.get(
                    "before_hash"
                ) != proof.get("changed_hash")
                base = base and valid_turn and changed
                if not expected_check:
                    base = (
                        base
                        and proof.get("rewind_requested") is False
                        and proof.get("after_hash") == proof.get("changed_hash")
                    )
            if lesson in {20, 21, 25}:
                base = base and proof.get("observation_passed") is True
            if lesson == 40:
                base = bool(record.get("status") == "completed"
                            and proof.get("experiment_passed") is expected_check
                            and proof.get("connection_closed") is True
                            and proof.get("source_unchanged") is True
                            and proof.get("exact_drop_verified") is True
                            and proof.get("unsafe_refusal_verified") is True
                            and proof.get("recovery_verified") is True)
            if lesson == 41:
                built = proof.get("base") or {}
                resumed = proof.get("resume") or {}
                turns = built.get("turns") or []
                base = bool(record.get("status") == "completed"
                            and proof.get("experiment_passed") is expected_check
                            and proof.get("connection_closed") is True
                            and proof.get("source_label") == "real Python SDK client and provider-backed CLI"
                            and len(turns) == 3
                            and built.get("query_after_disconnect") == "CLIConnectionError"
                            and all(item.get("subtype") == "success" and item.get("is_error") is False
                                    and item.get("session_id") == built.get("session_id") for item in turns)
                            and resumed.get("result", {}).get("session_id") == built.get("session_id")
                            and resumed.get("experiment_passed") is True)
            if lesson == 42:
                lanes = proof.get("lanes") or []
                base = bool(record.get("status") == "completed"
                            and proof.get("experiment_passed") is expected_check
                            and proof.get("connection_closed") is True
                            and proof.get("source_label") == "provider-backed SDK web tool calls and host hook observations"
                            and lanes
                            and all(lane.get("terminal", {}).get("subtype") == "success"
                                    and lane.get("terminal", {}).get("is_error") is False
                                    and lane.get("closed") is True for lane in lanes))
            if lesson == 43:
                calls = proof.get("calls") or []
                results = proof.get("results") or []
                ids = {item.get("id") for item in results if item.get("is_error") is not True}
                base = bool(record.get("status") == "completed"
                            and proof.get("experiment_passed") is expected_check
                            and proof.get("connection_closed") is True
                            and proof.get("source_label") == "provider-backed SDK remote MCP tool and resource calls"
                            and valid_turn and calls
                            and all(item.get("id") in ids for item in calls)
                            and proof.get("handlers")
                            and (name.startswith(("tool-", "reconnect-", "rotate-"))
                                 or proof.get("resource_reads")))
                if name.startswith("rotate-"):
                    rotated = proof.get("reconnect") or {}
                    base = bool(base and rotated.get("revoked_status") == 401
                                and rotated.get("second_credential_label") == "credential-2"
                                and rotated.get("set_servers", {}).get("added") == ["lesson_remote"]
                                and {row.get("credential_label") for row in proof.get("handlers", [])}
                                    == {"credential-1", "credential-2"})
            if lesson == 44:
                lanes = proof.get("lanes") or []
                cost = sum(lane["terminals"][0]["cost_usd"] for lane in lanes
                           if lane.get("terminals"))
                base = bool(record.get("status") == "completed"
                            and proof.get("experiment_passed") is expected_check
                            and proof.get("closed") is True
                            and proof.get("source_label") == "native SDK subprocess"
                            and len(lanes) == (2 if name in {"privacy", "exporters"} else 1)
                            and all(len(lane.get("terminals", [])) == 1
                                    and lane["terminals"][0]["subtype"] == "success"
                                    and {row["signal"] for row in lane.get("receipts", [])
                                         if row["sender"] == "subprocess" and row["count"] > 0}
                                        == {"metrics", "logs", "traces"} for lane in lanes)
                            and isinstance(record.get("cost_usd"), (int, float))
                            and abs(record["cost_usd"] - cost) < 1e-9)
            record["passed"] = bool(base)
            records.append(record)
            (folder / "report.json").write_text(
                json.dumps({"lesson": lesson, "scenarios": records}, indent=2), encoding="utf-8"
            )
            print(
                json.dumps({key: value for key, value in record.items() if key != "experiment"}),
                flush=True,
            )
            if not record["passed"]:
                print(f"Stopped on the first failure. Report: {folder / 'report.json'}", flush=True)
                return 1
        print(f"All live cases passed. Report: {folder / 'report.json'}", flush=True)
        return 0
    finally:
        await service.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lesson", type=int, choices=CASES)
    parser.add_argument(
        "--live",
        action="store_true",
        help="Authorize the selected paid scenarios, each with a $0.10 threshold (not a hard billing cap).",
    )
    parser.add_argument("--case", help="Run one named scenario in a fresh bounded lesson run.")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args.lesson, args.live, args.case)))
