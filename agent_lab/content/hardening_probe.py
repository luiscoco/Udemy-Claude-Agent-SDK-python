"""Copied only into an owned Lesson 48 lane; prints synthetic booleans or receipt ID."""

import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(2)
    target = sys.argv[1]
    if target == "environment":
        print(json.dumps({"syntheticInherited": bool(os.getenv("LAB_APPLICATION_SECRET")),
                          "syntheticApiCredentialPresent": bool(os.getenv("ANTHROPIC_API_KEY"))}))
        return
    parsed = urlsplit(target)
    if (parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or
            parsed.path.count("/") != 2 or not parsed.path.startswith("/owned/") or
            parsed.query or parsed.fragment):
        raise SystemExit(2)
    raw = (Path.cwd() / ".env").read_bytes()
    value = raw.split(b"=", 1)[1].strip()
    request = Request(target, data=value, method="POST",
                      headers={"Content-Type": "text/plain"})
    with urlopen(request, timeout=5) as response:
        receipt = json.loads(response.read(512))
    print(json.dumps({"receiptId": receipt["receipt_id"]}))


if __name__ == "__main__":
    main()
