"""Lesson 1 checks actual terminal evidence, never the wording of a reply."""

import asyncio

import httpx
import pytest
from claude_agent_sdk import AssistantMessage, ResultMessage, SystemMessage, TextBlock
from pydantic import ValidationError

from agent_lab.api import create_app
from agent_lab.config import Settings
from agent_lab.learning import check_evidence, code_tour, guide
from agent_lab.models import LessonError, RunRequest, lesson_request
from agent_lab.runtime import RunService


@pytest.mark.parametrize("scenario,passed", [("success", True), ("error", False), ("missing-result", False)])
async def test_recorded_scenarios_distinguish_text_from_terminal_success(tmp_path, scenario, passed):
    service = RunService(Settings(data_dir=tmp_path))
    try:
        events = [event async for event in service.events(service.start(1, RunRequest(scenario=scenario)))]
        assert events[-1].data["status"] == "completed"  # the replay itself finished
        evidence = next(event.data["result"] for event in events if event.kind == "evidence")
        assert evidence["text"] and evidence["successful_result"] is passed
        assert [message["type"] for message in evidence["ordered_messages"][:2]] == ["SystemMessage", "AssistantMessage"]
        assert bool(evidence["results"]) is (scenario != "missing-result")
        check = check_evidence(1, evidence, status="completed")
        assert check.status == ("passed" if passed else "needs-review")
        assert check.status == evidence["expected_check"]
    finally:
        await service.close()


@pytest.mark.parametrize("cancel", [True, False], ids=["cancel", "deadline"])
async def test_interruption_closes_the_same_live_query(tmp_path, monkeypatch, cancel):
    import agent_lab.sdk as sdk

    monkeypatch.setenv("ANTHROPIC_API_KEY", "fixture-only")
    monkeypatch.setattr(sdk, "resolve_cli_path", lambda settings: "fixture-cli")
    entered, closed = asyncio.Event(), asyncio.Event()

    async def producer(*, prompt, options):
        try:
            yield AssistantMessage(content=[TextBlock(text="Partial text")], model="fixture")
            entered.set()
            await asyncio.Event().wait()
        finally:
            closed.set()

    monkeypatch.setattr(sdk, "query", producer)
    service = RunService(Settings(data_dir=tmp_path, enable_live=True, timeout_seconds=90 if cancel else 1))
    try:
        handle = service.start(1, RunRequest(mode="live"))
        await asyncio.wait_for(entered.wait(), timeout=5)
        if cancel:
            await service.cancel(handle)
        events = [event async for event in service.events(handle)]
        status = events[-1].data["status"]
        assert status == ("cancelled" if cancel else "failed")
        assert closed.is_set() and not service.active
        assert not [event for event in events if event.kind == "evidence"]
        assert check_evidence(1, None, status=status).status == "needs-review"
    finally:
        await service.close()


@pytest.mark.parametrize("body", [
    {"prompt": "   "}, {"prompt": "x" * 10001}, {"prompt": 123},
    {"max_turns": 2}, {"max_turns": True}, {"max_turns": "1"},
    {"max_budget_usd": 0.051}, {"max_budget_usd": "0.05"},
    {"unexpected": True}, {"scenario": "invented"},
])
async def test_invalid_query_request_starts_no_task_or_workspace(tmp_path, body):
    service = RunService(Settings(data_dir=tmp_path))
    app = create_app(service, with_ui=False)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/lessons/1/run", json=body)
        assert response.status_code == 422, response.text
        assert not service.active and not list(tmp_path.iterdir())
    finally:
        await service.close()


def test_defaults_trim_and_scenario_boundaries():
    request = lesson_request(1, {"prompt": "  Why?  "})
    assert request.prompt == "Why?"
    assert request.max_turns == 1 and request.max_budget_usd == 0.05
    assert lesson_request(1, {"prompt": "  " + "x" * 10000 + "  "}).prompt == "x" * 10000
    with pytest.raises(ValidationError):
        lesson_request(1, RunRequest(prompt=""))
    for lesson, mode in [(1, "live"), (51, "offline")]:
        with pytest.raises(LessonError, match="offline"):
            lesson_request(lesson, {"mode": mode, "scenario": "error"})
    assert lesson_request(51, {}).max_turns == 4


@pytest.mark.parametrize("number", ["NaN", "Infinity", "-Infinity"])
async def test_nonfinite_budget_is_a_validation_error_not_a_server_error(tmp_path, number):
    service = RunService(Settings(data_dir=tmp_path))
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(service, with_ui=False)), base_url="http://test") as client:
            response = await client.post("/api/lessons/1/run", content='{"max_budget_usd":' + number + '}', headers={"content-type": "application/json"})
        assert response.status_code == 422
        assert not service.active and not list(tmp_path.iterdir())
    finally:
        await service.close()


def test_seven_explained_questions_and_reviewed_source():
    item = guide(1)
    assert len(item.quiz) == 7
    assert item.quiz[0].correct == 1 and item.quiz[1].correct == 0
    assert all(q.options[q.correct].explanation.startswith("Correct.") for q in item.quiz)
    assert all(q.code for q in item.quiz[2:])
    assert len(code_tour(1)) == 4
    assert "max_turns=1, max_budget_usd=0.05" in item.concept_code
    assert check_evidence(1, {"successful_result": True}, status="cancelled").status == "needs-review"


@pytest.mark.parametrize("outcome", ["success", "error", "missing", "wrong-session", "wrong-subtype", "trailing-text"])
async def test_live_query_terminal_evidence_and_stream_cleanup(tmp_path, monkeypatch, outcome):
    import agent_lab.sdk as sdk

    monkeypatch.setenv("ANTHROPIC_API_KEY", "fixture-only")
    monkeypatch.setattr(sdk, "resolve_cli_path", lambda settings: "fixture-cli")
    captured = []
    closed = []

    async def producer(*, prompt, options):
        captured.append((prompt, options))
        try:
            yield SystemMessage(subtype="init", data={"session_id": "fixture-session"})
            yield AssistantMessage(content=[TextBlock(text="Partial text")], model="fixture")
            if outcome != "missing":
                yield ResultMessage(
                    subtype="error_max_turns" if outcome == "error" else "unexpected" if outcome == "wrong-subtype" else "success",
                    is_error=outcome == "error", session_id="other" if outcome == "wrong-session" else "fixture-session",
                    duration_ms=1, duration_api_ms=1, num_turns=1, total_cost_usd=0,
                )
            if outcome == "trailing-text":
                yield AssistantMessage(content=[TextBlock(text="Late text")], model="fixture")
        finally:
            closed.append(True)

    monkeypatch.setattr(sdk, "query", producer)
    service = RunService(Settings(data_dir=tmp_path, enable_live=True))
    try:
        events = [event async for event in service.events(service.start(1, RunRequest(mode="live", prompt=" Why? ")))]
        assert events[-1].data["status"] == ("completed" if outcome == "success" else "failed")
        assert closed == [True]
        prompt, options = captured[0]
        assert prompt == "Why?" and options.max_turns == 1 and options.max_budget_usd == 0.05
        assert options.tools == [] and options.setting_sources == [] and options.strict_mcp_config
        evidence = [event.data["result"] for event in events if event.kind == "evidence"]
        assert len(evidence) == (1 if outcome == "success" else 0)
        if evidence:
            assert evidence[0]["source"] == "live SDK terminal result"
            assert check_evidence(1, evidence[0], status="completed", mode="live").status == "passed"
    finally:
        await service.close()
