"""Lesson 41 Python client lifecycle evidence and ownership."""

from pathlib import Path

import pytest

from agent_lab.client_lifecycle_lab import base, compare, facts, resume, state
from agent_lab.config import Settings


async def test_prepared_base_persists_and_resumes_owned_session(tmp_path: Path) -> None:
    built = await base(tmp_path, Settings(), "prepared")
    assert built["experiment_passed"]
    assert len(built["turns"]) == 3
    assert built["query_after_disconnect"] == "CLIConnectionError"
    saved = state(tmp_path)
    assert saved["build_id"] == built["build_id"]
    assert saved["session_id"] == built["session_id"]
    followed = await resume(tmp_path, built["build_id"], Settings(), "prepared")
    assert followed["experiment_passed"]
    assert followed["result"]["session_id"] == saved["session_id"]
    assert facts()["historical_typescript_v2"].startswith("not installed")


@pytest.mark.parametrize("scenario", ["missing", "foreign", "failed"])
async def test_prepared_faults_never_replace_valid_latest(tmp_path: Path, scenario: str) -> None:
    good = await base(tmp_path, Settings(), "prepared")
    failed = await base(tmp_path, Settings(), "prepared", scenario)
    assert not failed["experiment_passed"]
    assert state(tmp_path)["build_id"] == good["build_id"]
    follow = await resume(tmp_path, good["build_id"], Settings(), "prepared", scenario)
    assert not follow["experiment_passed"]


async def test_comparison_and_mode_ownership(tmp_path: Path) -> None:
    report = await compare(tmp_path, Settings(), "prepared")
    assert report["experiment_passed"]
    assert report["base"]["session_id"] == report["resume"]["result"]["session_id"]
    with pytest.raises(ValueError, match="owned base"):
        await resume(tmp_path, report["base"]["build_id"], Settings(), "live")
    with pytest.raises(ValueError, match="Invalid owned"):
        state(tmp_path, "../foreign")
