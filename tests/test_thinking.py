"""Requested option mapping, actual Stop callback execution and honest unknowns."""

from pathlib import Path

import httpx
import pytest

from agent_lab.api import create_app
from agent_lab.config import Settings
from agent_lab.foundation_models import ThinkingInputs
from agent_lab.foundations import source_sections
from agent_lab.hooks import call_hook
from agent_lab.learning import check_evidence
from agent_lab.models import LessonError, RunRequest
from agent_lab.runtime import RunService
from agent_lab.thinking import Lane, counter, local_thinking, plan_lanes, thinking_config


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("disabled", {"type": "disabled"}),
        ("adaptive", {"type": "adaptive", "display": "omitted"}),
        ("enabled", {"type": "enabled", "budget_tokens": 2048, "display": "omitted"}),
    ],
)
def test_sdk_mapping_only_includes_relevant_fields(mode, expected):
    assert (
        thinking_config(ThinkingInputs(thinking=mode, budget_tokens=2048, display="omitted"))
        == expected
    )


@pytest.mark.parametrize("comparison", ["none", "effort", "thinking", "model"])
async def test_comparison_freezes_prompt_changes_one_dimension_and_keeps_metrics_unknown(
    tmp_path, comparison
):
    result = await local_thinking(
        tmp_path,
        RunRequest(
            prompt="Use this exact fixed prompt.", lesson_options={"comparison": comparison}
        ),
    )
    proof = result["experiment"]
    assert result["experiment_passed"]
    lanes = proof["lanes"]
    assert len(lanes) == (1 if comparison == "none" else 2)
    assert len({lane["prompt_sha256"] for lane in lanes}) == 1
    for lane in lanes:
        assert lane["metrics"]["sdk_duration_ms"] is None
        assert lane["metrics"]["input_tokens"] is None
        assert lane["metrics"]["output_tokens"] is None
        assert lane["metrics"]["cost_usd"] is None
        assert lane["stop_observations"][0]["event"] == "Stop"
        assert lane["connection_closed"]
    if comparison != "none":
        changed = {
            key
            for key in lanes[0]["requested"]
            if lanes[0]["requested"][key] != lanes[1]["requested"][key]
        }
        assert changed == {comparison}
    assert check_evidence(14, result, status="completed").status == "passed"
    assert check_evidence(14, result, status="completed", mode="live").status == "needs-review"


@pytest.mark.parametrize(
    "scenario",
    [
        "missing-evidence",
        "wrong-identity",
        "missing-effort",
        "unsupported",
        "model-error",
        "interrupted",
    ],
)
async def test_recorded_failures_and_unknown_effort_never_pass(tmp_path, scenario):
    result = await local_thinking(tmp_path, RunRequest(scenario=scenario))
    assert not result["experiment_passed"]
    assert check_evidence(14, result, status="completed").status == "needs-review"
    if scenario == "missing-effort":
        lane = result["experiment"]["lanes"][0]
        assert lane["stop_observations"] and lane["observed_effort"] is None


async def test_actual_stop_callback_keeps_requested_and_observed_effort_separate(tmp_path):
    lane = Lane("A", "run", ThinkingInputs(effort="high"), "Prompt", True)
    lane.initialization = ["parent"]
    lane.terminals = [
        {
            "session_id": "parent",
            "subtype": "success",
            "is_error": False,
            "usage": {"input_tokens": 0, "output_tokens": 9},
        }
    ]
    lane.last_root_message, lane.connection_closed = "ResultMessage", True
    await call_hook(
        lane.stop,
        {
            "hook_event_name": "Stop",
            "session_id": "parent",
            "prompt_id": lane.input_id,
            "effort": {"level": "low"},
        },
        None,
    )
    proof = lane.report()
    assert proof["experiment_passed"] and proof["observed_effort"] == "low"
    assert proof["metrics"]["input_tokens"] == 0 and proof["metrics"]["cost_usd"] is None
    lane.hooks[0]["prompt_id"] = "wrong"
    assert not lane.report()["experiment_passed"]
    lane.hooks[0]["prompt_id"] = lane.input_id
    lane.hooks[0]["root"] = False
    assert not lane.report()["experiment_passed"]


