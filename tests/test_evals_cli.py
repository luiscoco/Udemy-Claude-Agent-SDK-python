"""Standalone Lesson 52 CLI status and zero-network boundaries."""

import json
import os
import subprocess
import sys

from agent_lab.config import ROOT


def invoke(*args: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    for name in ("ANTHROPIC_API_KEY", "INWORLD_API_KEY", "OPENAI_API_KEY"):
        environment.pop(name, None)
    return subprocess.run([sys.executable, str(ROOT / "scripts/eval.py"), *args],
                          cwd=ROOT, env=environment, capture_output=True, text=True, timeout=30)


def test_free_cli_statuses_and_paid_admission():
    for variant, code, status in (("baseline", 0, "pass"), ("cold-tone", 1, "fail"),
                                  ("fix-findings", 0, "pass")):
        result = invoke("--demo", variant)
        assert result.returncode == code, result.stderr
        report = json.loads(result.stdout)
        assert report["status"] == status and report["rows"] == 9
        assert report["metrics"] == 24 and report["modelCalls"] == 0
        assert report["networkAttempts"] == 0 and report["actualBilledUsd"] == 0
    assert invoke("--demo", "foreign").returncode == 2
    assert invoke("--live").returncode == 2
    assert invoke("--trials", "4").returncode == 2
