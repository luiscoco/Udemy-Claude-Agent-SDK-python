from pathlib import Path

import claude_agent_sdk

from agent_lab import doctor
from agent_lab.config import Settings


def test_native_user_install_is_found_without_path_or_bundled_cli(tmp_path, monkeypatch):
    monkeypatch.setattr(doctor.sys, "platform", "win32")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(doctor.shutil, "which", lambda name: None)
    monkeypatch.setattr(claude_agent_sdk, "__file__", str(tmp_path / "sdk/__init__.py"))
    settings = Settings(cli_path=None)
    assert doctor.resolve_cli_path(settings) is None
    native = tmp_path / ".local/bin/claude.exe"
    native.parent.mkdir(parents=True)
    native.touch()
    assert doctor.resolve_cli_path(settings) == str(native)
    assert doctor.diagnose(settings)["cli_available"]


def test_explicit_cli_path_takes_priority_and_missing_path_is_reported(tmp_path):
    configured = tmp_path / "custom/claude.exe"
    settings = Settings(cli_path=str(configured))
    assert doctor.resolve_cli_path(settings) == str(configured)
    assert not doctor.diagnose(settings)["cli_available"]