@pytest.mark.parametrize("value", [None, True, -1, float("nan"), float("inf"), "0"])
def test_unknown_or_invalid_metrics_are_not_zero(value):
    assert counter(value) is None


def test_missing_usage_remains_unknown_after_output_redaction():
    from agent_lab.policy import redact

    metrics = {"input_tokens": None, "output_tokens": None, "cost_usd": None}
    assert redact(redact(metrics)) == metrics
    assert redact({"control_token": "private-value"})["control_token"] == "[REDACTED]"


@pytest.mark.parametrize(
    "options",
    [
        {"thinking": "automatic"},
        {"effort": "extreme"},
        {"budget_tokens": True},
        {"budget_tokens": 100},
        {"model": ""},
        {"display": "full"},
        {"comparison": "effort", "comparison_effort": "medium"},
    ],
)
async def test_bad_options_reject_before_task_and_files(tmp_path, options):
    runner = RunService(Settings(data_dir=tmp_path))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(runner, with_ui=False)), base_url="http://test"
    ) as client:
        response = await client.post("/api/lessons/14/run", json={"lesson_options": options})
    assert response.status_code == 422, response.text
    assert not runner.active and not list(tmp_path.iterdir())


async def test_two_live_lanes_require_explicit_authorization_before_start(tmp_path):
    runner = RunService(Settings(data_dir=tmp_path, enable_live=True))
    with pytest.raises(LessonError, match="both paid"):
        runner.start(14, RunRequest(mode="live", lesson_options={"comparison": "effort"}))
    assert not runner.active and not list(tmp_path.iterdir())


async def test_draft_routes_are_scoped_edit_without_model_calls_and_send_fresh_runs(tmp_path):
    runner = RunService(Settings(data_dir=tmp_path))
    app = create_app(runner, with_ui=False)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            opened = (
                await client.post("/api/c14/session", json={"prompt": "Fixed question"})
            ).json()
            key = {k: opened[k] for k in ("application_handle", "control_token")}
            assert not runner.active and not list(tmp_path.iterdir())
            for route, values in (
                ("effort", {"effort": "high"}),
                ("thinking", {"thinking": "enabled", "budget_tokens": 2048}),
                ("model", {"model": "sonnet"}),
            ):
                response = await client.post("/api/c14/" + route, json=key | values)
                assert response.status_code == 200, response.text
                assert response.json()["prompt"] == "Fixed question"
            assert not list(tmp_path.iterdir())
            assert (
                await client.post(
                    "/api/c14/effort", json=key | {"control_token": "x" * 32, "effort": "low"}
                )
            ).status_code == 403
            assert (
                await client.post(
                    "/api/c14/thinking", json=key | {"thinking": "enabled", "budget_tokens": False}
                )
            ).status_code == 422
            response = await client.post("/api/c14/send", json=key)
            assert response.status_code == 200, response.text
            proof = next(
                e["data"]["result"] for e in response.json()["events"] if e["kind"] == "evidence"
            )
            assert proof["experiment_passed"]
            assert proof["experiment"]["lanes"][0]["requested"]["model"] == "sonnet"
            assert (await client.post("/api/c14/end", json=key)).json()["closed"]
            assert (await client.post("/api/c14/send", json=key)).status_code == 409
    finally:
        await runner.close()
        await app.state.thinking_sessions.close()


def test_three_exact_excerpts_and_identical_lane_rejection():
    for section in source_sections(14):
        lines = (
            (Path(__file__).resolve().parents[1] / section["path"])
            .read_text(encoding="utf-8")
            .splitlines()
        )
        assert section["code"].splitlines() == lines[section["start"] - 1 : section["end"]]
    with pytest.raises(LessonError):
        plan_lanes({"comparison": "model", "comparison_model": "sonnet"}, "sonnet")
