"""Owned worktrees, root serialization and lesson 39 evidence boundaries."""

from pathlib import Path

import pytest

from agent_lab.config import Settings
from agent_lab.config_root_lab import dry_flags, fixture, local, startup
from agent_lab.models import RunRequest


async def test_owned_worktrees_and_inert_sdk_argv(tmp_path: Path) -> None:
    paths = await fixture(tmp_path / "owned")
    assert all((paths[name] / ".git").exists() for name in ("trusted", "branch", "docs"))
    assert (paths["trusted"] / ".claude" / "commands" / "l39-trusted.md").is_file()
    assert (paths["branch"] / ".claude" / "commands" / "l39-branch.md").is_file()
    assert not (paths["docs"] / ".claude").exists()
    dry = dry_flags(paths, Settings())
    assert dry["all_serialized"] and dry["inert_process"] and not dry["sdk_called"]
    assert dry["rows"][0]["project_config_root_values"] == []
    assert dry["rows"][1]["project_config_root_values"] == [str(paths["trusted"])]


@pytest.mark.parametrize("selected", [{}, {"root": "omitted"}, {"root": "branch"},
                                      {"cwd": "docs", "root": "omitted"}, {"sources": "none"}])
async def test_prepared_origin_requires_owned_evidence(tmp_path: Path, selected: dict[str, str]) -> None:
    report = (await local(tmp_path, RunRequest(lesson_options=selected)))["experiment"]
    assert report["experiment_passed"]
    assert report["identity_matched"] and report["origin_matched"] and report["fixture_intact"]
    assert report["before_hashes"] == report["after_hashes"]


@pytest.mark.parametrize("scenario", ["missing-evidence", "wrong-identity", "failed", "interrupted",
                                      "wrong-hook", "duplicate-hook", "duplicate-result",
                                      "missing-command", "changed-fixture"])
async def test_prepared_negative_origin(tmp_path: Path, scenario: str) -> None:
    report = (await local(tmp_path, RunRequest(scenario=scenario)))["experiment"]
    assert not report["experiment_passed"]


@pytest.mark.parametrize("scenario", ["missing-evidence", "wrong-identity", "failed", "interrupted",
                                      "wrong-hook", "duplicate-hook", "duplicate-result",
                                      "changed-fixture", "wrong-effect"])
async def test_prepared_negative_takeover(tmp_path: Path, scenario: str) -> None:
    report = (await local(tmp_path, RunRequest(scenario=scenario,
        lesson_options={"action": "takeover", "root": "omitted"})))["experiment"]
    assert not report["experiment_passed"]


@pytest.mark.parametrize("root", ["trusted", "omitted"])
async def test_prepared_takeover_uses_exact_owned_command(tmp_path: Path, root: str) -> None:
    report = (await local(tmp_path, RunRequest(lesson_options={"action": "takeover", "root": root})))["experiment"]
    assert report["experiment_passed"] and report["effect_matched"]
    assert report["proof_file"] == report["nonce"] if root == "omitted" else report["proof_file"] is None


@pytest.mark.parametrize("root", ["relative", "missing", "file"])
async def test_credential_free_invalid_root_startup(tmp_path: Path, root: str) -> None:
    result = await startup(tmp_path, root, Settings())
    assert result["startup_failure_observed"]
    assert not result["provider_credentials_present"]
    assert not result["normal_success"]
