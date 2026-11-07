"""Credential-free real CLI startup failures for lesson 39."""

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_lab.config import ROOT, Settings  # noqa: E402
from agent_lab.config_root_lab import startup  # noqa: E402


async def run() -> int:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    folder = ROOT / ".lab-data" / "lesson39-startup-smoke" / stamp
    folder.mkdir(parents=True)
    records = []
    for name in ("relative", "missing", "file"):
        record = await startup(folder, name, Settings())
        records.append(record)
        (folder / "report.json").write_text(json.dumps({"lesson": 39, "startup": records}, indent=2), encoding="utf-8")
        print(json.dumps({"root": name, "exit_code": record["exit_code"],
                          "startup_failure_observed": record["startup_failure_observed"]}), flush=True)
        if not record["startup_failure_observed"]:
            return 1
    print(f"All credential-free CLI startup probes observed. Report: {folder / 'report.json'}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="Launch three local CLI startup probes without provider credentials.")
    args = parser.parse_args()
    if not args.run:
        print("No CLI started. Use --run for the three fixed credential-free startup probes.")
        raise SystemExit(0)
    raise SystemExit(asyncio.run(run()))
