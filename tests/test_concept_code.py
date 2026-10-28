import re
import subprocess
import sys

import pytest

from agent_lab.config import ROOT
from agent_lab.curriculum import LESSONS
from agent_lab.learning import guide, prepared_answer

FOREIGN = ("maxTurns", "createSdkMcpServer", "Zod", "npm ", "TypeScript", "z.object")


@pytest.mark.parametrize("lesson_id", LESSONS)
def test_concept_code_is_focused_valid_python(lesson_id):
    code = guide(lesson_id).concept_code
    compile(code, f"lesson_{lesson_id:02}.py", "exec")
    assert 3 <= len(code.splitlines()) <= 70, lesson_id
    assert not [term for term in FOREIGN if term in code], lesson_id
    # Something key-shaped, not a redaction pattern that mentions the prefix.
    assert not re.search(r"sk-ant-[A-Za-z0-9]{8,}", code), lesson_id
    assert "api_key=" not in code.replace(" ", ""), lesson_id


def test_concept_code_type_checks_against_the_installed_sdk(tmp_path):
    """Every snippet is real SDK usage: mypy checks names, arguments and types."""
    for lesson_id in LESSONS:
        (tmp_path / f"lesson_{lesson_id:02}.py").write_text(
            guide(lesson_id).concept_code, encoding="utf-8"
        )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mypy",
            "--config-file",
            str(ROOT / "pyproject.toml"),
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        timeout=300,
    )
    assert result.returncode == 0, result.stdout[-4000:]


@pytest.mark.parametrize(
    ("lesson_id", "required"),
    [(1, "query("), (5, "create_sdk_mcp_server"), (7, "HookMatcher"), (14, "thinking")],
)
def test_concept_code_shows_the_lesson_concept(lesson_id, required):
    assert required in guide(lesson_id).concept_code


def test_tutor_code_answer_and_latest_run():
    assert "query(" in prepared_answer(1, "code")
    with_run = prepared_answer(1, "expected", "Mode: offline. Status: completed.")
    assert "### Your latest run" in with_run and "Status: completed." in with_run
    assert "### Your latest run" not in prepared_answer(1, "hint", "Mode: offline.")


def test_run_summary_is_short_and_redacted():
    from agent_lab.learning import CheckResult
    from agent_lab.output import OutputState
    from agent_lab.ui_learning import run_summary

    state = OutputState(mode="live", status="completed")
    state.evidence = {"api_key": "secret", "rows": ["x" * 5000]}
    state.answers = ["A" * 9000]
    summary = run_summary(state, CheckResult(status="passed", detail="ok"))
    assert len(summary) <= 6000
    assert "secret" not in summary and "[REDACTED]" in summary
    assert summary.startswith("Mode: live. Status: completed.")
