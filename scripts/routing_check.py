"""Free, network-guarded Lesson 59 prepared routing harness."""

import hashlib
import json
import socket
import sys
import uuid
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 1:
        print("The free routing check takes no arguments.", file=sys.stderr)
        return 2
    attempts = 0
    original_connect = socket.socket.connect
    original_create = socket.create_connection

    def denied_connect(self, address):
        nonlocal attempts
        attempts += 1
        raise OSError("Free routing check forbids network access")

    def denied_create(address, timeout=None, source_address=None, *, all_errors=False):
        nonlocal attempts
        attempts += 1
        raise OSError("Free routing check forbids network access")

    socket.socket.connect = denied_connect
    socket.create_connection = denied_create
    try:
        root = Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(root))
        from agent_lab.routing_lab import STRATEGIES, RoutingInput, prepared

        tracked = (root / "pyproject.toml", root / "uv.lock")
        before = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in tracked}
        report = prepared(RoutingInput(strategies=list(STRATEGIES)))
        statuses = {strategy: prepared(RoutingInput(strategies=[strategy]))["check"]["status"]
                    for strategy in STRATEGIES}
        after = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in tracked}
        passed = (len(report["rows"]) == 104 and
                  {name for name, value in statuses.items() if value == "pass"} ==
                  set(STRATEGIES) - {"light", "cascade"} and
                  report["sdkQueries"] == report["reportedSdkUsd"] == 0 and
                  before == after and attempts == 0)
        owned = root / ".lab-data" / "live-validation" / f"routing-{uuid.uuid4()}"
        owned.mkdir(parents=True)
        summary = {"passed": passed, "source": "synthetic-authored-fixture",
                   "strategies": statuses, "rows": len(report["rows"]),
                   "sdkQueries": 0, "reportedSdkUsd": 0, "networkAttempts": attempts,
                   "packageLockUnchanged": before == after,
                   "note": "Harness pass validates expected teaching outcomes; light and cascade suites remain needs-review."}
        (owned / "report.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(json.dumps({**summary, "path": str(owned / "report.json")}))
        return 0 if passed else 1
    finally:
        socket.socket.connect = original_connect
        socket.create_connection = original_create


if __name__ == "__main__":
    raise SystemExit(main())
