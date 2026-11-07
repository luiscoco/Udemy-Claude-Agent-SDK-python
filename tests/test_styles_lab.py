import hashlib
import json

import pytest

from agent_lab.config import Settings
from agent_lab.foundation_models import SCENARIOS
from agent_lab.models import LessonError, RunRequest, lesson_request
from agent_lab.styles_lab import local_styles, owned, prepare_style, style_options, style_text


def test_owned_style_files_and_sdk_source_scope(tmp_path):
    hashes = prepare_style(tmp_path, "teaching")
    assert hashes[".claude/output-styles/teaching.md"] == hashlib.sha256(style_text("teaching").encode()).hexdigest()
    assert json.loads((tmp_path / ".claude" / "settings.json").read_text()) == {"outputStyle": "teaching"}
    assert "Bash" not in style_text("teaching")
    options = style_options(tmp_path, tmp_path / "config", lesson_request(34, RunRequest()), Settings())
    assert options.setting_sources == ["project"]
    assert options.tools == options.allowed_tools == []
    with pytest.raises(ValueError):
        owned(tmp_path, "../outside/file")


@pytest.mark.parametrize("selection", [{}, {"style": "brief"}, {"source": "none"}])
async def test_style_comparisons(tmp_path, selection):
    proof = await local_styles(tmp_path, RunRequest(lesson_options=selection))
    report = proof["experiment"]
    assert report["experiment_passed"]
    assert report["project_files_unchanged"]
    assert report["style_behavior_observed"]
    assert report["configured"]["tools"] == []


@pytest.mark.parametrize("scenario", [key for key in SCENARIOS[34] if key != "success"])
async def test_recorded_style_failures_need_review(tmp_path, scenario):
    proof = await local_styles(tmp_path, RunRequest(scenario=scenario))
    assert not proof["experiment_passed"]
    assert proof["experiment"]["expected_check"] == "needs-review"


def test_live_rejects_negative_fixture_and_custom_prompt():
    with pytest.raises(LessonError):
        lesson_request(34, RunRequest(mode="live", scenario="changed-style"))
    with pytest.raises(LessonError):
        lesson_request(34, RunRequest(prompt="different"))
