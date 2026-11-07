"""Fixed child for lesson 36; only controlled arguments reach this process."""

import argparse
import json
import sys
import time
from pathlib import Path


def frame(kind: str, **fields: object) -> None:
    sys.stdout.write(json.dumps({"kind": kind, **fields}, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=["success", "stderr", "timeout", "cancel"])
    args = parser.parse_args()
    frame("init", location=Path.cwd().name)
    if args.case in {"timeout", "cancel"}:
        time.sleep(10)
    frame("host_tool", operation="inspect-owned-child")
    if args.case == "stderr":
        print("CHILD_DIAGNOSTIC_36", file=sys.stderr, flush=True)
    frame("done", outcome="HOST_OK_36")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
