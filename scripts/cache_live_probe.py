"""Explicit one-action native Lesson 46 cache probe through the owned observer."""

import argparse
import asyncio
import json

from agent_lab.cache_lab import ACTIONS, POLICIES, PREFIXES, TTLS, live_action


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", required=True)
    parser.add_argument("--budget", type=float, required=True)
    parser.add_argument("--action", choices=ACTIONS, required=True)
    parser.add_argument("--ttl", choices=TTLS, default="5m")
    parser.add_argument("--prefix", choices=PREFIXES, default="stable")
    parser.add_argument("--policy", choices=POLICIES, default="cap")
    args = parser.parse_args()
    if not args.live or args.budget != 0.15:
        parser.error("Confirm --live and the fixed $0.15 two-turn ceiling.")
    report = asyncio.run(live_action(args.action, args.ttl, args.prefix, args.policy))
    results = [frame for frame in report["frames"] if frame.get("kind") == "result"]
    print(json.dumps({"operation": report["operation"], "action": args.action,
                      "passed": report["experiment_passed"],
                      "forwarded": report["forwarded"],
                      "wire_statuses": [row.get("status") for row in report["receipts"]],
                      "native_result_count": len(results),
                      "sdk_last_cumulative_usd": results[-1].get("total_cost_usd") if results else None}))
    return 0 if report["experiment_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
