"""Usage checks inspect terminal evidence, grouped messages and accounting effects."""

import asyncio
from pathlib import Path

import httpx
import pytest
from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ThinkingBlock,
)

from agent_lab.api import create_app
from agent_lab.config import Settings
from agent_lab.foundation_models import SCENARIOS
from agent_lab.foundations import source_sections
from agent_lab.learning import check_evidence
from agent_lab.models import LessonError, RunRequest
from agent_lab.runtime import RunService
from agent_lab.usage import UsageMeter, usage_options
from agent_lab.usage_sessions import UsageSessions


@pytest.mark.parametrize("scenario", SCENARIOS[15])
async def test_recorded_usage_grades_actual_final_fields(tmp_path, scenario):
    runner = RunService(Settings(data_dir=tmp_path))
    events = [
        event async for event in runner.events(runner.start(15, RunRequest(scenario=scenario)))
    ]
    proof = next(e.data["result"] for e in events if e.kind == "evidence")
    assert proof["experiment_passed"] is (scenario == "success")
    assert check_evidence(15, proof, status="completed").status == (
        "passed" if scenario == "success" else "needs-review"
    )
    assert check_evidence(15, proof, status="completed", mode="live").status == "needs-review"
    experiment = proof["experiment"]
    assert experiment["identified_messages"] == 1
    assert experiment["messages"][0]["block_types"] == ["TextBlock", "ThinkingBlock"]
    if scenario == "success":
        assert experiment["final"]["usage"]["output_tokens"] == 4
        assert experiment["messages"][0]["intermediate_usage"]["output_tokens"] == 1


def test_meter_subtracts_before_update_and_does_not_bridge_unknowns_or_unrelated_sessions():
    meter = UsageMeter()
    assert meter.observe("one", 0.01)["delta_usd"] == 0.01
    assert meter.observe("one", 0.025)["delta_usd"] == 0.015
    assert sum(s["delta_usd"] for s in meter.samples) == 0.025
    assert meter.observe("one", None)["delta_usd"] is None
    assert meter.observe("one", 0.04)["delta_usd"] is None
    assert meter.observe("one", 0.05)["delta_usd"] == 0.01
    assert meter.observe("one", 0.01)["delta_usd"] is None
    assert meter.observe("other", 0.10)["delta_usd"] is None
    assert meter.observe("other", 0.12)["delta_usd"] is None


def test_limits_task_guidance_agent_and_exact_source_excerpts(tmp_path):
    request = RunRequest(
        lesson_options={
            "omit_turn_limit": True,
            "omit_budget_limit": True,
            "task_tokens": 2048,
            "allow_agent": True,
        }
    )
    options = usage_options(request, tmp_path, tmp_path / "config", Settings())
    assert options.max_turns is None and options.max_budget_usd is None
    assert options.task_budget == {"total": 2048} and options.tools == ["Agent"]
    assert options.agents["usage_reader"].tools == []
    for section in source_sections(15):
        lines = (
            (Path(__file__).resolve().parents[1] / section["path"])
            .read_text(encoding="utf-8")
            .splitlines()
        )
        assert section["code"].splitlines() == lines[section["start"] - 1 : section["end"]]


@pytest.mark.parametrize(
    "options",
    [
        {"task_tokens": True},
        {"task_tokens": 0},
        {"task_tokens": 1.5},
        {"omit_budget_limit": "true"},
        {"allow_agent": 1},
        {"unknown": True},
    ],
)
async def test_usage_rejects_before_task_files_or_client(tmp_path, options):
    runner = RunService(Settings(data_dir=tmp_path))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(runner, with_ui=False)), base_url="http://test"
    ) as client:
        response = await client.post("/api/lessons/15/run", json={"lesson_options": options})
        assert response.status_code == 422
    assert not runner.active and not list(tmp_path.iterdir())


async def test_session_routes_inspection_is_read_only_and_meter_is_cumulative(tmp_path):
    runner = RunService(Settings(data_dir=tmp_path))
    app = create_app(runner, with_ui=False)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        opened = (await client.post("/api/c15/session", json={})).json()
        key = {k: opened[k] for k in ("application_handle", "control_token")}
        assert (await client.post("/api/c15/send", json=key | {"prompt": " "})).status_code == 409
        assert (
            await client.post("/api/c15/usage", json=key | {"control_token": "x" * 32})
        ).status_code == 403
        assert (await client.post("/api/c15/context", json=key)).json()["prompt_sent"] is False
        for _ in range(2):
            response = await client.post(
                "/api/c15/send", json=key | {"prompt": "One bounded message"}
            )
            assert response.status_code == 200, response.text
        snapshot = (await client.post("/api/c15/usage", json=key)).json()
        assert snapshot["sends"] == 2 and [s["delta_usd"] for s in snapshot["meter"]] == [
            0.01,
            0.015,
        ]
        assert not snapshot["connection_closed"]
        ended = (await client.post("/api/c15/end", json=key)).json()
        assert ended["closed"] and ended["connection_closed"]
        assert (
            await client.post("/api/c15/send", json=key | {"prompt": "later"})
        ).status_code == 409
    await app.state.usage_sessions.close()


