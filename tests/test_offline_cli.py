"""Standalone Lesson 51 process has no model/network path."""

import json
import os
import socket
import subprocess
import sys

from agent_lab.config import ROOT
from agent_lab.offline_guard import NetworkGuard


def test_network_guard_denies_before_connect() -> None:
    with NetworkGuard() as guard:
        try:
            with socket.socket() as probe:
                probe.connect(("invalid.example", 443))
        except RuntimeError as exc:
            assert "denied" in str(exc)
        else:
            raise AssertionError("The controlled socket path connected")
        assert guard.attempts == 1


def test_standalone_cli_normal_mutation_and_rejected_live() -> None:
    script = ROOT / "scripts/offline_host.py"
    env = {key: value for key, value in os.environ.items()
           if key not in {"ANTHROPIC_API_KEY", "INWORLD_API_KEY", "OPENAI_API_KEY"}}
    for arguments, code in (([], 0), (["--mutation"], 1), (["--live"], 2)):
        process = subprocess.run([sys.executable, str(script), *arguments],
                                 cwd=ROOT, env=env, capture_output=True,
                                 text=True, timeout=30, check=False)
        assert process.returncode == code, process.stderr
        if code != 2:
            result = json.loads(process.stdout)
            assert result["modelCalls"] == result["networkAttempts"] == 0
            assert result["actualBilledUsd"] == 0
            assert result["summary"]["passed"] == (16 if code == 0 else 15)
