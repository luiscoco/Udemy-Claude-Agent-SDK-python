"""One input iterator, scoped controls and truthful streaming-session evidence."""

import asyncio
import copy
from pathlib import Path

import httpx
import pytest

from agent_lab.api import create_app
from agent_lab.config import Settings
from agent_lab.foundations import source_sections
from agent_lab.learning import check_evidence
from agent_lab.models import LessonError, RunRequest, lesson_request
from agent_lab.runtime import RunService
from agent_lab.streaming import StreamSession, local_streaming, stream_report


async def test_live_sdk_error_preserves_terminal_evidence_fails_and_does_not_send_follow_up(
    tmp_path, monkeypatch
):
    from claude_agent_sdk import ClaudeSDKClient as RealClient

    import agent_lab.sdk as sdk
    import agent_lab.streaming as streaming

    class FailingFixture(streaming.StreamingFixture):
        async def _reply(self):
            await self._outbox.put(
                {
                    "type": "result",
                    "subtype": "error_during_execution",
                    "is_error": True,
                    "duration_ms": 0,
                    "duration_api_ms": 0,
                    "num_turns": 1,
                    "session_id": self.session_id,
                    "total_cost_usd": 0,
                    "result": "Recorded account/model failure",
                }
            )

    class Client(RealClient):
        def __init__(self, options, transport=None):
            super().__init__(options=options, transport=FailingFixture([]))

    monkeypatch.setattr(streaming, "ClaudeSDKClient", Client)
    monkeypatch.setattr(sdk, "require_live_access", lambda settings: None)
    monkeypatch.setattr(sdk, "resolve_cli_path", lambda settings: "fixture-cli")
    runner = RunService(Settings(data_dir=tmp_path, enable_live=True))
    handle = runner.start(
        12, RunRequest(mode="live", lesson_options={"queue_timing": "after-result"})
    )
    events = [event async for event in runner.events(handle)]
    assert events[-1].data["status"] == "failed"
    assert any(event.kind == "result" and event.data["is_error"] for event in events)
    assert any(
        event.kind == "error" and "No automatic retry" in event.data["message"] for event in events
    )
    proof = next(event.data["result"] for event in events if event.kind == "evidence")
    assert not proof["experiment_passed"]
    assert proof["experiment"]["source"] == "live SDK stream and actual host callbacks"
    assert handle.input_stream.connection_closed and len(handle.input_stream.submitted) == 1
    assert not runner.active


@pytest.mark.parametrize("timing", ["immediate", "after-result"])
@pytest.mark.parametrize("control", ["none", "model", "permission"])
async def test_script_uses_one_real_sdk_connection_and_closes_every_stream(
    tmp_path, timing, control
):
    result = await asyncio.wait_for(
        local_streaming(
            tmp_path,
            RunRequest(lesson_options={"queue_timing": timing, "runtime_control": control}),
        ),
        10,
    )
    assert result["experiment_passed"]
    proof = result["experiment"]
    state = proof["input_stream"]
    assert state["submitted_count"] == state["yielded_count"] == state["successful_results"] == 2
    assert state["application_handle"] != state["sdk_identity"]
    assert sum(row["stage"] == "connection-open" for row in state["timeline"]) == 1
    assert [r["input_id"] for r in state["inputs"]] == [
        r["input_id"] for r in state["yielded_inputs"]
    ]
    if control != "none":
        assert any(
            row["stage"] == "control-acknowledged" and row["action"] == control
            for row in state["timeline"]
        )
        assert state["acknowledged_settings"][control] == (
            "haiku" if control == "model" else "plan"
        )
    assert check_evidence(12, result, status="completed").status == "passed"
    assert check_evidence(12, result, status="completed", mode="live").status == "needs-review"


@pytest.mark.parametrize("scenario", ["missing-evidence", "wrong-identity", "interrupted"])
async def test_negative_stream_records_do_not_pass(tmp_path, scenario):
    result = await asyncio.wait_for(local_streaming(tmp_path, RunRequest(scenario=scenario)), 10)
    assert not result["experiment_passed"]
    assert check_evidence(12, result, status="completed").status == "needs-review"
    if scenario == "interrupted":
        state = result["experiment"]["input_stream"]
        assert state["aborted"] and state["connection_closed"]
        assert any(r["stage"] == "interrupt-acknowledged" for r in state["timeline"])


