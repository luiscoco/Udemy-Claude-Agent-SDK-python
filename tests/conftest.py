import pytest


def pytest_configure(config):
    """pyproject sets --basetemp=.lab-data/pytest; pytest creates that folder but not its
    git-ignored parent, so a fresh checkout (and CI) needs the parent made first."""
    (config.rootpath / ".lab-data").mkdir(exist_ok=True)


@pytest.fixture(autouse=True)
def isolate_live_configuration(monkeypatch):
    """Local .env credentials must never enable paid calls during the test suite."""
    monkeypatch.setenv("LAB_ENABLE_LIVE", "false")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    for name in ("CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY"):
        monkeypatch.setenv(name, "0")
