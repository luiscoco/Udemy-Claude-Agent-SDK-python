"""Actual option/hook wiring with injected SDK streams, and prompt-free metadata."""

import asyncio
from pathlib import Path

import pytest
from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    StreamEvent,
    SystemMessage,
    TextBlock,
    ThinkingBlock,
)

from agent_lab.config import Settings
from agent_lab.hooks import call_hook
from agent_lab.models import RunRequest
from agent_lab.runtime import RunService
from agent_lab.thinking_models import ModelMetadata


async def injected(tmp_path, monkeypatch, *, case="success", compare=False):
    import agent_lab.sdk as sdk

    captured, prompts, closed, owners = [], [], [], []
    monkeypatch.setattr(sdk, "require_live_access", lambda settings: None)
    monkeypatch.setattr(sdk, "resolve_cli_path", lambda settings: "injected-cli")

    class Client:
        def __init__(self, options):
            self.options, self.input_id = options, None
            self.identity = "parent-" + str(len(captured))
            captured.append(options)

        async def connect(self):
            owners.append(asyncio.current_task())

        async def disconnect(self):
            owners.append(asyncio.current_task())
            closed.append(self.identity)

        async def query(self, prompt):
            messages = [message async for message in prompt]
            assert len(messages) == 1
            self.input_id = messages[0]["uuid"]
            prompts.append(messages[0]["message"]["content"])

        async def receive_response(self):
            if case == "auth":
                yield SystemMessage(subtype="api_retry", data={"error_status": 401})
                return
            yield SystemMessage(subtype="init", data={"session_id": self.identity})
            yield StreamEvent(
                uuid="private-delta",
                session_id=self.identity,
                event={
                    "type": "content_block_delta",
                    "delta": {
                        "type": "thinking_delta",
                        "thinking": "private-delta-must-not-be-exposed",
                    },
                },
            )
            yield AssistantMessage(
                content=[
                    ThinkingBlock(
                        thinking="private-block-must-not-be-exposed", signature="signature"
                    ),
                    TextBlock(text="Public injected answer"),
                ],
                model="reported-model-name",
            )
            if case != "missing":
                payload = {
                    "hook_event_name": "Stop",
                    "session_id": "unrelated" if case == "wrong" else self.identity,
                    "prompt_id": self.input_id,
                    "stop_hook_active": False,
                    "effort": {"level": "low"},
                }
                if case == "unknown":
                    payload.pop("effort")
                for matcher in self.options.hooks["Stop"]:
                    for hook in matcher.hooks:
                        await call_hook(hook, payload, None)
            failed = case == "failed"
            yield ResultMessage(
                subtype="error_during_execution" if failed else "success",
                is_error=failed,
                duration_ms=23,
                duration_api_ms=20,
                num_turns=1,
                session_id=self.identity,
                total_cost_usd=0.001,
                usage={"input_tokens": 11, "output_tokens": 7},
            )

    monkeypatch.setattr(sdk, "ClaudeSDKClient", Client)
    runner = RunService(Settings(data_dir=tmp_path, enable_live=True))
    options = (
        {"comparison": "effort", "authorize_comparison": True}
        if compare
        else {"model": "requested-model-name"}
    )
    handle = runner.start(
        14, RunRequest(mode="live", prompt="Identical fixed question.", lesson_options=options)
    )
    events = [event async for event in runner.events(handle)]
    proof = next(event.data["result"] for event in events if event.kind == "evidence")
    assert not runner.active
    return events, proof, captured, prompts, closed, owners


async def test_live_comparison_uses_fresh_clients_same_prompt_and_actual_stop_observations(
    tmp_path, monkeypatch
):
    events, proof, captured, prompts, closed, owners = await injected(
        tmp_path, monkeypatch, compare=True
    )
    assert proof["experiment_passed"] and events[-1].data["status"] == "completed"
    assert len(captured) == len(closed) == 2 and prompts == ["Identical fixed question."] * 2
    assert (
        captured[0].model == captured[1].model
        and captured[0].effort == "medium"
        and captured[1].effort == "high"
    )
    assert all(owner is owners[0] for owner in owners)
    assert "private-block-must-not-be-exposed" not in str([event.model_dump() for event in events])
    assert "private-delta-must-not-be-exposed" not in str([event.model_dump() for event in events])
    lanes = proof["experiment"]["lanes"]
    assert [lane["observed_effort"] for lane in lanes] == [
        "low",
        "low",
    ]  # A difference is not fallback proof.
    assert (
        lanes[0]["metrics"]["sdk_duration_ms"] == 23 and lanes[0]["metrics"]["input_tokens"] == 11
    )
    assert lanes[0]["metrics"]["output_tokens"] == 7 and lanes[0]["reported_models"] == [
        "reported-model-name"
    ]


