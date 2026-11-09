"""Lesson 56 offline CLI and paid launcher admission stay separate."""

import json
import subprocess
import sys


def test_free_team_cli_and_paid_opt_in() -> None:
    free = subprocess.run([sys.executable, "scripts/teams_check.py"],
                          capture_output=True, text=True, check=False)
    assert free.returncode == 0
    report = json.loads(free.stdout)
    assert report["passed"] and report["steps"] == 16 and report["rejected"] == 5
    assert report["modelCalls"] == report["networkAttempts"] == report["reportedSdkUsd"] == 0
    rejected = subprocess.run([sys.executable, "scripts/teams_check.py", "--live"],
                              capture_output=True, text=True, check=False)
    assert rejected.returncode == 2 and "accepts no arguments" in rejected.stderr
    paid = subprocess.run([sys.executable, "scripts/live_teams_check.py"],
                          capture_output=True, text=True, check=False)
    assert paid.returncode == 2 and "requires --live --budget" in paid.stderr
