"""Skills: actual owned file loads, strict boundaries and correlated invocations."""

import copy
from pathlib import Path

import httpx
import pytest
from claude_agent_sdk import ClaudeAgentOptions

from agent_lab.api import create_app
from agent_lab.config import Settings
from agent_lab.curriculum import LESSONS
from agent_lab.exercises import seed_workspace
from agent_lab.foundations import Evidence, configure, run_local
from agent_lab.models import RunRequest, lesson_request
from agent_lab.runtime import RunService
from agent_lab.skills import parse_skill, prepare_skills, skill_policy, skill_prompt


@pytest.mark.parametrize("source", ["project", "plugin"])
@pytest.mark.parametrize("loading", ["invoke", "discovery", "preload"])
@pytest.mark.parametrize("support", [False, True])
async def test_discovery_invocation_and_preload_have_distinct_host_effects(
    tmp_path, source, loading, support
):
    seed_workspace(tmp_path, LESSONS[11])
    request = RunRequest(
        lesson_options={"discovery": source, "loading": loading, "load_support": support}
    )
    result = await run_local(tmp_path, request, LESSONS[11])
    report = result["experiment"]
    assert result["experiment_passed"] is (loading == "invoke")
    assert report["local_effects"]["generated_files_verified"] is False
    stages = report["local_effects"]["timeline"]
    assert stages[0]["stage"] == "host-inspection" and "body" not in stages[0]
    assert any(row["stage"] == "host-support-load" for row in stages) is (
        support and loading != "discovery"
    )
    if loading == "preload":
        assert not report["calls"] and report["configured"]["skills"] == []
        assert "Host-preloaded instructions" in report["configured"]["system_prompt"]["append"]
    elif loading == "discovery":
        assert len(stages) == 1 and not report["calls"]
    else:
        expected = "lesson-summary" if source == "project" else "lesson-skills:lesson-summary"
        assert report["calls"][0]["arguments"] == {"skill": expected}
        assert report["results"][0]["id"] == report["calls"][0]["id"]
    assert report["configured"]["setting_sources"] == (["project"] if source == "project" else [])


async def test_hidden_skill_has_failed_fixture_result_but_prepared_files_remain(tmp_path):
    seed_workspace(tmp_path, LESSONS[11])
    result = await run_local(tmp_path, RunRequest(lesson_options={"visible": False}), LESSONS[11])
    assert not result["experiment_passed"]
    assert result["experiment"]["results"][0]["is_error"] is True
    selected = lesson_request(11, {"lesson_options": {"visible": False}}).lesson_options
    assert not skill_policy(tmp_path, selected, "Skill", {"skill": "lesson-summary"})[0]
    assert skill_policy(
        tmp_path, selected, "Read", {"file_path": ".claude/skills/lesson-summary/SKILL.md"}
    )[0]
    for target in (".claude/settings.json", ".env", "../outside.md"):
        assert not skill_policy(tmp_path, selected, "Read", {"file_path": target})[0]
    assert not skill_policy(tmp_path, selected, "Write", {"file_path": "notes.txt"})[0]


@pytest.mark.parametrize(
    "options",
    [
        {"loading": "native-subagent"},
        {"visible": "true"},
        {"discovery": "user"},
        {"path": "../secret"},
        {"load_support": 1},
    ],
)
async def test_invalid_skill_inputs_are_rejected_before_workspace_creation(tmp_path, options):
    service = RunService(Settings(data_dir=tmp_path))
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app(service, with_ui=False)),
            base_url="http://test",
        ) as client:
            response = await client.post("/api/lessons/11/run", json={"lesson_options": options})
        assert response.status_code == 422 and not service.active
        assert not list(tmp_path.iterdir())
    finally:
        await service.close()


@pytest.mark.parametrize(
    "text",
    [
        "no frontmatter",
        "---\nname: x\n---\nbody",
        "---\nname: x\nname: y\ndescription: d\n---\nbody",
        "---\nname: x\ndescription: d\n---\n",
    ],
)
def test_simple_parser_rejects_missing_duplicate_or_empty_fields(text):
    with pytest.raises(ValueError):
        parse_skill(text)


def test_actual_sdk_options_and_prompt_expose_exact_selected_source(tmp_path):
    request = lesson_request(
        11,
        {
            "prompt": "Explain agents.",
            "lesson_options": {"discovery": "plugin", "load_support": True},
        },
    )
    options = ClaudeAgentOptions()
    echo = configure(options, LESSONS[11], request, tmp_path)
    assert options.skills == ["lesson-skills:lesson-summary"]
    assert options.setting_sources == []  # Never let the SDK default to user settings.
    assert Path(options.plugins[0]["path"]).is_relative_to(tmp_path)
    assert "lesson-skills:lesson-summary" in skill_prompt(request)
    assert "resources/checklist.md" in skill_prompt(request)
    assert echo["skills"] == options.skills


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate-call",
        "duplicate-result",
        "child-only",
        "wrong-skill",
        "wrong-run",
        "failed-result",
        "failed-parent",
        "text-after-terminal",
    ],
)
async def test_invocation_proof_rejects_ambiguous_or_unrelated_evidence(tmp_path, mutation):
    seed_workspace(tmp_path, LESSONS[11])
    report = (await run_local(tmp_path, RunRequest(), LESSONS[11]))["experiment"]
    proof = Evidence(11, report["run"], tmp_path, lesson_request(11, {}).lesson_options, "test")
    proof.configured = report["configured"]
    proof.initialized = report["initialization"]
    proof.calls = copy.deepcopy(report["calls"])
    proof.results = copy.deepcopy(report["results"])
    proof.terminals = copy.deepcopy(report["terminal_results"])
    assert proof.report()["experiment_passed"]
    if mutation == "duplicate-call":
        proof.calls += copy.deepcopy(proof.calls)
    elif mutation == "duplicate-result":
        proof.results += copy.deepcopy(proof.results)
    elif mutation == "child-only":
        proof.calls[0]["parent_tool_use_id"] = "worker"
    elif mutation == "wrong-skill":
        proof.calls[0]["arguments"]["skill"] = "other"
    elif mutation == "wrong-run":
        proof.results[0]["run_id"] = "different"
    elif mutation == "failed-result":
        proof.results[0]["is_error"] = True
    elif mutation == "failed-parent":
        proof.terminals[0]["is_error"] = True
    else:
        proof.last_root_message = "AssistantMessage"
    assert not proof.report()["experiment_passed"]


def test_prepared_files_do_not_follow_a_symlink_outside_owned_workspace(tmp_path):
    work = tmp_path / "work"
    outside = tmp_path / "outside"
    work.mkdir()
    outside.mkdir()
    try:
        (work / ".claude").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Creating symlinks requires platform privileges.")
    with pytest.raises(ValueError, match="owned workspace"):
        prepare_skills(work)
    assert not list(outside.iterdir())
