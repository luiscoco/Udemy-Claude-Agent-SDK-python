import asyncio
from pathlib import Path

import pytest

from agent_lab.background_lab import background_report, execute_background, local_background
from agent_lab.config import Settings
from agent_lab.foundations import Evidence
from agent_lab.models import Event, LessonError, RunRequest, lesson_request


@pytest.mark.parametrize("ending", ["cancel", "finish"])
async def test_offline_watcher_settles_before_return(tmp_path: Path, ending: str) -> None:
    report = (await local_background(tmp_path, RunRequest(lesson_options={"ending": ending})))["experiment"]
    watcher = report["watcher"]
    assert report["experiment_passed"] is True
    assert watcher["running_during_query"] is True
    assert watcher["awaited"] is True
    assert watcher["done"] is True
    assert watcher["cleanup_ran"] is True
    assert watcher["cancelled"] is (ending == "cancel")
    assert watcher["released"] is (ending == "finish")


@pytest.mark.parametrize("scenario", ["missing-evidence", "wrong-identity", "missing-cleanup", "unawaited", "not-running"])
async def test_recorded_negative_watcher_scenarios_need_review(tmp_path: Path, scenario: str) -> None:
    report = (await local_background(tmp_path, RunRequest(scenario=scenario)))["experiment"]
    assert report["experiment_passed"] is False
    assert report["expected_check"] == "needs-review"


def test_report_rejects_watcher_that_was_never_running(tmp_path: Path) -> None:
    state = Evidence(27, "run", tmp_path, {"ending": "cancel"}, "fixture")
    state.initialized = [{"session_id": "one"}]
    state.terminals = [{"session_id": "one", "subtype": "success", "is_error": False}]
    watcher = {"started": True, "running_during_query": False, "awaited": True, "done": True, "cleanup_ran": True, "owner_same_task": True, "cancelled": True, "released": False}
    report = background_report(state, state.selected, watcher, ["BACKGROUND_27"], True)
    assert report["experiment_passed"] is False


def test_request_rejects_unsupported_ending_and_live_fixture() -> None:
    with pytest.raises(ValueError):
        lesson_request(27, {"lesson_options": {"ending": "detach"}})
    with pytest.raises(LessonError):
        lesson_request(27, {"mode": "live", "scenario": "unawaited"})


async def test_cancelled_sdk_run_settles_host_watcher(tmp_path: Path, monkeypatch) -> None:
    import agent_lab.background_lab as background_lab
    import agent_lab.sdk as sdk

    monkeypatch.setattr(sdk, "require_live_access", lambda settings: None)
    monkeypatch.setattr(sdk, "resolve_cli_path", lambda settings: "C:/fixture/claude.exe")
    queried = asyncio.Event()
    disconnected = []

    class WaitingClient:
        def __init__(self, options):
            pass

        async def connect(self):
            pass

        async def query(self, prompt):
            queried.set()

        async def receive_response(self):
            await asyncio.Event().wait()
            if False:
                yield None

        async def disconnect(self):
            disconnected.append(True)

    monkeypatch.setattr(background_lab, "ClaudeSDKClient", WaitingClient)
    events: list[Event] = []

    async def emit(event: Event) -> None:
        events.append(event)

    run = asyncio.create_task(execute_background(tmp_path, RunRequest(mode="live"), Settings(enable_live=True), emit))
    await asyncio.wait_for(queried.wait(), 5)
    run.cancel()
    with pytest.raises(asyncio.CancelledError):
        await run
    assert disconnected == [True]
    assert not any(task.get_name() == "lesson-27-host-watcher" and not task.done() for task in asyncio.all_tasks())
    assert events[-1].kind == "evidence"
    assert events[-1].data["result"]["experiment"]["watcher"]["cleanup_ran"] is True
