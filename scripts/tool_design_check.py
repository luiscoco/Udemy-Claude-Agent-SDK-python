"""Lesson 54 free guarded matrix or explicitly paid two-profile native comparison."""

import argparse
import asyncio
import json
import socket
import sys
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_lab.config import ROOT, Settings  # noqa: E402
from agent_lab.debug_lab import safe_redact  # noqa: E402
from agent_lab.tool_design_catalog import Catalog  # noqa: E402
from agent_lab.tool_design_lab import DesignInput, grade, prepared  # noqa: E402


async def run(live: bool, budget: float | None) -> int:
    from agent_lab.tool_design_native import native

    network_attempts = 0
    patcher = None
    if not live:
        def blocked(_socket: socket.socket, _address: Any) -> Any:
            nonlocal network_attempts
            network_attempts += 1
            raise RuntimeError("Free catalog validation cannot use the network")
        patcher = patch.object(socket.socket, "connect", blocked)
        patcher.start()
    rows: list[dict[str, Any]] = []
    reports: list[dict[str, Any]] = []
    try:
        choices = (("vague", "concise"), ("focused", "concise")) if live else (
            ("vague", "concise"), ("focused", "concise"),
            ("vague", "detailed"), ("focused", "detailed"))
        known_cost = 0.0
        for profile, format in choices:
            selected = DesignInput.model_validate({"mode": "live" if live else "prepared",
                                                   "profile": profile, "format": format,
                                                   "consent": live, "budget": budget or 0.5})
            identifier = uuid.uuid4()
            report = (await native(selected, identifier, Settings(enable_live=True),
                                   ROOT / ".lab-data/lesson-54", catalog=Catalog())
                      if live else await prepared(selected, identifier, catalog=Catalog()))
            reports.append(safe_redact(report, ROOT))
            summary = report["summary"]
            observed = summary["reportedSdkUsd"]
            if live and (not isinstance(observed, (int, float)) or observed < 0 or observed > 0.25):
                rows.append({"profile": profile, "format": format, "passed": False,
                             "reportedSdkUsd": observed, "reason": "Unknown or over-ceiling cost"})
                break
            known_cost += float(observed or 0)
            focused_passed = grade(selected, report)
            observation_valid = (report["closed"] and not report["interrupted"] and
                                 not report["error"] and not report.get("exception") and
                                 summary["errors"] == 0 and summary["calls"] > 0 and
                                 report["beforeSha256"] == report["afterSha256"])
            rows.append({"profile": profile, "format": format,
                         "passed": focused_passed if profile == "focused" else observation_valid,
                         "lessonCheck": "passed" if focused_passed else "not-awarded",
                         "calls": summary["calls"], "envelopeBytes": summary["envelopeBytes"],
                         "modelCalls": summary["modelCalls"], "reportedSdkUsd": observed})
        passed = len(rows) == len(choices) and all(row["passed"] for row in rows) and network_attempts == 0
    finally:
        if patcher is not None:
            patcher.stop()
    destination = ROOT / ".lab-data/offline-validation" / ("tool-design-" + str(uuid.uuid4()))
    destination.mkdir(parents=True, exist_ok=False)
    evidence = destination / "report.json"
    evidence.write_text(json.dumps({"lesson": 54, "mode": "live" if live else "prepared",
                                    "passed": passed, "rows": rows, "reports": reports,
                                    "networkAttempts": network_attempts}, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"lesson": 54, "mode": "live" if live else "prepared", "passed": passed,
                      "rows": rows, "modelCalls": sum(row["modelCalls"] for row in rows),
                      "knownSdkUsd": known_cost, "networkAttempts": network_attempts,
                      "evidence": str(evidence)}, indent=2))
    return 0 if passed else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--budget", type=float)
    args = parser.parse_args()
    if args.live and (args.budget is None or not 0.5 <= args.budget <= 1):
        parser.error("Paid comparison requires --live --budget between 0.5 and 1")
    if not args.live and args.budget is not None:
        parser.error("The free matrix does not accept a paid budget")
    return asyncio.run(run(args.live, args.budget))


if __name__ == "__main__":
    raise SystemExit(main())