@pytest.mark.parametrize("case", ["missing", "wrong", "unknown", "failed", "auth"])
async def test_absent_unrelated_or_failed_live_evidence_never_passes_and_closes(
    tmp_path, monkeypatch, case
):
    events, proof, captured, prompts, closed, _ = await injected(
        tmp_path, monkeypatch, case=case, compare=True
    )
    assert not proof["experiment_passed"] and len(closed) == len(captured)
    if case in {"failed", "auth"}:
        assert events[-1].data["status"] == "failed"
        assert len(prompts) == len(captured) == 1
        assert proof["experiment"]["not_started_lanes"] == 1
        assert any(event.kind == "error" for event in events)
    if case == "unknown":
        assert all(lane["observed_effort"] is None for lane in proof["experiment"]["lanes"])


async def test_cancellation_closes_owned_lane_and_does_not_start_second_lane(tmp_path, monkeypatch):
    import agent_lab.sdk as sdk

    entered = asyncio.Event()
    closed = []
    clients = []
    monkeypatch.setattr(sdk, "require_live_access", lambda settings: None)
    monkeypatch.setattr(sdk, "resolve_cli_path", lambda settings: "injected-cli")

    class Client:
        def __init__(self, options):
            clients.append(self)

        async def connect(self):
            self.owner = asyncio.current_task()

        async def query(self, prompt):
            assert len([message async for message in prompt]) == 1

        async def receive_response(self):
            entered.set()
            await asyncio.Event().wait()
            yield  # pragma: no cover

        async def disconnect(self):
            assert asyncio.current_task() is self.owner
            closed.append(self)

    monkeypatch.setattr(sdk, "ClaudeSDKClient", Client)
    runner = RunService(Settings(data_dir=tmp_path, enable_live=True))
    handle = runner.start(
        14,
        RunRequest(
            mode="live", lesson_options={"comparison": "effort", "authorize_comparison": True}
        ),
    )
    consumer = asyncio.create_task(_consume(runner, handle))
    await asyncio.wait_for(entered.wait(), timeout=5)
    await runner.cancel(handle)
    events = await asyncio.wait_for(consumer, timeout=5)
    assert len(clients) == len(closed) == 1 and not runner.active
    assert events[-1].data["status"] == "cancelled"
    proof = next(event.data["result"] for event in events if event.kind == "evidence")
    assert not proof["experiment_passed"] and proof["experiment"]["not_started_lanes"] == 1


async def _consume(runner, handle):
    return [event async for event in runner.events(handle)]


async def test_disabled_metadata_never_starts_a_client_or_claims_a_fallback(tmp_path, monkeypatch):
    import agent_lab.sdk as sdk

    def forbidden(*args, **kwargs):
        raise AssertionError("Disabled metadata must not start the CLI")

    monkeypatch.setattr(sdk, "ClaudeSDKClient", forbidden)
    metadata = await ModelMetadata(Settings(data_dir=tmp_path, enable_live=False)).inspect()
    assert metadata["status"] == "disabled" and metadata["models"] is None
    assert metadata["configured_model_verified"] is False and metadata["prompt_sent"] is False
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("missing", [False, True])
async def test_metadata_reads_initialize_models_without_query_and_cleans_owned_tempdir(
    tmp_path, monkeypatch, missing
):
    import agent_lab.sdk as sdk

    configured, closed = [], []
    monkeypatch.setattr(sdk, "require_live_access", lambda settings: None)
    monkeypatch.setattr(sdk, "resolve_cli_path", lambda settings: "injected-cli")

    class Client:
        def __init__(self, options):
            configured.append(options)

        async def connect(self, prompt=None):
            assert prompt is None

        async def query(self, *args):
            raise AssertionError("Metadata inspection must not submit a prompt")

        async def get_server_info(self):
            return (
                {}
                if missing
                else {
                    "models": [
                        {
                            "value": "reported",
                            "displayName": "Reported model",
                            "supportsEffort": True,
                        }
                    ],
                    "account": {"api_key": "must-not-escape"},
                }
            )

        async def disconnect(self):
            closed.append(True)

    monkeypatch.setattr(sdk, "ClaudeSDKClient", Client)
    inspector = ModelMetadata(Settings(data_dir=tmp_path, enable_live=True))
    metadata = await inspector.inspect()
    assert metadata["status"] == ("unavailable" if missing else "observed")
    assert metadata["prompt_sent"] is False and metadata["connection_closed"]
    assert metadata["configured_model_verified"] is False and "must-not-escape" not in str(metadata)
    assert closed and not await asyncio.to_thread(Path(configured[0].cwd).exists)
    assert (await inspector.inspect())["cached"] and len(configured) == 1