@pytest.mark.parametrize(
    "case",
    ["success", "missing", "wrong", "invalid", "missing-cost", "nonfinite-cost", "limit", "auth"],
)
async def test_live_usage_uses_actual_stream_and_closes_client(tmp_path, monkeypatch, case):
    import agent_lab.sdk as sdk

    closed, owners = [], []
    monkeypatch.setattr(sdk, "require_live_access", lambda settings: None)
    monkeypatch.setattr(sdk, "resolve_cli_path", lambda settings: "injected-cli")

    class Client:
        def __init__(self, options):
            assert options.tools == [] and options.max_budget_usd == 0.1

        async def connect(self):
            owners.append(asyncio.current_task())

        async def query(self, prompt):
            assert prompt.strip()

        async def receive_response(self):
            if case == "auth":
                yield SystemMessage(subtype="api_retry", data={"error_status": 401})
                return
            yield SystemMessage(subtype="init", data={"session_id": "actual-parent"})
            for block in (
                TextBlock(text="Public example"),
                ThinkingBlock(thinking="private-do-not-expose", signature="private-signature"),
            ):
                yield AssistantMessage(
                    content=[block],
                    model="injected",
                    message_id="same-id",
                    usage={"input_tokens": 5, "output_tokens": 1},
                )
            if case == "missing":
                return
            yield ResultMessage(
                subtype="error_max_turns" if case == "limit" else "success",
                duration_ms=2,
                duration_api_ms=1,
                is_error=case == "limit",
                num_turns=1,
                session_id="wrong" if case == "wrong" else "actual-parent",
                total_cost_usd=None
                if case == "missing-cost"
                else float("nan")
                if case == "nonfinite-cost"
                else 0.002,
                usage={"input_tokens": -1 if case == "invalid" else 12, "output_tokens": 6},
                model_usage={"injected": {"inputTokens": 12, "outputTokens": 6, "costUSD": 0.002}},
            )

        async def disconnect(self):
            owners.append(asyncio.current_task())
            closed.append(True)

    monkeypatch.setattr(sdk, "ClaudeSDKClient", Client)
    runner = RunService(Settings(data_dir=tmp_path, enable_live=True))
    events = [e async for e in runner.events(runner.start(15, RunRequest(mode="live")))]
    proof = next(e.data["result"] for e in events if e.kind == "evidence")
    assert proof["experiment_passed"] is (case == "success")
    if case == "wrong":
        assert proof["experiment"]["meter"]["delta_usd"] is None
    assert closed == [True] and owners[0] is owners[1] and not runner.active
    assert "private-do-not-expose" not in str(events) and "private-signature" not in str(events)
    if case == "success":
        assert proof["experiment"]["identified_messages"] == 1
        assert proof["experiment"]["final"]["total_cost_usd"] == 0.002
    if case in {"limit", "auth", "missing"}:
        assert events[-1].data["status"] == "failed"


async def test_live_session_context_has_no_prompt_and_two_sends_share_one_owned_client(
    tmp_path, monkeypatch
):
    import agent_lab.sdk as sdk

    owners, queries, clients = [], [], []
    monkeypatch.setattr(sdk, "require_live_access", lambda settings: None)
    monkeypatch.setattr(sdk, "resolve_cli_path", lambda settings: "injected-cli")

    class Client:
        def __init__(self, options):
            self.turn = 0
            clients.append(self)

        async def connect(self):
            owners.append(asyncio.current_task())

        async def query(self, prompt):
            self.turn += 1
            queries.append(prompt)

        async def receive_response(self):
            if self.turn == 1:
                yield SystemMessage(subtype="init", data={"session_id": "owned-live"})
            yield ResultMessage(
                subtype="success",
                is_error=False,
                duration_ms=1,
                duration_api_ms=1,
                num_turns=1,
                session_id="owned-live",
                total_cost_usd=0.01 if self.turn == 1 else 0.025,
                usage={"input_tokens": 12, "output_tokens": 4},
            )

        async def get_context_usage(self):
            owners.append(asyncio.current_task())
            return {"used_tokens": 16, "max_tokens": 100000}

        async def disconnect(self):
            owners.append(asyncio.current_task())

    monkeypatch.setattr(sdk, "ClaudeSDKClient", Client)
    registry = UsageSessions(Settings(data_dir=tmp_path, enable_live=True))
    session = await registry.open(RunRequest(mode="live"))
    assert queries == []
    assert (await registry.command(session, "context"))["prompt_sent"] is False
    assert queries == []
    for _ in range(2):
        await registry.command(session, "send", "Same question")
    assert len(clients) == 1 and queries == ["Same question"] * 2
    assert [s["delta_usd"] for s in session.meter.samples] == [0.01, 0.015]
    await registry.end(session)
    assert all(owner is owners[0] for owner in owners) and session.connection_closed


async def test_session_end_cancels_inflight_send_and_owner_closes(tmp_path, monkeypatch):
    import agent_lab.sdk as sdk

    entered = asyncio.Event()
    owners = []
    monkeypatch.setattr(sdk, "require_live_access", lambda settings: None)
    monkeypatch.setattr(sdk, "resolve_cli_path", lambda settings: "injected-cli")

    class Client:
        def __init__(self, options):
            pass

        async def connect(self):
            owners.append(asyncio.current_task())

        async def query(self, prompt):
            pass

        async def receive_response(self):
            entered.set()
            await asyncio.Event().wait()
            yield

        async def disconnect(self):
            owners.append(asyncio.current_task())

    monkeypatch.setattr(sdk, "ClaudeSDKClient", Client)
    registry = UsageSessions(Settings(data_dir=tmp_path, enable_live=True))
    session = await registry.open(RunRequest(mode="live"))
    sending = asyncio.create_task(registry.command(session, "send", "Wait until cancelled"))
    await asyncio.wait_for(entered.wait(), 5)
    with pytest.raises(LessonError, match="busy"):
        await registry.command(session, "context")
    ended = await registry.end(session)
    with pytest.raises(LessonError, match="cancelled"):
        await asyncio.wait_for(sending, 5)
    assert ended["connection_closed"] and owners[0] is owners[1] and session.task.done()
