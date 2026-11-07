"""Owned Lesson 49 process fixture. Its machine results are authored, never SDK results."""

import json
import sys
import time


def main() -> int:
    if len(sys.argv) != 5:
        return 2
    scenario, run_id, verdict, issue = sys.argv[1:]
    sys.stdin.read()  # DEVNULL gives immediate EOF; a CI child must not wait for input.
    print("owned-child-stderr", file=sys.stderr, flush=True)
    if scenario == "timeout":
        time.sleep(30)
        return 0
    if scenario == "missing-result":
        print("owned child produced no machine terminal", flush=True)
        return 0
    result = {"run": run_id, "verdict": verdict,
              "issues": [] if issue == "none" else issue.split(",")}
    terminal = {"type": "result", "is_error": scenario == "unsuccessful",
                "permission_denials": ["owned denial"] if scenario == "denied" else [],
                "cost_usd": 0, "structured_output": result}
    print(json.dumps(terminal, separators=(",", ":")), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