async def test_empty_open_queue_waits_and_end_wakes_the_generator():
    session = StreamSession("application")
    iterator = session.messages()
    waiting = asyncio.create_task(anext(iterator, None))
    await asyncio.sleep(0)
    assert not waiting.done() and not session.iterator_closed
    session.end()
    assert await asyncio.wait_for(waiting, 1) is None
    assert session.iterator_closed
    with pytest.raises(LessonError, match="closed"):
        session.push("Too late")


async def test_queued_message_is_not_a_completed_turn():
    session = StreamSession("application")
    identity = session.push("Queued input")
    assert session.snapshot()["queued_count"] == 1
    assert session.snapshot()["successful_results"] == session.snapshot()["yielded_count"] == 0
    iterator = session.messages()
    message = await anext(iterator)
    assert message["uuid"] == identity
    assert session.snapshot()["yielded_count"] == 1 and not session.results
    await iterator.aclose()


@pytest.mark.parametrize(
    "field", ["input_closed", "iterator_closed", "output_closed", "connection_closed"]
)
async def test_incomplete_closure_cannot_pass(tmp_path, field):
    result = (await local_streaming(tmp_path, RunRequest()))["experiment"]["input_stream"]
    session = StreamSession(result["application_handle"])
    session.submitted = result["inputs"]
    session.yielded = result["yielded_inputs"]
    session.results = result["terminal_results"]
    session.initialization = [result["sdk_identity"]]
    for flag in ("input_closed", "iterator_closed", "output_closed", "connection_closed"):
        setattr(session, flag, True)
    assert stream_report(session, "fixture")["experiment_passed"]
    setattr(session, field, False)
    assert not stream_report(session, "fixture")["experiment_passed"]
    setattr(session, field, True)
    session.yielded = copy.deepcopy(session.yielded) + copy.deepcopy(session.yielded)
    assert not stream_report(session, "fixture")["experiment_passed"]


async def wait_context(client, key, predicate):
    async with asyncio.timeout(10):
        while True:
            response = await client.post("/api/c12/context", json=key)
            assert response.status_code == 200, response.text
            data = response.json()
            if predicate(data):
                return data
            await asyncio.sleep(0.01)


async def test_session_api_controls_are_scoped_acknowledged_and_read_only_inspection_is_idle(
    tmp_path,
):
    runner = RunService(Settings(data_dir=tmp_path))
    app = create_app(runner, with_ui=False)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/api/c12/session", json={"prompt": "First"})
            assert response.status_code == 200, response.text
            key = {k: response.json()[k] for k in ("application_handle", "control_token")}
            first = await wait_context(
                client, key, lambda d: d["state"]["ready"] and d["state"]["successful_results"] == 1
            )
            assert not first["state"]["input_closed"] and not first["state"]["connection_closed"]
            for _ in range(3):
                assert (await client.post("/api/c12/context", json=key)).json()["state"][
                    "submitted_count"
                ] == 1
            assert (
                await client.post(
                    "/api/c12/send", json=key | {"control_token": "x" * 32, "text": "Stolen"}
                )
            ).status_code == 403
            assert (
                await client.post("/api/c12/send", json=key | {"text": "  "})
            ).status_code == 422
            for route, payload in (
                ("model", {"model": "haiku"}),
                ("permission-mode", {"permission_mode": "plan"}),
            ):
                response = await client.post("/api/c12/" + route, json=key | payload)
                assert response.status_code == 200, response.text
            state = (await client.post("/api/c12/context", json=key)).json()["state"]
            assert state["acknowledged_settings"] == {"model": "haiku", "permission": "plan"}
            assert (
                await client.post("/api/c12/send", json=key | {"text": "Second"})
            ).status_code == 200
            assert (
                await client.post("/api/c12/send", json=key | {"text": "Third"})
            ).status_code == 409
            assert (await client.post("/api/c12/end", json=key)).status_code == 200
            finished = await wait_context(client, key, lambda d: d["status"] != "running")
            assert finished["status"] == "completed" and finished["evidence"]["experiment_passed"]
            assert (
                finished["state"]["connection_closed"]
                and finished["state"]["successful_results"] == 2
            )
            assert (
                await client.post("/api/c12/send", json=key | {"text": "After closure"})
            ).status_code == 409
            assert (
                await client.post("/api/c12/model", json=key | {"model": "sonnet"})
            ).status_code == 409
            assert (await client.post("/api/c12/context", json=key)).json()["state"] == finished[
                "state"
            ]
    finally:
        await app.state.input_streams.close()
        await runner.close()
    assert not runner.active


