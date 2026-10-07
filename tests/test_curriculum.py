import json

import pytest

from agent_lab.config import Settings
from agent_lab.curriculum import LESSONS, TOPICS
from agent_lab.models import RunRequest
from agent_lab.runtime import RunService


def test_curriculum_is_complete_and_topics_have_no_duplicates():
    assert set(LESSONS) == set(range(1, 76))
    assert sorted(number for ids in TOPICS.values() for number in ids) == list(range(1, 76))


@pytest.mark.parametrize("lesson_id", range(1, 76))
async def test_each_offline_lesson_runs_real_host_code_without_sdk_process(
    lesson_id, tmp_path, monkeypatch
):
    import agent_lab.sdk

    async def forbidden(*args, **kwargs):
        raise AssertionError("Offline mode must not start an SDK process")

    monkeypatch.setattr(agent_lab.sdk, "run_sdk", forbidden)
    service = RunService(Settings(data_dir=tmp_path))
    handle = service.start(lesson_id, RunRequest())
    events = [event async for event in service.events(handle)]
    assert events[0].kind == "started"
    assert events[-1].kind == "done"
    assert events[-1].data["status"] == "completed", [event.model_dump() for event in events]
    assert len([event for event in events if event.kind == "done"]) == 1
    assert not service.active
    assert any(event.kind == "evidence" for event in events)
    for event in events:
        json.loads(event.model_dump_json())


async def test_actual_capstone_gate_and_analysis_evidence(tmp_path):
    service = RunService(Settings(data_dir=tmp_path))
    for number, key, expected in [(75, "release_gate", True), (71, "grand_total", 240)]:
        events = [event async for event in service.events(service.start(number, RunRequest()))]
        evidence = next(event.data["result"] for event in events if event.kind == "evidence")
        assert evidence[key] == expected


async def test_missing_cli_reports_setup_instructions_without_raw_error(tmp_path, monkeypatch):
    from claude_agent_sdk import CLINotFoundError

    import agent_lab.sdk

    async def missing_cli(*args, **kwargs):
        raise CLINotFoundError("private diagnostic must not be exposed")

    monkeypatch.setattr(agent_lab.sdk, "run_sdk", missing_cli)
    service = RunService(Settings(data_dir=tmp_path, enable_live=True))
    events = [event async for event in service.events(service.start(1, RunRequest(mode="live")))]
    error = next(event.data["message"] for event in events if event.kind == "error")
    assert "Install native Claude Code" in error
    assert "LAB_CLI_PATH" in error
    assert "private diagnostic" not in error
    assert events[-1].data["status"] == "failed"
    assert not service.active
