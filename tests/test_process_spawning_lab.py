"""Lesson 36's owned child effects and framing boundaries."""

from pathlib import Path

import pytest

from agent_lab.models import LessonError, RunRequest, lesson_request
from agent_lab.process_spawning_lab import FrameTap, local_spawn


def test_frame_tap_retains_partial_utf8_and_original_chunks() -> None:
    tap = FrameTap()
    raw = '{"kind":"init","text":"café"}\n'.encode()
    chunks = [raw[:10], raw[10:-3], raw[-3:]]
    assert b"".join(tap.feed(chunk) for chunk in chunks) == raw
    assert tap.finish()
    assert tap.forwarded == raw
    assert tap.frames == [{"kind": "init", "text": "café"}]
    assert tap.partial_chunks > 0


@pytest.mark.parametrize("action,passed", [
    ("success", True), ("stderr", True), ("failed-launch", False),
    ("timeout", False), ("cancel", False),
])
async def test_owned_child_actions(tmp_path: Path, action: str, passed: bool) -> None:
    proof = await local_spawn(tmp_path / "work", RunRequest(lesson_options={"action": action}))
    report = proof["experiment"]
    assert proof["experiment_passed"] is passed
    assert report["sdk_success"]
    if action == "failed-launch":
        assert report["child"]["launch_error"] == "FileNotFoundError"
    else:
        assert report["child"]["child_cleaned"]
    if action in {"timeout", "cancel"}:
        assert report["child"]["interrupted"]
    if action == "stderr":
        assert report["child"]["stderr_marker"]
        assert [frame["kind"] for frame in report["child"]["frames"]] == ["init", "host_tool", "done"]


async def test_second_local_location_and_recorded_failures(tmp_path: Path) -> None:
    proof = await local_spawn(tmp_path / "work", RunRequest(lesson_options={"location": "machine-b"}))
    assert proof["experiment_passed"]
    assert proof["experiment"]["child"]["frames"][0]["location"] == "machine-b"
    for scenario in ("missing-evidence", "wrong-identity", "wrong-frame", "wrong-answer"):
        negative = await local_spawn(tmp_path / scenario / "work", RunRequest(scenario=scenario))
        assert not negative["experiment_passed"]


def test_strict_spawn_inputs() -> None:
    with pytest.raises(LessonError):
        lesson_request(36, RunRequest(prompt="arbitrary"))
    with pytest.raises(ValueError):
        lesson_request(36, RunRequest(lesson_options={"location": "remote-server"}))
    with pytest.raises(LessonError):
        lesson_request(36, RunRequest(mode="live", scenario="wrong-frame"))