@pytest.mark.parametrize(
    "body",
    [
        {"lesson_options": {"max_messages": 10}},
        {"lesson_options": {"interactive": "true"}},
        {"lesson_options": {"queue_timing": "invented"}},
        {"lesson_options": {"runtime_control": "bypass"}},
        {"follow_up": " "},
        {"prompt": " "},
        {"mode": "live", "scenario": "wrong-identity", "consent": True},
    ],
)
async def test_bad_api_input_has_no_task_or_workspace(tmp_path, body):
    runner = RunService(Settings(data_dir=tmp_path, enable_live=True))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(runner, with_ui=False)), base_url="http://test"
    ) as client:
        response = await client.post("/api/c12/script", json=body)
    assert response.status_code == 422, response.text
    assert not runner.active and not list(tmp_path.iterdir())


async def test_paid_api_session_requires_explicit_consent_before_starting(tmp_path):
    runner = RunService(Settings(data_dir=tmp_path, enable_live=True))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(runner, with_ui=False)), base_url="http://test"
    ) as client:
        assert (await client.post("/api/c12/session", json={"mode": "live"})).status_code == 403
    assert not runner.active and not list(tmp_path.iterdir())


async def test_cancelling_an_idle_manual_session_closes_the_client_and_does_not_pass(tmp_path):
    runner = RunService(Settings(data_dir=tmp_path))
    request = RunRequest(lesson_options={"interactive": True})
    handle = runner.start(12, request)
    events = []
    result_ready = asyncio.Event()

    async def consume():
        async for event in runner.events(handle):
            events.append(event)
            if event.kind == "result":
                result_ready.set()

    consumer = asyncio.create_task(consume())
    assert handle.input_stream is not None
    await asyncio.wait_for(result_ready.wait(), 5)
    await asyncio.wait_for(runner.cancel(handle), 3)
    await consumer
    assert events[-1].data["status"] == "cancelled"
    assert handle.input_stream.connection_closed and handle.input_stream.iterator_closed
    assert handle.input_stream.aborted and not runner.active
    assert not stream_report(handle.input_stream, "fixture")["experiment_passed"]


def test_twelve_has_three_current_source_excerpts_and_strict_stream_defaults():
    from agent_lab.learning import guide

    assert len(guide(12).quiz) == 7
    request = lesson_request(12, {})
    assert request.prompt and request.follow_up and request.lesson_options["max_messages"] == 2
    sections = source_sections(12)
    assert len(sections) == 3
    for section in sections:
        lines = (
            (Path(__file__).resolve().parents[1] / section["path"])
            .read_text(encoding="utf-8")
            .splitlines()
        )
        assert section["code"].splitlines() == lines[section["start"] - 1 : section["end"]]


async def test_deadline_closes_an_idle_input_session_and_reports_failure(tmp_path):
    runner = RunService(Settings(data_dir=tmp_path, timeout_seconds=1))
    handle = runner.start(12, RunRequest(lesson_options={"interactive": True}))
    events = [event async for event in runner.events(handle)]
    assert events[-1].data["status"] == "failed"
    assert any(
        event.kind == "error" and "deadline" in event.data["message"].lower() for event in events
    )
    assert handle.input_stream.connection_closed and handle.input_stream.iterator_closed
    assert handle.input_stream.aborted and not runner.active


async def test_blocked_final_event_consumer_does_not_hold_sdk_cleanup(tmp_path):
    from agent_lab.streaming import execute_stream

    session = StreamSession("application")
    result_ready = asyncio.Event()

    async def emit(event):
        if event.kind == "result":
            result_ready.set()

    async def blocked(event):
        await asyncio.Event().wait()

    task = asyncio.create_task(
        execute_stream(
            session,
            RunRequest(lesson_options={"interactive": True}),
            tmp_path,
            tmp_path / "config",
            Settings(),
            emit,
        )
    )
    await asyncio.wait_for(result_ready.wait(), 5)
    session.emit = blocked
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 3)
    assert session.connection_closed and session.iterator_closed and session.aborted


