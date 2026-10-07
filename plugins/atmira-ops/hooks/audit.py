"""Python command hook: JSON input on stdin, JSON decision on stdout."""
import datetime
import json
import os
import re
import sys
from pathlib import Path


def evaluate(arguments: dict) -> dict:
    event = arguments.get("hook_event_name")
    if event == "SessionStart":
        return {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "atmira-ops is active. Ticket ids look like ATM-123. Sign ticket answers with — atmira-ops."}}
    if event == "PreToolUse" and str(arguments.get("tool_name", "")).endswith("get_ticket") and re.search("ATM-999", str(arguments.get("tool_input", {}).get("id", "")), re.I):
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": "ATM-999 is confidential."}}
    return {}


def main() -> None:
    arguments = json.loads(sys.stdin.read(100000) or "{}")
    result = evaluate(arguments)
    if os.getenv("ATMIRA_AUDIT_LOG"):
        record = {"at": datetime.datetime.now(datetime.UTC).isoformat(), "event": arguments.get("hook_event_name"), "tool": arguments.get("tool_name"), "decision": result.get("hookSpecificOutput", {}).get("permissionDecision", "none")}
        with Path(os.environ["ATMIRA_AUDIT_LOG"]).open("a", encoding="utf-8") as output:
            output.write(json.dumps(record) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