async def test_session_slots_and_runtime_input_schemas_prevent_unowned_effects(tmp_path):
    runner = RunService(Settings(data_dir=tmp_path, max_concurrent_runs=1))
    app = create_app(runner, with_ui=False)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            started = (await client.post("/api/c12/session", json={})).json()
            key = {k: started[k] for k in ("application_handle", "control_token")}
            await wait_context(client, key, lambda d: d["state"]["ready"])
            assert (await client.post("/api/c12/session", json={})).status_code == 429
            for route, payload in (
                ("model", {"model": "unlisted-model"}),
                ("permission-mode", {"permission_mode": "bypassPermissions"}),
            ):
                assert (
                    await client.post("/api/c12/" + route, json=key | payload)
                ).status_code == 422
            wrong = key | {"application_handle": "f" * 32, "text": "Wrong owner"}
            assert (await client.post("/api/c12/send", json=wrong)).status_code == 403
            state = (await client.post("/api/c12/context", json=key)).json()["state"]
            assert state["submitted_count"] == 1 and len(runner.active) == 1
            await client.post("/api/c12/end", json=key)
            done = await wait_context(client, key, lambda d: d["status"] != "running")
            assert done["evidence"]["experiment_passed"]
    finally:
        await app.state.input_streams.close()
        await runner.close()


async def test_automatic_script_rejects_manual_interference_before_its_first_result(
    tmp_path, monkeypatch
):
    import agent_lab.streaming as streaming

    gate = asyncio.Event()
    original = streaming.StreamingFixture

    class GatedFixture(original):
        async def _reply(self):
            await gate.wait()
            await super()._reply()

    monkeypatch.setattr(streaming, "StreamingFixture", GatedFixture)
    runner = RunService(Settings(data_dir=tmp_path))
    app = create_app(runner, with_ui=False)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/c12/script", json={"lesson_options": {"queue_timing": "after-result"}}
            )
            key = {k: response.json()[k] for k in ("application_handle", "control_token")}
            state = await wait_context(client, key, lambda d: d["state"]["ready"])
            assert not state["state"]["manual_mode"] and not state["state"]["terminal_results"]
            assert (
                await client.post("/api/c12/send", json=key | {"text": "Unexpected extra input"})
            ).status_code == 409
            assert (
                await client.post("/api/c12/model", json=key | {"model": "sonnet"})
            ).status_code == 409
            gate.set()
            done = await wait_context(client, key, lambda d: d["status"] != "running")
            assert done["evidence"]["experiment_passed"] and done["state"]["submitted_count"] == 2
    finally:
        gate.set()
        await app.state.input_streams.close()
        await runner.close()


async def test_rejected_runtime_control_is_not_reported_as_an_acknowledged_change(
    tmp_path, monkeypatch
):
    import agent_lab.streaming as streaming

    original = streaming.StreamingFixture

    class RejectingFixture(original):
        async def _control(self, request_id, request):
            if request.get("subtype") == "set_model":
                await self._outbox.put(
                    {
                        "type": "control_response",
                        "response": {
                            "subtype": "error",
                            "request_id": request_id,
                            "error": "Recorded unavailable model",
                        },
                    }
                )
            else:
                await super()._control(request_id, request)

    monkeypatch.setattr(streaming, "StreamingFixture", RejectingFixture)
    runner = RunService(Settings(data_dir=tmp_path))
    app = create_app(runner, with_ui=False)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/api/c12/session", json={})
            key = {k: response.json()[k] for k in ("application_handle", "control_token")}
            await wait_context(client, key, lambda d: d["state"]["ready"])
            response = await client.post("/api/c12/model", json=key | {"model": "sonnet"})
            assert response.status_code == 409 and "rejected" in response.text
            state = (await client.post("/api/c12/context", json=key)).json()["state"]
            assert state["configured_settings"]["model"] == runner.settings.model
            assert "model" not in state["acknowledged_settings"]
            assert any(r["stage"] == "control-rejected" for r in state["timeline"])
            assert not any(r["stage"] == "control-acknowledged" for r in state["timeline"])
            await client.post("/api/c12/end", json=key)
            done = await wait_context(client, key, lambda d: d["status"] != "running")
            assert done["state"]["connection_closed"]
    finally:
        await app.state.input_streams.close()
        await runner.close()
